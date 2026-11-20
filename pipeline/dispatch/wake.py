"""The wake minter (contract 05, SCH8).

Per-item wake minter for the connector bridge queue.
Bridged connector requests (chat_send, chat_list,
chat_tail, permissions_list, permissions_history) queue
as JSON records and wait for a home-side executor
holding the runtime tools.
This minter is the programmatic generation half of that
end state — per queue item, no agent in the middle, it
mints one wake addressed to that item's own thread:

- it reads the queue directly from the record files (the
  queue is plain JSON; the read needs no credential),
- it resolves the item's target thread from the routing
  data it is handed — for chat_send, the drain home when
  one is configured (delivery is the drain's work; the
  destination chat is data inside the record, never the
  executor's address — see target_for), else the record's
  own args.chat_id; for the read tools, the owning thread
  of the requesting caller from the owners table
  (contract 01) —
- and it plants one wake ping per item in the outbox
  through the Outbox class (the outbox file is the
  cross-process source of truth; planting from a second
  process is a designed case). The ping's job id is
  bridge-wake-<request_id>, its kind agent-due, its body
  the per-item executor body, and its detail carries
  exactly {request_id, tool, caller, target_chat} — the
  item's identity and destination, never its text.

Idempotence needs no minter state file: a mint is
skipped while a pending ping for the item exists, and a
record that leaves the queued state is never re-minted,
so the outbox itself is the dedupe record. A ping acked
while its record is still queued (the executor claimed
then failed before fulfilling) is re-minted on the next
pass — the fulfill, not the mint, is the lock, and the
bridge refuses a second fulfill of a terminal record.

An item whose target cannot be resolved — a read tool
from a caller with no owner mapping — is left queued
and named on an UNRESOLVED line: a finding, never a
guessed target.

Episode escalation (F5 home, 2026-11-11): the per-item
pings address the item's own thread, but the executor is
one job — bridge-drain, an agent entry whose body is the
drain executor. A pass that finds at least one resolvable
queued item and no pending bridge-drain ping plants that
ping (detail: the resolvable count, plus target_chat
when a drain home is configured). The executor acks it
only when its final poll finds the queue empty, so a
standing bridge-drain ping IS the open episode: new
items coalesce into it, and the first pass after the ack
re-mints — the episode re-arms with no minter state, the
same outbox-as-record discipline as the per-item mints.
An unresolved-only queue never escalates: no executor
can work an item with no target, and its UNRESOLVED
line already reports it.

Output alphabet (the bridge-wake entry's report rule
keys on it): a quiet pass prints nothing; each mint
prints one WAKE line; each unresolvable item prints one
UNRESOLVED line; an escalation mint prints one DRAIN
line. WAKE and DRAIN are the entry's quiet patterns,
UNRESOLVED its report pattern.

Moved at S6 from the pinned scheduler's ops script; the
scheduling entry keeps the owners-config parsing (the
registry YAML subset is the scheduling package's) and
hands this minter the resolved routing data — owners
(caller -> chat id) and the drain home chat.
"""
import json
import os
from datetime import datetime, timezone

from .ledger import Ledger
from .outbox import Outbox

UTC = timezone.utc

BODY_REF = "bodies/bridge-wake-item.md"
JOB_PREFIX = "bridge-wake-"
DRAIN_JOB = "bridge-drain"
DRAIN_BODY = "bodies/bridge-drain.md"


def queued_records(bridge_dir):
    """The bridge queue, read from the record files: every
    record whose status is queued, in filename order."""
    records = []
    if not os.path.isdir(bridge_dir):
        return records
    for name in sorted(os.listdir(bridge_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(bridge_dir, name),
                      encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get("status") == "queued" \
                and isinstance(record.get("id"), str):
            records.append(record)
    return records


def target_for(record, owners, drain_chat=None):
    """The thread this item's wake is addressed to, or None
    when no honest target exists. A chat_send is addressed
    to the drain home when one is configured: delivery is
    the drain executor's work, and addressing the wake to
    the destination chat instead put an instruction-shaped
    payload in front of a working lane whose job is not
    relaying — executor cycles there read the record, hit
    the prompt-injection screen on its content, and stalled
    the whole dispatch class (2026-11-12). Unconfigured,
    the pre-drain fallback holds: the chat it will post
    into. A read tool's result belongs to the requesting
    caller's owning thread."""
    if record.get("tool") == "chat_send":
        if drain_chat:
            return drain_chat
        args = record.get("args") or {}
        chat = args.get("chat_id")
        return chat if isinstance(chat, str) and chat else None
    return owners.get(str(record.get("caller") or ""))


def mint(record, target, outbox, now):
    """Plant the item's wake ping. Returns True when a ping
    was created, False when one is already pending (the
    coalesce — the mint is a no-op, never a second ping)."""
    detail = {
        "request_id": record["id"],
        "tool": record.get("tool"),
        "caller": record.get("caller"),
        "target_chat": target,
    }
    _ping, created = outbox.add_or_coalesce(
        JOB_PREFIX + record["id"], now, "agent-due",
        body_ref=BODY_REF, detail=detail, now=now)
    return created


def run(bridge_dir, state_dir, owners, drain_chat=None,
        now=None, outbox=None):
    """One minting pass. `owners` is the resolved routing
    table (caller -> chat id) and `drain_chat` the drain
    home chat or None — both are contract 01 data, parsed
    by the calling entry from the owners config. Returns
    the run's output lines."""
    now = now or datetime.now(UTC)
    if outbox is None:
        outbox = Outbox(state_dir, Ledger(state_dir))
    pending_jobs = {ping["job_id"] for ping in outbox.pending()}
    lines = []
    resolvable = 0
    for record in queued_records(bridge_dir):
        job_id = JOB_PREFIX + record["id"]
        target = target_for(record, owners, drain_chat)
        if target is not None:
            resolvable += 1
        if job_id in pending_jobs:
            continue
        if target is None:
            lines.append(
                f"UNRESOLVED {record['id']} tool={record.get('tool')} "
                f"caller={record.get('caller')}: no target thread "
                f"resolvable; left queued")
            continue
        if mint(record, target, outbox, now):
            lines.append(
                f"WAKE {record['id']} tool={record.get('tool')} "
                f"target={target}")
    if resolvable and DRAIN_JOB not in pending_jobs:
        detail = {"items": resolvable}
        if drain_chat:
            detail["target_chat"] = drain_chat
        _ping, created = outbox.add_or_coalesce(
            DRAIN_JOB, now, "agent-due", body_ref=DRAIN_BODY,
            detail=detail, now=now)
        if created:
            lines.append(f"DRAIN items={resolvable}")
    return lines
