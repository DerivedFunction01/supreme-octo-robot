import importlib.util as _ilu
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent.parent.parent / "paths.py"
)
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)


def var_dir(repo: Path) -> Path:
    return Path(os.environ.get("COLAB_RUNNER_VAR", repo / "var"))


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


# --- Dial caches (E14) -------------------------------------------------------
# A state read should not re-dial the account for a value it
# read seconds ago. A cache file in var/ beside the liveness
# files: a {fetched_at, value} stamp; a missing, unreadable,
# or stale cache falls back to the dial; only a successful
# dial refreshes the stamp (a failed dial is never cached, so
# recovery is never masked). One home for the mechanism —
# state.py's portions and access.access_list share it, and
# the live-list cache file itself.

DIAL_CACHE_TTL_S = 30


def dial_cache_read(repo: Path, name: str, now_dt: datetime):
    """One dial's cached value, or None when the cache is
    missing, unreadable, or older than the TTL. A cached
    value is never itself None (failures are not cached), so
    None unambiguously means: dial."""
    data = load_json(var_dir(repo) / name, None)
    if not isinstance(data, dict) or "value" not in data:
        return None
    try:
        fetched = parse_dt(data.get("fetched_at"))
    except (TypeError, ValueError):
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    age = (now_dt - fetched).total_seconds()
    if age < 0 or age > DIAL_CACHE_TTL_S:
        return None
    return data["value"]


def dial_cache_write(repo: Path, name: str, value, now_dt: datetime) -> None:
    """Refresh one dial cache (staged sibling + rename, the
    record discipline). Best-effort by design: a failed cache
    write costs a re-dial on the next read, never a failed
    read."""
    p = var_dir(repo) / name
    try:
        staged_write(
            p, json.dumps({"fetched_at": now_dt.isoformat(), "value": value}).encode()
        )
    except Exception:
        pass


def load_config(repo: Path) -> dict:
    return load_json(repo / "config" / "lease.json", {"enabled": False})


# --- Venue identity (S5, plan §7 V1) ------------------------------------------
# The extracted core serves one venue per store: this instance's
# records are written through the Colab adapter, so the stamp is
# the adapter's name. The stamp is applied at WRITE time only
# (records.save_record, the runner's save_record) — no reader
# defaults a missing key (plan §10.3: legacy records are stamped
# once by the migration, never defaulted at read). A second
# venue's core instance carries its own name here.

VENUE = "colab"
ADAPTER = "colab"


def adapter_dir(repo: Path) -> Path:
    """The venue adapter's material home (plan §7 V3): the
    Colab payload — snippets, probes, job manifests — lives
    under adapters/<venue>/, never in the core's tree."""
    return repo / "adapters" / ADAPTER


def snippet_path(repo: Path, name: str) -> Path:
    return adapter_dir(repo) / "snippets" / name


def adapter_jobs_dir(repo: Path) -> Path:
    return adapter_dir(repo) / "jobs"


# --- Unified writer seam (S5, plan §4.15 / contract 15) -----------------------
# Record writes ride the pipeline platform's unified writer,
# PERFORMED by the scheduler /ops service. The writer's own
# design (its header) is that mutations are performed by the
# long-lived server class, never a deniable caller process:
# the write-denial flap kills short-lived processes at their
# first write (the 2026-11-22 reaper deaths at exit 120 died
# inside an in-process staged_write). So where the platform
# tree exists, this seam hands each write to the platform
# /ops client (loaded by path from beside the writer), which
# POSTs it to the service under the venue machinery caller;
# the service runs the stage → fsync → read-back → rename
# protocol server-side. A service failure raises the
# writer's WriterError with the target byte-identical —
# there is NO local fallback on failure: a local write in a
# denied process is the death being cured. Where no
# platform tree exists (the pinned source repo's own
# layout, where no /ops service exists either), the
# fallback below is the same protocol inline, so behaviour
# never differs by home.


def _load_writer():
    cand = _paths.PLATFORM_WRITER
    if cand.exists():
        spec = _ilu.spec_from_file_location("pipeline_platform_writer", cand)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    return None


def _load_ops_client():
    cand = _paths.PLATFORM_OPS_CLIENT
    if cand.exists():
        spec = _ilu.spec_from_file_location("pipeline_platform_ops_client", cand)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    return None


WRITER = _load_writer()
OPS_CLIENT = _load_ops_client()

# The seam's /ops caller: a machinery caller (code
# constant, the venue AGENTS.md rule), registered in the
# scheduler's connector registry with the write-state
# scope alone — the seam performs writes, never exec. Its
# raw token lives in the ops token home like every
# caller's (contract 04, §10.1).
OPS_CALLER = "venue"


def staged_write(path: Path, data: bytes, mode: int | None = None) -> None:
    """Write bytes to path through the unified writer's
    protocol, performed by the /ops service: stage to a
    fresh sibling, flush + fsync, read back and compare,
    rename over, directory fsync — all server-side. A
    denial or failure at any stage leaves the target
    byte-identical. This seam is the venue's ONE writer
    (register E5): every session/lease state write in the
    tree rides it. An explicit `mode` (credential-class
    targets) is stamped by the writer; without one, the
    target's existing mode carries."""
    if OPS_CLIENT is not None:
        try:
            OPS_CLIENT.staged_write(OPS_CALLER, str(path), data, mode=mode)
        except OPS_CLIENT.WriterError as exc:
            # Normalize onto the writer module this seam
            # loaded: a caller catching the seam's
            # WriterError sees one class, whichever module
            # instance raised it.
            raise WRITER.WriterError(exc.name, exc.detail) from exc
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.sched-tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "rb") as fh:
            if fh.read() != data:
                raise OSError(f"read-back mismatch for {path}")
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# --- Session shape gate -------------------------------------------------------
# Local why: a bare panel tag is not a bypass — the bypass needs the
# server-carried env claim too — and the gate is admission only,
# never eviction. It is a journaled guardrail at the same trust
# level, not a security boundary. Mechanics:
# docs/lease-workflow.md.

ACTOR_ENV_CLAIM = "COLAB_LEASE_ACTOR"
PANEL_ACTOR = "panel"
GATE_DEFAULT_AGENT_CLASSES = ("high_ram",)
GATE_DEFAULT_BYPASS_ACTORS = (PANEL_ACTOR,)
GATE_DEFAULT_INFRA_ACTOR = "standing"


def parse_dt(text: str) -> datetime:
    return datetime.fromisoformat(text)


def iso_utc(dt: datetime) -> str:
    """An instant → its UTC ISO-8601 string."""
    return dt.astimezone(UTC).isoformat()


def stamp(now_dt: datetime | None = None) -> str:
    """The given instant (or now) as an ISO-8601 string —
    the identity stamp's form."""
    return (now_dt or datetime.now(UTC)).isoformat()


def now_or(now_dt: datetime | None) -> datetime:
    """The given instant, or now (UTC) when none is given —
    the claim clock's injection seam."""
    return now_dt or datetime.now(UTC)


def epoch(iso: str | None) -> float | None:
    """An ISO stamp → epoch seconds, else None (a missing
    or malformed stamp is an honest unknown)."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def parse_balance(usage_text: str) -> float | None:
    m = re.search(r"balance:?\s*([0-9]+(?:\.[0-9]+)?)", usage_text, re.IGNORECASE)
    return float(m.group(1)) if m else None


# --- Attributed spend accounting ----------------------------------------------
# Local why: the balance carries no per-source breakdown, so spend
# is built only from this repo's own lease segments; a late-detected
# death overcounts by at most the detection lag, and an unconfirmed
# rate contributes nothing. Mechanics: docs/lease-workflow.md.


def spend_journal_path(repo: Path) -> Path:
    return var_dir(repo) / "lease-spend-journal.jsonl"


def reaper_events_path(repo: Path) -> Path:
    return var_dir(repo) / "reaper-events.jsonl"


def append_reaper_event(repo: Path, event: dict) -> bool:
    """Spool a core-side lifecycle event for the companion server to
    drain into the UI outbox. The outbox has exactly one writer (the
    server, which owns seq allocation), so reap() never writes it
    directly. Best-effort: a failed spool write never breaks reap —
    the reap result itself still carries the outcome."""
    try:
        p = reaper_events_path(repo)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps(event) + "\n")
        return True
    except OSError:
        return False


# Absence confirmation (2026-11-13): a lease record is deleted
# only on a confirmed-absent session reading, and one reading
# inside one flicker window is not a confirmation — the session
# list renders live sessions unnamed for whole minutes under
# load. The stamp is shared by both delete legs (the reap's
# cleared-dead leg and acquire's candidate-clearing leg): the
# first absent observation stamps and spares the record; an
# observation still absent at least ABSENT_CONFIRM_S after the
# first stamp confirms; any live read clears the stamp.
ABSENT_CONFIRM_S = 900


def absent_stamp_path(repo: Path, session: str) -> Path:
    return var_dir(repo) / f"absent-{session}.json"


def absent_since(repo: Path, session: str) -> datetime | None:
    try:
        data = json.loads(absent_stamp_path(repo, session).read_text())
        return parse_dt(data["first_absent_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def stamp_absent(repo: Path, session: str, first: datetime, now_dt: datetime) -> None:
    path = absent_stamp_path(repo, session)
    try:
        staged_write(
            path,
            json.dumps(
                {
                    "first_absent_at": first.isoformat(),
                    "last_absent_at": now_dt.isoformat(),
                }
            ).encode(),
        )
    except Exception:  # noqa: BLE001 - best-effort stamp, as before
        pass


def clear_absent_stamp(repo: Path, session: str) -> None:
    try:
        absent_stamp_path(repo, session).unlink(missing_ok=True)
    except OSError:
        pass
