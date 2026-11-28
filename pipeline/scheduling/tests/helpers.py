"""Shared fixtures: a throwaway scheduler home (jobs/, bodies/,
state/) plus entry writers, so every test runs against real files
in a temp dir — never against the live registry."""
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import config as config_mod  # noqa: E402

UTC = timezone.utc


def make_home(root):
    for sub in ("jobs", "bodies", "state"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    config_path = os.path.join(root, "config.json")
    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    values, sources = config_mod.resolve(config_path, env={})
    return values, sources


def tracked_job_files(pkg_root):
    """The tracked registry fleet, from git's own index — the
    expectation derives from the tracked set itself, so
    provisioned per-deployment entries (machine progress arms,
    liveness entries) never enter it, in any checkout."""
    out = subprocess.run(
        ["git", "-C", pkg_root, "ls-files", "--", "jobs"],
        capture_output=True, text=True, check=True).stdout
    names = sorted(n for n in out.splitlines()
                   if n.endswith(".yaml"))
    assert names, "git ls-files returned no tracked jobs"
    return names


def seed_tracked_fleet(root, pkg_root):
    """Build a fixture home carrying the tracked fleet: copy
    each tracked entry into root/jobs and stub every body it
    references (bodies are per-deployment instance data,
    untracked by design; validation needs the files to exist).
    Returns the sorted tracked entry ids."""
    make_home(root)
    ids = []
    for rel in tracked_job_files(pkg_root):
        with open(os.path.join(pkg_root, rel),
                  encoding="utf-8") as fh:
            text = fh.read()
        job_id = os.path.basename(rel)[: -len(".yaml")]
        write_entry(root, job_id, text)
        ids.append(job_id)
        for line in text.splitlines():
            for field in ("body:", "escalate_body:"):
                if line.startswith(field):
                    ref = line.split(":", 1)[1].strip().strip("'\"")
                    path = os.path.join(root, ref)
                    os.makedirs(os.path.dirname(path),
                                exist_ok=True)
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write("Fixture body stub.\n")
    return sorted(ids)


def write_body(root, job_id, text="Body for the test job.\n"):
    path = os.path.join(root, "bodies", f"{job_id}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def write_script(root, name, code):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code)
    return path


def scripted_yaml(job_id, script_path, every="5m", timeout=10, report="  when: on_failure\n",
                  ok_codes="    - 0\n", extra_report="", extra=""):
    # Entries are portable: the script is addressed by anchor, never
    # by the temp dir's absolute path (registry portability rule).
    anchored = "${REPO}/" + os.path.basename(script_path)
    return (
        f"id: {job_id}\n"
        f"title: Test {job_id}\n"
        f"kind: scripted\n"
        f"cadence:\n  type: interval\n  every: {every}\n"
        f"owner: goal:test-goal\n"
        f"run:\n  argv:\n    - python3\n    - {anchored}\n"
        f"timeout_secs: {timeout}\n"
        f"report:\n{report}  ok_exit_codes:\n{ok_codes}{extra_report}"
        f"state_paths: []\n"
        f"classification: test fixture\n"
        f"{extra}"
    )


def agent_yaml(job_id, every="5m", timeout=60, extra=""):
    return (
        f"id: {job_id}\n"
        f"title: Test {job_id}\n"
        f"kind: agent\n"
        f"cadence:\n  type: interval\n  every: {every}\n"
        f"owner: goal:test-goal\n"
        f"body: bodies/{job_id}.md\n"
        f"executor: test-agent-surface\n"
        f"timeout_secs: {timeout}\n"
        f"state_paths: []\n"
        f"classification: test fixture\n"
        f"{extra}"
    )


def write_entry(root, job_id, text):
    path = os.path.join(root, "jobs", f"{job_id}.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class Clock:
    def __init__(self, start):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, **kwargs):
        from datetime import timedelta
        self.t += timedelta(**kwargs)
        return self.t


T0 = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)
