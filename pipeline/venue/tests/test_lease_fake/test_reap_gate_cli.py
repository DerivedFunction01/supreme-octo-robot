"""The reap's approval-gate flags at the CLI: a malformed
host list refuses (exit 2) before any lease work runs — the
gate set is the reaper hook's word about which tunnel hosts
may not be dialed, and a garbled word must never degrade into
an unscoped pass.
"""

from fake_harness import lease_env, run_lease_rc  # noqa: F401


def test_reap_gate_malformed_host_refuses(tmp_path):
    env = lease_env(tmp_path)
    rc, out = run_lease_rc(env, "reap", "--gate-pending-hosts", "bad host")
    assert rc == 2
    assert out == {}


def test_reap_gate_probe_outside_pending_refuses(tmp_path):
    env = lease_env(tmp_path)
    rc, out = run_lease_rc(env, "reap", "--gate-pending-hosts", "ok.example", "--gate-probe-hosts", "other.example")
    assert rc == 2
    assert out == {}


def test_reap_gate_stray_argument_refuses(tmp_path):
    env = lease_env(tmp_path)
    rc, out = run_lease_rc(env, "reap", "stray")
    assert rc == 2
    assert out == {}
