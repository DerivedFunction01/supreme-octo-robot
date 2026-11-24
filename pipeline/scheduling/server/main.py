"""Thin wiring: resolve config, take the single-instance lock,
build the engine, serve HTTP on the platform serving core,
tick on the main thread. Nothing else lives here."""
import sys
import time

from . import bootrecord, paths
from . import config as config_mod
from .firing.engine import Engine, LockError
from .serving.http import make_server
from dispatch.stateio import StateError


def main(argv=None):
    started_monotonic = time.monotonic()
    argv = list(sys.argv[1:] if argv is None else argv)
    config_path = config_mod.default_config_path()
    if "--config" in argv:
        config_path = argv[argv.index("--config") + 1]
    try:
        config_mod.require_live_config(config_path)
        values, sources = config_mod.resolve(config_path)
    except config_mod.ConfigError as exc:
        print(f"scheduler: {exc}", file=sys.stderr)
        return 2
    engine = Engine(values)
    try:
        engine.acquire_lock()
    except LockError as exc:
        print(f"scheduler: {exc}", file=sys.stderr)
        return 2
    engine.start_stackdump()
    # The durable boot record (bootrecord.py): opened
    # only once the lock is held, so a refused second
    # instance never records a boot; stamped ready once
    # the server is started. A record failure prints and
    # the serve proceeds unrecorded — observability must
    # never down the serve it observes.
    boot = None
    try:
        boot = bootrecord.open_boot(
            bootrecord.record_path(values["home"]),
            entry="server", repo_root=paths.REPO_ROOT)
    except Exception as exc:  # noqa: BLE001 — see above
        print(f"scheduler: boot record not opened: {exc!r}",
              file=sys.stderr)
    server = make_server(engine, values, sources)
    server.start()
    if boot is not None:
        try:
            bootrecord.stamp_ready(
                bootrecord.record_path(values["home"]),
                boot["instance"],
                started_monotonic=started_monotonic)
        except Exception as exc:  # noqa: BLE001 — see above
            print(f"scheduler: boot record ready stamp "
                  f"failed: {exc!r}", file=sys.stderr)
    print(f"scheduler: serving on {values['host']}:{values['port']} "
          f"(home {values['home']}, tick {values['tick_secs']}s)", flush=True)
    try:
        while True:
            engine.tick()
            time.sleep(values["tick_secs"])
    except KeyboardInterrupt:
        pass
    finally:
        engine.wait_idle(timeout=10)
        server.shutdown()
        server.server_close()
        engine.release_lock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
