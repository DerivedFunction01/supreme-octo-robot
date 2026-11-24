#!/usr/bin/env python3
"""The single Colab CLI funnel: resolution, environment, invocation.

Every automated call to the official google-colab-cli goes through
here. Resolution order (stated once, in AGENTS.md): $COLAB_BIN (the
test seam), else the uv tool venv
(~/.local/share/uv/tools/google-colab-cli/bin/colab), else PATH,
else ~/.local/bin/colab. The CLI is deliberately NOT installed on
PATH (no global shim): this funnel is the only sanctioned access,
and a bare `colab` in an agent shell is a contract breach, not a
shortcut. Every call passes --auth oauth2 explicitly and runs with
the NO_PROXY suffixes that keep Colab/Google traffic off this
machine's egress proxy.

The guarded colab() below is the auth guard of record (mechanics:
docs/auth.md). It moved here from bin/colab-run unchanged; the
runner and every other consumer load this module by path and call
the one implementation.
"""

# Portability exceptions (gate component directives):
# portability-exception: ~/.local/share/uv/tools/google-colab-cli/bin/colab — the google-colab-cli uv tool venv binary, this funnel's documented resolution target
# portability-exception: ~/.local/bin/colab. — the removed per-user CLI shim location, named in the docstring above to forbid it (the trailing period is the sentence's, captured in the matched string)

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import importlib.util as _ilu

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

REPO = _paths.REPO_RESOLVED
TOKEN = Path.home() / ".config" / "colab-cli" / "token.json"


# --- Unified writer seam (register E5; contract 15) --------------------------
# The funnel's own state writes — the token restore, the
# session-binding heal, the auth-required marker — ride the
# shared writer route (sync/writer_route.py, the one home
# for the sync package's non-lease writes): performed by
# the /ops service where it answers, else the platform
# writer in-process under denial retry, else the protocol
# inline. Loaded by path, like every funnel seam.

_route_spec = _ilu.spec_from_file_location(
    "venue_writer_route", Path(__file__).resolve().parent / "writer_route.py")
_route = _ilu.module_from_spec(_route_spec)
_route_spec.loader.exec_module(_route)

_staged_write = _route.staged_write


def colab_bin() -> str:
    env_bin = os.environ.get("COLAB_BIN")
    if env_bin:
        return env_bin
    venv_bin = Path.home() / ".local" / "share" / "uv" / "tools" / "google-colab-cli" / "bin" / "colab"
    if venv_bin.exists():
        return str(venv_bin)
    return shutil.which("colab") or str(Path.home() / ".local" / "bin" / "colab")


def colab_env() -> dict:
    env = dict(os.environ)
    for key in ("NO_PROXY", "no_proxy"):
        suffix = "google.com,googleapis.com,googleusercontent.com,colab.dev"
        env[key] = f"{env[key]},{suffix}" if env.get(key) else suffix
    return env


# --- Venue dispatch (S5, plan §7 V2) -------------------------------------------
# The funnel is the adapter seam: the lease core receives this
# module's callable by injection, and extraction puts a per-venue
# dispatch behind it. One venue is implemented (D1/D2): colab.
# A second venue registers here — its own bin resolution, env,
# verb set, and shape-catalog source (a new venue's catalog does
# NOT parse this CLI's help text; the Colab catalog keeps its
# parser, in sync/lease/core/catalog.py) — and the lease core does
# not change shape. The OAuth token guard below is adapter-side
# auth (plan §7 V3): it guards this venue's credential, at this
# funnel, and no other venue inherits it.

VENUE = "colab"

_COLAB_VERBS = {
    "new": "new",
    "stop": "stop",
    "exec": "exec",
    "run": "run",
    "list": "list",
    "upload": "upload",
    "download": "download",
    "usage": "usage",
}

VENUES = {
    "colab": {
        "bin": "colab_bin",
        "env": "colab_env",
        "verbs": _COLAB_VERBS,
        "catalog": "cli-help",
        "auth": "oauth2-token-guard",
    },
}


def venue_dispatch(venue: str = VENUE) -> dict:
    """The adapter registration for one venue: how its channel
    binary resolves, the environment its calls run under, the
    verb set the core's operations map onto, where its shape
    catalog comes from, and its auth discipline. An unregistered
    venue is a hard error, never a silent fall back to Colab."""
    try:
        return VENUES[venue]
    except KeyError:
        raise ValueError(f"unregistered venue: {venue!r}") from None


def venue_verbs(venue: str = VENUE) -> dict:
    return venue_dispatch(venue)["verbs"]


AUTH_PROMPT = "Enter the authorization code"
AUTH_RC = 3
TOKEN_MIN_REFRESH_LEN = 20


def _var_dir() -> Path:
    # The lease core's var seam (sync/lease/core/foundation.py var_dir): the
    # COLAB_RUNNER_VAR override, else this repo's var/. Mirrored
    # here so the funnel carries no lease import; the auth-required
    # marker is the only var/ state the guard touches.
    return Path(os.environ.get("COLAB_RUNNER_VAR", REPO / "var"))


def _token_bytes() -> bytes | None:
    try:
        return TOKEN.read_bytes()
    except OSError:
        return None


def _token_valid(data: bytes | None) -> bool:
    """A stored credential is valid when it parses as JSON and carries
    a refresh_token of plausible length. The interactive flow's stub
    (a lone refresh_token key, 15 chars) fails this, as does any
    truncated or non-JSON write. Contents are never printed."""
    if not data:
        return False
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(parsed, dict):
        return False
    rt = parsed.get("refresh_token")
    return isinstance(rt, str) and len(rt) >= TOKEN_MIN_REFRESH_LEN


def _atomic_write_token(data: bytes) -> None:
    """Write the token through the unified writer, so no reader ever
    sees a partial credential and an interrupted write cannot destroy
    the live file (owner ruling: token writes are atomic
    at every seam)."""
    _staged_write(TOKEN, data, mode=0o600)


SESSIONS = Path.home() / ".config" / "colab-cli" / "sessions.json"


def _binding_bytes() -> bytes | None:
    try:
        return SESSIONS.read_bytes()
    except OSError:
        return None


def _binding_snapshot(data: bytes | None) -> bytes | None:
    """The binding is worth guarding only in its healthy shape: a
    non-empty JSON object. Anything else (missing, torn, an empty
    object) is already the damaged state — no snapshot, no restore."""
    if not data:
        return None
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(parsed, dict) and parsed else None


def _binding_clobbered(snapshot: bytes | None) -> bool:
    """A call clobbered the binding when a healthy snapshot existed
    and the file is now missing or unparseable (the
    write-denial flap truncated sessions.json to 0 bytes under a
    CLI rewrite — every recorded session read absent and the
    fleet blinded while its lease records stayed correct). A
    file that still parses — even {} after the last session
    stops — is the CLI's own view and is never overridden."""
    if snapshot is None:
        return False
    data = _binding_bytes()
    if data is None:
        return True
    try:
        json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return True
    return False


def _restore_binding(snapshot: bytes | None) -> bool:
    """Restore a clobbered binding atomically; never raise — a
    failed restore must not break the call it guards. Returns
    True when a restore landed, so the heal can journal the
    outcome instead of swallowing it."""
    try:
        if _binding_clobbered(snapshot):
            _staged_write(SESSIONS, snapshot, mode=0o600)
            return True
    except Exception:  # noqa: BLE001 - a failed restore never breaks the call
        pass
    return False


def _lease_record_live(name: str) -> bool:
    """The lease record is the authority on whether <name>'s
    binding entry should exist: a record whose deadline is still
    in the future means the session is the fleet's to use."""
    try:
        rec = json.loads((_var_dir() / f"lease-{name}.json").read_text())
        deadline = datetime.fromisoformat(rec["deadline"])
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline > datetime.now(timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _restore_pruned_entries(snapshot: bytes | None) -> None:
    """Re-add binding entries a call pruned while their lease
    records live (the CLI's rewrites kept
    dropping individual entries under the recovery traffic — the
    file stayed parseable, the name vanished, and runs orphaned
    mid-flight while their assignments lived; the whole-file
    guard above cannot see a parseable file). The snapshot's
    entry goes back verbatim, merged into the CLI's current map
    so its surviving view and additions are preserved; an entry
    whose record is gone or past its deadline stays pruned —
    stop and expiry removals are the CLI's own business. Never
    raises."""
    if snapshot is None:
        return
    try:
        before = json.loads(snapshot)
        data = _binding_bytes()
        if data is None:
            return
        current = json.loads(data)
        if not isinstance(before, dict) or not isinstance(current, dict):
            return
        restored = {name: before[name] for name in before if name not in current and _lease_record_live(name)}
        if not restored:
            return
        current.update(restored)
        _staged_write(SESSIONS, json.dumps(current, indent=2).encode(), mode=0o600)
    except Exception:  # noqa: BLE001 - never raises, as before
        pass


def _binding_parse() -> dict | None:
    """The binding as a map, or None when the file is damaged:
    missing, empty, or unparseable. A parseable map — even {}
    after the last session stops — is the CLI's own view and
    is never damage."""
    data = _binding_bytes()
    if not data:
        return None
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _binding_damaged() -> bool:
    """The binding file exists but is damaged: empty,
    unparseable, or not a map. A missing file is not damage
    — a store the CLI has not created yet is its own
    business — and a parseable map, even {}, is the CLI's
    own view. The lease read side (sessions.binding_damaged)
    classifies the same shapes the same way."""
    try:
        data = SESSIONS.read_bytes()
    except OSError:
        return False
    if not data.strip():
        return True
    try:
        return not isinstance(json.loads(data), dict)
    except (ValueError, UnicodeDecodeError):
        return True


def _journal_binding(event: str, detail: str) -> None:
    """One line to the binding journal (var/binding-journal
    .jsonl); never raises — the journal is evidence, not a
    gate on the call it records."""
    try:
        var = _var_dir()
        var.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": event, "detail": detail})
        with open(var / "binding-journal.jsonl", "a") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 - evidence never breaks the call
        pass


def _serve_binding_state(state: str, detail: str) -> None:
    """The served binding finding (var/binding-state.json):
    the state document's binding portion reads this file, so
    a damaged binding serves as binding-damaged, never as
    sessions dead. Written on transitions only; never
    raises."""
    try:
        var = _var_dir()
        path = var / "binding-state.json"
        current = None
        try:
            current = json.loads(path.read_text()).get("state")
        except (OSError, ValueError, AttributeError):
            current = None
        if current == state:
            return
        var.mkdir(parents=True, exist_ok=True)
        _staged_write(path, json.dumps({"state": state, "at": datetime.now(timezone.utc).isoformat(), "detail": detail}, indent=2).encode())
    except Exception:  # noqa: BLE001 - the finding never breaks the call
        pass


def _persist_last_healthy(data: bytes) -> None:
    """Keep the last healthy binding bytes in var/ (staged,
    0600): the sticky heal's source when a later call starts
    against a damaged file with no snapshot of its own.
    Written only when the bytes change; never raises."""
    try:
        var = _var_dir()
        path = var / "binding-last-healthy.json"
        try:
            if path.read_bytes() == data:
                return
        except OSError:
            pass
        var.mkdir(parents=True, exist_ok=True)
        _staged_write(path, data, mode=0o600)
    except Exception:  # noqa: BLE001 - the copy never breaks the call
        pass


def _restore_from_last_healthy() -> str:
    """Restore a damaged binding from the persisted
    last-healthy copy, filtered to entries whose lease
    records live (the pruned-entries rule: an entry with no
    live record is the CLI's own removal and stays removed).
    Returns the outcome for the journal: "restored",
    "no-persisted-copy", "no-live-entries", or
    "write-failed". Never raises."""
    try:
        persisted = json.loads((_var_dir() / "binding-last-healthy.json").read_bytes())
    except (OSError, ValueError):
        return "no-persisted-copy"
    if not isinstance(persisted, dict):
        return "no-persisted-copy"
    live = {name: entry for name, entry in persisted.items() if _lease_record_live(name)}
    if not live:
        return "no-live-entries"
    try:
        _staged_write(SESSIONS, json.dumps(live, indent=2).encode(), mode=0o600)
    except Exception:  # noqa: BLE001 - reported, never raised
        return "write-failed"
    return "restored"


def _heal_binding(snapshot: bytes | None) -> None:
    """Heal the binding after a call — loudly and stickily
    (the silent single-shot restore disarmed
    itself. A restore denied in the same wave that truncated
    the file left it at 0 bytes; every later call snapshotted
    the damage, computed "no snapshot, no restore", and
    stood down; the fleet read blind for hours, twice in one
    night). Now damage is journaled and served
    (var/binding-state.json), a call that starts against a
    damaged file heals from the persisted last-healthy copy
    instead of standing down, and every healthy ending
    refreshes that copy."""
    if snapshot is not None:
        if _binding_clobbered(snapshot):
            if _restore_binding(snapshot):
                _journal_binding("restored", "snapshot restore after clobber")
            else:
                _journal_binding("restore-failed", "snapshot restore did not land")
                _serve_binding_state("damaged", "restore-failed")
                return
        else:
            _restore_pruned_entries(snapshot)
    elif _binding_damaged():
        outcome = _restore_from_last_healthy()
        _journal_binding("sticky-heal", outcome)
        if outcome != "restored":
            _serve_binding_state("damaged", outcome)
            return
    if _binding_parse() is not None:
        healthy = _binding_bytes()
        if healthy is not None and _binding_snapshot(healthy) is not None:
            _persist_last_healthy(healthy)
        _serve_binding_state("ok", "healthy")


def _note_auth_required(reason: str) -> None:
    try:
        var = _var_dir()
        var.mkdir(parents=True, exist_ok=True)
        noted_at = datetime.now(timezone.utc).isoformat()
        _staged_write(var / "auth-required.json", json.dumps({"noted_at": noted_at, "reason": reason}, indent=2).encode())
    except Exception:  # noqa: BLE001 - the marker is best-effort, as before
        pass


def _clear_auth_required() -> None:
    try:
        (_var_dir() / "auth-required.json").unlink(missing_ok=True)
    except OSError:
        pass


def _auth_blocked(cmd: list[str], reason: str) -> subprocess.CompletedProcess:
    _note_auth_required(reason)
    return subprocess.CompletedProcess(args=cmd, returncode=AUTH_RC, stdout="", stderr=f"colab auth required: {reason}")


def colab(*args: str, timeout: int = 18000) -> subprocess.CompletedProcess:
    """The one funnel for every automated Colab CLI call, guarded so a
    dead credential can never again masquerade as data (a
    failed token refresh dropped the CLI into its interactive login
    flow, which overwrote the stored token with a stub and printed the
    auth prompt where callers expected a session list / usage text —
    the prompt read as "session absent" and a live lease's record was
    deleted under it). The guard:
    - never invokes the CLI when the stored token is missing/invalid;
    - snapshots the token before the call and restores it atomically
      if the call leaves it invalid (the flow writes its stub BEFORE
      prompting, so this also covers a call that times out blocked on
      the prompt);
    - turns any call whose output carries the auth prompt into an
      auth-required result (rc 3, empty stdout), so downstream reads
      see "unknown", never junk data.
    - snapshots the session binding (sessions.json) the same way:
      the CLI rewrites it non-atomically on ordinary calls, so a
      write denied after the truncate leaves 0 bytes and every
      recorded session reads absent. A call that
      leaves the binding missing or unparseable gets the snapshot
      restored. A call that prunes an individual entry from a
      still-parseable binding gets that entry restored when its
      lease record lives — the CLI's rewrites drop entries under
      load while their assignments live on; an entry with no
      live record stays pruned, as the CLI's own removal. The
      heal is loud and sticky: damage is journaled
      (var/binding-journal.jsonl) and served
      (var/binding-state.json), a call that starts against a
      damaged binding heals from the persisted last-healthy
      copy (var/binding-last-healthy.json) instead of standing
      down, and every healthy ending refreshes that copy.
    Inert under COLAB_BIN: the test fakes are not credential flows."""
    cmd = [colab_bin(), "--auth", "oauth2", *args]
    if os.environ.get("COLAB_BIN"):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=colab_env())
    snapshot = _token_bytes()
    if not _token_valid(snapshot):
        return _auth_blocked(cmd, "stored token missing or invalid; re-authorization required (no CLI call made)")
    binding_snapshot = _binding_snapshot(_binding_bytes())
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=colab_env(), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        if not _token_valid(_token_bytes()):
            _atomic_write_token(snapshot)
            _note_auth_required("CLI call timed out after overwriting the token; snapshot restored")
        _heal_binding(binding_snapshot)
        raise
    if AUTH_PROMPT in (result.stdout + result.stderr):
        if not _token_valid(_token_bytes()):
            _atomic_write_token(snapshot)
        _heal_binding(binding_snapshot)
        return _auth_blocked(cmd, "CLI entered its interactive login flow")
    if not _token_valid(_token_bytes()):
        _atomic_write_token(snapshot)
        _heal_binding(binding_snapshot)
        return _auth_blocked(cmd, "CLI call overwrote the stored token; snapshot restored")
    _heal_binding(binding_snapshot)
    if result.returncode == 0:
        _clear_auth_required()
    return result


def json_object_from_output(stdout: str) -> dict:
    """The JSON object an exec probe printed, read from the call's
    stdout: the object starting at the first '{', exactly one value,
    with anything after it ignored. Probes print one JSON object as
    their answer; the CLI may add chatter of its own around a call's
    output — its update nag ("A new version of Colab CLI is
    available", three [colab] lines) intermittently TRAILS the
    probe's object, and parsing the whole remainder as JSON then
    fails on a call whose payload landed fine (launch
    upload-verifies died "unreadable" on banner-polluted reads,
    intermittently, on both live sessions). Raises ValueError when
    no complete object is present — the failure family every call
    site already catches as "unreadable"."""
    data, _end = json.JSONDecoder().raw_decode(stdout[stdout.index("{"):])
    if not isinstance(data, dict):
        raise ValueError("CLI output's first JSON value is not an object")
    return data
