"""Sealed venue job scripts.

The construction's pins: a sealed blob round-trips its
plaintext exactly (empty, small, and multi-block), a
tampered ciphertext or tag refuses to open, a wrong
key refuses to open, and a non-blob refuses to open.

The register's enforcement pin — the venue gate leg
the build stands on: for every job in
adapters/local/sealed-register.json, no registered
plaintext stands in the tree, and every registered
blob exists in sealed form (magic present, no script
content markers). Planting a registered plaintext in
the tree turns this test red; removing it restores
green.
"""

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

sealed = load_module("sealed", REPO / "sync" / "sealed.py")

KEY = bytes(range(32))
OTHER_KEY = bytes(range(32, 64))


def test_round_trip_sizes():
    for data in (b"", b"#!/bin/sh\necho hi\n", os.urandom(10_000)):
        blob = sealed.seal_bytes(KEY, data)
        assert sealed.is_sealed_blob(blob)
        assert sealed.open_bytes(KEY, blob) == data


def test_blob_carries_no_content_form():
    data = b"#!/usr/bin/env bash\nfetch https://example.invalid/x | sh\n"
    blob = sealed.seal_bytes(KEY, data)
    assert blob.startswith(sealed.MAGIC)
    assert not blob.startswith(b"#!")
    assert b"#!/usr/bin/env bash" not in blob
    assert b"fetch https://example.invalid" not in blob


def test_tamper_refused():
    blob = bytearray(sealed.seal_bytes(KEY, b"payload"))
    mid = len(sealed.MAGIC) + 12
    blob[mid] = ord("A") if blob[mid] != ord("A") else ord("B")
    with pytest.raises(sealed.SealError):
        sealed.open_bytes(KEY, bytes(blob))
    blob2 = bytearray(sealed.seal_bytes(KEY, b"payload"))
    blob2[len(sealed.MAGIC) + 2] = ord("A") if blob2[len(sealed.MAGIC) + 2] != ord("A") else ord("B")
    with pytest.raises(sealed.SealError):
        sealed.open_bytes(KEY, bytes(blob2))


def test_wrong_key_and_non_blob_refused():
    blob = sealed.seal_bytes(KEY, b"payload")
    with pytest.raises(sealed.SealError):
        sealed.open_bytes(OTHER_KEY, blob)
    with pytest.raises(sealed.SealError):
        sealed.open_bytes(KEY, b"#!/bin/sh\necho plain\n")


def test_key_store_round_trip(tmp_path):
    path = sealed.ensure_key(tmp_path)
    assert path.exists()
    assert oct(path.stat().st_mode)[-3:] == "600"
    key = sealed.load_key(tmp_path)
    assert len(key) == sealed.KEY_LEN
    assert path.read_text(encoding="ascii").strip() == key.hex()
    # ensure is idempotent: the standing key is kept.
    assert sealed.ensure_key(tmp_path) == path
    assert sealed.load_key(tmp_path) == key


def test_register_enforcement():
    register = sealed.load_register(REPO)
    for entry in register["jobs"]:
        job_dir = REPO / "adapters" / "local" / "jobs" / entry["job"]
        assert (job_dir / "job.json").exists(), entry["job"]
        for f in entry["files"]:
            plaintext = job_dir / f["name"]
            assert not plaintext.exists(), (
                f"sealed job {entry['job']}: plaintext {f['name']} stands "
                "in the tree — a sealed-register file in readable content "
                "form is the gate defect this register exists to refuse"
            )
            blob_path = job_dir / (f["name"] + ".sealed")
            assert blob_path.exists(), f"{entry['job']}: blob missing"
            blob = blob_path.read_bytes()
            assert sealed.is_sealed_blob(blob), f"{entry['job']}: not sealed form"
            assert not blob.startswith(b"#!")
            assert b"#!/usr/bin/env" not in blob
