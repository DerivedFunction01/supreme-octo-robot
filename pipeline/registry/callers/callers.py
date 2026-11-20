"""Thread + machinery caller claims (contract 01, RUN3).

The semantics are carried whole from the runner's pinned
registry code (`sync/lease/core/callers.py` at the runner pin);
what changes is the source: the thread-caller file form is
a section of the one registry store, not a per-repo config
file. Caller (which thread) is never a substitute for
actor (which channel acted); machinery callers are
constants so a missing local registry never breaks the
panel or the duties.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

# Machinery callers are code constants, never listed in any
# file: panel (the lease panel), standing (the gate's
# default infrastructure actor), test, lease.
MACHINERY_CALLERS = ("panel", "standing", "test", "lease")

_CALLER_PART = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


def caller_bases(registry) -> set:
    """The valid caller bases: the machinery constants plus
    the store's thread callers. A missing or malformed
    thread section yields the machinery set alone —
    fail-closed for thread claims, never a crash."""
    names = set(MACHINERY_CALLERS)
    listed = registry.thread_callers().get("callers")
    if isinstance(listed, list):
        for name in listed:
            if isinstance(name, str) and _CALLER_PART.fullmatch(name):
                names.add(name)
    return names


def validate_claim(registry, raw) -> str | None:
    """Validate one raw claim: the normalized caller (base,
    with its lane suffix when carried) or None — for an
    absent claim, an unregistered base, or a malformed
    shape alike. Callers that must distinguish "no claim"
    from "bad claim" use claim_error."""
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        return None
    base, sep, suffix = raw.partition(":")
    if not _CALLER_PART.fullmatch(base):
        return None
    if sep and not _CALLER_PART.fullmatch(suffix):
        return None
    if base not in caller_bases(registry):
        return None
    return f"{base}:{suffix}" if sep else base


def active_bases(registry) -> set:
    """The registered callers marked active in the store's
    "active" list. Active is the owner's standing marking:
    a caller with a potential use for a venue even when no
    session is currently up — while marked active its work
    is detached-only, and the sync gate refuses its
    synchronous attaches outright. Markings naming
    unregistered callers are ignored; a missing or
    malformed list marks nobody."""
    names = set()
    listed = registry.thread_callers().get("active")
    if isinstance(listed, list):
        registered = caller_bases(registry)
        for name in listed:
            if isinstance(name, str) and name in registered:
                names.add(name)
    return names


def is_active(registry, raw) -> bool:
    """Whether a presented caller claim belongs to an
    active-marked caller: the claim must validate, and its
    base must be marked — a lane suffix inherits its base's
    marking."""
    validated = validate_claim(registry, raw)
    if validated is None:
        return False
    return validated.partition(":")[0] in active_bases(registry)


def resolve_claim(registry, flag=None, env=None) -> str | None:
    """The seam's caller claim, resolved: the flag when one
    was presented, else the env value, validated (flag over
    env). None when no claim was presented or the presented
    claim is invalid — an absent claim is unattributed,
    never an error."""
    raw = flag if flag is not None else env
    return validate_claim(registry, raw)


def claim_error(registry, flag=None, env=None) -> str | None:
    """Why the presented claim failed, or None: no claim
    presented, or the claim validated. The wrapper seams
    refuse on a presented but invalid claim (an unregistered
    caller is refused at claim time) while an absent claim
    simply leaves the call unattributed."""
    raw = flag if flag is not None else env
    if raw is None:
        return None
    if validate_claim(registry, raw) is not None:
        return None
    return (f"unregistered caller {raw!r} (registry: the "
            f"pipeline registry; machinery callers always valid)")


# -- the claims journal --------------------------------------

def append_claim(journal_path, session, caller, seam) -> bool:
    """Journal one attach claim: who attached to which
    session, when, through which wrapper. The claims are
    the attribution evidence for sessions that live outside
    lease records. Best-effort like every journal here."""
    try:
        path = journal_path
        parent = path.parent if hasattr(path, "parent") else None
        if parent is not None:
            parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "session": session, "caller": caller,
                "seam": seam}) + "\n")
        return True
    except OSError:
        return False


def load_claims(journal_path) -> dict:
    """The latest attributed claim per session:
    {session: {"caller", "ts"}}. Claims with no caller are
    attach evidence only and do not attribute."""
    out: dict = {}
    try:
        lines = journal_path.read_text(encoding="utf-8").splitlines()
    except (OSError, AttributeError):
        try:
            with open(journal_path, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            claim = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(claim, dict) and claim.get("session") \
                and claim.get("caller"):
            out[claim["session"]] = {"caller": claim["caller"],
                                     "ts": claim.get("ts")}
    return out
