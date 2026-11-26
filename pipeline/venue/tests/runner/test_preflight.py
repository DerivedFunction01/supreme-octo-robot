"""The pre-dispatch validation pass (wall-clock plan,
step 2): manifest_shape.preflight_error and the branch
pin's resolution (manifest_shape.pin_resolution_error).

The deaths this cures: fires that discovered their own
defects minutes in — a manifest whose script field was
absent crashed the launch window on a KeyError with the
lease held; a declared upload missing on disk failed the
run after the session was acquired; a branch pin naming a
commit the source repo never held died at the session-side
clone. These pins hold the pass to its contract: every
verdict a dispatch can know locally settles before any
upload, lease, or launch work, refusing named and in
seconds — and a sound manifest passes untouched.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

shape = load_module("manifest_shape_unit", REPO / "sync" / "runner" / "manifest_shape.py")

SHA = "a" * 40


def test_shape_verdicts_still_refuse():
    err = shape.preflight_error({"script": "x.py", "uploads": [{"mapped": 1}]})
    assert err is not None and "uploads" in err
    err = shape.preflight_error({"script": "x.py", "transport": {"kind": "branch", "repo": "r", "branch": "b", "sha": "short"}})
    assert err is not None and "sha" in err


def test_script_field_verdict():
    assert "script" in shape.script_field_error({})
    assert "script" in shape.script_field_error({"script": 3})
    assert shape.script_field_error({"script": "x.py"}) is None
    # The field verdict rides the pass as its shape_error leg.
    err = shape.preflight_error({"uploads": []}, shape_error=shape.script_field_error({}))
    assert err is not None and "script" in err


def test_presence_verdict(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("# payload\n")
    upload = tmp_path / "cfg.json"
    upload.write_text("{}\n")
    job = {"script": "run.py", "uploads": ["cfg.json"]}
    assert shape.presence_error(job, script_path=script, uploads_base=tmp_path) is None
    missing_upload = shape.presence_error(job, script_path=script, uploads_base=tmp_path / "elsewhere")
    assert missing_upload is not None and "cfg.json" in missing_upload
    missing_script = shape.presence_error(job, script_path=tmp_path / "gone.py", uploads_base=tmp_path)
    assert missing_script is not None and "gone.py" in missing_script


def test_pass_composition_order(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("# payload\n")
    clean = {"script": "run.py", "uploads": []}
    # A shape defect beats every later leg.
    dirty = {"script": "run.py", "uploads": [42]}
    assert "uploads" in shape.preflight_error(dirty, script_path=script, uploads_base=tmp_path, claim_error="claim!", pin_error="pin!")
    # Presence beats the claim; the claim beats the pin.
    assert "not found" in shape.preflight_error(clean, script_path=tmp_path / "gone.py", uploads_base=tmp_path, claim_error="claim!")
    assert shape.preflight_error(clean, script_path=script, uploads_base=tmp_path, claim_error="claim!", pin_error="pin!") == "claim!"
    assert shape.preflight_error(clean, script_path=script, uploads_base=tmp_path, pin_error="pin!") == "pin!"
    assert shape.preflight_error(clean, script_path=script, uploads_base=tmp_path) is None


class FakeRegistry:
    def __init__(self, entries):
        self.entries = entries

    def load_local_registry(self, repo):
        return {"repos": self.entries}

    def get_entry(self, registry, repo_id):
        repos = registry["repos"]
        if repo_id not in repos:
            raise ValueError(f"registry: repo {repo_id!r} is not registered (have: {sorted(repos)})")
        return repo_id, repos[repo_id]


def git_head(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "f.txt").write_text("x\n")
    subprocess.run(["git", "-C", str(path), "-c", "user.name=T", "-c", "user.email=t@t", "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "one"], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def test_pin_resolution(tmp_path):
    pin = shape.pin_resolution_error
    assert pin(None, repo=tmp_path, repo_registry=FakeRegistry({})) is None

    transport = {"kind": "branch", "repo": "src", "branch": "formation/x", "sha": SHA}
    err = pin(transport, repo=tmp_path, repo_registry=FakeRegistry({}))
    assert err is not None and err.startswith("branch transport:") and "not registered" in err

    err = pin(transport, repo=tmp_path, repo_registry=FakeRegistry({"src": {"local_path": str(tmp_path / "absent")}}))
    assert err is not None and "does not stand" in err

    checkout = tmp_path / "src"
    checkout.mkdir()
    head = git_head(checkout)
    registry = FakeRegistry({"src": {"local_path": str(checkout)}})
    err = pin(transport, repo=tmp_path, repo_registry=registry)
    assert err is not None and "does not resolve to a commit" in err and SHA in err

    resolved = dict(transport, sha=head)
    assert pin(resolved, repo=tmp_path, repo_registry=registry) is None
