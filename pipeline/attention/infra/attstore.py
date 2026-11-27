"""The migrated attention state store (contract 01's
annex; plan §4.15's S7 re-point) — re-homed from the
registry package into this package (commission 12):
a package owns its store. The store's API,
behaviour, and writer seam are unchanged by the move.

ATT1's discipline, carried whole from the pinned store
(`backend/infra/store.py` at the attention pin): one
JSON-shaped state dict; registry seeds appended when
absent, never overwritten (backfill); the datetime decode
heuristic (ISO strings restored on load) carried verbatim
— it is a format coupling, deliberately preserved, never
drifted into.

What changes is the writer. The pinned store wrote through
its own in-process .tmp sibling + rename; that writer
retires here. Every save serializes with the pinned
encoder and lands through the unified writer (contract
15): staged sibling, fsync, read-back compare, rename
over, directory fsync — wrapper-mediated, so a denial at
any stage leaves the previous store byte-identical.

The seed data (the pin's domain defaults) lives in
attstore_seeds.json at this package's root — carried with
the store at its re-home; extracted from the pinned code
at build time (see the S7 report for provenance).
The live attention service is untouched by this module:
this is the migration path, built and rehearsed against
the S1 captured copy of the store.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import UTC, datetime

from attention import paths as _paths
from attention.domain.catalogs import default_freshness_registry

_SEEDS_PATH = _paths.SEEDS


def _load_platform_writer():
    """The staged-write protocol core lives in the
    pipeline platform home (contract 15); loaded by path
    from this package's paths module, so the protocol has
    exactly one implementation."""
    path = _paths.PLATFORM_WRITER
    spec = importlib.util.spec_from_file_location("pipeline_platform_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()


def _seeds() -> dict:
    with open(_SEEDS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def empty_state() -> dict:
    """The empty state: the pinned skeleton, with the
    registry defaults from the carried seed data (fresh
    copies — callers mutate what they load)."""
    seeds = _seeds()
    return {
        "handlers": [],
        "items": [],
        "presence": {"mode": "active", "expires_at": None, "expectation": ""},
        "waits": [],
        "action_log": [],
        "source_health": {},
        "muted": [],
        "allowlist": [],
        "handler_status": {},
        "handler_freshness": {},
        # The freshness registry's seed is the domain
        # catalog's default (the sample builder's form
        # for the shipped registries), not the JSON seed
        # data: the vocabulary is young and the JSON file
        # sits at its line cap.
        "freshness": default_freshness_registry(),
        "rules": seeds["rules"],
        "status_codes": seeds["status_codes"],
        "fields": seeds["fields"],
        "wait_classes": seeds["wait_classes"],
        "templates": seeds["templates"],
        "item_kinds": seeds["item_kinds"],
        "sends": [],
        "presence_seen": "active",
        "capacity_snapshot": None,
        "capacity_error": None,
        "digest_assembly": None,
        "staffing_rows": {},
        "dispatch_failures": [],
        "verifications": [],
        "action_rules": seeds["action_rules"],
        "owner_actions": [],
        "tap_counts": {},
        "pings": {},
        "owner_directed": {},
        "card_watch": {},
    }


def backfill(state: dict) -> dict:
    """Registry seeds reach stores written before them:
    appended when their kind/id is absent, never
    overwritten (the pinned logic, over the carried seed
    data)."""
    seeds = _seeds()
    have = {t["kind"] for t in state.get("templates", [])}
    state.setdefault("templates", []).extend(
        t for t in seeds["templates"] if t["kind"] not in have
    )
    have = {e["kind"] for e in state.get("item_kinds", [])}
    state.setdefault("item_kinds", []).extend(
        e for e in seeds["item_kinds"] if e["kind"] not in have
    )
    have = {r["id"] for r in state.get("action_rules", [])}
    state.setdefault("action_rules", []).extend(
        r for r in seeds["action_rules"] if r["id"] not in have
    )
    _backfill_staleness(state, seeds)
    _backfill_attention_fold(state)
    return state


# --- the attention fold: dispatch retired,
# supervision folded to wb + gap-closure ---

"""A handler is retired at the fold when its own
freshness record of record carries the retired-with-cause
verdict: the retirement is served data, keyed by handle,
and no chat binding is named in code."""

_FOLD_FROZEN_STATUS_HANDLES = ("@checker", "@sweeper")
"""Retired handlers whose frozen legacy handler_status
summaries are removed outright (the status-code post
transport is retired; the summaries are not a live
projection of anything)."""

_FOLD_SHADOW_REFS = ("tail:", "ping:")
"""Item source_ref prefixes minted as copies of records
wb/scheduler own (handler-status tails, scheduler report
pings): wb is the record of truth, so the open copies
settle done. Genuine owner/commission items — provenance
commission/owner, and wait-surfaced approvals — carry
neither prefix and are untouched."""


def _backfill_attention_fold(state: dict) -> None:
    """One-time, idempotent migration for the attention
    fold (steps 1/3/5), riding the load
    path like every backfill: each leg keys on the
    un-migrated shape, so a second load changes nothing.

    - Every send neither delivered nor already suppressed
      is settled retired (the engine's settle_retired, so
      the born-retired and migrated shapes are one shape);
      delivered/suppressed history is untouched.
    - Frozen legacy handler_status entries for retired
      handlers are removed; handlers bound to dead chats
      are marked retired.
    - Triage-open shadow items copied from wb/scheduler
      records settle done with the reason on the record.
    - An item already triage-done has its presentation
      cleared (status_code, due_at) — the zombie cure for
      items closed before the action path learned to
      clear them in the same write.
    - The venue-fold target programme's stored venue is
      stamped from its supervision declaration — the one
      declaration carrying the venue_fold_target marker;
      its declared venue is what the store's frozen copy
      lagged. No marker, no stamp."""
    # Deferred: the waits engine and the supervision
    # registry are services modules; the composition
    # binds at call time, never at import time (the
    # store seam loads under every service).
    from attention.services.measure import registry
    from attention.services.waits import engine

    fallback_at = datetime(2026, 11, 26, tzinfo=UTC)
    for send in state.get("sends", []):
        record = send.get("dispatch") or {}
        if record.get("delivered_at") is not None:
            continue
        if record.get("suppressed_at") is not None:
            continue
        at = send.get("at")
        engine.settle_retired(send, at if isinstance(at, datetime) else fallback_at)
    statuses = state.get("handler_status")
    if isinstance(statuses, dict):
        for handle in _FOLD_FROZEN_STATUS_HANDLES:
            statuses.pop(handle, None)
    freshness = state.get("handler_freshness") or {}
    for handler in state.get("handlers", []):
        record = freshness.get(handler.get("handle")) or {}
        if record.get("verdict") == "retired-with-cause":
            handler["retired"] = True
    for item in state.get("items", []):
        if item.get("triage") == "done":
            item["status_code"] = None
            item["due_at"] = None
        elif item.get("triage") == "open" and str(
            item.get("source_ref") or ""
        ).startswith(_FOLD_SHADOW_REFS):
            item["triage"] = "done"
            item["status_code"] = None
            item["due_at"] = None
            item["settled_reason"] = (
                "wb is the record of truth — shadow copy settled "
                "at the attention fold (2026-11-26)"
            )
    fold_slug = registry.venue_fold_slug()
    fold_row = registry.for_slug(fold_slug) if fold_slug else None
    for programme in state.get("programmes", []):
        if fold_row and programme.get("slug") == fold_slug:
            programme["venue"] = fold_row["venue"]


def _backfill_staleness(state: dict, seeds: dict) -> None:
    """Field-level backfill for the staleness pair (the
    decision-staleness plan, Step 1): a stored wait-class
    or item-kind entry missing stale_after_hours /
    on_stale gains its seed entry's values; an entry with
    no seed counterpart gains the floor defaults (no age
    cap; expire_blocked for a hard-stop class, expire
    otherwise). A field already present — owner-edited
    included — is never overwritten."""
    class_seeds = {c["name"]: c for c in seeds["wait_classes"]}
    for entry in state.get("wait_classes", []):
        seed = class_seeds.get(entry["name"], {})
        if "stale_after_hours" not in entry:
            entry["stale_after_hours"] = seed.get("stale_after_hours")
        if "on_stale" not in entry:
            entry["on_stale"] = seed.get(
                "on_stale",
                "expire_blocked" if entry.get("hard_stop") else "expire",
            )
    kind_seeds = {e["kind"]: e for e in seeds["item_kinds"]}
    for entry in state.get("item_kinds", []):
        seed = kind_seeds.get(entry["kind"], {})
        if "stale_after_hours" not in entry:
            entry["stale_after_hours"] = seed.get("stale_after_hours")
        if "on_stale" not in entry:
            entry["on_stale"] = seed.get("on_stale", "expire")


class _Encoder(json.JSONEncoder):
    """The pinned encoder: datetimes ride as ISO strings."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def _decode(value):
    """Restore datetimes from their ISO strings on load —
    the pinned heuristic, verbatim: it is a format
    coupling the migration carries deliberately."""
    if isinstance(value, dict):
        return {key: _decode(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_decode(val) for val in value]
    if isinstance(value, str) and _looks_like_datetime(value):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _looks_like_datetime(value: str) -> bool:
    return len(value) >= 19 and value[4] == "-" and value[10] == "T"


class AttentionStateStore:
    """The state dict at one path: loads with the pinned
    merge + backfill; saves through the unified writer.
    The Store protocol's shape (load_state / save_state),
    so the attention services consume it unchanged when
    their tree lands."""

    def __init__(self, path) -> None:
        self._path = os.fspath(path)

    def load_state(self) -> dict:
        if not os.path.isfile(self._path):
            return empty_state()
        with open(self._path, encoding="utf-8") as fh:
            state = _decode(json.load(fh))
        merged = empty_state()
        merged.update(state)
        return backfill(merged)

    def save_state(self, state: dict) -> None:
        payload = json.dumps(state, cls=_Encoder, indent=2).encode("utf-8")
        _writer.staged_write(self._path, payload)
