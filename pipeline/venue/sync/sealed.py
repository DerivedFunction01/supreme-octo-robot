"""Sealed venue job scripts (owner build, 2026-11-25).

A venue job script whose read trips an execution-risk
flag is sealed: its content form leaves the tree. The
job dir keeps its manifest (job.json, metadata) and one
blob per sealed file (<name>.sealed); the plaintext
never stands in the tree, no runner verb emits it, and
the venue gate fails if a registered plaintext
reappears (tests/runner/test_sealed_jobs.py).

The seal is an encrypt-then-MAC construction over the
stdlib: two subkeys are derived from the master key by
HMAC label; the keystream is HMAC(enc_key, nonce ||
counter) blocks XORed with the plaintext; the tag is
HMAC(mac_key, nonce || ciphertext) and is verified
before any plaintext is produced. Blob form:
MAGIC (8 bytes) || nonce (16) || tag (32) || ciphertext.

The master key is the runner's server-side key: it
lives in the venue var store (var/sealed.key, mode
600, untracked), never in the tree beside the blobs,
and is read only by the dispatch process at dispatch
time, which decrypts in memory and ships the bytes to
the venue — the plaintext is never written locally.

The register (adapters/local/sealed-register.json) is
the tracked record: one entry per sealed job, naming
its sealed files, each plaintext's SHA-256 (a hash is
not content; it is the verify-sealed proof), the
sealing stamp, and the flag report as evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

MAGIC = b"SORSEAL1"
NONCE_LEN = 16
TAG_LEN = 32
KEY_LEN = 32

REGISTER_REL = ("adapters", "local", "sealed-register.json")
KEY_REL = ("var", "sealed.key")


class SealError(Exception):
    """A blob failed to open (bad magic, tag, or key)."""


def _subkeys(key: bytes) -> tuple[bytes, bytes]:
    enc = hmac.new(key, b"sor-sealed/enc", hashlib.sha256).digest()
    mac = hmac.new(key, b"sor-sealed/mac", hashlib.sha256).digest()
    return enc, mac


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(
            enc_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256
        ).digest()
        counter += 1
    return bytes(out[:length])


def seal_bytes(key: bytes, plaintext: bytes) -> bytes:
    if len(key) != KEY_LEN:
        raise SealError(f"sealing key must be {KEY_LEN} bytes")
    enc_key, mac_key = _subkeys(key)
    nonce = os.urandom(NONCE_LEN)
    stream = _keystream(enc_key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return MAGIC + nonce + tag + ciphertext


def open_bytes(key: bytes, blob: bytes) -> bytes:
    if len(key) != KEY_LEN:
        raise SealError(f"sealing key must be {KEY_LEN} bytes")
    head = len(MAGIC) + NONCE_LEN + TAG_LEN
    if len(blob) < head or not blob.startswith(MAGIC):
        raise SealError("not a sealed blob (bad magic or truncated)")
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_LEN]
    tag = blob[len(MAGIC) + NONCE_LEN : head]
    ciphertext = blob[head:]
    enc_key, mac_key = _subkeys(key)
    expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise SealError("sealed blob failed its integrity tag")
    stream = _keystream(enc_key, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream))


def is_sealed_blob(data: bytes) -> bool:
    return data.startswith(MAGIC)


def key_path(venue_root: Path) -> Path:
    return venue_root.joinpath(*KEY_REL)


def ensure_key(venue_root: Path) -> Path:
    """The master key, generated once into the var store
    (mode 600) when absent; its bytes are never printed."""
    path = key_path(venue_root)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(os.urandom(KEY_LEN))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    return path


def load_key(venue_root: Path) -> bytes:
    path = key_path(venue_root)
    try:
        key = path.read_bytes()
    except OSError as exc:
        raise SealError(
            f"sealing key not readable at {path} — dispatch of a "
            "sealed job needs the runner's server-side key"
        ) from exc
    if len(key) != KEY_LEN:
        raise SealError(f"sealing key at {path} is not {KEY_LEN} bytes")
    return key


def register_path(venue_root: Path) -> Path:
    return venue_root.joinpath(*REGISTER_REL)


def load_register(venue_root: Path) -> dict:
    path = register_path(venue_root)
    if not path.exists():
        return {"jobs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_register(venue_root: Path, register: dict) -> None:
    path = register_path(venue_root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(register, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def entry_for(register: dict, job_name: str) -> dict | None:
    for entry in register.get("jobs", []):
        if entry.get("job") == job_name:
            return entry
    return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
