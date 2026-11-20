#!/usr/bin/env python3
"""colab-sh's local-state helpers: session resolution, the
lease-module seam, the liveness cache, and the transient-mirror
freshness stamp.

Extracted from bin/colab-sh (consolidation Lane B step 5) with
no behaviour change; bin/colab-sh binds these names from here,
so its module surface is unchanged. This module is deliberately
self-contained: it never imports bin/colab-sh (the dependency
runs the other way).
"""

import importlib.util as _ilu
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

REPO = _paths.REPO_RESOLVED


def _var_dir() -> Path:
    return Path(os.environ.get("COLAB_RUNNER_VAR", REPO / "var"))


def _lease_module():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from sync import lease

    return lease


def resolve_session(flag: str | None) -> str | None:
    """-s flag, then $COLAB_SH_SESSION, then the most recently
    used lease record — the core's own definition (records
    .load_record), the one every other consumer resolves by.
    The retired single-record var/lease.json is never read (E9):
    a copy resurrected by a transient restore would name a stale
    session."""
    if flag:
        return flag
    if os.environ.get("COLAB_SH_SESSION"):
        return os.environ["COLAB_SH_SESSION"]
    try:
        rec = _lease_module().load_record(REPO)
    except Exception:  # noqa: BLE001
        return None
    return rec.get("session") if rec else None


# Rapid successive attaches reuse a short-TTL liveness cache
# (E4): a burst of small ops pays one dial, not one per op. The
# cache lives in the session's liveness file (var/liveness-
# <session>.json — the checker's file; the wrapper keeps one key
# of its own in it and preserves the rest, written with the same
# staged-sibling discipline the checker uses). Only a just-dialed
# "alive" is ever cached, and only inside the TTL: a stale or
# absent entry always falls back to the dial. That bounds the
# minting window the connect guard exists to close to the TTL.
LIVENESS_CACHE_TTL_S = 60
_CACHE_KEY = "colab_sh_cache"


def _liveness_cache_read(session: str) -> bool:
    """True when the cache holds a fresh dialed-alive verdict."""
    try:
        data = json.loads((_var_dir() / f"liveness-{session}.json").read_text())
        entry = data.get(_CACHE_KEY) or {}
        if entry.get("state") != "alive":
            return False
        at = datetime.fromisoformat(entry["at"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - at).total_seconds() <= LIVENESS_CACHE_TTL_S
    except Exception:  # noqa: BLE001
        return False


def _liveness_cache_write(session: str) -> None:
    """Record a just-dialed alive verdict in the liveness file.
    Best-effort: a lost cache write costs one dial, never more.
    The write rides the lease core's writer seam (register
    E5): this file is shared with the liveness checker, and
    both writers stage through the one platform writer."""
    try:
        path = _var_dir() / f"liveness-{session}.json"
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                data = {}
        except Exception:  # noqa: BLE001
            data = {}
        data[_CACHE_KEY] = {"state": "alive", "at": datetime.now(timezone.utc).isoformat()}
        path.parent.mkdir(parents=True, exist_ok=True)
        _lease_module().foundation.staged_write(path, json.dumps(data, indent=1).encode())
    except Exception:  # noqa: BLE001
        pass


# The mirror restore is a subprocess every attach used to pay
# (E4). The wrapper keeps its own freshness stamp in var/ and
# skips the restore while the last successful one is fresh.
MIRROR_FRESH_S = 300


def _mirror_fresh() -> bool:
    try:
        at = datetime.fromisoformat((_var_dir() / "mirror-restore.stamp").read_text().strip())
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - at).total_seconds() <= MIRROR_FRESH_S
    except Exception:  # noqa: BLE001
        return False


def restore_transient() -> None:
    """Restore transient state on entry (wrapper parity),
    best-effort — skipped while the last restore is fresh."""
    if _mirror_fresh():
        return
    try:
        r = subprocess.run(
            [sys.executable, str(REPO / "ops" / "mirror_transient.py"), "restore"],
            capture_output=True, timeout=120,
        )
    except Exception:  # noqa: BLE001
        return
    if r.returncode == 0:
        try:
            path = _var_dir() / "mirror-restore.stamp"
            path.parent.mkdir(parents=True, exist_ok=True)
            _lease_module().foundation.staged_write(path, datetime.now(timezone.utc).isoformat().encode())
        except Exception:  # noqa: BLE001
            pass
