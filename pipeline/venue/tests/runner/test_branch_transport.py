"""Branch transport (plan, Steps 1–2): the
manifest declaration, the record stamp, and the base-clone
drive.

The declaration's pins: branch is the only declared kind;
kind branch requires repo, branch, and a full 40-hex sha,
each refusal naming its field; no transport at all is the
bundle path and validates clean. The drive's pins: the
session's base clone is driven to the declared tip and
its echoed HEAD is asserted against the announcement — a
mismatch or a fetch that never lands is a refusal here,
never a silent bundle substitution. Driven against a stub
foundation whose colab is scripted, in the upload-probe
suite's idiom.

The plant pins (plant cure): the drive verifies
the session's git plant before the substrate upload — a
plant that fails its checks is a refusal naming the plant,
with no upload and no clone attempted; the probe's rewrite
check asserts the plant's own contract — the insteadOf
entry keyed by the SSH base, holding the HTTPS base as its
value — executed here against planted, missing, wrong, and
inverted config shapes; the plant script reads the config
it writes back before it may report OK, so a plant the
probe would refuse fails in its own run; and the plant job's
own upload set pairs the kit's key with the tracked pinned
known-hosts artifact beside the plant script, whose lines
are GitHub's published host keys.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
BRANCH = {"kind": "branch", "repo": "supreme-octo-robot", "branch": "cure/x-20261123", "sha": SHA}
PLANT_OK = json.dumps({"failed": [], "greeting": "Hi redacted! You've successfully authenticated, but GitHub does not provide shell access."}) + "\n"
PLANT_SPLIT = json.dumps({"failed": ["hosts", "greeting"], "greeting": "Host key verification failed."}) + "\n"


def _json_object_from_output(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON object in output")


class ScriptedColab:
    """Uploads land unless upload_rc says otherwise; exec
    outcomes follow the script: ("probe",) renders the
    verify probe's own output for the fixture base_clone.sh,
    ("stdout", text) returns text, ("timeout",) raises."""

    def __init__(self, script, probe_file, upload_rc=0):
        self.script = list(script)
        self.probe_file = probe_file
        self.upload_rc = upload_rc
        self.exec_calls = 0
        self.upload_calls = 0

    def __call__(self, *argv, timeout=None):
        if argv[0] == "upload":
            self.upload_calls += 1
            return subprocess.CompletedProcess(argv, self.upload_rc, "", "upload refused")
        assert argv[0] == "exec", argv
        self.exec_calls += 1
        outcome = self.script.pop(0)
        if outcome[0] == "timeout":
            raise subprocess.TimeoutExpired(argv, timeout)
        if outcome[0] == "probe":
            data = self.probe_file.read_bytes()
            body = json.dumps({"size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            return subprocess.CompletedProcess(argv, 0, body + "\n", "")
        if outcome[0] == "stdout":
            return subprocess.CompletedProcess(argv, 0, outcome[1], "")
        raise AssertionError(outcome)


def load_launch(tmp_path, colab):
    package = types.ModuleType("runner_branch_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_branch_unit"] = package
    foundation = types.ModuleType("runner_branch_unit.foundation")
    foundation.REPO = tmp_path
    foundation.colab = colab
    foundation.json_object_from_output = _json_object_from_output
    journal = []
    foundation.lease = types.SimpleNamespace(
        append_launch_outcome=lambda repo, session, stage, ok, detail="": journal.append(
            {"stage": stage, "ok": ok, "detail": detail}))
    foundation.transfer = types.SimpleNamespace(
        chunked_upload=lambda *a, **k: {"ok": True})
    sys.modules["runner_branch_unit.foundation"] = foundation
    launch = load_module(
        "runner_branch_unit.launch", REPO / "sync" / "runner" / "launch.py", register=True)
    return launch, foundation, journal


def make_base_clone(tmp_path):
    src = tmp_path / "sync" / "base_clone.sh"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"#!/usr/bin/env bash\necho base clone\n")
    return src


# --- the declaration (Step 1) ---


def test_no_transport_validates_clean(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    assert launch.transport_error({}) is None
    assert launch.transport_error({"uploads": []}) is None
    assert launch.parse_transport({}) is None


def test_valid_branch_declaration_validates_and_parses(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    job = {"transport": dict(BRANCH)}
    assert launch.transport_error(job) is None
    assert launch.parse_transport(job) == BRANCH


def test_missing_fields_refuse_naming_the_field(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    for field in ("repo", "branch", "sha"):
        declared = {k: v for k, v in BRANCH.items() if k != field}
        err = launch.transport_error({"transport": declared})
        assert err is not None and field in err and "missing" in err, (field, err)


def test_missing_and_unknown_kind_refuse(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    err = launch.transport_error({"transport": {"repo": "r", "branch": "b", "sha": SHA}})
    assert err is not None and "kind" in err
    err = launch.transport_error({"transport": {"kind": "bundle", "repo": "r", "branch": "b", "sha": SHA}})
    assert err is not None and "bundle" in err and "kind" in err


def test_short_sha_and_nonstring_fields_refuse(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    err = launch.transport_error({"transport": {**BRANCH, "sha": "0123abcd"}})
    assert err is not None and "sha" in err and "40-hex" in err
    err = launch.transport_error({"transport": {**BRANCH, "branch": 7}})
    assert err is not None and "branch" in err
    err = launch.transport_error({"transport": ["branch"]})
    assert err is not None and "transport" in err


# --- the record stamp ---


def test_stamp_transport_branch_and_bundle(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    rec = {}
    parsed = launch.stamp_transport(rec, {"transport": dict(BRANCH)})
    assert parsed == BRANCH
    assert rec["transport"]["kind"] == "branch"
    assert rec["transport"]["sha"] == SHA
    assert rec["transport"]["bytes_moved"] == 0
    assert rec["transport"]["fetch_bytes"] is None
    rec2 = {}
    assert launch.stamp_transport(rec2, {}) is None
    assert rec2["transport"] == {"kind": "bundle", "bytes_moved": 0}


def test_stamp_transport_span(tmp_path):
    launch, foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))

    def _epoch(value):
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError):
            return None

    foundation.epoch = _epoch
    rec = {"transport": {"kind": "branch"}, "started_at": "2026-11-23T00:00:00+00:00",
           "launch_confirmed_at": "2026-11-23T00:01:30+00:00"}
    launch.stamp_transport_span(rec)
    assert rec["transport"]["claim_to_launch_s"] == 90.0
    rec2 = {"transport": {"kind": "bundle"}, "started_at": "2026-11-23T00:00:00+00:00"}
    launch.stamp_transport_span(rec2)
    assert "claim_to_launch_s" not in rec2["transport"]


# --- registry resolution ---


def test_resolve_branch_ctx(tmp_path):
    launch, foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))

    class Registry:
        @staticmethod
        def load_local_registry(root):
            return {}

        @staticmethod
        def get_entry(registry, repo_id):
            if repo_id != "supreme-octo-robot":
                raise ValueError(f"unknown repo {repo_id!r}")
            return repo_id, {"clone_url": "https://example.invalid/r.git", "dest": "supreme-octo-robot"}

    foundation.repo_registry = Registry
    assert launch.resolve_branch_ctx(None, None) == (None, None)
    err, ctx = launch.resolve_branch_ctx(BRANCH, {"manifest": {}})
    assert err is not None and "both" in err and ctx is None
    err, ctx = launch.resolve_branch_ctx({**BRANCH, "repo": "nope"}, None)
    assert err is not None and err.startswith("branch transport:") and ctx is None
    err, ctx = launch.resolve_branch_ctx(BRANCH, None)
    assert err is None
    assert ctx == {"clone_url": "https://example.invalid/r.git", "dest": "supreme-octo-robot"}


# --- the drive (Step 2) ---


def test_prepare_branch_lands_at_the_announced_sha(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("stdout", PLANT_OK), ("probe",), ("stdout", f"base clone at {SHA} tree abc\n")], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-1")
    assert err is None, err
    assert info == {"dest": "supreme-octo-robot", "head": SHA}
    assert {"stage": "branch", "ok": True, "detail": BRANCH["branch"]} in journal


def test_prepare_branch_refuses_a_mismatched_head(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("stdout", PLANT_OK), ("probe",), ("stdout", f"base clone at {OTHER} tree abc\n")], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-2")
    assert err is not None and "!=" in err and OTHER in err and SHA in err
    assert info == {}
    assert {"stage": "branch", "ok": False, "detail": BRANCH["branch"]} in journal


def test_prepare_branch_refuses_a_fetch_that_never_lands(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("stdout", PLANT_OK), ("probe",), ("stdout", "fatal: could not read from remote repository\n")], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-3")
    assert err is not None and "did not land" in err
    assert info == {}
    assert {"stage": "branch", "ok": False, "detail": BRANCH["branch"]} in journal


def test_prepare_branch_refuses_when_the_substrate_upload_fails(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("stdout", PLANT_OK)], src, upload_rc=1)
    launch, _foundation, _journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-4")
    assert err is not None and "base_clone.sh upload" in err
    assert info == {}
    assert colab.exec_calls == 1  # the plant probe only; the clone never runs


# --- the plant verification (plant cure) ---


def test_prepare_branch_refuses_at_an_unhealthy_plant_before_any_upload(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("stdout", PLANT_SPLIT)], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-5")
    assert err is not None and err.startswith("branch transport: git plant on session sess")
    assert "hosts" in err and "plant-github-key" in err
    assert info == {}
    assert colab.upload_calls == 0 and colab.exec_calls == 1
    assert {"stage": "branch", "ok": False, "detail": "plant"} in journal


def test_prepare_branch_refuses_when_the_plant_probe_never_answers(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("timeout",)], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-6")
    assert err is not None and "plant probe" in err and "timed out" in err
    assert info == {}
    assert colab.upload_calls == 0 and colab.exec_calls == 1
    assert {"stage": "branch", "ok": False, "detail": "plant"} in journal


def test_prepare_branch_refuses_when_the_plant_probe_returns_no_verdict(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("stdout", "some unstructured kernel noise\n")], src)
    launch, _foundation, _journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-7")
    assert err is not None and "plant probe" in err and "no verdict" in err
    assert info == {}
    assert colab.upload_calls == 0


# --- the plant's own upload set and pinned artifact ---

PLANT_JOB = REPO / "adapters" / "colab" / "jobs" / "plant-github-key" / "job.json"
PLANT_SCRIPT = REPO / "adapters" / "colab" / "snippets" / "jobs" / "plant_github_key.sh"
PINNED_HOSTS = REPO / "adapters" / "colab" / "snippets" / "jobs" / "known_hosts_github"
# GitHub's published github.com host keys (their docs' fingerprint set):
# the artifact pins these exact key bodies, never a learned-on-first-use set.
GITHUB_PUBLISHED = {
    "ssh-ed25519": "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl",
    "ecdsa-sha2-nistp256": "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=",
    "ssh-rsa": "AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=",
}


def test_plant_job_uploads_pair_the_kit_key_with_the_tracked_pinned_hosts():
    job = json.loads(PLANT_JOB.read_text())
    uploads = job["uploads"]
    # The key (a secret) rides the untracked kit; the known-hosts half
    # rides the tracked pinned artifact beside the plant script — the
    # same upload set plants both halves, every plant.
    assert "var/kit-github/id_ed25519" in uploads
    assert "adapters/colab/snippets/jobs/known_hosts_github" in uploads
    assert "var/kit-github/known_hosts_github" not in uploads
    assert "adapters/colab/snippets/jobs/plant_github_key.sh" in uploads


def test_pinned_known_hosts_carry_githubs_published_keys():
    seen = {}
    for line in PINNED_HOSTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        host, keytype, body = line.split()
        assert host == "github.com"
        seen[keytype] = body
    assert seen == GITHUB_PUBLISHED


def test_plant_script_plants_both_halves_to_the_sshcommand_paths():
    script = PLANT_SCRIPT.read_text()
    # Both halves are refused loudly when their upload is missing, and
    # both are planted under $HOME/.ssh in the same run.
    assert '"key upload missing' in script and '"known-hosts upload missing"' in script
    assert 'cp "$UP/id_ed25519" "$HOME/.ssh/id_github"' in script
    assert 'cp "$UP/known_hosts_github" "$HOME/.ssh/known_hosts_github"' in script
    # The sshCommand the clone reads names the planted pinned file as
    # its host-key source, with strict checking held at yes — and the
    # greeting verifies over that same file before the plant is OK.
    assert "UserKnownHostsFile=$HOME/.ssh/known_hosts_github" in script
    assert "StrictHostKeyChecking=yes" in script
    assert "accept-new" not in script and "StrictHostKeyChecking=no" not in script


# --- the probe's rewrite contract, executed ---

GREETING = "Hi redacted! You've successfully authenticated, but GitHub does not provide shell access."


def _fake_ssh_bin(tmp_path):
    """An ssh that answers with GitHub's greeting, as the
    planted key's auth does; the probe reads the greeting
    text, never a status."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    ssh = bin_dir / "ssh"
    ssh.write_text(f"#!/bin/sh\necho \"{GREETING}\" >&2\nexit 1\n")
    ssh.chmod(0o755)
    return bin_dir


def _probe_home(tmp_path, rewrite):
    """A session home in the plant's own shapes: both halves
    on disk, the planted sshCommand, and the insteadOf entry
    in the state the case names — planted (the HTTPS base as
    the value), missing, wrong (another value), or inverted
    (the SSH base sitting in the value, the shape the
    pre-cure check searched for)."""
    home = tmp_path / "home"
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(parents=True)
    (ssh_dir / "id_github").write_text("fake key\n")
    (ssh_dir / "known_hosts_github").write_text(
        "github.com ssh-ed25519 " + GITHUB_PUBLISHED["ssh-ed25519"] + "\n")
    env = dict(os.environ, HOME=str(home))

    def git_config(*args):
        subprocess.run(["git", "config", "--global", *args], env=env, check=True, capture_output=True)

    git_config("core.sshCommand",
               f"ssh -i {home}/.ssh/id_github -o UserKnownHostsFile={home}/.ssh/known_hosts_github -o StrictHostKeyChecking=yes")
    if rewrite == "planted":
        git_config("url.git@github.com:.insteadOf", "https://github.com/")
    elif rewrite == "wrong":
        git_config("url.git@github.com:.insteadOf", "https://example.invalid/")
    elif rewrite == "inverted":
        git_config("url.git@github.com:.insteadOf", "git@github.com:")
    elif rewrite != "missing":
        raise AssertionError(rewrite)
    return home


def _generated_probe(tmp_path):
    """The probe driver verify_git_plant generates, captured
    through the scripted colab it is exec'd by."""
    colab = ScriptedColab([("stdout", PLANT_OK)], Path(tmp_path))
    launch, _foundation, _journal = load_launch(tmp_path, colab)
    assert launch.verify_git_plant("sess", "probe-run") is None
    return (tmp_path / "var" / "plant-probe-probe-run.py").read_text()


def _execute_probe(tmp_path, driver_text, home):
    driver = tmp_path / "probe-driver.py"
    driver.write_text(driver_text)
    env = dict(os.environ, HOME=str(home),
               PATH=str(_fake_ssh_bin(tmp_path)) + os.pathsep + os.environ["PATH"])
    r = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_plant_probe_accepts_the_planted_rewrite(tmp_path):
    verdict = _execute_probe(tmp_path, _generated_probe(tmp_path), _probe_home(tmp_path, "planted"))
    assert verdict["failed"] == []


def test_plant_probe_refuses_a_missing_rewrite(tmp_path):
    verdict = _execute_probe(tmp_path, _generated_probe(tmp_path), _probe_home(tmp_path, "missing"))
    assert verdict["failed"] == ["rewrite"]


def test_plant_probe_refuses_a_wrong_rewrite_value(tmp_path):
    verdict = _execute_probe(tmp_path, _generated_probe(tmp_path), _probe_home(tmp_path, "wrong"))
    assert verdict["failed"] == ["rewrite"]


def test_plant_probe_refuses_the_inverted_rewrite(tmp_path):
    verdict = _execute_probe(tmp_path, _generated_probe(tmp_path), _probe_home(tmp_path, "inverted"))
    assert verdict["failed"] == ["rewrite"]


# --- the plant's read-back, executed ---


def _run_plant(tmp_path, extra_bin=None):
    """Run the plant script itself against a scratch home:
    the kit's uploads staged, ssh answering with the
    greeting, no probe repo named (the greeting alone
    verifies, as the script's header states)."""
    home = tmp_path / "plant-home"
    home.mkdir(exist_ok=True)
    up = tmp_path / "uploads"
    up.mkdir(exist_ok=True)
    (up / "id_ed25519").write_text("fake key\n")
    (up / "known_hosts_github").write_text(PINNED_HOSTS.read_text())
    dirs = ([extra_bin] if extra_bin else []) + [_fake_ssh_bin(tmp_path)]
    env = dict(os.environ, HOME=str(home),
               PATH=os.pathsep.join([str(d) for d in dirs] + [os.environ["PATH"]]),
               SHELL_JOB_UPLOADS=str(up), SHELL_JOB_OUT=str(tmp_path / "plant-out"))
    r = subprocess.run(["bash", str(PLANT_SCRIPT)], capture_output=True, text=True, env=env)
    return r, home


def _misreading_git_bin(tmp_path):
    """A git that delegates everything to the real git except
    the insteadOf read-back, which it answers with a wrong
    value — the plant's writes land, its read-back disagrees."""
    bin_dir = tmp_path / "git-shim-bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        "get=0; rewrite=0\n"
        "for a in \"$@\"; do\n"
        "  [ \"$a\" = \"--get\" ] && get=1\n"
        "  case \"$a\" in *insteadOf*) rewrite=1;; esac\n"
        "done\n"
        "if [ \"$get\" = 1 ] && [ \"$rewrite\" = 1 ]; then echo \"https://example.invalid/\"; exit 0; fi\n"
        f"exec {shutil.which('git')} \"$@\"\n")
    shim.chmod(0o755)
    return bin_dir


def test_plant_script_reads_back_the_config_it_writes():
    script = PLANT_SCRIPT.read_text()
    assert '--get url."git@github.com:".insteadOf' in script
    assert "--get core.sshCommand" in script
    assert "read-back" in script


def test_plant_script_reports_ok_with_its_config_read_back(tmp_path):
    r, home = _run_plant(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PLANT OK" in r.stdout
    env = dict(os.environ, HOME=str(home))
    rewrite = subprocess.run(
        ["git", "config", "--global", "--get", "url.git@github.com:.insteadOf"],
        env=env, capture_output=True, text=True).stdout.strip()
    assert rewrite == "https://github.com/"


def test_plant_script_fails_when_the_config_reads_back_wrong(tmp_path):
    r, _home = _run_plant(tmp_path, extra_bin=_misreading_git_bin(tmp_path))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "PLANT FAILED" in r.stdout and "read-back" in r.stdout
    assert "PLANT OK" not in r.stdout
