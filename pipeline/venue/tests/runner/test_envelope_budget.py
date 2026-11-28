"""The envelope budget leaf (sync/runner/envelope.py):
the budget division over declared capacity fixtures, the
remainder order, the burst-priced worker count, and the
per-job connection-pool worst cases. Pure arithmetic —
the leaf loads by path, with no package context."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

env = load_module("envelope_unit", REPO / "sync" / "runner" / "envelope.py")


def test_declared_capacities_are_the_two_local_shapes():
    assert env.declared_capacity("local") == {"cores": 16, "pids": 1024}
    assert env.declared_capacity("local-hp") == {"cores": 8, "pids": 1024}
    assert env.declared_capacity("nope") is None


def test_budget_is_the_named_fraction_net_of_the_system_reserve():
    # The reserve (128) comes off the ceiling before the
    # fraction: (1024 - 128) * fraction, at any fraction —
    # a fraction of 1.0 still never budgets the reserve.
    assert env.SYSTEM_RESERVE_THREADS == 128
    assert env.envelope_budget(1024) == 672
    assert env.envelope_budget(1024, 0.5) == 448
    assert env.envelope_budget(1024, 1.0) == 896
    assert env.envelope_budget(4096) == 2976


def test_divide_default_burst_prices_one_worker_at_these_shares():
    # The default worst case (860) exceeds every share the
    # 672 budget divides into at N >= 1, so the burst term
    # binds everywhere: one worker per job, its pool cap
    # the whole share. A share of 336 pricing exactly 1
    # worker is the coordinator's hand-set form, pinned.
    expected_shares = {
        1: [672],
        2: [336, 336],
        3: [224, 224, 224],
        4: [168, 168, 168, 168],
        5: [135, 135, 134, 134, 134],
        6: [112, 112, 112, 112, 112, 112],
    }
    for shape, cores in (("local", 16), ("local-hp", 8)):
        budget = env.envelope_budget(env.declared_capacity(shape)["pids"])
        for n, shares in expected_shares.items():
            divisions = env.divide(budget, cores, n)
            assert [d["thread_share"] for d in divisions] == shares, (shape, n)
            assert [d["workers"] for d in divisions] == [1] * n, (shape, n)
            assert [d["pool_cap"] for d in divisions] == shares, (shape, n)


def test_divide_remainder_goes_to_the_first_jobs_in_order():
    divisions = env.divide(770, 16, 3, burst_per_worker=100)
    assert [d["thread_share"] for d in divisions] == [257, 257, 256]
    assert [d["workers"] for d in divisions] == [2, 2, 2]
    assert [d["pool_cap"] for d in divisions] == [128, 128, 128]


def test_divide_small_burst_override_lets_workers_scale():
    divisions = env.divide(768, 16, 2, burst_per_worker=100)
    assert [d["workers"] for d in divisions] == [3, 3]
    assert [d["pool_cap"] for d in divisions] == [128, 128]


def test_divide_core_share_bounds_when_the_burst_term_does_not():
    divisions = env.divide(768, 8, 2, burst_per_worker=10)
    assert [d["workers"] for d in divisions] == [4, 4]
    assert [d["pool_cap"] for d in divisions] == [96, 96]


def test_connection_worst_case_is_connections_times_per_plus_overhead():
    assert env.connection_worst_case(5, 39) == 345
    assert env.connection_worst_case(2, 8) == 166
    assert env.declared_worst_case("plain-name") is None
    assert env.declared_worst_case({"name": "x"}) is None
    assert (
        env.declared_worst_case(
            {"name": "x", "connections": 5, "threads_per_connection": 39}
        )
        == 345
    )


def test_duckdb_declared_and_undeclared_both_price_one_worker_by_different_routes():
    # Declared route: 384 // 345 == 1. Undeclared route:
    # 384 // 860 == 0, floored to 1. Same bound, and the
    # routes must not be conflated — the declared figure
    # scales with connections, the flat one does not.
    divisions = env.divide(768, 16, 2, worst_cases=[345, None])
    assert divisions[0]["workers"] == 1
    assert divisions[1]["workers"] == 1
    scaled = env.divide(4096, 16, 1, worst_cases=[345])
    assert scaled[0]["workers"] == 11  # 4096 // 345, under the 16-core share
    flat = env.divide(4096, 16, 1)
    assert flat[0]["workers"] == 4  # 4096 // 860


def test_small_pool_job_prices_two_workers_against_a_384_share():
    divisions = env.divide(768, 16, 2, worst_cases=[166, 166])
    assert [d["workers"] for d in divisions] == [2, 2]
    assert [d["pool_cap"] for d in divisions] == [192, 192]


def test_envelope_error_accepts_plain_and_object_entries():
    assert env.envelope_error({"shape": "local", "jobs": ["a", "b"]}) is None
    assert (
        env.envelope_error(
            {
                "shape": "local-hp",
                "jobs": [{"name": "a", "connections": 5, "threads_per_connection": 39}],
                "fraction": 0.5,
                "burst_per_worker": 100,
            }
        )
        is None
    )


def test_envelope_error_refusals_name_the_field():
    cases = [
        ({"jobs": ["a"]}, "shape"),
        ({"shape": "nope", "jobs": ["a"]}, "declares no capacity"),
        ({"shape": "local", "jobs": []}, "non-empty"),
        ({"shape": "local", "jobs": ["a", "a"]}, "named twice"),
        ({"shape": "local", "jobs": ["a/b"]}, "path-safe"),
        ({"shape": "local", "jobs": ["a"], "fraction": 0}, "fraction"),
        ({"shape": "local", "jobs": ["a"], "fraction": 1.5}, "fraction"),
        ({"shape": "local", "jobs": ["a"], "burst_per_worker": 0}, "burst_per_worker"),
        (
            {"shape": "local", "jobs": [{"name": "a", "connections": 5}]},
            "as a pair",
        ),
        (
            {
                "shape": "local",
                "jobs": [{"name": "a", "connections": 0, "threads_per_connection": 39}],
            },
            "connections",
        ),
    ]
    for spec, needle in cases:
        error = env.envelope_error(spec)
        assert error is not None and needle in error, (spec, error)
