#!/usr/bin/env python3
"""run.py — the mega app's ONE entry point (owner ruling:
the proven shape). Every pipeline CLI links
here in-process as a subcommand, and the serving commands
mount the backends on the platform serving core
(pipeline/platform/serving.py) — the serving
implementation remains exactly one. The processes follow
coupling (owner ruling, refining the entry-point ruling):
`serve` mounts the two surfaces that stayed coupled —
scheduling (8796) and attention (8797) — in one process;
`serve-workbench` mounts the workbench (8792) in its own
process, because its feeds assembly saturation must not
be able to starve the coupled surfaces' health; and
`serve-venue` mounts the lease panel (8793) in its own
process, because its state reads shell out synchronously
to the lease core and it faces the heaviest polling of
the surfaces, so its saturation must not starve the
coupled pair either. Each surface keeps its own port,
because the published apps expect their own origins;
each process carries its own unit and its own health
verdict, and no probe or shim joins them.

Subcommands (the link map):

  sched <verb> ...    the scheduler registry tool
                      (pipeline/scheduling/bin/sched)
  harness <verb> ...  the harness connector client
                      (pipeline/scheduling/bin/harness)
  wb <verb> ...       the workbench harness CLI
                      (pipeline/workrecord/wb)
  attn <verb> ...     the attention connector CLI
                      (pipeline/attention/cli.py) — posts
                      and reads over the attention
                      surface (ATTN_URL, default
                      http://127.0.0.1:8797)
  colab-lease ...     the venue lease CLI, plus the other
  colab-run ...       venue bins under their own names:
  ...                 the Python bins (colab-bridge,
                      colab-check, colab-extend-guard,
                      colab-harness-bootstrap,
                      colab-harness-relay, colab-liveness,
                      colab-sh, colab-venue-migrate,
                      colab-xfer) link in-process; the
                      four bash bins (colab-down, colab-fs,
                      colab-status, colab-up) are shell
                      programs — run.py dispatches them as
                      child processes under the same
                      surface, the one honest mechanism a
                      shell entry admits.
  serve [--config P]  the coupled serving process (below)
  serve-workbench     the workbench's own serving
                      process (below)
  serve-venue         the lease panel's own serving
                      process (below)

Serve mode's supervision: the scheduling engine's tick
runs as a supervised worker thread beside the listeners
(platform.serving.serve). A route fault is contained in
its request and can never reach the tick; a tick fault
surfaces — the listeners shut down and the process exits
non-zero, so the unit's Restart brings it back loudly
rather than leaving a serving process with a dead engine.
The attention tick/capacity loops ride as supervised
workers in the coupled process on the same terms, and
the workbench message-maintenance loops ride as
supervised workers in the workbench process on the same
terms (their per-pass containment is their own packages'
discipline, unchanged). The lease panel carries no
supervised workers: its stackdump watchdog rides inside
its own process on its module's terms, as it always has.

The attention surface binds its state store EXPLICITLY:
serve refuses to start unless ATTENTION_DATA names the
migrated store file (and the file exists). There is no
default and no seeded-sample fallback in this process —
a missing binding is a startup refusal, never fiction
served as state.
"""

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

# Process start, for the serve boot record's startup
# latency (server/bootrecord.py): this module is the
# serve process's entry, so its load is the closest
# in-process stamp to the process's own start.
_PROCESS_MONOTONIC = time.monotonic()

REPO_ROOT = Path(__file__).resolve().parent
PIPELINE = REPO_ROOT / "pipeline"
for _root in (str(REPO_ROOT), str(PIPELINE)):
    if _root not in sys.path:
        sys.path.insert(0, _root)


def _load(name, path):
    """Load one file as a module under a private name,
    registered in sys.modules before it executes (its own
    sibling imports resolve against the registration),
    whatever its own bootstrap does with sys.path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:  # an extensionless entry point (sched, wb)
        from importlib.machinery import SourceFileLoader
        spec = importlib.util.spec_from_file_location(
            name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _serving_core():
    """The platform serving core, loaded by location —
    the tree's established pattern for platform modules
    (the stdlib owns the bare name `platform`)."""
    return _load("platform_serving",
                 PIPELINE / "platform" / "serving.py")


def _exit_code(exc):
    code = exc.code
    return code if isinstance(code, int) else (0 if code is None else 1)


# ----------------------------------------------------------------
# CLI links
# ----------------------------------------------------------------

def cmd_sched(argv):
    module = _load("runpy_sched", PIPELINE / "scheduling" / "bin" / "sched")
    return module.main(["sched"] + argv)


def cmd_harness(argv):
    module = _load("runpy_harness",
                   PIPELINE / "scheduling" / "bin" / "harness")
    return module.main(["harness"] + argv)


def cmd_wb(argv):
    module = _load("runpy_wb", PIPELINE / "workrecord" / "wb")
    return module.main(argv)


def cmd_attn(argv):
    from attention import cli
    return cli.main(argv)


_VENUE_BIN = PIPELINE / "venue" / "bin"
_VENUE_PYTHON_BINS = {
    "colab-bridge", "colab-check", "colab-extend-guard",
    "colab-harness-bootstrap", "colab-harness-relay",
    "colab-lease", "colab-liveness", "colab-run", "colab-sh",
    "colab-venue-migrate", "colab-xfer",
}
_VENUE_BASH_BINS = {"colab-down", "colab-fs", "colab-status",
                    "colab-up"}
_VENUE_ALIASES = {"lease": "colab-lease", "run": "colab-run",
                  "sh": "colab-sh", "fs": "colab-fs",
                  "status": "colab-status", "up": "colab-up",
                  "down": "colab-down", "liveness": "colab-liveness",
                  "check": "colab-check", "xfer": "colab-xfer"}


def cmd_venue(name, argv):
    import runpy
    path = _VENUE_BIN / name
    if name in _VENUE_BASH_BINS:
        proc = subprocess.run([str(path)] + argv)
        return proc.returncode
    old_argv = sys.argv
    sys.argv = [str(path)] + argv
    try:
        runpy.run_path(str(path), run_name="__main__")
        return 0
    except SystemExit as exc:
        return _exit_code(exc)
    finally:
        sys.argv = old_argv


# ----------------------------------------------------------------
# Serve — three processes by coupling: the coupled pair
# (scheduling, attention) in `serve`, the workbench alone
# in `serve-workbench`, the lease panel alone in
# `serve-venue`
# ----------------------------------------------------------------

def _load_workrecord_server():
    """The work-record server package under a private
    alias: the top-level name `server` belongs to the
    scheduling server in the coupled process (its catalog
    module imports it absolutely), and the work-record
    package's own modules import relatively plus `lib` —
    the alias load runs its __init__ path seams exactly
    as its own process would. One loading mechanism for
    both serve forms."""
    root = PIPELINE / "workrecord"
    spec = importlib.util.spec_from_file_location(
        "workrecord_server", root / "server" / "__init__.py",
        submodule_search_locations=[str(root / "server")])
    module = importlib.util.module_from_spec(spec)
    sys.modules["workrecord_server"] = module
    spec.loader.exec_module(module)
    return module


def _load_venue_ui():
    """The venue panel module by location, its stackdump
    sibling pre-loaded under its own name (the module's
    one absolute sibling import)."""
    ui = PIPELINE / "venue" / "ui"
    _load("stackdump", ui / "stackdump.py")
    return _load("venue_ui_server", ui / "server.py")


def _open_boot_record(values):
    """Open this serve's durable boot record
    (server/bootrecord.py). Observability must never
    down the serve it observes: any failure prints and
    returns None, and the serve proceeds unrecorded."""
    try:
        from server import bootrecord
        return bootrecord.open_boot(
            bootrecord.record_path(values["home"]),
            entry="run.py serve", repo_root=str(REPO_ROOT))
    except Exception as exc:  # noqa: BLE001 — see docstring
        print(f"run.py serve: boot record not opened: {exc!r}",
              file=sys.stderr)
        return None


def _stamp_boot_ready(values, boot):
    """Stamp the boot record health-ready: the listeners
    are bound (a Listener's socket binds at construction,
    in _assemble) and the serve loop is about to start."""
    if boot is None:
        return
    try:
        from server import bootrecord
        bootrecord.stamp_ready(
            bootrecord.record_path(values["home"]),
            boot["instance"],
            started_monotonic=_PROCESS_MONOTONIC)
    except Exception as exc:  # noqa: BLE001 — see _open_boot_record
        print(f"run.py serve: boot record ready stamp "
              f"failed: {exc!r}", file=sys.stderr)


def cmd_serve(argv):
    serving = _serving_core()

    config_path = None
    if "--config" in argv:
        config_path = argv[argv.index("--config") + 1]

    # -- scheduling engine + config (the tick's home) ----
    sys.path.insert(0, str(PIPELINE / "scheduling"))
    import server.config as sched_config
    from server.firing.engine import Engine, LockError
    if config_path is None:
        config_path = sched_config.default_config_path()
    try:
        sched_config.require_live_config(config_path)
        values, sources = sched_config.resolve(config_path)
    except sched_config.ConfigError as exc:
        print(f"run.py serve: {exc}", file=sys.stderr)
        return 2

    # -- attention binding: explicit or refusal ----------
    from attention import server as attention_server
    from attention import settings as attention_settings
    att_settings = attention_settings.Settings.from_env()
    if att_settings.data_path is None:
        print("run.py serve: ATTENTION_DATA is not set — the "
              "attention surface binds its migrated store "
              "explicitly or not at all", file=sys.stderr)
        return 2
    if not att_settings.data_path.is_file():
        print(f"run.py serve: ATTENTION_DATA names no file: "
              f"{att_settings.data_path}", file=sys.stderr)
        return 2
    att_store = attention_server.make_store(att_settings)

    engine = Engine(values)
    try:
        engine.acquire_lock()
    except LockError as exc:
        print(f"run.py serve: {exc}", file=sys.stderr)
        return 2
    engine.start_stackdump()
    boot = _open_boot_record(values)
    try:
        listeners, workers = _assemble(
            serving, engine, values, sources,
            att_settings, att_store)
        print(f"run.py serve: scheduling "
              f"{values['host']}:{values['port']}, "
              f"attention {att_settings.host}:"
              f"{att_settings.port} — one process "
              f"(the coupled surfaces)", flush=True)
        _stamp_boot_ready(values, boot)
        return serving.serve(listeners, workers=workers,
                             log=lambda line: print(line,
                                                    flush=True))
    finally:
        engine.wait_idle(timeout=10)
        engine.release_lock()


def cmd_serve_workbench(argv):
    """The workbench's own serving process (owner ruling:
    process boundaries follow coupling). Its
    feeds assembly saturation must not be able to starve
    the coupled surfaces' health, so this surface serves
    alone, under its own unit and its own health verdict:
    the work-record server's own standalone entry — the
    same mount its package's run.py runs — with the
    pinned startup discipline intact (the mount primes
    the feeds document cache and starts its warm-up on
    its own thread inside build_mount; the bind follows
    on this thread, so warm-up can never park it). Its
    config is its own seam (WB_VIEWER_* env > its
    config.json > defaults); no scheduler config, no
    engine lock, and no attention binding is consulted
    here, and nothing in this process loads the coupled
    surfaces' mounts."""
    if argv:
        print("run.py serve-workbench: takes no arguments "
              "(the surface's config is its own WB_VIEWER_* "
              "seam)", file=sys.stderr)
        return 2
    _load_workrecord_server()
    from workrecord_server import serving as wr_serving
    return wr_serving.main()


def cmd_serve_venue(argv):
    """The lease panel's own serving process (owner
    ruling: process boundaries follow coupling,
    extended to the venue). Its state reads
    shell out synchronously to the lease core — a hung
    call pins its request thread — and the panel faces
    the heaviest polling of the surfaces, so this surface
    serves alone, under its own unit and its own health
    verdict: the venue UI server's own standalone entry —
    the same main its module's __main__ runs — with its
    hardened serving intact (state reads
    stale-while-recompute under a read-scoped timeout,
    handler threads bounded; both are the panel module's
    own seams). Its config is its own seam (ui/config.json
    plus COLAB_LEASE_UI_* env); no scheduler config, no
    engine lock, and no attention binding is consulted
    here, and nothing in this process loads the coupled
    surfaces' mounts."""
    if argv:
        print("run.py serve-venue: takes no arguments "
              "(the surface's config is its own "
              "COLAB_LEASE_UI_* seam)", file=sys.stderr)
        return 2
    venue_ui = _load_venue_ui()
    return venue_ui.main([])


def _assemble(serving, engine, values, sources,
              att_settings, att_store):
    import server.serving.http as sched_http
    listeners = []
    workers = {}

    sched_mount = sched_http.build_mount(engine, values, sources)
    listeners.append(serving.Listener(
        sched_mount, values["host"], values["port"]))

    from attention import server as att_serve
    att_mount, att_workers = att_serve.build_mount(
        att_settings, att_store)
    listeners.append(serving.Listener(
        att_mount, att_settings.host, att_settings.port))
    workers.update(att_workers)

    def tick(stop):
        while not stop.is_set():
            engine.tick()
            stop.wait(values["tick_secs"])

    workers["scheduler-tick"] = tick
    return listeners, workers


# ----------------------------------------------------------------

COMMANDS = {
    "sched": cmd_sched,
    "harness": cmd_harness,
    "wb": cmd_wb,
    "attn": cmd_attn,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 2
    name, rest = argv[0], argv[1:]
    if name == "serve":
        return cmd_serve(rest)
    if name == "serve-workbench":
        return cmd_serve_workbench(rest)
    if name == "serve-venue":
        return cmd_serve_venue(rest)
    if name in COMMANDS:
        return COMMANDS[name](rest)
    venue_name = _VENUE_ALIASES.get(name, name)
    if venue_name in _VENUE_PYTHON_BINS | _VENUE_BASH_BINS:
        return cmd_venue(venue_name, rest)
    print(f"run.py: unknown command: {name}", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
