"""The attention surface's serving shell, on the platform
serving core (pipeline/platform/serving.py) — the one
serving implementation for the whole mega app (owner
ruling). Run standalone:
`python3 -m attention.server` from the pipeline root;
the mega app's one process (the repo-root run.py) builds
the same mount beside the other three surfaces.

The shell owns no logic: parse, wire, dispatch — the
services carry every derivation. What it carries is the
pinned server's discipline, whole:

- ONE lock around the whole load -> evaluate -> dispatch
  -> save cycle, shared with the tick: a response is
  never readable before its save lands (poll-after-post).
  Every request — reads included — first evaluates waits
  and action rules against the loaded state, exactly as
  the pinned dispatch did.
- The security baseline on every reply (API and problem
  alike), with the caller's Origin reflected — the
  Library-published frontend is a different origin.
- Errors cross the seam as problem+json (API.md, api/1),
  with a correlation id per problem.
- The 60-second evaluation tick and the slow capacity
  collector run as supervised workers beside the listener
  (their per-pass containment is the pinned loops' own:
  a failed pass never kills the serve; a loop that itself
  dies surfaces through the core's supervision instead
  of expiring silently on a daemon thread).
- The digest assembly is persisted, not per-request
  (perf lane L-B): build_digest costs
  seconds — its staffing measure scans the detached run
  records on every call — so a third supervised worker
  assembles it off the request path and the digest route
  serves the stored payload. The record lives in the
  state beside the other snapshots (capacity, workbench
  facts) and carries a fingerprint of the whole state
  minus the assembly's own keys, so every write path
  invalidates it by landing in the state at all. The
  worker wakes on the save epoch (every save through
  this mount advances it) and on a maximum-age cadence
  for the inputs that move no state key — the run
  records on disk, the push items' git facts, the clock
  itself. A recompute never holds the request lock
  while it computes: it loads and assembles outside the
  lock and takes it only to merge, so a glance read
  never queues behind a digest build. Before the first
  assembly lands, the digest route builds live, exactly
  as the workbench-facts snapshot's readers do.

THE BINDING (OI-3, carried into the one-process ruling):
the store path is explicit or the process refuses to
start. make_store raises when ATTENTION_DATA is unset,
and again when it names no file — there is no default
and no seeded-sample fallback in the serving path. The
sample builder (infra/sample_data) survives only as a
fixture source for tests.

One named delta from the pinned shell, stricter: a
request body that is not JSON answers a problem 422
(the pinned shell dropped the connection). The pinned
shell's static and font routes are retired (AC-10):
the surface ships in the fullstack artifact, and this
shell serves the API only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from attention.capacity import _capacity_loop
from attention.errors import AppError, NotFound, problem_details
from attention.infra import scheduler_client
from attention.infra.attstore import _Encoder
from attention.infra.store import JsonFileStore, Store
from attention.services import programmes
from attention.services.dispatch import dispatch, dispatch_consumer
from attention.services.measure import continuation
from attention.services.reads import derive, digest, model
from attention.services.waits import (
    action_rules,
    actions,
    engine,
    facts,
)
from attention.services.writes import ingest, writes
from attention.settings import Settings

PACKAGE_ROOT = Path(__file__).resolve().parent

# Security baseline (docs/fundamentals.md): set once here,
# at the shell, so every route inherits them.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def _load_core():
    spec = importlib.util.spec_from_file_location(
        "platform_serving", PACKAGE_ROOT.parent / "platform" / "serving.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


serving = _load_core()


class StoreBindingError(ValueError):
    """The explicit store binding is absent or names no
    file: a startup refusal, never a default."""


def make_store(settings: Settings) -> Store:
    if settings.data_path is None:
        raise StoreBindingError(
            "ATTENTION_DATA is not set — the attention "
            "surface binds its migrated store explicitly "
            "or not at all"
        )
    if not settings.data_path.is_file():
        raise StoreBindingError(
            f"ATTENTION_DATA names no file: "
            f"{settings.data_path} — the migrated store "
            f"is not in place"
        )
    return JsonFileStore(settings.data_path)


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(val) for val in value]
    return value


def wait_view(wait: dict) -> dict:
    return _jsonable(
        {
            "wait_id": wait["id"],
            "handle": wait["handle"],
            "posted_by": wait.get("posted_by"),
            "wait_class": wait["wait_class"],
            "summary": wait["summary"],
            "decision": wait["decision"],
            "rule_id": wait["rule_id"],
            "owner_note": wait.get("owner_note"),
            "posted_at": wait["posted_at"],
            "decided_at": wait["decided_at"],
        }
    )


class _EpochStore:
    """The store, counting its saves. Every write path in
    this process lands through save_state — request
    cycles, the tick, the collectors — so the count is
    the write-path invalidation signal the digest
    assembly worker watches: a save the worker has not
    seen means the state it fingerprinted may have moved.
    Loads do not advance it."""

    def __init__(self, inner: Store) -> None:
        self._inner = inner
        self.epoch = 0

    def load_state(self) -> dict:
        return self._inner.load_state()

    def save_state(self, state: dict) -> None:
        self._inner.save_state(state)
        self.epoch += 1


# The assembly's own keys: the record itself, and the
# staffing measure's first-seen memory, whose sole
# writer is the assembly (build_staffing). Neither is an
# input the fingerprint must catch — a change to either
# originates in an assembly, never in a write path the
# assembly has to react to.
_ASSEMBLY_KEYS = ("digest_assembly", "staffing_rows")


def digest_fingerprint(state: dict) -> str:
    """The digest inputs' fingerprint: the canonical
    serialization (the store's own encoder) of the whole
    state minus the assembly's own keys, hashed. Total
    by construction — every writer of every other key
    moves it, so per-writer invalidation reduces to one
    question: does the write land in the state? (They
    all do; the state is the only store.) The digest's
    external inputs — the detached run records and the
    push items' git facts — move no state key; the
    assembly's maximum-age refresh bounds their lag, and
    the capacity collection folds run-record movement
    into the capacity snapshot, a fingerprinted key."""
    view = {k: v for k, v in state.items() if k not in _ASSEMBLY_KEYS}
    blob = json.dumps(view, cls=_Encoder, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def assemble_digest(
    state: dict,
    settings: Settings,
    now: datetime,
    push_facts: dict | None = None,
) -> dict:
    """One digest assembly over a working copy of the
    state: the push facts derived once, the payload built
    by the same builder the route used per request, both
    normalized to the served JSON shape for storage. The
    build's one state mutation — the staffing measure's
    first-seen memory — lands on the working copy; the
    caller merges it back with the record. `push_facts`
    is the test seam: production derives them here."""
    if push_facts is None:
        push_facts = facts.derive_push_facts(state, now)
    payload = digest.build_digest(state, settings, now, push_facts)
    return {
        "fingerprint": digest_fingerprint(state),
        "assembled_at": _jsonable(now),
        "push_facts": _jsonable(push_facts),
        "payload": _jsonable(payload),
    }


def _push_facts(state: dict, now: datetime) -> dict:
    """The push facts the read routes serve: the digest
    assembly's stored derivation when one has landed —
    facts measured at assembly time, as their verified_at
    says — derived live only before the first assembly,
    the digest route's own fallback discipline."""
    record = state.get("digest_assembly") or {}
    stored = record.get("push_facts")
    if stored is not None:
        return stored
    return facts.derive_push_facts(state, now)


def build_mount(settings: Settings, store: Store):
    """This surface's mount and its supervised workers;
    returns (mount, workers). One lock is shared by the
    request cycle and the loops. The store is wrapped in
    the save-counting seam first, so every save the cycle
    and the loops land advances the epoch the digest
    assembly worker invalidates on."""
    store = _EpochStore(store)
    lock = threading.Lock()
    r = serving.Router()

    def decorate(reply, request):
        for name, value in SECURITY_HEADERS.items():
            reply.headers[name] = value
        origin = request.headers.get("Origin")
        if origin:
            reply.headers["Access-Control-Allow-Origin"] = origin
            reply.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            reply.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return reply

    def pre_route(request):
        if request.method == "OPTIONS":
            return serving.Reply(204, b"", "text/plain")
        return None

    def error_mapper(exc):
        if isinstance(exc, AppError):
            correlation_id = uuid.uuid4().hex
            payload = problem_details(
                exc.code,
                exc.status,
                exc.message,
                correlation_id,
                getattr(exc, "field_errors", None),
            )
            return serving.Reply(
                exc.status,
                json.dumps(payload).encode("utf-8"),
                "application/problem+json",
                headers={"X-Correlation-Id": correlation_id},
            )
        return None

    def not_found(request):
        # The pinned shell's no-route answer is a problem,
        # in the surface's own error language.
        raise NotFound("No such route.")

    mount = serving.Mount(
        "attention",
        r,
        prepare_payload=_jsonable,
        dumps=lambda payload: json.dumps(payload),
        error_mapper=error_mapper,
        decorate=decorate,
        pre_route=pre_route,
        not_found=not_found,
    )

    def cycle(handler):
        """The pinned dispatch cycle, as a wrapper: under
        the one lock — load, evaluate waits and action
        rules, dispatch, save when anything moved. The
        handler receives (state, now, request) and returns
        (status, payload, dirty). The save sits in the
        same finally the pinned shell's did: a handler
        that raises still lands the evaluation's moves."""

        def wrapped(request):
            with lock:
                now = datetime.now().astimezone()
                state = store.load_state()
                decided = engine.evaluate_waits(state, settings, now)
                acted = action_rules.evaluate_action_rules(state, settings, now)
                dirty = bool(decided) or bool(acted)
                try:
                    status, payload, handler_dirty = handler(state, now, request)
                except Exception:
                    if dirty:
                        store.save_state(state)
                    raise
                if dirty or handler_dirty:
                    store.save_state(state)
                return mount.json_reply(status, payload)

        return wrapped

    def body(request) -> dict:
        if not request.body:
            return {}
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            from attention.errors import Validation

            raise Validation("body must be JSON", []) from err
        return data if isinstance(data, dict) else {}

    # -- routes (the pinned table, in its order) -----------
    def health(state, now, request):
        return (
            200,
            {
                "status": "ok",
                "contract": "api/1",
                "environment": settings.environment,
                "last_stackdump_at": None,
            },
            False,
        )

    def glance(state, now, request):
        push_facts = _push_facts(state, now)
        return 200, model.build_glance(state, settings, now, push_facts), False

    def today(state, now, request):
        push_facts = _push_facts(state, now)
        return 200, model.build_today(state, settings, now, push_facts), False

    def digest_route(state, now, request):
        record = state.get("digest_assembly") or {}
        if record.get("payload"):
            return 200, record["payload"], False
        push_facts = facts.derive_push_facts(state, now)
        return 200, digest.build_digest(state, settings, now, push_facts), False

    def rules(state, now, request):
        return (
            200,
            {
                "contract": "api/1",
                "rules": [model.rule_view(r, state) for r in state["rules"]],
            },
            False,
        )

    def registries(state, now, request):
        return 200, model.build_registries(state), False

    def programmes_route(state, now, request):
        return (
            200,
            {
                "contract": "api/1",
                "programmes": programmes.declarations(state),
            },
            False,
        )

    def sends(state, now, request):
        return 200, model.build_sends(state, now=now), False

    def sends_undispatched(state, now, request):
        return (
            200,
            {
                "contract": "api/1",
                "sends": [
                    model.send_view(s, now) for s in dispatch.undispatched(state, now)
                ],
            },
            False,
        )

    def send_claim(state, now, request):
        send = dispatch.claim(
            state, request.params["send_id"], body(request), settings, now
        )
        return 200, model.send_view(send, now), True

    def send_ack(state, now, request):
        send = dispatch.ack(state, request.params["send_id"], body(request), now)
        return 200, model.send_view(send, now), True

    def send_suppress(state, now, request):
        send = dispatch.suppress(state, request.params["send_id"], body(request), now)
        return 200, model.send_view(send, now), True

    def handler_view(state, now, request):
        handle = request.params["handle"]
        derived = derive.derive_for(state, settings, handle, now)
        push_facts = _push_facts(state, now)
        view = model.build_handler(state, settings, now, handle, derived, push_facts)
        if view is None:
            raise NotFound("No such handler.")
        return 200, view, False

    def wait_get(state, now, request):
        return 200, wait_view(ingest.get_wait(state, request.params["wait_id"])), False

    def presence(state, now, request):
        writes.set_presence(state, body(request))
        engine.evaluate_waits(state, settings, now)
        return 200, model.presence_view(state, now), True

    def item_action(state, now, request):
        item = actions.apply_item_action(
            state, settings, request.params["item_id"], body(request), now
        )
        return 200, model.item_view(item, state, now, settings), True

    def handler_action(state, now, request):
        result = actions.apply_handler_action(
            state, settings, request.params["handle"], body(request), now
        )
        return 200, result, True

    def handler_unmute(state, now, request):
        result = writes.unmute_type(state, request.params["handle"], body(request))
        return 200, result, True

    def handler_mute(state, now, request):
        result = writes.mute_type(state, request.params["handle"], body(request))
        return 200, result, True

    def digest_prefs(state, now, request):
        result = writes.set_digest_prefs(state, body(request))
        return 200, {"contract": "api/1", "digest_prefs": result}, True

    def rule_add(state, now, request):
        rule = writes.add_rule(state, body(request))
        engine.evaluate_waits(state, settings, now)
        # The response is the served rule view — labels
        # composed here, the one home (AC-13).
        return 201, model.rule_view(rule, state), True

    def rule_preview(state, now, request):
        data = body(request)
        would = engine.preview_rule(state, data.get("rule") or {}, settings, now)
        return 200, {"contract": "api/1", "would_fire": would}, False

    def vocab_add(write_fn):
        def route(state, now, request):
            return 201, write_fn(state, body(request)), True

        return route

    def handler_register(state, now, request):
        return 201, writes.register_handler(state, body(request)), True

    def programme_upsert(state, now, request):
        return 201, writes.upsert_programme(state, body(request)), True

    def item_upsert(state, now, request):
        item = ingest.upsert_item(state, body(request), now)
        return 201, model.item_view(item, state, now, settings), True

    def item_resolve(state, now, request):
        item = ingest.resolve_item(state, request.params["item_id"], body(request))
        return 200, model.item_view(item, state, now, settings), True

    def wait_post(state, now, request):
        wait = ingest.post_wait(state, body(request), now)
        engine.evaluate_waits(state, settings, now)
        return 201, wait_view(wait), True

    def dispatch_failure(state, now, request):
        result = writes.record_dispatch_failure(state, body(request), now)
        return 201, result, True

    def verification(state, now, request):
        result = writes.record_verification(state, body(request), now)
        return 201, result, True

    r.add("GET", "/health", cycle(health))
    r.add("GET", "/api/v1/glance", cycle(glance))
    r.add("GET", "/api/v1/today", cycle(today))
    r.add("GET", "/api/v1/digest", cycle(digest_route))
    r.add("GET", "/api/v1/rules", cycle(rules))
    r.add("GET", "/api/v1/registries", cycle(registries))
    r.add("GET", "/api/v1/programmes", cycle(programmes_route))
    r.add("GET", "/api/v1/sends", cycle(sends))
    r.add("GET", "/api/v1/sends/undispatched", cycle(sends_undispatched))
    r.add("POST", "/api/v1/sends/{send_id}/claim", cycle(send_claim))
    r.add("POST", "/api/v1/sends/{send_id}/ack", cycle(send_ack))
    r.add("POST", "/api/v1/sends/{send_id}/suppress", cycle(send_suppress))
    r.add("GET", "/api/v1/handlers/{handle}", cycle(handler_view))
    r.add("GET", "/api/v1/agent/waits/{wait_id}", cycle(wait_get))
    r.add("POST", "/api/v1/presence", cycle(presence))
    r.add("POST", "/api/v1/items/{item_id}/action", cycle(item_action))
    r.add("POST", "/api/v1/handlers/{handle}/action", cycle(handler_action))
    r.add("POST", "/api/v1/handlers/{handle}/unmute", cycle(handler_unmute))
    r.add("POST", "/api/v1/handlers/{handle}/mute", cycle(handler_mute))
    r.add("POST", "/api/v1/digest/prefs", cycle(digest_prefs))
    r.add("POST", "/api/v1/rules", cycle(rule_add))
    r.add("POST", "/api/v1/rules/preview", cycle(rule_preview))
    r.add(
        "POST", "/api/v1/vocab/status-codes", cycle(vocab_add(writes.add_status_code))
    )
    r.add("POST", "/api/v1/vocab/fields", cycle(vocab_add(writes.add_field)))
    r.add("POST", "/api/v1/vocab/classes", cycle(vocab_add(writes.add_wait_class)))
    r.add("POST", "/api/v1/vocab/templates", cycle(vocab_add(writes.add_template)))
    r.add("POST", "/api/v1/vocab/kinds", cycle(vocab_add(writes.add_item_kind)))
    r.add("POST", "/api/v1/handlers", cycle(handler_register))
    r.add("POST", "/api/v1/programmes", cycle(programme_upsert))
    r.add("POST", "/api/v1/agent/items", cycle(item_upsert))
    r.add("POST", "/api/v1/agent/items/{item_id}/resolve", cycle(item_resolve))
    r.add("POST", "/api/v1/agent/waits", cycle(wait_post))
    r.add("POST", "/api/v1/agent/dispatch-failures", cycle(dispatch_failure))
    r.add("POST", "/api/v1/agent/verifications", cycle(verification))

    workers = {
        "attention-tick": lambda stop: _tick_loop(stop, store, settings, lock),
        "attention-capacity": lambda stop: _capacity_loop(stop, store, settings, lock),
        "attention-digest": lambda stop: _digest_loop(stop, store, settings, lock),
    }
    return mount, workers


def _tick_pass(store: Store, settings: Settings, lock) -> None:
    """One evaluation tick (the pinned loop's body): time-
    based triggers cannot fire from request traffic alone,
    so the engine also runs on a clock. A failed pass is
    contained here — it never kills the serve."""
    try:
        now = datetime.now().astimezone()
        with lock:
            state = store.load_state()
            expired = False
            presence = state["presence"]
            expires = presence.get("expires_at")
            if presence["mode"] != "active" and expires is not None and expires <= now:
                presence["mode"] = "active"
                presence["expires_at"] = None
                expired = True
            promoted = ingest.promote_tail_items(state, now)
            # S-5: scheduler report pings ingest as
            # agent-clearable items. A failed fetch skips
            # the leg — it clears nothing.
            try:
                pings = scheduler_client.fetch_pending_pings(settings)
                pinged_items = ingest.ingest_report_pings(state, pings, now)
            except scheduler_client.SchedulerUnavailable:
                pinged_items = False
            armed = programmes.ingest_armed(state, settings.armed_dir, now)
            cleared = facts.clear_resolved(state, now)
            fired = engine.evaluate_waits(state, settings, now)
            lapsed = engine.evaluate_expiry(state, now)
            acted = action_rules.evaluate_action_rules(state, settings, now)
            pinged = continuation.run_pass(state, settings, now)
            _, consumed = dispatch_consumer.run_pass(state, settings, now)
            if (
                fired
                or lapsed
                or acted
                or promoted
                or expired
                or cleared
                or consumed
                or armed
                or pinged
                or pinged_items
            ):
                store.save_state(state)
    except Exception:
        pass  # a failed tick never kills the serve


def _tick_loop(stop, store: Store, settings: Settings, lock) -> None:
    while not stop.wait(60):
        _tick_pass(store, settings, lock)


def _digest_pass(
    store: Store, settings: Settings, lock, now: datetime | None = None
) -> bool:
    """One digest assembly pass (the worker's body): when
    the stored assembly's fingerprint no longer matches
    the state's, or the assembly is older than the
    maximum age, recompute it — the load and the build
    run outside the request lock — and merge the record
    and the staffing memory back under the lock, the
    capacity collector's merge shape. True when a new
    assembly landed. A failed pass is contained here,
    like the tick's and the capacity collector's: it
    never kills the serve."""
    try:
        now = now or datetime.now().astimezone()
        working = store.load_state()
        record = working.get("digest_assembly") or {}
        fresh = record.get("fingerprint") == digest_fingerprint(working)
        assembled_raw = record.get("assembled_at")
        assembled_at = (
            assembled_raw
            if isinstance(assembled_raw, datetime)
            else datetime.fromisoformat(assembled_raw)
            if assembled_raw
            else None
        )
        if (
            fresh
            and assembled_at is not None
            and (now - assembled_at).total_seconds() < settings.digest_max_age_s
        ):
            return False
        record = assemble_digest(working, settings, now)
        with lock:
            current = store.load_state()
            current["digest_assembly"] = record
            current["staffing_rows"] = working.get("staffing_rows", {})
            store.save_state(current)
        return True
    except Exception:
        return False


def _digest_loop(stop, store: _EpochStore, settings: Settings, lock) -> None:
    """The digest assembly worker: a pass whenever a save
    the worker has not seen has landed (write-path
    invalidation, via the epoch every save through this
    mount advances), and at least every maximum-age
    interval for the inputs that move no state key — the
    run records on disk, the push items' git facts, the
    clock itself (stall thresholds, digest windows).
    Between passes it only compares the epoch: the check
    costs nothing, and a pass that finds the fingerprint
    unmoved recomputes nothing."""
    seen_epoch: int | None = None
    last_pass: datetime | None = None
    while not stop.is_set():
        now = datetime.now().astimezone()
        due = (
            seen_epoch is None
            or store.epoch != seen_epoch
            or last_pass is None
            or (now - last_pass).total_seconds() >= settings.digest_max_age_s
        )
        if due:
            _digest_pass(store, settings, lock, now)
            seen_epoch = store.epoch
            last_pass = now
        stop.wait(settings.digest_poll_s)


def main() -> int:
    """The standalone entry: the same refusal, mount, and
    workers the one process uses."""
    settings = Settings.from_env()
    try:
        store = make_store(settings)
    except StoreBindingError as exc:
        print(f"attention: {exc}")
        return 2
    mount, workers = build_mount(settings, store)
    listener = serving.Listener(mount, settings.host, settings.port)
    print(f"owner-attention on http://{settings.host}:{settings.port}")
    return serving.serve([listener], workers=workers)


if __name__ == "__main__":
    raise SystemExit(main())
