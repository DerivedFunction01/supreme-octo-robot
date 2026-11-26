#!/usr/bin/env python3
"""Per-item wake minter for the connector bridge queue —
the scheduling entry.

The minter itself is the pipeline dispatch substrate's
(`dispatch.wake`, contract 05): it reads the bridge queue,
resolves each item's target from the routing data it is
handed, and plants one wake ping per item in the outbox,
plus the bridge-drain episode escalation. This entry
keeps what is scheduling-side: deriving the queue, state,
and owners-config paths from its own location, and
parsing the owners config (the registry YAML subset is
this package's) into the resolved routing data the
minter consumes — owners (caller -> chat id) and the
drain home chat.

Output alphabet (the entry's report rule keys on it): a
quiet pass prints nothing; each mint prints one WAKE
line; each unresolvable item prints one UNRESOLVED line;
an escalation mint prints one DRAIN line.

Stdlib only; paths derived from this file's location.
"""
import os
import sys
from datetime import datetime, timezone

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

REPO = paths.REPO_ROOT
sys.path.insert(0, REPO)
sys.path.insert(0, paths.script_dir(__file__))

from server import registry  # noqa: E402
from dispatch import wake  # noqa: E402

UTC = timezone.utc

BRIDGE_DIR = os.path.join(paths.STATE_DIR, "connector-bridge")
STATE_DIR = paths.STATE_DIR
OWNERS_PATH = os.path.join(paths.BODIES_DIR, "bridge-wake-owners.yaml")
BODY_REF = wake.BODY_REF
JOB_PREFIX = wake.JOB_PREFIX
DRAIN_JOB = wake.DRAIN_JOB
DRAIN_BODY = wake.DRAIN_BODY


def load_owners(path):
    """caller -> chat id from the live owners config, in the
    registry YAML subset (block mappings only). A missing or
    malformed config resolves nobody — read-tool items go
    unresolved (a chat_send falls back to its own target
    only when no drain home is configured either)."""
    try:
        with open(path, encoding="utf-8") as fh:
            config = registry.parse_yaml(fh.read(), path)
    except (OSError, registry.EntryError):
        return {}
    owners = config.get("owners") if isinstance(config, dict) else None
    if not isinstance(owners, dict):
        return {}
    resolved = {}
    for caller, spec in owners.items():
        if isinstance(spec, dict) and isinstance(spec.get("chat"), str) \
                and spec["chat"]:
            resolved[str(caller)] = spec["chat"]
    return resolved


def load_drain_chat(path):
    """The drain home chat from the live owners config (the
    `drain` mapping's chat), or None when unconfigured. The
    escalation ping carries it as detail.target_chat — the
    same addressing the per-item wakes use — because the
    executor must be a full agent surface: worker-class
    runtimes hold only the read half of the chat namespace
    (no send function even after the namespace loads), so an
    unaddressed drain ping claimed by such a worker stalls
    every chat_send item behind a correctly-kept discipline.
    The configured home is a thread whose agent carries the
    send function (proven on the F5 proof drain)."""
    try:
        with open(path, encoding="utf-8") as fh:
            config = registry.parse_yaml(fh.read(), path)
    except (OSError, registry.EntryError):
        return None
    drain = config.get("drain") if isinstance(config, dict) else None
    if isinstance(drain, dict) and isinstance(drain.get("chat"), str) \
            and drain["chat"]:
        return drain["chat"]
    return None


def run(bridge_dir=BRIDGE_DIR, state_dir=STATE_DIR,
        owners_path=OWNERS_PATH, now=None, outbox=None):
    """One minting pass. Returns the run's output lines."""
    return wake.run(
        bridge_dir, state_dir,
        owners=load_owners(owners_path),
        drain_chat=load_drain_chat(owners_path),
        now=now, outbox=outbox)


DECL = {"name": "bridge_wake",
        "summary": "One bridge-wake minting pass. "
                   "Takes no arguments."}


def main(argv):
    _result, code = paths.parse_argv(DECL, argv)
    if _result is None:
        return code
    for line in run():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
