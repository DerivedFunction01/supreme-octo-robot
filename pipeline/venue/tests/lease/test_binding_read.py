"""Binding-damage read-side units.

Pins the read half of the binding cure: a
sessions listing dialed against a damaged binding store
(missing, empty, or unparseable sessions.json) is not
evidence. The CLI's empty-store view is indistinguishable
from "no sessions" at the text seam, and reading it as
absence served every live lease as recorded-but-dead —
twice in one night. Such a read now classifies unknown,
never absent; a parseable store, even {}, classifies
exactly as before.
"""

import importlib
import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location(
    "lease", REPO / "sync" / "lease" / "__init__.py",
    submodule_search_locations=[str(REPO / "sync" / "lease")])
lease = importlib.util.module_from_spec(spec)
sys.modules.setdefault("lease", lease)
if "sessions" not in dir(lease):
    spec.loader.exec_module(lease)
sessions = importlib.import_module("lease.sessions.sessions")

_fixture_spec = importlib.util.spec_from_loader("repo_fixture", SourceFileLoader("repo_fixture", str(REPO / "tests" / "fixtures" / "repo_fixture.py")))
repo_fixture = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(repo_fixture)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = repo_fixture.scratch_repo(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    cfg = tmp_path / "home" / ".config" / "colab-cli"
    cfg.mkdir(parents=True)
    return root, cfg / "sessions.json"


class _Result:
    def __init__(self, stdout):
        self.stdout = stdout


def stub_colab(text):
    def colab(*args, **kwargs):
        return _Result(text)
    return colab


@pytest.mark.parametrize("content,damaged", [
    (None, False),
    (b"", True),
    (b"not json", True),
    (b"[1, 2]", True),
    (b"{}", False),
    (b'{"x": {}}', False),
])
def test_binding_damaged_shapes(home, content, damaged):
    _root, path = home
    if content is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(content)
    assert sessions.binding_damaged() is damaged


def test_listing_against_damaged_store_is_unknown(home):
    _root, path = home
    path.write_bytes(b"")
    diag = {}
    verdict = sessions.session_state(stub_colab("[]"), "live-one", diag=diag, attempts=1)
    assert verdict == "unknown"
    assert diag["read_error"] == "binding-damaged"


def test_listing_against_healthy_store_classifies(home):
    _root, path = home
    path.write_bytes(b'{"live-one": {}}')
    assert sessions.session_state(stub_colab("live-one listed"), "live-one", attempts=1) == "alive"
    assert sessions.session_state(stub_colab("someone-else listed"), "live-one", attempts=1) == "absent"
