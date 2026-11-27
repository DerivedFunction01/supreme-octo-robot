"""Sealed venue job scripts.

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
before any plaintext is produced. Blob form, stored
as text so every write rides the tree's one writer:
MAGIC || base64(nonce (16) || tag (32) || ciphertext).

The master key is the runner's server-side key: it
lives in the venue var store (var/sealed.key, mode
600, untracked, the 32 key bytes as hex text), never
in the tree beside the blobs, and is read only by the
dispatch process at dispatch time, which decrypts in
memory and ships the bytes to the venue — the
plaintext is never written locally.

The register (var/sealed-register.json) is untracked
working state in the runner's var store, beside the key:
one entry per sealed job, naming its sealed files, each
plaintext's SHA-256 (a hash is not content; it is the
verify-sealed proof), the sealing stamp, and the flag
report as evidence — the evidence names the flag's
function only (its class and count), never seat, owner,
or narrative detail.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

MAGIC = b"SORSEAL1"
NONCE_LEN = 16
TAG_LEN = 32
KEY_LEN = 32

REGISTER_REL = ("var", "sealed-register.json")
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
    return MAGIC + base64.b64encode(nonce + tag + ciphertext) + b"\n"


def open_bytes(key: bytes, blob: bytes) -> bytes:
    if len(key) != KEY_LEN:
        raise SealError(f"sealing key must be {KEY_LEN} bytes")
    if not blob.startswith(MAGIC):
        raise SealError("not a sealed blob (bad magic)")
    try:
        raw = base64.b64decode(blob[len(MAGIC) :].strip(), validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise SealError("sealed blob is not valid base64") from exc
    if len(raw) < NONCE_LEN + TAG_LEN:
        raise SealError("sealed blob truncated")
    nonce = raw[:NONCE_LEN]
    tag = raw[NONCE_LEN : NONCE_LEN + TAG_LEN]
    ciphertext = raw[NONCE_LEN + TAG_LEN :]
    enc_key, mac_key = _subkeys(key)
    expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise SealError("sealed blob failed its integrity tag")
    stream = _keystream(enc_key, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream))


def is_sealed_blob(data: bytes) -> bool:
    return data.startswith(MAGIC)


def staged_write(path: Path, data: bytes, mode: int | None = None) -> None:
    """The staged protocol inline (contract 15): stage
    to a fresh sibling, fsync, read back and compare,
    stamp the mode, rename over; a failure at any stage
    unlinks the staging file and leaves the target
    byte-identical. This module is a declared standalone
    seam (the writer-uniqueness EXCEPTIONS table): it is
    loaded by path by the dispatcher, outside the server
    context the writer route's /ops leg needs, and its
    writes are the dispatcher's own store — the key,
    the blobs, the register. The protocol, not the
    module, is the invariant."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.sched-tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "rb") as fh:
            if fh.read() != data:
                raise SealError(f"staged write read-back mismatch for {path}")
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def key_path(venue_root: Path) -> Path:
    return venue_root.joinpath(*KEY_REL)


def ensure_key(venue_root: Path) -> Path:
    """The master key, generated once into the var store
    (mode 600, the key bytes as hex text) when absent;
    its bytes are never printed."""
    path = key_path(venue_root)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        staged_write(path, os.urandom(KEY_LEN).hex().encode("ascii"), mode=0o600)
    return path


def load_key(venue_root: Path) -> bytes:
    path = key_path(venue_root)
    try:
        text = path.read_text(encoding="ascii").strip()
        key = bytes.fromhex(text)
    except (OSError, ValueError) as exc:
        raise SealError(
            f"sealing key not readable at {path} — dispatch of a "
            "sealed job needs the runner's server-side key"
        ) from exc
    if len(key) != KEY_LEN:
        raise SealError(f"sealing key at {path} does not hold {KEY_LEN} bytes")
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
    data = (json.dumps(register, indent=1) + "\n").encode("utf-8")
    staged_write(path, data)


def entry_for(register: dict, job_name: str) -> dict | None:
    for entry in register.get("jobs", []):
        if entry.get("job") == job_name:
            return entry
    return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
