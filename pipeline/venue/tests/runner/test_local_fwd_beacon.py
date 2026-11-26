"""Local forwarder beacon: the declared argv surface.

The beacon's --venue-root used to be found by a membership
test and taken by index — the argv-idioms hazard class (a
missing value crashed with a traceback, an unknown flag was
silently ignored). The specimens pin the migrated surface
through the unified contract's parse-only mode: both value
forms parse, a missing value and an unknown flag refuse at
exit 2, and the dummy battery matches across the whole
declaration. The beacon's main is exercised only on its
refusal and help paths — a valid argv would run the real
restock against the live config, which no test may do.
"""

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEACON = ROOT / "bin" / "local-fwd-beacon"


_MOD = None


def load_beacon():
    global _MOD
    if _MOD is None:
        spec = importlib.util.spec_from_loader(
            "local_fwd_beacon_under_test", SourceFileLoader("local_fwd_beacon_under_test", str(BEACON))
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MOD = mod
    return _MOD


def test_declaration_dummy_battery_matches():
    mod = load_beacon()
    cases = mod._argv.dummy(mod.DECLARATION)
    assert cases and all(c["matched"] for c in cases)


def test_parse_only_value_forms_and_refusals():
    mod = load_beacon()
    parse_only = mod._argv.parse_only
    plain = parse_only(mod.DECLARATION, [])
    assert plain["ok"] and plain["result"]["flags"]["venue-root"] is None
    spaced = parse_only(mod.DECLARATION, ["--venue-root", "/srv/venue"])
    assert spaced["ok"] and spaced["result"]["flags"]["venue-root"] == "/srv/venue"
    joined = parse_only(mod.DECLARATION, ["--venue-root=/srv/venue"])
    assert joined["ok"] and joined["result"]["flags"]["venue-root"] == "/srv/venue"
    for bad in (
        ["--venue-root"],
        ["--venue-root", "--bogus"],
        ["--bogus"],
        ["--venue"],
        ["surplus"],
    ):
        out = parse_only(mod.DECLARATION, bad)
        assert not out["ok"] and out["exit_code"] == 2, bad


def test_main_refuses_an_unknown_flag_at_exit_2(capsys):
    mod = load_beacon()
    assert mod.main(["--bogus"]) == 2
    assert "unknown flag" in capsys.readouterr().err


def test_main_missing_value_is_a_usage_refusal_not_a_traceback(capsys):
    mod = load_beacon()
    assert mod.main(["--venue-root"]) == 2
    assert "needs a value" in capsys.readouterr().err


def test_main_help_exits_0(capsys):
    mod = load_beacon()
    assert mod.main(["--help"]) == 0
    assert "usage: local-fwd-beacon" in capsys.readouterr().out
