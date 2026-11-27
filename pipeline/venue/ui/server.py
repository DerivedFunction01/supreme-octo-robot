#!/usr/bin/env python3
"""Lease control UI server — the operator's manual control surface for the
colab-runner lease.

Standard library only (repo rule). Binds 127.0.0.1 (default port 8793,
see ui/config.json). The server contains no lease logic: every read and
mutation shells out to bin/colab-lease, whose JSON is passed through to
the page — all derivation stays core-side; the page's only client-side
derivation is countdown arithmetic on served timestamps.

Mutations append events to var/ui-outbox.jsonl (this
server, plus the runner core's run-terminal appends).
The notify hook (colab-lease-notify) tails that file and wakes
the main chat; GET /api/outbox reads never acknowledge anything.

The HTTP plumbing rides the platform serving core
(pipeline/platform/serving.py) — the one serving
implementation for the whole mega app (owner ruling).
This module owns the panel's routes and
their core-shelling behavior; the wire, the reply
framing, and the containment are the core's.

This surface serves in its OWN process (owner ruling,
extending the workbench split: process
boundaries follow coupling) — run.py serve-venue, under
its own unit — because its state reads shell out
synchronously to the lease core and the panel faces the
heaviest polling of the surfaces, so its saturation
must never starve the coupled scheduler+attention
process. Inside this process the reads are hardened for
that load: state reads serve stale-while-recompute
under a read-scoped timeout (state_reads.py) and the
listener's handler threads are bounded
(bounded_server.py), so a hung core call degrades the
panel alone.

Env overrides (used by the tests):
  VENUE_LEASE_BIN   lease CLI path (default <repo>/bin/colab-lease)
  VENUE_LEASE_UI_SH UI control script path (default <repo>/ui/ui.sh)
  VENUE_RUNNER_VAR  var dir (default <repo>/var)
  VENUE_LEASE_UI_HOST / VENUE_LEASE_UI_PORT
  VENUE_LEASE_UI_STACKDUMP  "0" disables the stack-dump watchdog
"""

import importlib.util
import json
import os
import subprocess
import sys
import threading
import types
from datetime import datetime, timezone
from pathlib import Path

from stackdump import StackDumpWatchdog

UI_DIR = Path(__file__).resolve().parent
REPO = UI_DIR.parent
STATIC_DIR = UI_DIR / "static"
CONFIG_PATH = UI_DIR / "config.json"
PIPELINE_ROOT = REPO.parent


def _load_by_location(name: str, path: Path):
    """Load one module by location, registered before it
    executes: the platform serving core and this panel's
    own sibling seams (state_reads, bounded_server) all
    load this one way, in every entry form — the
    standalone script, run.py's by-location load, and the
    test fixture's copied tree alike."""
    spec = importlib.util.spec_from_file_location(
        name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


serving = _load_by_location(
    "platform_serving",
    PIPELINE_ROOT / "platform" / "serving.py")
state_reads = _load_by_location(
    "venue_state_reads", UI_DIR / "state_reads.py")
bounded_server = _load_by_location(
    "venue_bounded_server", UI_DIR / "bounded_server.py")
state_surface = _load_by_location(
    "venue_state_surface", UI_DIR / "state_surface.py")
route_surface = _load_by_location(
    "venue_route_surface", UI_DIR / "route_surface.py")
writer = _load_by_location(
    "platform_writer", PIPELINE_ROOT / "platform" / "writer.py")
uargv = _load_by_location(
    "platform_argv", PIPELINE_ROOT / "platform" / "argv.py")

CORE_TIMEOUT_S = 1800
# The state-read bounds live with the state-read wiring
# in state_surface.py; these
# aliases keep the names this module's own readers use.
# They are import-time snapshots, NOT live knobs:
# state_surface.build_state_reads reads its own module
# global, so a test that patches a cadence patches
# state_surface.STATE_REFRESH_AFTER_S, never this alias.
STATE_READ_TIMEOUT_S = state_surface.STATE_READ_TIMEOUT_S
STATE_COMPUTE_TIMEOUT_S = state_surface.STATE_COMPUTE_TIMEOUT_S
STATE_REFRESH_AFTER_S = state_surface.STATE_REFRESH_AFTER_S


def lease_bin() -> str:
    return os.environ.get("VENUE_LEASE_BIN", os.environ.get("COLAB_LEASE_BIN", str(REPO / "bin" / "colab-lease")))  # step6-retire: COLAB_ dual-read fallback


def ui_sh() -> str:
    return os.environ.get("VENUE_LEASE_UI_SH", os.environ.get("COLAB_LEASE_UI_SH", str(UI_DIR / "ui.sh")))  # step6-retire: COLAB_ dual-read fallback


def var_dir() -> Path:
    return Path(os.environ.get("VENUE_RUNNER_VAR", os.environ.get("COLAB_RUNNER_VAR", REPO / "var")))  # step6-retire: COLAB_ dual-read fallback


def outbox_path() -> Path:
    return var_dir() / "ui-outbox.jsonl"


def parse_core_json(stdout: str):
    """bin/colab-lease prints one JSON result; tolerate any log lines
    around it by falling back to the last decodable JSON object."""
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for idx in range(len(text) - 1, -1, -1):
        if text[idx] == "{":
            try:
                obj, _ = decoder.raw_decode(text[idx:])
                return obj
            except json.JSONDecodeError:
                continue
    return None


def run_core(*args: str,
             timeout: float = CORE_TIMEOUT_S
             ) -> tuple[int, dict | None, str]:
    """Run the lease CLI; return (returncode, parsed_json, stderr_tail).

    The timeout defaults to the action bound
    (CORE_TIMEOUT_S); the state/read path passes
    STATE_COMPUTE_TIMEOUT_S instead."""
    try:
        proc = subprocess.run(
            [lease_bin(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            # The panel's actor identity for the core's session
            # shape gate: claimed in the child env on every call
            # (unconditionally — a stale inherited value must never
            # speak for the panel), paired with the --via panel tag
            # on the action calls. The core's bypass requires both.
            env={**os.environ, "VENUE_LEASE_ACTOR": "panel"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, None, f"{type(exc).__name__}: {exc}"
    return proc.returncode, parse_core_json(proc.stdout), (proc.stderr or "").strip()[-500:]


class Outbox:
    """Append-only event log with a stored-shape read path.

    The file is the durable record; this class also keeps
    the parsed events as the shape reads serve (the venue
    state parts' discipline: serve the stored shape, never
    recompute it per request — a read used to re-read and
    re-parse the whole file on every poll, 200 ms at N=1
    growing to ~2 s at N=8 on the profiled payload).

    The shape is kept current by the write paths. append()
    — this server's own writes, panel mutations and the
    drained reaper spool alike — first refreshes the shape
    from the file if it changed, then extends it with the
    event it just wrote, re-parsed from the written line
    so the stored dicts are exactly what a file read
    yields. The
    runner core's run-terminal appends write the file
    directly and cannot touch this memory, so after()
    stats the file first (one stat, never a payload
    recompute): any change since the shape was built —
    an external append, a replacement, a shrink —
    rebuilds the shape from the file before serving.
    The recorded signature is the stat taken BEFORE the
    build's read, so a write landing mid-build leaves the
    signature older than the file and the next read
    rebuilds again: a read never serves a shape older
    than the file state its signature check saw.

    The shape also persists across this process's
    restarts (shape_store): at every point
    the shape is (re)built — construction, a signature
    rebuild, an append — it is stored under the
    signature it was built from, and construction primes
    from the store when the stored signature still
    equals the file's, skipping the parse. The file
    remains the durable record; the stored shape is its
    materialised copy, and any doubt (no store, a moved
    signature, an undecodable payload) falls back to
    the parse, which is the pre-persistence behaviour."""

    def __init__(self, path: Path, store=None):
        self.path = path
        self._shape_store = store
        self.lock = threading.Lock()
        self.seq = 0
        self._signature = self._stat_signature()
        primed = self._prime_shape()
        self._events = primed if primed is not None \
            else self._read_all()
        for event in self._events:
            self.seq = max(self.seq, int(event.get("seq", 0)))
        if primed is None:
            self._persist_shape()

    def _prime_shape(self):
        """The persisted shape (shape_store), served in
        place of the construction parse when the store
        holds one under the file's CURRENT signature:
        the signature is the freshness proof, so a match
        means the persisted events are exactly what a
        parse of the file would yield. Any other state —
        no store, no row, a signature the file has moved
        past, a payload that does not decode — returns
        None and construction takes the parse path, which
        is today's behaviour."""
        if self._shape_store is None \
                or self._signature is None:
            return None
        try:
            held = self._shape_store.load_outbox()
        except Exception:
            return None
        if held is None or held[0] != self._signature:
            return None
        try:
            events = json.loads(held[1])
        except ValueError:
            return None
        if not isinstance(events, list):
            return None
        return events

    def _persist_shape(self) -> None:
        """Persist the current shape under the signature
        it was built from (the shape store's materialised
        copy, so the next process primes instead of
        re-parsing). Only a shape with a signature is
        persisted: a None signature means the shape's
        provenance is uncertain and the next read must
        rebuild — a persisted copy of it would prime a
        shape the file may not hold. The store contains
        its own failures; a failed persist costs only
        the next boot's parse."""
        if self._shape_store is None \
                or self._signature is None:
            return
        try:
            payload = json.dumps(self._events)
        except (TypeError, ValueError):
            return
        try:
            self._shape_store.save_outbox(
                self._signature, payload, self.seq)
        except Exception:
            pass

    def _stat_signature(self) -> tuple[int, int] | None:
        """The file's identity for freshness purposes:
        (size, mtime_ns), or None when it cannot be
        stat'ed (absent, like _read_all's empty read)."""
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_size, st.st_mtime_ns)

    def _read_all(self) -> list[dict]:
        events = []
        try:
            lines = self.path.read_text().splitlines()
        except OSError:
            return events
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _refresh_locked(self) -> None:
        """Rebuild the stored shape when the file changed
        since it was built. The caller holds the lock."""
        signature = self._stat_signature()
        if signature == self._signature:
            return
        self._events = self._read_all()
        self._signature = signature
        self._persist_shape()

    def append(self, kind: str, detail: dict) -> dict:
        with self.lock:
            # Bring the shape current with the file first:
            # the growth check below is sound only against
            # a shape the pre-write signature describes —
            # an external append that landed since the last
            # read must be in the shape before this write
            # extends it, or the write would adopt a
            # signature for a shape missing that event.
            self._refresh_locked()
            self.seq += 1
            event = {
                "seq": self.seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "detail": detail,
            }
            line = json.dumps(event) + "\n"
            before = self._stat_signature()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(line)
            self._events.append(json.loads(line))
            # Adopt the post-write signature only when the
            # file grew by exactly this line: any other
            # delta means another writer raced this append,
            # and the next read must rebuild rather than
            # trust the shape.
            after = self._stat_signature()
            grown = None if before is None else \
                before[0] + len(line.encode())
            self._signature = after if after is not None \
                and after[0] == grown else None
            self._persist_shape()
            return event

    def after(self, seq: int) -> tuple[list[dict], int]:
        with self.lock:
            self._refresh_locked()
            events = [e for e in self._events
                      if int(e.get("seq", 0)) > seq]
            last = max([seq] + [int(e.get("seq", 0)) for e in events])
            return events, last


OUTBOX: Outbox | None = None

SHAPE_STORE = None

STACKDUMP: StackDumpWatchdog | None = None

STATE_READS: state_reads.StateReads | None = None


def stackdump_health() -> bool:
    """The watchdog's health probe (state_surface.py);
    run_core resolves here at call time, so the probe is
    this module's own state path — and the test suites'
    patched run_core is the one it calls."""
    return state_surface.stackdump_health(run_core)


def load_stackdump_config() -> dict:
    """The watchdog's knobs (state_surface.py), read from
    this module's CONFIG_PATH at call time."""
    return state_surface.load_stackdump_config(CONFIG_PATH)


def stackdump_last_at():
    return STACKDUMP.last_dump_at if STACKDUMP is not None else None


def reaper_events_path() -> Path:
    return var_dir() / "reaper-events.jsonl"


def reaper_drain_path() -> Path:
    return var_dir() / "reaper-events.drained"


DRAIN_LOCK = threading.Lock()


def drain_reaper_events() -> None:
    """Fold core-spooled events (var/reaper-events.jsonl — written by
    reap(), e.g. lease-renewed, which happens outside this server)
    into the outbox, keeping this server the outbox's only writer.
    The marker is a byte offset and only complete lines are consumed,
    so a writer mid-append is never half-read. Runs before state and
    outbox reads so a renewal shows in the first poll that could
    carry it."""
    if OUTBOX is None:
        return
    with DRAIN_LOCK:
        try:
            data = reaper_events_path().read_bytes()
        except OSError:
            return
        try:
            offset = int(reaper_drain_path().read_text().strip())
        except (OSError, ValueError):
            offset = 0
        if offset > len(data):
            offset = 0  # spool replaced/rotated; start over
        chunk = data[offset:]
        last_nl = chunk.rfind(b"\n")
        if last_nl < 0:
            return
        complete = chunk[: last_nl + 1]
        for raw in complete.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or not event.get("kind"):
                continue
            detail = {k: v for k, v in event.items() if k != "kind"}
            OUTBOX.append(event["kind"], detail)
        try:
            writer.staged_write(str(reaper_drain_path()), str(offset + len(complete)).encode())
        except Exception:  # noqa: BLE001 - the old offset stands, so the next drain replays these lines
            pass


def load_ui_config() -> tuple[str, int]:
    host, port = "127.0.0.1", 8793
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        host = cfg.get("host", host)
        port = int(cfg.get("port", port))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    host = os.environ.get("VENUE_LEASE_UI_HOST", os.environ.get("COLAB_LEASE_UI_HOST", host))  # step6-retire: COLAB_ dual-read fallback
    raw_port = os.environ.get("VENUE_LEASE_UI_PORT", os.environ.get("COLAB_LEASE_UI_PORT"))  # step6-retire: COLAB_ dual-read fallback
    if raw_port:
        port = int(raw_port)
    return host, port


def repo_config() -> dict:
    """Budget caps from the repo config, served alongside the core
    state so the page never hardcodes them. (The shape catalog itself
    comes from the core's state, not from a config file.)"""
    caps: dict = {}
    try:
        lease_cfg = json.loads((REPO / "config" / "lease.json").read_text())
        # Caps are tied per (venue, account) in the budgets block
        # (the core's accounts.caps_for is the source of truth);
        # the served keys keep their names, the values are the
        # home venue's primary account's resolved caps.
        budgets = lease_cfg.get("budgets")
        per_venue = budgets.get("colab") if isinstance(budgets, dict) else None
        primary = per_venue.get("primary") if isinstance(per_venue, dict) else None
        if not isinstance(primary, dict):
            primary = {}
        caps = {"daily_cu_budget": primary.get("daily"), "monthly_cu_budget": primary.get("monthly"),
                "max_hours": lease_cfg.get("max_hours"), "rate_cu_per_hour": lease_cfg.get("rate_cu_per_hour")}
    except (OSError, json.JSONDecodeError):
        pass
    return caps


def _ensure_runtime() -> None:
    """The outbox, the watchdog, and the state-read cache
    exist before the first route answers — the standalone
    main's order, kept for every entry."""
    global OUTBOX, STACKDUMP, STATE_READS, SHAPE_STORE
    if SHAPE_STORE is None:
        # One shape store for both persisted shapes (the
        # outbox's stored shape, the state cache's builds):
        # the panel's assembled state survives this
        # process's restarts in the venue var dir.
        SHAPE_STORE = state_surface.shape_store.ShapeStore(
            var_dir() / "panel-shapes.db")
    if OUTBOX is None:
        OUTBOX = Outbox(outbox_path(), store=SHAPE_STORE)
    if STATE_READS is None:
        STATE_READS = state_surface.build_state_reads(
            lambda args: run_core(
                *args, timeout=STATE_COMPUTE_TIMEOUT_S),
            store=SHAPE_STORE)
    if STACKDUMP is None and \
            os.environ.get("VENUE_LEASE_UI_STACKDUMP", os.environ.get("COLAB_LEASE_UI_STACKDUMP", "1")) != "0":  # step6-retire: COLAB_ dual-read fallback
        STACKDUMP = StackDumpWatchdog(
            "colab-lease-panel",
            stackdump_health,
            var_dir() / "stackdumps.log",
            **load_stackdump_config(),
        )
        STACKDUMP.start()


def build_mount():
    """This surface's mount on the serving core; returns
    (mount, host, port)."""
    _ensure_runtime()
    r = serving.Router()
    mount = serving.Mount(
        "venue", r, dumps=lambda payload: json.dumps(payload),
        unquote_path=False,
        not_found=lambda request: serving.Reply.json(
            404, {"error": "not found"}, mount.dumps))

    # The route surface lives in route_surface.py;
    # its dependencies resolve
    # at call time through this env, so the suites'
    # monkeypatched run_core — and a reset OUTBOX /
    # STATE_READS global — is what a request calls.
    env = types.SimpleNamespace(
        run_core=lambda *a, **k: run_core(*a, **k),
        outbox=lambda: OUTBOX,
        state_reads=lambda: STATE_READS,
        drain_reaper_events=drain_reaper_events,
        repo_config=repo_config,
        stackdump_last_at=stackdump_last_at,
        ui_sh=ui_sh,
        static_dir=STATIC_DIR,
        serving=serving,
    )
    route_surface.register_routes(r, env)
    host, port = load_ui_config()
    return mount, host, port


# The declared surface, parsed by the unified argv
# module (pipeline/platform/argv.py): both value forms
# are one flag, unknown flags and surplus positionals
# refuse at exit 2, and help is generated from this
# declaration.
UI_DECL = {
    "name": "venue-ui",
    "flags": {
        "host": {"takes_value": True},
        "port": {"takes_value": True},
    },
}


def main(argv: list[str]) -> int:
    host, port = load_ui_config()
    outcome = uargv.parse_only(UI_DECL, argv)
    if not outcome["ok"]:
        print(outcome["error"], file=sys.stderr)
        print(outcome["usage"], file=sys.stderr)
        return uargv.USAGE_EXIT
    if "help" in outcome:
        print(outcome["help"], end="")
        return 0
    flags = outcome["result"]["flags"]
    if flags["host"] is not None:
        host = flags["host"]
    if flags["port"] is not None:
        try:
            port = int(flags["port"])
        except ValueError:
            print("venue-ui: flag --port needs an integer",
                  file=sys.stderr)
            print(uargv.help_text(UI_DECL), file=sys.stderr)
            return uargv.USAGE_EXIT
    mount, _host, _port = build_mount()
    listener = bounded_server.build_bounded_listener(
        serving, mount, host, port)
    print(f"lease-ui listening on http://{host}:{listener.server_address[1]}", flush=True)
    return serving.serve([listener])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
