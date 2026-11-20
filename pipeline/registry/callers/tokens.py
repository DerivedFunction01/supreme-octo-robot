"""Token callers (contract 01, SCH7).

The connector's registry nature: each caller maps to
{token_sha256, scopes}. Hashes only — raw tokens are
printed once at mint and never stored in any form. The
registry is read fresh from the store on every
authentication (mint/revoke needs no restart); a missing
or malformed registry means no callers and every call
refused. The cleaning and comparison rules are the pinned
connector's (`server/connector.py` at the scheduler pin),
unchanged; the boundary is absolute: no token approves a
permission, pushes, acquires a lease, or writes a
calendar.
"""

from __future__ import annotations

import hashlib
import hmac

from .. import store as store_mod

SCOPES = ("read", "write-state", "send", "bridge")


def load_token_callers(registry) -> dict:
    """The cleaned token-caller map: {name: {token_sha256,
    scopes}}. Entries whose digest is not a 64-char string,
    or whose scopes filter down to nothing against the
    closed scope set, do not exist as callers."""
    raw = registry.token_callers()
    clean: dict = {}
    if not isinstance(raw, dict):
        return clean
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        digest = spec.get("token_sha256")
        scopes = [s for s in (spec.get("scopes") or []) if s in SCOPES]
        if isinstance(digest, str) and len(digest) == 64 and scopes:
            clean[name] = {"token_sha256": digest, "scopes": scopes}
    return clean


def authenticate(registry, token) -> tuple | None:
    """Return (caller_name, scopes) for a bearer token, or
    None. The token itself is hashed and compared in
    constant time against every registered digest; it is
    never stored, logged, or returned."""
    if not isinstance(token, str) or not token:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    for name, spec in load_token_callers(registry).items():
        if hmac.compare_digest(digest, spec["token_sha256"]):
            return name, spec["scopes"]
    return None


def authenticate_fresh(store_path, token) -> tuple | None:
    """Authenticate against the store read fresh from disk
    on this call — the pinned read-fresh discipline: a
    mint or revoke lands without any consumer restarting."""
    return authenticate(store_mod.Registry.load(store_path), token)


def public_view(registry) -> dict:
    """The redacted view (the connector's /health half):
    caller names and scopes only — never hashes, never
    tokens."""
    return {"callers": {name: spec["scopes"]
                        for name, spec in
                        sorted(load_token_callers(registry).items())}}
