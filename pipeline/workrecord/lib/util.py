"""Shared low-level helpers for the workbench harness core.

Stdlib only. Everything here is pure or filesystem-leaf work;
no module in lib/ imports another lib module *through* this one
beyond these helpers.
"""

import hashlib
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from . import paths as _paths


def now_iso(timespec=None) -> str:
    """Current UTC time as an ISO-8601 string (the one format
    every timestamp in the system uses). `timespec` narrows
    the precision (the evaluation doctor's state stamps are
    seconds-precision); the default is the full form every
    existing caller renders."""
    now = datetime.now(timezone.utc)
    if timespec is None:
        return now.isoformat()
    return now.isoformat(timespec=timespec)


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def parse_instant(ts):
    """An ISO stamp → aware datetime, else None: the
    tolerant parse for served stamps — a trailing Z is
    accepted, a naive stamp reads as UTC (the stores'
    stamps are UTC), and a missing or malformed value is
    an honest None, never a guess."""
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(
            str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_day(value):
    """A YYYY-MM-DD value → date, else None (missing or
    malformed dates are honest unknowns, never guesses)."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


SCRATCH_DIR_MARKERS = frozenset(
    {"tmp", "temp", "scratch", "tmp-gate"})


def platform_temp_roots() -> set:
    """The platform's temp roots, resolved: the system
    temp (tempfile's answer), $TMPDIR when it names
    another, and the conventional defaults. Python caches
    its tempdir after the first call, so the answer is
    never trusted alone: the candidates derive from the
    CURRENT environment on every call. WB_TMP_ROOT is
    deliberately NOT consulted here — a per-run scratch
    dir leaked into it must not mint a fake root (the
    answer would then change with whatever last wrote
    the variable)."""
    roots = set()
    for candidate in (os.environ.get("TMPDIR"),
                      tempfile.gettempdir(),
                      "/tmp", "/var/tmp", "/usr/tmp"):
        if candidate:
            roots.add(Path(candidate).resolve())
    return roots


def temp_roots() -> set:
    """The platform temp roots plus every root the
    WB_TMP_ROOT seam lists (this box's discipline points
    TMPDIR at disk-backed scratch under the workspace
    itself, which no anchor or system-temp check can
    recognize — the seam names it). A seam entry that
    itself sits under a platform temp root is skipped:
    it is a run's own scratch dir, not a root."""
    roots = platform_temp_roots()
    for item in os.environ.get(
            "WB_TMP_ROOT", "").split(os.pathsep):
        if not item:
            continue
        path = Path(item).resolve()
        if any(path == root or root in path.parents
               for root in roots):
            continue
        roots.add(path)
    return roots


def under_temp_root(path) -> bool:
    """True when the resolved path sits under a temp
    root (see temp_roots) — scratch state (test fixtures,
    gate scratch), not the live workspace's own."""
    resolved = Path(path).resolve()
    return any(resolved == root
               or root in resolved.parents
               for root in temp_roots())


def scratch_marked(path) -> bool:
    """True when any component of the path names
    scratch: a dot-directory (hidden trees are scratch,
    snapshots, or tool state — never a live checkout's
    home), or a component carrying a scratch marker
    (an exact marker name, or one containing `tmp` /
    `scratch`). The caller passes the path RELATIVE to
    the sweep root it is judging under — components
    above that root (the machine's own directories)
    never convict a subtree."""
    for part in Path(path).parts:
        if part in (".", ".."):
            continue
        if part.startswith(".") and len(part) > 1:
            return True
        low = part.lower()
        if low in SCRATCH_DIR_MARKERS or "tmp" in low \
                or "scratch" in low:
            return True
    return False


_WRITER = None
_WRITER_TRIED = False


def _load_writer():
    """The pipeline's unified state writer (contract 15),
    loaded by path from the paths spine's PLATFORM_WRITER
    value — the ops service's standing pattern for
    cross-pipeline loads. None when the harness runs
    standalone, outside the mega repo (external adopters
    keep building with the pipeline absent; the
    sibling-seam rule)."""
    global _WRITER, _WRITER_TRIED
    if _WRITER_TRIED:
        return _WRITER
    _WRITER_TRIED = True
    try:
        import importlib.util
        writer_path = _paths.PLATFORM_WRITER
        spec = importlib.util.spec_from_file_location(
            "pipeline_platform_writer", writer_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _WRITER = module
    except Exception:
        _WRITER = None
    return _WRITER


def staged_write_bytes(path, data: bytes) -> None:
    """Write bytes through the unified writer's protocol
    (stage to a fresh sibling, fsync, read-back compare,
    rename over — contract 15), so no caller ever opens a
    target for truncate-write. Standalone (no pipeline),
    the same staging is performed locally: the protocol,
    not the module, is the invariant."""
    writer = _load_writer()
    if writer is not None:
        writer.staged_write(str(path), data)
        return
    directory = Path(path).parent
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / (Path(path).name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    # Same mode carry as the unified writer: an existing
    # target's mode moves onto the staged file, or the
    # rename-over resets it to the umask default.
    if os.path.exists(path):
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
    os.replace(tmp, path)


def write_text(path, text, *, encoding="utf-8") -> None:
    """The one write seam for the whole harness: every
    text write in lib/ rides this function, and the write
    strategy changes in exactly this one place. Since the
    S4 consolidation the strategy is the unified writer's
    staged protocol (contract 15) — the stage-verify-
    rename discipline replaces the former builtin-open
    write, whose truncate-first form is what the write-
    denial flap destroys files with. Path.write_text
    remains unused anywhere in lib/."""
    staged_write_bytes(path, text.encode(encoding))


def fan_out(fn, items, *, workers=1) -> list:
    """Map `fn` over `items`, on a bounded thread pool when
    `workers > 1`. Results come back in input order
    regardless of completion order; `workers <= 1` (or a
    single item) is a plain sequential map. An exception
    from `fn` propagates exactly as the sequential map
    would raise it — per-item containment stays with the
    caller, whose derivations already contain per item.

    The pool exists for subprocess- and IO-bound fan-outs
    (the per-repo and per-project git derivations), where
    the wait releases the GIL; it buys nothing for
    pure-Python CPU work such as parsing, which stays
    sequential by design."""
    items = list(items)
    if workers <= 1 or len(items) <= 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def canonical_json(obj) -> str:
    """Deterministic JSON: sorted keys, no float noise. The
    dagstore manifest habit — the same fold everywhere
    (exports, state snapshots, hashes over state)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def state_sha256(state) -> str:
    """Fingerprint of an entry's internal state (approval
    binding is over exactly this)."""
    return sha256_bytes(canonical_json(state or {}).encode("utf-8"))
