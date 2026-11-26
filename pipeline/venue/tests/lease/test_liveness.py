"""Session liveness: the checker (bin/colab-liveness) and the
derived scheduler entries (sync/liveness_entry.py).

The checker is driven as a subprocess against a fixture repo
so the tests exercise the shipped script end to end: local
fixtures for the lease record, the CLI binding, and the
approval-gate state, with every path seam pointed at the
fixture via the environment (the isolate-tests-from-live-
state rule: nothing here may touch the real registry, the
real binding, or the real gate state).
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO / "bin" / "colab-liveness"

sys.path.insert(0, str(REPO / "tests" / "fixtures"))
import env_fixtures  # noqa: E402
import repo_fixture  # noqa: E402

sys.path.insert(0, str(REPO / "sync"))
import liveness_entry as le  # noqa: E402

SESSION = "lilac-reef-93"
HOST = "8080-m-hm-test-aaaa.prod.r.colab.dev"


def iso(dt):
    return dt.isoformat()


def now():
    return datetime.now(timezone.utc)


class Fixture:
    def __init__(self, tmp_path):
        self.root = tmp_path / "runner"
        (self.root / "var").mkdir(parents=True)
        (self.root / "results" / "runs").mkdir(parents=True)
        self.jobs = tmp_path / "jobs"
        self.jobs.mkdir()
        self.bindings = tmp_path / "sessions.json"
        self.gate = tmp_path / "gate.json"
        self.env = {
            **os.environ,
            "COLAB_LIVENESS_JOBS_DIR": str(self.jobs),
            "COLAB_LIVENESS_BINDINGS": str(self.bindings),
            "COLAB_LIVENESS_GATE_STATE": str(self.gate),
            "COLAB_RUNNER_VAR": str(self.root / "var"),
        }

    def record(self, **over):
        rec = {
            "session": SESSION,
            "caller": "secforms",
            "shape": "cpu-highram",
            "host": HOST,
            "acquired_at": iso(now() - timedelta(hours=1)),
            "deadline": iso(now() + timedelta(hours=5)),
            "last_pulse_at": iso(now() - timedelta(minutes=5)),
            "last_pulse_result": "ok",
            "jobs": [],
        }
        rec.update(over)
        (self.root / "var" / f"lease-{SESSION}.json").write_text(json.dumps(rec))
        return rec

    def bind(self, host=HOST):
        self.bindings.write_text(json.dumps({SESSION: {"url": f"https://{host}/"}}))

    def gate_state(self, **over):
        meta = {"blocked": True, "contact_ok": False, "first_seen": iso(now() - timedelta(minutes=10)), "blocked_since": iso(now() - timedelta(minutes=9)), "last_probe": None}
        meta.update(over)
        self.gate.write_text(json.dumps({"hosts": {HOST: meta}}))

    def run(self, *args):
        return subprocess.run(
            [sys.executable, str(CHECKER), *args],
            capture_output=True, text=True, env=self.env, timeout=60,
        )

    def state(self):
        return json.loads((self.root / "var" / f"liveness-{SESSION}.json").read_text())


def healthy(tmp_path):
    fx = Fixture(tmp_path)
    fx.record()
    fx.bind()
    fx.gate_state(contact_ok=True, blocked=False)
    return fx


def test_healthy_is_silent(tmp_path):
    fx = healthy(tmp_path)
    r = fx.run(SESSION)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""
    assert fx.state()["open"] == {}


def test_gone_session_self_disarms(tmp_path):
    fx = healthy(tmp_path)
    entry = fx.jobs / f"colab-liveness-{SESSION}.yaml"
    entry.write_text(le.render_entry(SESSION))
    (fx.root / "var" / f"lease-{SESSION}.json").unlink()
    r = fx.run(SESSION)
    assert r.returncode == 0
    assert not entry.exists(), "leaked entry must delete itself"
    assert not (fx.root / "var" / f"liveness-{SESSION}.json").exists()


def test_binding_missing_speaks_once(tmp_path):
    fx = healthy(tmp_path)
    fx.bindings.write_text("{}")
    r1 = fx.run(SESSION)
    assert r1.returncode == 3 and "binding-missing" in r1.stdout
    r2 = fx.run(SESSION)
    assert r2.returncode == 0 and r2.stdout == "", "a persisting finding must not re-speak"


def test_binding_damaged_speaks_once_and_clears(tmp_path):
    fx = healthy(tmp_path)
    damaged = {"state": "damaged", "at": iso(now()), "detail": "restore-failed"}
    (fx.root / "var" / "binding-state.json").write_text(json.dumps(damaged))
    r1 = fx.run(SESSION)
    assert r1.returncode == 3 and "binding-damaged" in r1.stdout
    assert "binding-damaged" in fx.state()["open"]
    r2 = fx.run(SESSION)
    assert r2.returncode == 0 and r2.stdout == "", "a persisting finding must not re-speak"
    (fx.root / "var" / "binding-state.json").write_text(json.dumps({"state": "ok", "at": iso(now()), "detail": "restored"}))
    r3 = fx.run(SESSION)
    assert r3.returncode == 3 and "cleared" in r3.stdout
    assert fx.state()["open"] == {}


def _local_fx(tmp_path, with_target=True):
    """A local-venue record: no CLI binding exists for it by
    nature — its binding is the configured SSH target in the
    lease config under the fixture root."""
    fx = Fixture(tmp_path)
    fx.record(venue="local", host=None, shape="local")
    fx.gate_state(contact_ok=True, blocked=False)
    if with_target:
        cfg_dir = fx.root / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "lease.json").write_text(json.dumps({
            "venue_targets": {"local": {"host": "127.0.0.1", "port": 2222, "user": "agent", "session": SESSION}},
            "venue_shapes": {"local": [{"id": "local", "label": "Local machine"}]},
        }))
    return fx


def test_local_record_binds_through_its_target(tmp_path):
    fx = _local_fx(tmp_path)
    r = fx.run(SESSION)
    assert r.returncode == 0, r.stderr
    assert fx.state()["open"] == {}


def test_local_record_without_a_target_is_binding_missing(tmp_path):
    fx = _local_fx(tmp_path, with_target=False)
    r = fx.run(SESSION)
    assert r.returncode == 3 and "binding-missing" in r.stdout
    assert "no local target" in fx.state()["open"]["binding-missing"]["detail"]


def _fwd_state(**over):
    """A forwarder state record in the shape
    local_compute_fwd.py writes: every credential source
    failing, a streak open for twenty minutes."""
    failing = {"last_outcome": "proxy-407", "last_at": iso(now() - timedelta(minutes=20)), "attempts": 4, "failures": 4}
    state = {
        "target": "10.0.0.9:22",
        "listen_port": 2222,
        "started_at": iso(now() - timedelta(hours=1)),
        "sources": {
            "last_good": dict(failing),
            "launch": dict(failing, last_outcome="connect-error"),
            "pin_file": dict(failing),
        },
        "last_outcome": "failed",
        "last_at": iso(now() - timedelta(minutes=20)),
        "consecutive_failures": 12,
        "failing_since": iso(now() - timedelta(minutes=20)),
        "previous_instance": None,
    }
    state.update(over)
    return state


def _fwd_fx(tmp_path, state):
    """A local record whose target is a forwarder — the lease
    config names fwd_pin/fwd_dest — with the forwarder's
    state file beside the pin (or none, when state is None).
    The pulse is failing, as it is whenever the tunnel is
    dark."""
    fx = Fixture(tmp_path)
    fx.record(venue="local", host=None, shape="local", last_pulse_result="failed")
    fx.gate_state(contact_ok=True, blocked=False)
    pin = fx.root / "fwd-pin.env"
    pin.write_text("HTTPS_PROXY=http://x:x@proxy.invalid\n")
    cfg_dir = fx.root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "lease.json").write_text(json.dumps({
        "venue_targets": {"local": {
            "host": "127.0.0.1", "port": 2222, "user": "agent", "session": SESSION,
            "fwd_pin": str(pin), "fwd_dest": ["10.0.0.9", 22],
        }},
        "venue_shapes": {"local": [{"id": "local", "label": "Local machine"}]},
    }))
    if state is not None:
        Path(str(pin) + ".state.json").write_text(json.dumps(state))
    return fx


def test_forwarder_exhaustion_replaces_pulse_failing(tmp_path):
    fx = _fwd_fx(tmp_path, _fwd_state())
    r = fx.run(SESSION)
    assert r.returncode == 3 and "forwarder-credential-exhaustion" in r.stdout
    open_now = fx.state()["open"]
    assert "forwarder-credential-exhaustion" in open_now
    assert "pulse-failing" not in open_now
    r2 = fx.run(SESSION)
    assert r2.returncode == 0 and r2.stdout == "", "a persisting finding must not re-speak"


def test_forwarder_recent_established_clears_the_pulse_finding(tmp_path):
    state = _fwd_state(
        last_outcome="established",
        last_at=iso(now() - timedelta(minutes=2)),
        consecutive_failures=0,
        failing_since=None,
    )
    fx = _fwd_fx(tmp_path, state)
    r = fx.run(SESSION)
    assert r.returncode == 0, r.stdout + r.stderr
    assert fx.state()["open"] == {}


def test_forwarder_fresh_streak_is_not_yet_exhaustion(tmp_path):
    state = _fwd_state(
        last_at=iso(now() - timedelta(minutes=2)),
        consecutive_failures=2,
        failing_since=iso(now() - timedelta(minutes=2)),
    )
    fx = _fwd_fx(tmp_path, state)
    r = fx.run(SESSION)
    assert r.returncode == 3 and "pulse-failing" in r.stdout
    assert "forwarder-credential-exhaustion" not in r.stdout
    assert "forwarder-credential-exhaustion" not in fx.state()["open"]


def test_local_pulse_failing_stands_without_a_forwarder_state(tmp_path):
    fx = _fwd_fx(tmp_path, None)
    r = fx.run(SESSION)
    assert r.returncode == 3 and "pulse-failing" in r.stdout
    assert "forwarder-credential-exhaustion" not in r.stdout


def test_host_divergence(tmp_path):
    fx = healthy(tmp_path)
    fx.bind(host="8080-m-hm-test-zzzz.prod.r.colab.dev")
    r = fx.run(SESSION)
    assert r.returncode == 3 and "host-divergence" in r.stdout


def test_deadline_overdue(tmp_path):
    fx = healthy(tmp_path)
    fx.record(deadline=iso(now() - timedelta(minutes=30)))
    r = fx.run(SESSION)
    assert r.returncode == 3 and "deadline-overdue" in r.stdout


def test_pulse_failing_and_stale(tmp_path):
    fx = healthy(tmp_path)
    fx.record(last_pulse_result="failed")
    r = fx.run(SESSION)
    assert r.returncode == 3 and "pulse-failing" in r.stdout
    fx2 = healthy(tmp_path / "b")
    fx2.record(last_pulse_at=iso(now() - timedelta(hours=2)))
    r2 = fx2.run(SESSION)
    assert r2.returncode == 3 and "pulse-stale" in r2.stdout


def test_tonight_shape_approval_escalates_once_per_episode(tmp_path):
    """The lilac specimen: gate blocked, pulse failing, jobs
    empty. The approval finding stays unspoken below the
    threshold, escalates exactly once past it, and the
    mechanical pulse finding speaks on its own first sight."""
    fx = Fixture(tmp_path)
    fx.record(last_pulse_result="failed", jobs=[])
    fx.bind()
    fx.gate_state(first_seen=iso(now() - timedelta(minutes=10)))
    r = fx.run(SESSION)
    assert r.returncode == 3 and "pulse-failing" in r.stdout
    assert "approval-outstanding" not in r.stdout, "below threshold: no escalation yet"
    # The blockage ages past the 30-minute threshold.
    fx.gate_state(first_seen=iso(now() - timedelta(minutes=40)),
                  blocked_since=iso(now() - timedelta(minutes=39)))
    r = fx.run(SESSION)
    assert r.returncode == 3 and "approval-outstanding" in r.stdout
    # Next ping: the episode is spent, the pulse finding is old.
    r = fx.run(SESSION)
    assert r.returncode == 0 and r.stdout == ""
    # Approval lands: contact proves, everything clears, once.
    fx.record(last_pulse_result="ok")
    fx.gate_state(contact_ok=True, blocked=False)
    r = fx.run(SESSION)
    assert r.returncode == 3 and "cleared" in r.stdout
    r = fx.run(SESSION)
    assert r.returncode == 0 and r.stdout == ""


def lease_cli_env(tmp_path):
    """The test_lease_fake harness shape: scratch HOME with a
    fake token, the fake CLI, a scratch var — plus the jobs
    seam pointed at a scratch registry so the lifecycle arms
    and disarms entries the test can inspect."""
    env = env_fixtures.lease_env(tmp_path)
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    env["COLAB_LIVENESS_JOBS_DIR"] = str(jobs)
    return env, jobs


def run_lease_cli(env, *args):
    r = subprocess.run([sys.executable, str(Path(env["TEST_REPO_ROOT"]) / "bin" / "colab-lease"), *args],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_render_entry_shape():
    text = le.render_entry(SESSION)
    assert f"id: colab-liveness-{SESSION}" in text
    assert "every: 15m" in text
    assert "escalate_body: bodies/colab-liveness.md" in text
    # Amendment 3 (target registry format): the migration field
    # family does not exist — presence through the writer path
    # is admission, so the render carries no migrated stamp.
    assert "migrated" not in text
    assert "pipeline/venue/bin/colab-liveness" in text
    assert SESSION in text


def test_lease_lifecycle_arms_and_disarms(tmp_path):
    """Step 2's verify: acquire writes the session's entry via
    the record writers, release removes it — no seam calls in
    the test, the lifecycle itself does it."""
    env, jobs = lease_cli_env(tmp_path)
    out = run_lease_cli(env, "acquire", "--shape", "cpu")
    session = out["record"]["session"]
    entry = jobs / f"colab-liveness-{session}.yaml"
    assert entry.exists(), "acquire must arm the liveness entry"
    assert f"colab-liveness-{session}" in entry.read_text()
    run_lease_cli(env, "release")
    assert not entry.exists(), "release must retire the liveness entry"

    text = le.render_entry(SESSION)
    assert f"id: colab-liveness-{SESSION}" in text
    assert "every: 15m" in text
    assert "escalate_body: bodies/colab-liveness.md" in text
    assert SESSION in text


def test_arming_waits_for_the_escalate_body(tmp_path, monkeypatch):
    """Default-resolution arming refuses while the entry's
    shared escalate body is absent from the pipeline's
    scheduling tree: an entry pointing at a missing body fails
    registry validation, so the body lands first or nothing
    arms. (S5: default resolution is tree-relative — the
    pipeline's own scheduling registry beside the venue tree —
    so the fixture lays out a miniature pipeline tree and
    points the module's installed-repo root at it.)"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("COLAB_LIVENESS_JOBS_DIR", raising=False)
    venue_root = tmp_path / "pipeline" / "venue"
    venue_root.mkdir(parents=True)
    monkeypatch.setattr(le, "_MODULE_REPO", venue_root)
    jobs = tmp_path / "pipeline" / "scheduling" / "jobs"
    jobs.mkdir(parents=True)
    rec = {"session": "body-guard-00"}
    assert le.sync_for_record(venue_root, rec) == "unavailable"
    body = tmp_path / "pipeline" / "scheduling" / "bodies" / "colab-liveness.md"
    body.parent.mkdir(parents=True)
    body.write_text("# body\n")
    assert le.sync_for_record(venue_root, rec) == "written"
    assert (jobs / "colab-liveness-body-guard-00.yaml").exists()


def test_sync_and_reconcile(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    repo = tmp_path / "runner"
    (repo / "var").mkdir(parents=True)
    os.environ["COLAB_LIVENESS_JOBS_DIR"] = str(jobs)
    try:
        rec = {"session": SESSION, "caller": "secforms"}
        assert le.sync_for_record(repo, rec) == "written"
        assert le.sync_for_record(repo, rec) == "present", "refresh must not churn identical content"
        orphan = jobs / "colab-liveness-ghost-00.yaml"
        orphan.write_text(le.render_entry("ghost-00"))
        out = le.reconcile(repo, [rec])
        assert out["removed"] == ["ghost-00"] and not orphan.exists()
        assert le.remove_for_session(repo, SESSION) == "removed"
        assert not (jobs / f"colab-liveness-{SESSION}.yaml").exists()
        out = le.reconcile(repo, [rec])
        assert out["armed"] == [SESSION], "reconcile re-arms a live session whose entry was deleted"
    finally:
        del os.environ["COLAB_LIVENESS_JOBS_DIR"]
