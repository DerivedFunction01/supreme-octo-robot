#!/usr/bin/env python3
"""Permission-card watch — the cadence adapter (permission-card
plan, Step 5).

One behavior: run one watcher pass. The adapter owns only
what the cadence home owns — the dedicated caller's
provisioning shape, the token file's resolution, the bridged
card source's construction, and the exit alphabet the
registry entry's report rule branches on. Everything about
cards themselves — reconciliation, posting waits, resolution
watching, nudges, resumption verification — is the registry
watcher core's (`pipeline/registry/cardwatch.py`, Steps
2–4); this adapter hands the core a source and a clock and
maps its enumerable outcome to an exit code. The core is
resolved through the single seam below (`load_core_runner`),
so the final wiring is that one resolution, never a second
implementation here.

The caller: a dedicated machinery caller, `card-watch`,
holding the connector's `read` scope only. Its provisioning
shape is declared here as code constants (the governed
form: the name and scopes a mint must carry, stated once,
in code); the mint itself rides the existing connector-token
route into the untracked live config, hashes only server-side,
and the raw token reaches this script solely as the token
file the ops token home holds (`<caller>.token`, the
contract 04 home the mint's --save-client writes). A missing
or unreadable token file resolves to no token: the connector
client then runs in shadow, the source reads that as
source-stale, and the pass records a non-run — an
unprovisioned watcher never reads as zero cards.

The hard-stop floor is structural, and the entry test pins
it: the caller's one scope is `read`; every resolving or
mutating tool the connector exposes needs another scope and
is refused before performing, and no approve/deny tool
exists on the connector surface at all. This adapter holds
no code path that writes a runtime decision.

Exit alphabet (the entry declares 0/3/4 as normal):
  0  pass complete — silent.
  3  source-stale non-run — the source did not answer; no
     watcher state was touched.
  4  partial history — the snapshot answered but at least
     one history read did not; the core's line says which.
  5  core unavailable or nonconforming — a defect, reported
     as a failure by the entry's report rule, never a pass.
The core decides when a pass speaks; its line is printed
verbatim, and a line carrying the CARD_WATCH_DEFECT marker
turns an otherwise-normal exit into a failure under the
entry's fail_patterns (the repeated-source-stale escalation
rides that marker).

Determinism: the clock is injected everywhere a stamp is
taken (the source seam takes it as a callable); the
production clock is the one wall-clock read in this module,
and tests pass a fake.
"""
import importlib
import importlib.util as _importlib_util
import os
import sys
from datetime import datetime, timezone

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

_timestamps_spec = _importlib_util.spec_from_file_location(
    "ops_timestamps",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "timestamps.py"),
                       os.path.join(_here, "timestamps.py"))
         if os.path.isfile(_p)))
timestamps = _importlib_util.module_from_spec(_timestamps_spec)
_timestamps_spec.loader.exec_module(timestamps)

SCHEDULING_ROOT = paths.REPO_ROOT
PIPELINE_ROOT = os.path.dirname(SCHEDULING_ROOT)
if PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, PIPELINE_ROOT)

JOB_ID = "card-watch"
CADENCE_EVERY = "15m"

# The dedicated caller's provisioning shape (code constants):
# the name every mint and token file carries, the one scope
# it may hold, and the two bridged reads that scope covers.
CALLER_NAME = "card-watch"
CALLER_SCOPES = ("read",)
SOURCE_TOOLS = ("permissions_list", "permissions_history")

# Token resolution: an explicit file wins, else the ops
# token home (contract 04 — the mint's --save-client target,
# re-pointable through the same env seam the ops client
# reads), one file per caller.
TOKEN_FILE_ENV = "CARD_WATCH_TOKEN_FILE"
TOKEN_DIR_ENV = "SCHED_OPS_TOKEN_DIR"
DEFAULT_TOKEN_DIR = os.path.join(SCHEDULING_ROOT, "ops-tokens")

EXIT_PASS_COMPLETE = 0
EXIT_SOURCE_STALE = 3
EXIT_PARTIAL_HISTORY = 4
EXIT_CORE_UNAVAILABLE = 5

OUTCOME_EXIT_CODES = {
    "pass_complete": EXIT_PASS_COMPLETE,
    "source_stale": EXIT_SOURCE_STALE,
    "partial_history": EXIT_PARTIAL_HISTORY,
}

DEFECT_MARKER = "CARD_WATCH_DEFECT"


def caller_provisioning():
    """The mint the freeze performs, as data: the caller's
    name, its scopes, the tools those scopes cover, and the
    existing route that mints it. No credential material —
    the raw token exists only in the token file the mint's
    client-save writes and is never a tracked value."""
    return {
        "name": CALLER_NAME,
        "scopes": list(CALLER_SCOPES),
        "source_tools": list(SOURCE_TOOLS),
        "mint_argv": [
            "bin/sched", "connector-token", CALLER_NAME,
            "--scopes", ",".join(CALLER_SCOPES), "--save-client",
        ],
        "token_file": f"<ops token home>/{CALLER_NAME}.token",
    }


def token_file_path(env=None):
    env = os.environ if env is None else env
    explicit = env.get(TOKEN_FILE_ENV)
    if explicit:
        return explicit
    home = env.get(TOKEN_DIR_ENV) or DEFAULT_TOKEN_DIR
    return os.path.join(home, f"{CALLER_NAME}.token")


def read_token(env=None):
    """The caller's raw token from its token file, read at
    call time, or None — a missing, unreadable, or empty
    file is an unprovisioned caller, never an invented one."""
    try:
        with open(token_file_path(env), encoding="utf-8") as fh:
            token = fh.read().strip()
    except OSError:
        return None
    return token or None


# The production clock: an ISO stamp in the source seam's
# format, from the ops clock home. Tests inject a fake
# instead (the `clock or iso_now` seam in build_source).
iso_now = timestamps.zstamp_now


def build_source(env=None, clock=None, transport=None, poll_seconds=1200):
    """The production card source: the registry source seam
    over the shared connector client, authenticated as the
    dedicated caller. `transport` is injectable so tests
    drive the seam over a fake bridge with a fake clock."""
    from registry.cards import cardsource

    if transport is None:
        bridge_dir = paths.cluster_dir("bridge")
        if bridge_dir not in sys.path:
            sys.path.insert(0, bridge_dir)
        import connector_client

        transport = connector_client.Client(
            token=read_token(env), poll_seconds=poll_seconds)
    return cardsource.BridgeCardSource(transport, clock or iso_now)


STATE_FILE_ENV = "CARD_WATCH_STATE_FILE"


def default_store():
    """The production attention store for a pass: the
    attention package's AttentionStateStore over the live
    attention state file — CARD_WATCH_STATE_FILE when set,
    else the registry var dir's `state.json` (the migrated
    store's filename at its pin, in its mega var home)."""
    from registry import paths as registry_paths
    from attention.infra import attstore

    path = os.environ.get(STATE_FILE_ENV) or os.path.join(
        registry_paths.VAR_DIR, "state.json")
    return attstore.AttentionStateStore(path)


def _parse_now(now):
    """The core takes an aware datetime; this adapter's
    clock speaks the source seam's ISO stamps. Accept
    either, normalize to aware UTC — the registry cardwatch
    module's strict normalize home, bound lazily like the
    watcher core below."""
    from registry.cards.cardwatch import _as_dt_strict

    return _as_dt_strict(now)


# The core's PassResult kinds -> this entry's outcome
# tokens (the exit alphabet's names for the same facts).
_CORE_OUTCOMES = {
    "complete": "pass_complete",
    "source_stale": "source_stale",
    "partial_history": "partial_history",
}


def load_core_runner():
    """The watcher core's pass entry point, or None when the
    core is not in the tree or does not expose it. The
    core's frozen contract (registry.cards.cardwatch, Steps 2–4):
    `run_pass(store, source, now)` — the attention store,
    a card source, an aware datetime — returning a
    PassResult whose kind is "complete" | "source_stale" |
    "partial_history" with a detail. The runner returned
    here binds that contract to this adapter's seam: it
    builds the production store, parses the pass's ISO
    stamp, and maps the result onto the exit alphabet
    (a spoken line rides the mapping for the two non-run
    kinds; a complete pass is silent). A core that fails
    to import for any other reason is a defect and raises,
    never a silent absence."""
    try:
        module = importlib.import_module("registry.cards.cardwatch")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".")[0] == "registry" \
                and ("cardwatch" in exc.name
                     or exc.name == "registry.cards"):
            return None
        raise
    run_pass = getattr(module, "run_pass", None)
    if not callable(run_pass):
        return None

    def runner(source, now):
        result = run_pass(default_store(), source, _parse_now(now))
        outcome = _CORE_OUTCOMES.get(getattr(result, "kind", None))
        if outcome is None:
            return result
        if result.kind == "source_stale":
            return {"outcome": outcome, "line": (
                f"card-watch: source_stale ({result.detail}) — "
                "non-run, watcher state untouched")}
        if result.kind == "partial_history":
            return {"outcome": outcome, "line": (
                f"card-watch: partial_history ({result.detail})")}
        return outcome

    return runner


def run_once(source, core_runner, now):
    """One pass over the injected seam -> (exit_code, line).
    Pure mapping: the core's outcome token decides the exit;
    the core's line (when it speaks) is relayed verbatim. An
    outcome outside the alphabet is a core contract defect,
    exit 5 — never folded into a pass."""
    if core_runner is None:
        return EXIT_CORE_UNAVAILABLE, (
            "CARD_WATCH_CORE_UNAVAILABLE: the registry watcher "
            "core is not in the tree or exposes no run_pass")
    result = core_runner(source, now)
    if isinstance(result, dict):
        outcome = result.get("outcome")
        line = result.get("line")
    else:
        outcome, line = result, None
    code = OUTCOME_EXIT_CODES.get(outcome)
    if code is None:
        return EXIT_CORE_UNAVAILABLE, (
            f"{DEFECT_MARKER}: core returned an outcome outside "
            f"the exit alphabet: {outcome!r}")
    return code, line


def main(argv=None, env=None, source=None, core_runner=None, clock=None):
    clock = clock or iso_now
    now = clock()
    if source is None:
        source = build_source(env=env, clock=clock)
    if core_runner is None:
        core_runner = load_core_runner()
    code, line = run_once(source, core_runner, now)
    if line:
        print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
