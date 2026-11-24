"""The panel's state-read surface: the bounds, the
state-read cache's construction, and the stackdump
watchdog's health probe and config — extracted from
server.py along the state_reads seam as
that file approached its size cap. server.py keeps the
route surface and the runtime singletons; this module
owns how a state read is bounded, built, and watched.

The two bounds, kept apart (the wedge cure):
a cold reader waits at most STATE_READ_TIMEOUT_S for a
build to land, while the build itself runs under
STATE_COMPUTE_TIMEOUT_S — a build slower than the
reader's wait must still land and warm the cache, or a
slow core wedges every read at the bound forever. Lease
actions keep the action bound (server.py's
CORE_TIMEOUT_S) — an acquire may legitimately take that
long. A cached build older than STATE_REFRESH_AFTER_S
kicks a background refresh on its next read (the
discipline itself is state_reads.py's).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

STATE_READ_TIMEOUT_S = 30
STATE_COMPUTE_TIMEOUT_S = 300
STATE_REFRESH_AFTER_S = 5.0


def _load_state_reads():
    """The sibling seam, loaded by location under the
    same registered name server.py uses, so every entry
    form shares one module object."""
    name = "venue_state_reads"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / "state_reads.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


state_reads = _load_state_reads()


def _load_shape_store():
    """The shape store seam, loaded by location under
    the same registered name server.py's loads use, so
    every entry form shares one module object."""
    name = "venue_shape_store"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / "shape_store.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


shape_store = _load_shape_store()


class StateShapePersister:
    """The state-read cache's persister over one
    ShapeStore: the encoding seam between the cache's
    (key, rc, result, err) builds and the store's opaque
    text. Keys are the core call's argument tuples,
    carried as their JSON list form; payloads are the
    build's own fields as JSON, so a primed build's
    served bytes are the stored build's bytes. A record
    that does not decode to a dict result is skipped —
    the cache stores only dict builds, so anything else
    in the store is not a build this cache landed."""

    def __init__(self, store):
        self._store = store

    def load_all(self) -> dict:
        out = {}
        for key_text, payload_text in \
                self._store.load_all_states().items():
            try:
                key = tuple(json.loads(key_text))
                record = json.loads(payload_text)
                result = record["result"]
                entry = (record["rc"], result,
                         record["err"])
            except Exception:
                continue
            if isinstance(result, dict):
                out[key] = entry
        return out

    def save(self, key, rc, result, err) -> None:
        try:
            payload_text = json.dumps(
                {"rc": rc, "result": result, "err": err})
            key_text = json.dumps(list(key))
        except (TypeError, ValueError):
            return
        self._store.save_state(key_text, payload_text)


def build_state_reads(compute, store=None):
    """The state-read cache over one compute callable
    (the panel's run_core bound to the compute timeout):
    warm reads serve stale-while-recompute; a cold read
    waits at most the read bound while its build runs on
    to land under the compute bound. With a shape store,
    the cache also persists its builds across restarts
    (StateShapePersister) — primed at construction,
    saved at every landing."""
    return state_reads.StateReads(
        compute,
        refresh_after_s=STATE_REFRESH_AFTER_S,
        cold_wait_s=STATE_READ_TIMEOUT_S,
        persister=StateShapePersister(store)
        if store is not None else None)


def stackdump_health(run_core) -> bool:
    """The watchdog's internal check (stackdump-contract:
    v1): the state computation the panel's own reads
    serve — run_core's state path, called directly,
    never an HTTP self-call. Answers (a parsed state
    document) is healthy; anything else is a
    non-completion the lag clock accrues against. The
    probe keeps the READ bound — it measures
    responsiveness, not completion."""
    _rc, result, _err = run_core(
        "state", timeout=STATE_READ_TIMEOUT_S)
    return isinstance(result, dict)


def load_stackdump_config(config_path) -> dict:
    """Watchdog knobs from the panel's config file,
    contract defaults as the shipped values
    (stackdump-contract: v1, clause 2)."""
    knobs = {"cadence_s": 5.0, "threshold_s": 15.0, "repeat_s": 60.0, "max_bytes": 16 * 1024 * 1024}
    try:
        cfg = json.loads(Path(config_path).read_text())
    except (OSError, json.JSONDecodeError):
        return knobs
    for key, field, cast in (
        ("stackdump_cadence_s", "cadence_s", float),
        ("stackdump_threshold_s", "threshold_s", float),
        ("stackdump_repeat_s", "repeat_s", float),
        ("stackdump_max_bytes", "max_bytes", int),
    ):
        try:
            if cfg.get(key) is not None:
                knobs[field] = cast(cfg[key])
        except (TypeError, ValueError):
            pass
    return knobs
