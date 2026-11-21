#!/usr/bin/env python3
"""Local-test watcher — defect routing and the disposition
record (the enforcement half of local_test_watch.py).

Detection alone pooled findings in the scheduler outbox,
acked unseen (2026-11-15 audit, S-5) — a flag explained in
a relay note was closed with its reason nowhere on record
(the 2026-11-14 programme flags). This module is the
consumer the watcher was missing, kept mechanical: fixed
branches on recorded fields, no content judgment.

Three pieces:

- The DEFECT item: on a first sighting the watcher posts
  one item per episode to the attention surface (the
  consumed supervision surface; the card watch's cadence
  adapter writing the same store is the precedent) through
  the attention package's own ingest validation, over the
  migrated store the attention service serves. The item is
  posted under the registered `main` handle, carries
  kind=defect, names the programme (repo root segment),
  the process (kind, runner, argv, cwd), and the venue
  state at flag time (mode, live session count, load,
  first-seen stamp) in its title, and carries the defect
  routing pair (the scheduler workhorse; the owning thread
  the routes file names). `clears_at_source` is False: the
  item does not evaporate when the process exits — it
  clears by a recorded disposition (below), never by an
  ack or by the episode ending.
- The disposition record: one entry per episode signature
  in the watcher's own state file (untracked, named in
  the job entry's state_paths). An entry is born `open`
  when its defect is raised, with the finding and the
  routing outcomes. It closes only through the watcher's
  `disposition` verb, which writes the reason, the actor,
  and the stamp into the record. A reappearing episode
  whose signature carries a closed entry with a reason is
  the same explained process: no new defect item, no new
  sends — one printed line per episode says so. An entry
  still open explains nothing: a reappearance re-raises.
- The store seam: the production poster resolves the
  attention store path (env seam, else the platform var
  home the install units bind as ATTENTION_DATA) and
  returns None when no store file stands there — the
  watcher then reports the item outcome as unconfigured
  on its printed line, exactly as an unconfigured
  connector route reports print-only. Tests inject fake
  posters and scratch stores; production reads the live
  store only through this seam.

Stdlib only in this module's own code; the attention
package imports ride the poster's call, lazily, so a
tree without the attention package still runs the
watcher's detection and print cycle.
"""
import json
import os
import sys
from datetime import datetime, timezone

ITEM_HANDLE = "main"
ITEM_SOURCE_PREFIX = "local-test-watch-"
ROUTING_WORKHORSE = "scheduler"
DISPOSITION_KIND = "legitimate-tooling"
ATTENTION_STATE_ENV = "LOCAL_TEST_WATCH_ATTENTION_STATE"


def send_outcome(sender, chat_id, text, envelope_id):
    """One connector send's outcome token: queued when
    the sender queues it, failed when it raises or
    refuses — a send never propagates an exception into
    the watcher's cycle."""
    try:
        if sender(chat_id, text, envelope_id):
            return "queued"
    except Exception:
        pass
    return "failed"


def source_ref(sig):
    return ITEM_SOURCE_PREFIX + sig


def item_id(sig):
    return ITEM_HANDLE + ":" + source_ref(sig)


def repo_segment(cwd, workspace):
    """The programme name: the finding's repo root segment
    under the workspace (the attention `repo` field's own
    shape — one segment, never a path)."""
    rel = os.path.relpath(cwd, workspace)
    return rel.split(os.sep)[0]


def build_item_payload(sig, finding, programme, thread_label,
                       mode, live_count, load, at):
    """The defect item as data: programme, process, and
    venue state at flag time, in the post shape the
    attention ingest validates."""
    argv_text = " ".join(finding["argv"])
    title = (
        "LOCAL-EXEC %s %s in %s (%s) — argv=%s cwd=%s "
        "mode=%s sessions_live=%d load=%s first-seen=%s" % (
            finding.get("kind", "test"), finding["runner"],
            programme, thread_label, argv_text, finding["cwd"],
            mode, live_count, load, at))
    return {
        "handle": ITEM_HANDLE,
        "source_ref": source_ref(sig),
        "kind": "defect",
        "title": title,
        "provenance": "commission",
        "clears_at_source": False,
        "routing": {
            "workhorse": ROUTING_WORKHORSE,
            "thread": thread_label,
            "at": at,
            "evidence": "local-test-watch disposition " + sig,
        },
        "repo": programme,
    }


# -- the disposition record --------------------------------

def load_dispositions(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data.get("dispositions"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"dispositions": {}}


def _ops_paths():
    """The ops tree's paths spine (ops/paths.py), loaded by
    file location — this module is itself loaded by file
    location (by the local-test watch), so the spine rides
    the same pattern from this file's parent directory."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ops_paths",
        os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))),
            "paths.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_dispositions(path, record):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _ops_paths().save_json(path, record)


def is_explained(record, sig):
    """True only for a closed entry carrying a reason —
    the mechanical measure that clears a signature. An
    open entry, a missing entry, or a reasonless close
    explains nothing."""
    entry = (record.get("dispositions") or {}).get(sig) or {}
    if entry.get("status") != "closed":
        return False
    reason = (entry.get("disposition") or {}).get("reason") or ""
    return bool(str(reason).strip())


def open_entry(record, sig, finding, programme, at, outcomes):
    """Born (or refreshed) when a defect is raised: the
    finding, the programme, and this raise's routing
    outcomes, so the record shows what was sent where."""
    entries = record.setdefault("dispositions", {})
    entry = entries.get(sig)
    if entry is None:
        entry = {
            "status": "open",
            "opened_at": at,
            "programme": programme,
            "finding": {
                "kind": finding.get("kind", "test"),
                "runner": finding["runner"],
                "cwd": finding["cwd"],
                "argv": list(finding["argv"]),
            },
            "disposition": None,
        }
        entries[sig] = entry
    entry["last_raised_at"] = at
    entry["routing"] = dict(outcomes)
    return entry


def record_disposition(path, sig, reason, actor, at):
    """The disposition act: close one signature's entry
    with its reason, actor, and stamp. Refuses an unknown
    signature, an empty reason, or an empty actor — a
    disposition that names nothing records nothing.
    Returns (ok, detail)."""
    if not (reason or "").strip():
        return False, "a disposition carries its reason"
    if not (actor or "").strip():
        return False, "a disposition names its actor"
    record = load_dispositions(path)
    entry = (record.get("dispositions") or {}).get(sig)
    if entry is None:
        return False, "no disposition entry for signature " + sig
    entry["status"] = "closed"
    entry["disposition"] = {
        "kind": DISPOSITION_KIND,
        "reason": reason.strip(),
        "actor": actor.strip(),
        "at": at,
    }
    save_dispositions(path, record)
    return True, "closed " + sig


# -- the attention store seam -------------------------------

def attention_state_path(scheduling_root):
    """The migrated attention store: the env seam when
    set, else the platform var home beside the scheduling
    root (the path the install units bind as
    ATTENTION_DATA)."""
    env = os.environ.get(ATTENTION_STATE_ENV)
    if env:
        return env
    pipeline_root = os.path.dirname(scheduling_root)
    return os.path.join(
        pipeline_root, "platform", "var", "attention-state.json")


def _parse_stamp(at):
    try:
        return datetime.strptime(
            at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _load_attention(scheduling_root):
    pipeline_root = os.path.dirname(scheduling_root)
    if pipeline_root not in sys.path:
        sys.path.insert(0, pipeline_root)
    from attention.infra import attstore
    from attention.services.writes import ingest
    return attstore, ingest


def post_item_to_store(store, ingest, payload, at):
    """One ingest-validated upsert over an injected store
    (the attstore load/save seam): the dedupe is the
    ingest's own, keyed on handle + source_ref, so a
    re-raise updates the one item and reopens it if it
    was triaged done."""
    state = store.load_state()
    ingest.upsert_item(state, payload, _parse_stamp(at))
    store.save_state(state)
    return True


def default_item_poster(scheduling_root):
    """A poster(payload, at) over the live attention
    store, or None when no store file stands at the
    resolved path (unconfigured — the watcher reports
    the outcome on its line and never fails the cycle)."""
    path = attention_state_path(scheduling_root)
    if not os.path.isfile(path):
        return None

    def poster(payload, at):
        attstore, ingest = _load_attention(scheduling_root)
        store = attstore.AttentionStateStore(path)
        return post_item_to_store(store, ingest, payload, at)

    return poster


def default_item_resolver(scheduling_root):
    """A resolver(sig) that marks the signature's defect
    item done in the live store (the disposition verb's
    second half), or None when unconfigured. A missing
    item resolves to False, never an exception."""
    path = attention_state_path(scheduling_root)
    if not os.path.isfile(path):
        return None

    def resolver(sig):
        attstore, ingest = _load_attention(scheduling_root)
        store = attstore.AttentionStateStore(path)
        state = store.load_state()
        try:
            ingest.resolve_item(
                state, item_id(sig), {"resolution": "done"})
        except Exception:
            return False
        store.save_state(state)
        return True

    return resolver
