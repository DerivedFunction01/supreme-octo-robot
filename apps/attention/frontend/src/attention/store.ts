// The mock adapter: a stateful store behind the
// AttentionDataSource seam, seeded with fictional,
// contract-shaped data. It implements plan §9 / contract 05's
// decision semantics against the mock ledger:
//
//   verdict at the tap, validated against the served verb set
//   -> the item leaves the open queue into the "Decided —
//      awaiting fulfillment" band (states queued / sent /
//      recorded)
//   -> fulfillment is derived, never assumed: from the send
//      ledger for send-backed decisions, from the push-fact
//      feed for push_needed, recorded for snooze
//   -> fulfilled: the item clears and its effect is shown
//   -> failed or unfulfilled past 120 minutes (stalled): the
//      item returns to the queue with decision_history and
//      the failure on its face
//   -> replay guards: an idempotency key short-circuits; a
//      repeated tap on a standing decision records and sends
//      nothing; a fulfilled decision is never changed.
//
// The simulated dispatch consumer settles outstanding claimed
// sends before claiming new ones (contract 05, §9.2a),
// claims on a 15-minute lease, and delivers only via an ack
// carrying the fulfillment's submission reference (ATT6).
// Shadow sends are never dispatchable (ATT5). Replies route
// direct to the owning thread, main copied (ATT3).
//
// Scenario clock: the mock scenario is Wednesday, March 4,
// 2026, America/New_York (EST, UTC-5 throughout the scenario
// window). The default clock starts at 14:04 scenario time
// and advances 1:1 with real time; tests inject a manual
// clock. All wall-clock math goes through the scenario zone.

import handlersSeed from "./seed/handlers.json";
import programmesSeed from "./seed/programmes.json";
import waitsSeed from "./seed/waits.json";
import sendsSeed from "./seed/sends.json";
import presenceSeed from "./seed/presence.json";
import itemsSeed from "./seed/items.json";
import surfacesSeed from "./seed/surfaces.json";
import statusesSeed from "./seed/statuses.json";
import registriesSeed from "./seed/registries.json";
import rulesSeed from "./seed/rules.json";
import digestSeed from "./seed/digest.json";
import type {
  ActionRuleView,
  AttentionDataSource,
  AwaitingView,
  BandState,
  DecideInput,
  DecideResult,
  DecisionRecord,
  DigestContentView,
  DigestSettings,
  DigestView,
  ExpiryChoice,
  FieldInput,
  FulfilledEntry,
  GlanceView,
  SurfaceHealth,
  HandlerActionResult,
  HandlerDetailView,
  HandlerRow,
  HandlerStatusView,
  HandlerSurface,
  HandlersView,
  ItemKindInput,
  ItemView,
  OwnerActionView,
  OwnerItem,
  PresenceMode,
  PresenceRow,
  PresenceView,
  ProgrammeCardView,
  ProgrammeRow,
  ProposalPayload,
  RegistriesView,
  RulePreviewResult,
  RuleRecord,
  RuleSaveResult,
  RuleView,
  SendRow,
  Severity,
  SnoozeOptionsView,
  StatusCodeInput,
  TemplateInput,
  TodayView,
  VerbEntry,
  VocabResult,
  WaitClassInput,
  WaitRow,
  WouldFire,
} from "./types";
import { VERB_LABELS, verbLabel } from "./verb-labels";

const SCENARIO_START = Date.parse("2026-03-04T14:04:00-05:00");
const STALL_MS = 120 * 60_000; // contract 05: unfulfilled past 120 min reads stalled
const CLAIM_LEASE_MS = 15 * 60_000; // ATT6: 15-minute claim lease
const CONSUMER = "attention-service";
/** Mock transport fact: deliveries to this target fail. The
 * seeded failure path (the return leg of the decision loop). */
const FAILING_TARGETS: Record<string, string> = {
  "thread-quarry": "target thread unreachable (mock transport)",
};
const MAIN_THREAD = "thread-main";
const EXPECTATIONS: Record<PresenceMode, string> = {
  active: "",
  focus: "Only breakthroughs and decisions",
  away: "Items hold for the next digest window",
};

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

// ---- scenario-zone time helpers (EST, UTC-5, fixed) ----

function wallParts(d: Date): { y: number; mo: number; da: number; h: number; mi: number } {
  const shifted = new Date(d.getTime() - 5 * 3_600_000);
  return {
    y: shifted.getUTCFullYear(),
    mo: shifted.getUTCMonth() + 1,
    da: shifted.getUTCDate(),
    h: shifted.getUTCHours(),
    mi: shifted.getUTCMinutes(),
  };
}

function scenarioInstant(y: number, mo: number, da: number, h: number, mi: number): number {
  return Date.UTC(y, mo - 1, da, h + 5, mi, 0);
}

const timeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});
const dateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "long",
  month: "long",
  day: "numeric",
});
const clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  hour12: false,
});

function timeLabel(iso: string | number): string {
  return timeFmt.format(new Date(iso)).toUpperCase();
}

function durationLabel(ms: number): string {
  const mins = Math.max(0, Math.floor(ms / 60_000));
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h} h ${String(m).padStart(2, "0")} min`;
}



/** Handler steering verbs (backend HANDLER_VERBS). */
const HANDLER_VERBS = [
  "status_ping",
  "parallelize",
  "critic_pass",
  "perf_pass",
  "consolidation_pass",
  "organize_pass",
  "stop",
  "park",
  "resume",
] as const;

/** The quick verbs placed on a status ride the handler
 * endpoint too (backend STATUS_QUICK_VERBS). */
const STATUS_QUICK_VERBS = [
  "continue",
  "go",
  "accept_review",
  "reject_incomplete",
  "close",
  "leave_it",
] as const;

/** The pass commissions: verb -> the item title's name. */
const PASS_VERBS: Record<string, string> = {
  critic_pass: "Critic pass",
  perf_pass: "Performance pass",
  consolidation_pass: "Consolidation pass",
  organize_pass: "Organize pass",
};

/** The lane's answering status post for a directed verb:
 * the fake simulates the lane replying to the verdict
 * with its new status — it lands on the next tick. */
const DIRECTED_STATUS: Record<string, { status_code: string; summary: string }> = {
  park: {
    status_code: "PARKED",
    summary: "Parked at the owner's direction — resumes on the word.",
  },
  stop: { status_code: "PARKED", summary: "Stopped at the owner's direction." },
  resume: { status_code: "WORKING", summary: "Resumed — back on the work." },
  accept_review: {
    status_code: "DONE",
    summary: "Review accepted — the work stands as reviewed.",
  },
  reject_incomplete: {
    status_code: "WORKING",
    summary: "Sent back as incomplete — rework under way.",
  },
  close: { status_code: "CLOSED", summary: "Closed by the owner." },
};

const STALL_AFTER_HOURS = 6; // backend Settings.stall_after_hours

/** The learning loop (backend D-A7/D-A8): verdict taps
 * are counted per handler + class + verb; at the
 * threshold a rule proposal surfaces. The spellings are
 * this store's verb taxonomy — "approve" counts as the
 * backend's approve_once, "decide" as its pick. Bookmarks
 * (snooze, done, mute_type, leave_it) and reply/modify
 * are never counted: their judgment rides the note. */
const COUNTED_VERBS = new Set([
  "approve",
  "deny",
  "decide",
  "accept",
  "reject",
  "push",
  "close_on_verify",
  "continue",
  "go",
  "accept_review",
  "reject_incomplete",
]);
const PROPOSAL_THRESHOLD = 3; // backend dom.PROPOSAL_THRESHOLD

/** An action rule record (backend action_rules shape):
 * created by a promotion tap, evaluated for shadow
 * hints and proposal suppression, served composed. */
interface ActionRuleRecord {
  id: string;
  match: { handle?: string; kind?: string; wait_class?: string };
  verb: string;
  mode: string;
  created_from: string;
  at: string;
  option_id?: string | null;
}

const PROVENANCE_LABELS: Record<string, string> = {
  commission: "Owner commission",
  offer: "Agent offer — awaiting your tap",
};

const DIGEST_OWNER_LABELS: Record<string, string> = {
  owner: "Waiting on you",
  lane: "Back with the lane",
  self: "Poster closeout",
};

/** Staffing row kind labels (backend staffing KIND_LABELS). */
const STAFFING_KIND_LABELS: Record<string, string> = {
  understaffed: "Understaffed",
  fleet_idle: "Idle session",
  idle_unlanded: "Idle — work complete",
  no_successor: "No successor staffed",
  record_gap: "Record not moving",
  phantom_stop: "Unverified owner stop",
  unrouted_defect: "Unrouted defect",
  blocked_uncited: "Blocked — no basis",
  blocked_unverified: "Blocked — unverified",
  serial_plan: "Serial plan",
  steer_undeliverable: "Steer undeliverable",
  owner_waiting: "Owner waiting",
  owner_waiting_unanswered: "Owner waiting — ask unanswered",
  armed_unposted: "Armed — no post yet",
};

export interface MockClock {
  now(): number;
  advance(ms: number): void;
}

export function manualClock(start: number = SCENARIO_START): MockClock {
  let t = start;
  return {
    now: () => t,
    advance: (ms: number) => {
      t += ms;
    },
  };
}

/** A handler's latest status post, as served (labels are
 * composed at read time from the registries). */
interface StatusRecord {
  status_code: string;
  summary: string;
  at: string;
  done?: string[];
  ongoing?: string[];
  tail?: { kind: string; title: string; owner: string }[];
  blockers?: { summary: string; clearing_act: string | null; whose: string }[];
}

interface RegistriesState {
  status_codes: RegistriesView["status_codes"];
  fields: { name: string; type: string; source: string; poster_settable: boolean }[];
  wait_classes: { name: string; hard_stop: boolean }[];
  operators: { op: string; label: string }[];
  triggers: { on: string; label: string }[];
  actions: { type: string; label: string }[];
  templates: RegistriesView["templates"];
  item_kinds: { kind: string; label: string; status_kind: boolean; digest_owner: string | null }[];
}

interface DigestSeedState {
  sections: {
    kind: string;
    rows: { title: string; handle: string; provenance: string; at: string }[];
  }[];
  staffing: {
    available: boolean;
    reason: string | null;
    idle_minutes_total: number;
    rows: {
      topic: string | null;
      handle: string | null;
      kind: string;
      detail: string;
      escalation: string;
    }[];
  };
  parked_plans: {
    available: boolean;
    reason: string | null;
    plans: { project: string; path: string; title: string; age_days: number | null }[];
  };
}

interface OwnerActionRecord {
  id: string;
  handle: string;
  verb: string;
  note: string;
  at: string;
  actor: string;
  rule_id: string | null;
}

interface StoreState {
  handlers: HandlerRow[];
  programmes: ProgrammeRow[];
  waits: WaitRow[];
  sends: SendRow[];
  presence: PresenceRow;
  items: OwnerItem[];
  fulfilled: FulfilledEntry[];
  handlerSurfaces: Record<string, HandlerSurface>;
  digest: DigestSettings;
  statuses: Record<string, StatusRecord>;
  registries: RegistriesState;
  rules: RuleRecord[];
  digestContent: DigestSeedState;
  ownerActions: OwnerActionRecord[];
  pings: Record<string, { count: number; last_at: number | null }>;
  ownerDirected: Record<string, { at: string; handle: string }>;
  /** Directed-control status posts land on the next tick —
   * the lane's answering post, simulated. */
  pendingStatus: Record<string, { status_code: string; summary: string }>;
  sendCounter: number;
  actionCounter: number;
  commissionCounter: number;
  ruleCounter: number;
  tickCount: number;
  pushFact: { state: "current" | "pushed"; flipAtTick: number | null };
  /** Recorded decisions (snooze, proposal verdicts) clear
   * on a later pass with the effect composed at the tap:
   * item_id -> {tick, effect}. */
  recordedResolveAt: Record<string, { tick: number; effect: string }>;
  /** The learning loop: tap counts per handle|cls|verb,
   * and the action rules promotions have created. */
  tapCounts: Record<string, { count: number; cycles: number }>;
  actionRules: ActionRuleRecord[];
  /** Items held by a type mute (backend triage "muted"):
   * out of every open derivation until the type unmutes. */
  mutedItems: Set<string>;
  failures: { send_id: string; reason: string; at: string }[];
  idempotency: Record<string, DecideResult>;
  handlerIdempotency: Record<string, HandlerActionResult>;
}

export function createMockAttentionStore(clock?: MockClock): AttentionDataSource {
  const realStart = Date.now();
  const clk: MockClock = clock ?? {
    now: () => SCENARIO_START + (Date.now() - realStart),
    advance: () => undefined,
  };
  const nowMs = () => clk.now();
  const nowIso = () => new Date(nowMs()).toISOString();

  const surfaces = surfacesSeed as unknown as {
    handler_surfaces: Record<string, HandlerSurface>;
    digest: DigestSettings;
    fulfilled: FulfilledEntry[];
  };
  const state: StoreState = {
    handlers: clone(handlersSeed) as HandlerRow[],
    programmes: clone(programmesSeed) as ProgrammeRow[],
    waits: clone(waitsSeed) as WaitRow[],
    sends: clone(sendsSeed) as SendRow[],
    presence: clone(presenceSeed) as PresenceRow,
    items: clone(itemsSeed) as OwnerItem[],
    fulfilled: clone(surfaces.fulfilled),
    handlerSurfaces: clone(surfaces.handler_surfaces),
    digest: clone(surfaces.digest),
    statuses: clone(statusesSeed) as Record<string, StatusRecord>,
    registries: clone(registriesSeed) as RegistriesState,
    rules: clone(rulesSeed) as RuleRecord[],
    digestContent: clone(digestSeed) as DigestSeedState,
    ownerActions: [],
    pings: {},
    ownerDirected: {},
    pendingStatus: {},
    sendCounter: 7,
    actionCounter: 0,
    commissionCounter: 0,
    ruleCounter: 0,
    tickCount: 0,
    pushFact: { state: "current", flipAtTick: null },
    recordedResolveAt: {},
    tapCounts: {},
    actionRules: [],
    mutedItems: new Set<string>(),
    failures: [],
    idempotency: {},
    handlerIdempotency: {},
  };

  const listeners = new Set<() => void>();
  let version = 0;
  const bump = () => {
    version += 1;
    listeners.forEach((fn) => fn());
  };

  const handlerOf = (handle: string): HandlerRow =>
    state.handlers.find((h) => h.handle === handle) ?? state.handlers[0];

  // ---------- evaluator ----------

  /** Failed and stalled items return to the decision queue
   * with decision_history on the item's face (contract 05). */
  function returnToQueue(item: OwnerItem, outcome: "failed" | "stalled", failure: string): void {
    if (!item.decision) return;
    item.decision_history.push({ ...item.decision, outcome, failure });
    item.decision = null;
    item.failure = failure;
    delete state.recordedResolveAt[item.id];
  }

  function runEvaluator(): boolean {
    let changed = false;
    for (const item of state.items) {
      if (!item.decision) continue;
      const age = nowMs() - Date.parse(item.decision.at);
      if (age > STALL_MS) {
        returnToQueue(item, "stalled", "Fulfillment stalled — no delivery within 120 min");
        changed = true;
      }
    }
    return changed;
  }

  // ---------- dispatch consumer (simulated) ----------

  function fulfill(item: OwnerItem, effect: string): void {
    if (!item.decision) return;
    state.fulfilled.unshift({
      item_id: item.id,
      title: item.title,
      handle: item.handle,
      decision: item.decision,
      effect,
      at: item.decision.at,
      fulfilled_at: nowIso(),
    });
    state.items = state.items.filter((i) => i.id !== item.id);
    delete state.recordedResolveAt[item.id];
  }

  function recordFailure(send: SendRow, reason: string): void {
    // Deduped: one failure record per hour per send + reason (§9.2b).
    const dupe = state.failures.some(
      (f) => f.send_id === send.id && f.reason === reason && nowMs() - Date.parse(f.at) < 3_600_000,
    );
    if (!dupe) state.failures.push({ send_id: send.id, reason, at: nowIso() });
  }

  function runConsumer(): boolean {
    let changed = false;
    // Settle-first (§9.2a): resolve outstanding claimed sends
    // before claiming or enqueueing anything new.
    for (const send of [...state.sends]) {
      const d = send.dispatch;
      if (!d.consumer || d.delivered_at) continue;
      // A claim whose lease has expired at read time is not
      // in flight (ATT6) — it is an abandoned claim, left as
      // it stands (the seeded stalled send's picture).
      if (d.claim_expires_at && Date.parse(d.claim_expires_at) <= nowMs()) continue;
      const item = state.items.find((i) => i.decision?.send_id === send.id);
      const failReason = FAILING_TARGETS[send.target];
      if (failReason) {
        recordFailure(send, failReason);
        if (item) returnToQueue(item, "failed", `Delivery failed — ${failReason}`);
        changed = true;
      } else {
        // Delivered only via ack by the claiming consumer,
        // carrying the fulfillment's submission reference.
        d.delivered_at = nowIso();
        d.delivery_ref = `sub-${send.id}-${d.attempts}`;
        send.outcome = "delivered";
        if (item) {
          fulfill(item, `Reply delivered to ${handlerOf(item.handle).label} · ref ${d.delivery_ref}`);
        }
        changed = true;
      }
    }
    // Then claim the oldest queued send (shadow sends are
    // never dispatchable — ATT5).
    const next = state.sends.find(
      (s) => s.mode === "active" && s.outcome === "recorded" && !s.dispatch.consumer && !s.dispatch.delivered_at,
    );
    if (next) {
      next.dispatch.consumer = CONSUMER;
      next.dispatch.claimed_at = nowIso();
      next.dispatch.claim_expires_at = new Date(nowMs() + CLAIM_LEASE_MS).toISOString();
      next.dispatch.attempts += 1;
      changed = true;
    }
    // Recorded resolutions: a recorded decision (a snooze,
    // a proposal verdict) clears on the next pass with the
    // effect composed at the tap; a snoozed item's
    // resurface is a future wait-rule surfacing, outside
    // the frozen shapes.
    for (const item of [...state.items]) {
      const rec = state.recordedResolveAt[item.id];
      if (item.decision && rec && rec.tick <= state.tickCount) {
        fulfill(item, rec.effect);
        changed = true;
      }
    }
    // Push-fact feed: the measurement flips, then fulfills.
    if (state.pushFact.flipAtTick !== null && state.tickCount >= state.pushFact.flipAtTick) {
      state.pushFact.state = "pushed";
      state.pushFact.flipAtTick = null;
      changed = true;
    }
    if (state.pushFact.state === "pushed") {
      for (const item of [...state.items]) {
        if (item.decision && item.fulfillment === "push_needed") {
          fulfill(item, "Push measured · pushed");
          changed = true;
        }
      }
    }
    return changed;
  }

  // The seeded stalled decision returns on the first read,
  // exactly as the evaluator would derive it at assembly.
  runEvaluator();

  /** Write-path annotation: which expiry option produced the
   * current expires_at. The served record carries only the
   * absolute timestamp (the backend's shape), and a relative
   * preset ("1h") is indistinguishable from a custom instant
   * once time passes — so the adapter remembers the choice it
   * wrote, keyed by the timestamp it produced. */
  let lastPresenceWrite: { choice: ExpiryChoice; expires_at: string | null } | null = null;

  // ---------- derivations (served ready) ----------

  function resolvePresence(p: PresenceRow): PresenceView {
    // Expiry resolves at read time: an expired non-active
    // mode serves as active (presence schema), and the dead
    // window no longer bounds the served record.
    let mode = p.mode;
    let expires = p.expires_at;
    if (expires && Date.parse(expires) <= nowMs() && mode !== "active") {
      mode = "active";
      expires = null;
    }
    const wp = wallParts(new Date(nowMs()));
    let choice: ExpiryChoice = "none";
    if (expires) {
      if (lastPresenceWrite && lastPresenceWrite.expires_at === expires) {
        // Written through this adapter's write path: the
        // recorded option stays selected as time passes.
        choice = lastPresenceWrite.choice;
      } else {
        // Not written this session (a seed, a served
        // record): exact preset instants map to their
        // preset; any other instant is a custom one.
        const at = Date.parse(expires);
        if (at === scenarioInstant(wp.y, wp.mo, wp.da, 17, 0)) choice = "17:00";
        else if (at === scenarioInstant(wp.y, wp.mo, wp.da, 8, 0) + 86_400_000) choice = "tomorrow-08:00";
        else choice = "custom";
      }
    }
    return {
      mode,
      expires_at: expires,
      expiry_choice: choice,
      expectation: p.expectation,
      chip_label: `${mode[0].toUpperCase()}${mode.slice(1)}${expires ? ` · until ${timeLabel(expires)}` : ""}`,
      chip_severity: mode === "active" ? "ok" : mode === "focus" ? "info" : "warn",
    };
  }

  function itemSeverity(item: OwnerItem): Severity {
    if (item.failure) return "fail";
    if (item.kind === "breakthrough") {
      if (item.due_at && Date.parse(item.due_at) - nowMs() < 60 * 60_000) return "fail";
      return "warn";
    }
    const age = nowMs() - Date.parse(item.waiting_since);
    if (age >= 60 * 60_000) return "fail";
    if (age >= 15 * 60_000) return "warn";
    return "info";
  }

  function handlerSeverity(handle: string): Severity {
    const open = state.items.filter(
      (i) => i.handle === handle && !i.decision && !state.mutedItems.has(i.id),
    );
    if (open.some((i) => itemSeverity(i) === "fail")) return "fail";
    if (open.some((i) => itemSeverity(i) === "warn")) return "warn";
    if (open.length > 0) return "info";
    return "idle";
  }

  function toItemView(item: OwnerItem): ItemView {
    const h = handlerOf(item.handle);
    return {
      id: item.id,
      handle: item.handle,
      handler_label: h.label,
      color_slot: h.color_slot,
      kind: item.kind,
      title: item.title,
      waiting_label: `Waiting ${durationLabel(nowMs() - Date.parse(item.waiting_since))}`,
      severity: handlerSeverity(item.handle),
      verbs: item.verbs,
      options: item.options,
      failure: item.failure ?? null,
      history: item.decision_history,
      due_label: item.due_at ? timeLabel(item.due_at) : null,
      clears_at_source: item.clears_at_source,
      snooze_options: snoozeOptionsFor(),
      rule_hint: shadowHintFor(item),
      proposal: item.proposal ?? null,
    };
  }

  function bandState(item: OwnerItem): BandState {
    if (!item.decision) return "recorded";
    if (item.decision.verb === "snooze" || item.fulfillment !== "send") return "recorded";
    const send = state.sends.find((s) => s.id === item.decision?.send_id);
    return send?.dispatch.consumer ? "sent" : "queued";
  }

  function toAwaitingView(item: OwnerItem): AwaitingView {
    const bs = bandState(item);
    const d = item.decision as DecisionRecord;
    const optLabel = d.option_id
      ? item.options?.find((o) => o.id === d.option_id)?.label
      : null;
    let decided = `Decided ${durationLabel(nowMs() - Date.parse(d.at))} ago · ${optLabel ?? verbLabel(d.verb)}`;
    if (d.verb === "snooze" && item.snooze_return_at) {
      decided += ` · until ${snoozeTimeLabel(item.snooze_return_at)}`;
      if (item.snooze_on_activity) decided += " · or on new activity";
      if (item.resume_note) decided += ` · Resume: ${item.resume_note}`;
    }
    return {
      ...toItemView(item),
      band_state: bs,
      band_label: bs === "queued" ? "Queued" : bs === "sent" ? "Sent · awaiting delivery" : "Recorded",
      decided_label: decided,
      decision: d,
    };
  }

  function openItems(): OwnerItem[] {
    return state.items.filter((i) => !i.decision && !state.mutedItems.has(i.id));
  }

  // The one "waiting on the owner" set. Backend api/1
  // serves this count as glance decision_count and today
  // headline_count: the owner-actionable live items,
  // breakthrough items included — in the backend a
  // breakthrough is a tier over any kind, never an
  // exclusion from the count, and in this store's kind
  // taxonomy the breakthrough kind is the same owner-
  // decision concept (both kinds render as decision rows,
  // take decision verbs and carry the decision subrecord).
  // Every surface that reports how much is waiting on the
  // owner — Today/badge, glance, handlers, programmes,
  // digest — derives from this one set, never a local
  // recount. (The away/night glance is a different,
  // presence-filtered concept: breakthroughs only.)
  function waitingItems(items: OwnerItem[]): OwnerItem[] {
    return items.filter(
      (i) =>
        i.kind === "decision" ||
        i.kind === "breakthrough" ||
        i.kind === "rule_proposal",
    );
  }

  function nextDigest(): { label: string; detail: string; time: string } {
    const enabled = state.digest.windows.filter((w) => w.enabled);
    const p = wallParts(new Date(nowMs()));
    const todayStart = scenarioInstant(p.y, p.mo, p.da, 0, 0);
    const candidates: { at: number; label: string; day: string }[] = [];
    for (const w of enabled) {
      const [h, mi] = w.time.split(":").map(Number);
      const todayAt = todayStart + (h * 60 + mi) * 60_000;
      if (todayAt > nowMs()) candidates.push({ at: todayAt, label: w.label, day: "Today" });
      candidates.push({ at: todayAt + 86_400_000, label: w.label, day: "Tomorrow" });
    }
    candidates.sort((a, b) => a.at - b.at);
    const next = candidates[0];
    if (!next) return { label: "No window enabled", detail: "", time: "" };
    return {
      label: next.label,
      detail: `${next.day} · ${next.label}`,
      time: timeLabel(next.at),
    };
  }

  function digestDetail(at: number): string {
    return `${timeLabel(at)} · in ${durationLabel(at - nowMs())}`;
  }

  function nextDigestAt(): number | null {
    const enabled = state.digest.windows.filter((w) => w.enabled);
    const p = wallParts(new Date(nowMs()));
    const todayStart = scenarioInstant(p.y, p.mo, p.da, 0, 0);
    let best: number | null = null;
    for (const w of enabled) {
      const [h, mi] = w.time.split(":").map(Number);
      const todayAt = todayStart + (h * 60 + mi) * 60_000;
      const at = todayAt > nowMs() ? todayAt : todayAt + 86_400_000;
      if (best === null || at < best) best = at;
    }
    return best;
  }

  // ---------- registry lookups (labels come from the seed) ----------

function statusCodeOf(code: string) {
  return state.registries.status_codes.find((c) => c.code === code) ?? null;
}
function statusLabelOf(code: string): string {
  return statusCodeOf(code)?.label ?? code;
}
function kindLabel(kind: string): string {
  return state.registries.item_kinds.find((k) => k.kind === kind)?.label ?? kind;
}
/** A wait class's display name: the name, title-cased. */
function classLabel(name: string): string {
  const text = name.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
/** Backend waiting_label: "just now" / "N h" / "N days". */
function ageLabel(atIso: string): string {
  const mins = Math.floor((nowMs() - Date.parse(atIso)) / 60_000);
  if (mins < 60) return "just now";
  if (mins < 60 * 24) return `${Math.floor(mins / 60)} h`;
  const days = Math.floor(mins / (60 * 24));
  return days === 1 ? "1 day" : `${days} days`;
}

// ---------- snooze options (served per item) ----------

const weekdayFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
});

/** The snooze choices the backend serves on every item
 * (snooze_options): tomorrow at 9:00 and the next digest
 * window, with return-on-activity offered. Labels ride
 * the view so the panel renders served text. */
function snoozeOptionsFor(): SnoozeOptionsView {
  const p = wallParts(new Date(nowMs()));
  const tomorrowNine = scenarioInstant(p.y, p.mo, p.da, 9, 0) + 86_400_000;
  const times: SnoozeOptionsView["times"] = [
    {
      at: new Date(tomorrowNine).toISOString(),
      label: `${weekdayFmt.format(new Date(tomorrowNine))} · ${timeLabel(tomorrowNine)}`,
    },
  ];
  const nd = nextDigestAt();
  if (nd !== null && nd !== tomorrowNine) {
    times.push({
      at: new Date(nd).toISOString(),
      label: `${weekdayFmt.format(new Date(nd))} · ${timeLabel(nd)}`,
    });
  }
  return { times, on_activity: true };
}

function snoozeTimeLabel(atIso: string): string {
  const found = snoozeOptionsFor().times.find(
    (t) => Date.parse(t.at) === Date.parse(atIso),
  );
  if (found) return found.label;
  return `${weekdayFmt.format(new Date(atIso))} · ${timeLabel(atIso)}`;
}

// ---------- the learning loop (tap counts + action rules) ----------

function waitOf(item: OwnerItem): WaitRow | undefined {
  return item.wait_id
    ? state.waits.find((w) => w.id === item.wait_id)
    : undefined;
}

/** The class a tap counts under: the wait's class when a
 * wait stands behind the item, else the item's kind
 * (backend _count_tap). */
function classOf(item: OwnerItem): string {
  return waitOf(item)?.wait_class ?? item.kind;
}

function createActionRule(args: {
  match: ActionRuleRecord["match"];
  verb: string;
  mode: string;
  created_from: string;
  option_id?: string | null;
}): ActionRuleRecord {
  state.ruleCounter += 1;
  const rule: ActionRuleRecord = {
    id: `tap-${String(state.ruleCounter).padStart(4, "0")}`,
    match: args.match,
    verb: args.verb,
    mode: args.mode,
    created_from: args.created_from,
    at: nowIso(),
    option_id: args.option_id ?? null,
  };
  state.actionRules.push(rule);
  return rule;
}

/** Backend _rule_matches: a stored rule covers this
 * item + verb (a wait_class on the rule never matches
 * here — proposals count under classes, not waits). */
function actionRuleMatches(rule: ActionRuleRecord, item: OwnerItem, verb: string): boolean {
  if (rule.verb !== verb) return false;
  if (rule.match.handle && rule.match.handle !== item.handle) return false;
  if (rule.match.kind && rule.match.kind !== item.kind) return false;
  return true;
}

/** Backend _shadow_hint: a shadow rule that would fire
 * on this item speaks on the item's face. */
function shadowHintFor(item: OwnerItem): string | null {
  for (const rule of state.actionRules) {
    if (rule.mode !== "shadow") continue;
    if (!item.verbs.includes(rule.verb)) continue;
    if (rule.match.wait_class) continue;
    if (rule.match.handle && rule.match.handle !== item.handle) continue;
    if (rule.match.kind && rule.match.kind !== item.kind) continue;
    return `A shadow rule would ${verbLabel(rule.verb).toLowerCase()} this — the tap applies it once.`;
  }
  return null;
}

/** Repetition proposes the rule (D-A7): identical taps
 * counted per handler + class + verb; at the threshold
 * a rule_proposal item surfaces — unless a stored rule
 * already covers the pattern or the proposal is open. */
function countTap(item: OwnerItem, verb: string): void {
  if (!COUNTED_VERBS.has(verb)) return;
  const cls = classOf(item);
  const key = `${item.handle}|${cls}|${verb}`;
  const entry = (state.tapCounts[key] ??= { count: 0, cycles: 0 });
  entry.count += 1;
  if (entry.count < PROPOSAL_THRESHOLD) return;
  if (state.actionRules.some((r) => actionRuleMatches(r, item, verb))) return;
  const id = `${item.handle}:rule-proposal:${cls}:${verb}:${entry.cycles}`;
  if (state.items.some((i) => i.id === id)) return;
  const proposal: ProposalPayload = { cls, verb, count: entry.count, key };
  state.items.push({
    id,
    handle: item.handle,
    wait_id: null,
    kind: "rule_proposal",
    title: `You have tapped ${verbLabel(verb)} on ${cls} items from this lane ${entry.count} times — make it a rule?`,
    detail: "Standing-rule proposal · from your repeated taps",
    waiting_since: nowIso(),
    due_at: null,
    notice_type: null,
    verbs: ["accept_proposal", "reject_proposal"],
    options: null,
    fulfillment: "recorded",
    clears_at_source: false,
    proposal,
    decision: null,
    decision_history: [],
  });
}

// ---------- handler steering ----------

function verbEntry(verb: string): VerbEntry {
  return { verb, label: VERB_LABELS[verb] ?? verb };
}

/** The status's quick verbs (backend quick_verbs_for_status):
 * the primary steering acts ride the status card itself. */
function quickVerbsFor(code: string): VerbEntry[] {
  let verbs: string[] = [];
  if (code === "REVIEW") verbs = ["accept_review", "reject_incomplete"];
  else if (code === "DONE") verbs = ["close"];
  else if (["WORKING", "CONTINUE", "BLOCKED-OWNER", "BLOCKED-HARD"].includes(code))
    verbs = ["park"];
  if (code !== "CLOSED") verbs.push("leave_it");
  return verbs.map(verbEntry);
}

function statusViewOf(handle: string): HandlerStatusView | null {
  const rec = state.statuses[handle];
  if (!rec) return null;
  const code = statusCodeOf(rec.status_code);
  return {
    status_code: rec.status_code,
    status_label: code?.label ?? rec.status_code,
    need: (code?.need as HandlerStatusView["need"]) ?? "unclassified",
    summary: rec.summary,
    at_label: timeLabel(rec.at),
    age_hours: Math.round(((nowMs() - Date.parse(rec.at)) / 3_600_000) * 10) / 10,
    done: rec.done ?? null,
    ongoing: rec.ongoing ?? null,
    tail: rec.tail
      ? rec.tail.map((t) => ({
          kind: t.kind,
          kind_label: kindLabel(t.kind),
          title: t.title,
          owner_label: t.owner === "owner" ? "your tap" : "closeout",
        }))
      : null,
    blockers: rec.blockers
      ? rec.blockers.map((b) => ({
          summary: b.summary,
          clearing_act: b.clearing_act,
          whose_label: b.whose === "hard" ? "hard stop" : "yours",
        }))
      : null,
    quick_verbs: quickVerbsFor(rec.status_code),
    // The mock's statuses carry no workbench refs; it
    // serves no derived line.
    derived: null,
  };
}

/** HANDLER_VERBS minus the status's quick-verb ids: a verb
 * rides exactly one surface (backend build_handler). */
function handlerVerbsFor(handle: string): VerbEntry[] {
  const quick = new Set(quickVerbsFor(state.statuses[handle]?.status_code ?? "").map((v) => v.verb));
  return HANDLER_VERBS.filter((v) => !quick.has(v)).map(verbEntry);
}

function ownerActionsFor(handle: string): OwnerActionView[] {
  return state.ownerActions
    .filter((a) => a.handle === handle)
    .slice(-10)
    .reverse()
    .map((a) => ({
      id: a.id,
      verb: a.verb,
      verb_label: VERB_LABELS[a.verb] ?? a.verb,
      at_label: timeLabel(a.at),
      note: a.note,
      actor_label:
        a.actor === "rule" ? `rule ${a.rule_id ?? ""}`.trim() : "owner",
      shadow: false,
    }));
}

/** The start of the current digest window: the most recent
 * configured window instant at or before now (the ping
 * cooldown's unit, backend _window_start). */
function windowStartMs(): number {
  const now = new Date(nowMs());
  let best = Number.NEGATIVE_INFINITY;
  for (const dayOff of [0, -1]) {
    for (const w of state.digest.windows) {
      const [hh, mm] = w.time.split(":").map(Number);
      const d = new Date(now);
      d.setDate(d.getDate() + dayOff);
      d.setHours(hh, mm, 0, 0);
      if (d.getTime() <= nowMs() && d.getTime() > best) best = d.getTime();
    }
  }
  return best;
}

// ---------- digest content (build_digest, composed) ----------

function topicOf(handle: string): string {
  const bare = handle.replace(/^@/, "");
  return bare.includes("-") ? bare.split("-")[0] : bare;
}

function digestStalls(): DigestContentView["stalls"] {
  const terminal = new Set(
    state.registries.status_codes.filter((c) => c.terminal).map((c) => c.code),
  );
  const stalls: DigestContentView["stalls"] = [];
  for (const h of state.handlers) {
    if (h.retired) continue;
    const rec = state.statuses[h.handle];
    if (!rec || terminal.has(rec.status_code) || rec.status_code === "PARKED")
      continue;
    const ownerBlockers = (rec.blockers ?? []).filter(
      (b) => (b.whose ?? "owner") === "owner",
    );
    if (!ownerBlockers.length) continue;
    const ageH = (nowMs() - Date.parse(rec.at)) / 3_600_000;
    if (ageH > STALL_AFTER_HOURS) {
      stalls.push({
        handle: h.handle,
        handler_label: h.label,
        summary: ownerBlockers[0].summary,
        clearing_act: ownerBlockers[0].clearing_act,
        status_label: statusLabelOf(rec.status_code),
        age_hours: Math.round(ageH * 10) / 10,
        age_label: ageLabel(rec.at),
      });
    }
  }
  return stalls.sort((a, b) => b.age_hours - a.age_hours);
}

const WORST_RANK: Record<string, number> = {
  "BLOCKED-HARD": 0,
  "BLOCKED-OWNER": 0,
  REVIEW: 1,
  WORKING: 2,
  CONTINUE: 2,
  PARKED: 3,
  DONE: 4,
  CLOSED: 5,
};

interface TopicAcc {
  topic: string;
  worst_label: string | null;
  worst_rank: number;
  stalls: number;
  counts: Map<string, number>;
  lanes: DigestContentView["topics"][number]["lanes"];
}

function digestTopics(stalls: DigestContentView["stalls"]): DigestContentView["topics"] {
  const handles = new Set<string>([
    ...Object.keys(state.statuses),
    ...openItems().map((i) => i.handle),
  ]);
  const byTopic = new Map<string, TopicAcc>();
  for (const handle of handles) {
    const topic = topicOf(handle);
    const lane = state.handlers.find((h) => h.handle === handle);
    const rec = state.statuses[handle];
    const entry: TopicAcc = byTopic.get(topic) ?? {
      topic,
      worst_label: null,
      worst_rank: 6,
      stalls: 0,
      counts: new Map<string, number>(),
      lanes: [],
    };
    entry.lanes.push({
      handle,
      label: lane?.label ?? handle,
      status_label: rec ? statusLabelOf(rec.status_code) : null,
      stale: stalls.some((s) => s.handle === handle),
      quick_verbs: rec ? quickVerbsFor(rec.status_code) : [],
    });
    if (stalls.some((s) => s.handle === handle)) entry.stalls += 1;
    if (rec) {
      const rank = WORST_RANK[rec.status_code] ?? 6;
      if (rank < entry.worst_rank) {
        entry.worst_rank = rank;
        entry.worst_label = statusLabelOf(rec.status_code);
      }
    }
    for (const item of openItems()) {
      if (item.handle === handle)
        entry.counts.set(item.kind, (entry.counts.get(item.kind) ?? 0) + 1);
    }
    byTopic.set(topic, entry);
  }
  return [...byTopic.values()]
    .sort((a, b) => a.topic.localeCompare(b.topic))
    .map((t) => ({
      topic: t.topic,
      worst_label: t.worst_label,
      stalls: t.stalls,
      open_counts: [...t.counts.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([kind, count]) => ({ kind, kind_label: kindLabel(kind), count })),
      lanes: [...t.lanes].sort((a, b) => a.handle.localeCompare(b.handle)),
    }));
}

function digestContent(): DigestContentView {
  const stalls = digestStalls();
  const seed = state.digestContent;
  return {
    sections: seed.sections.map((s) => {
      const kindEntry = state.registries.item_kinds.find((k) => k.kind === s.kind);
      const owner = kindEntry?.digest_owner ?? "owner";
      return {
        kind: s.kind,
        kind_label: kindEntry?.label ?? s.kind,
        owner_label: DIGEST_OWNER_LABELS[owner] ?? owner,
        rows: s.rows.map((r) => ({
          title: r.title,
          handle: r.handle,
          handler_label: handlerOf(r.handle).label,
          provenance_label: PROVENANCE_LABELS[r.provenance] ?? r.provenance,
          at_label: timeLabel(r.at),
          age_label: ageLabel(r.at),
        })),
      };
    }),
    stalls,
    staffing: {
      available: seed.staffing.available,
      reason: seed.staffing.reason,
      idle_minutes_total: seed.staffing.idle_minutes_total,
      rows: seed.staffing.rows.map((r) => ({
        topic: r.topic,
        handle: r.handle,
        handler_label: r.handle
          ? handlerOf(r.handle).label
          : (STAFFING_KIND_LABELS[r.kind] ?? r.kind),
        kind: r.kind,
        kind_label: STAFFING_KIND_LABELS[r.kind] ?? r.kind,
        detail: r.detail,
        escalation_label: r.escalation === "main" ? "Escalated to Main" : null,
      })),
    },
    topics: digestTopics(stalls),
    parked_plans: {
      available: seed.parked_plans.available,
      reason: seed.parked_plans.reason,
      plans: seed.parked_plans.plans.map((p) => ({
        title: p.title ?? p.path,
        project: p.project,
        age_label:
          p.age_days === null
            ? ""
            : `waiting ${p.age_days} day${p.age_days === 1 ? "" : "s"}`,
      })),
    },
  };
}

// ---------- rules (rule_view + add_rule + preview) ----------

function titleCaseId(id: string): string {
  return id
    .replace(/-/g, " ")
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** rule_view: the stored rule plus its composed sentences. */
function ruleViewOf(rule: RuleRecord): RuleView {
  const parts: string[] = [];
  const m = rule.match;
  if (m?.wait_class) parts.push(`class is ${classLabel(m.wait_class)}`);
  if (m?.status_code) {
    const codes = Array.isArray(m.status_code) ? m.status_code : [m.status_code];
    parts.push(`status is ${codes.map(statusLabelOf).join(" or ")}`);
  }
  if (m?.kind) parts.push(`kind is ${kindLabel(m.kind)}`);
  if (m?.handle) parts.push(`handler is ${m.handle}`);
  const trig = rule.trigger ?? { on: "on_enter" };
  if (trig.on === "on_age") parts.push(`after ${trig.after_minutes ?? "?"} min`);
  else if (trig.on === "on_repeat") parts.push(`on the ${trig.count ?? "?"}th arrival`);
  else if (trig.on === "on_state_change") parts.push("when the state changes");
  else if (trig.on === "on_presence_enter") parts.push("when the scope is entered");
  if (rule.where) parts.push("+ conditions");
  if (rule.requires?.length) parts.push("with all flags holding");
  const whenLabel = parts.length ? `Wait — ${parts.join(" · ")}` : "Any wait";
  const action = rule.action;
  const head =
    {
      auto_apply: "Auto-apply the decision",
      surface: "Surface it for the owner",
      hold: "Hold it",
      post: "Post",
      post_and_apply: "Post, then auto-apply",
    }[action.type] ?? action.type;
  let thenLabel = action.template ? `${head} · ${action.template}` : head;
  const guards = rule.guards ?? {};
  const bits: string[] = [];
  if (guards.cooldown_minutes != null) bits.push(`cooldown ${guards.cooldown_minutes}m`);
  if (guards.max_posts != null) bits.push(`max posts ${guards.max_posts}`);
  if (guards.escalate_after != null) bits.push(`escalate after ${guards.escalate_after} → Main`);
  if (bits.length) thenLabel += ` · ${bits.join(" · ")}`;
  return {
    ...clone(rule),
    display_name: rule.name || titleCaseId(rule.id),
    when_label: whenLabel,
    then_label: thenLabel,
  };
}

/** normalize_rule, mirrored: a bare-string action becomes
 * {type}; mode defaults to shadow (D-A1: a new rule never
 * acts until it is switched on); trigger, priority, guards
 * and requires take their defaults. */
function normalizeRule(rule: RuleRecord): RuleRecord {
  const out = clone(rule);
  const action = out.action as unknown;
  if (typeof action === "string") out.action = { type: action };
  out.match = {
    wait_class: out.match?.wait_class ?? null,
    status_code: out.match?.status_code ?? null,
    kind: out.match?.kind ?? null,
    handle: out.match?.handle ?? null,
  };
  out.scope = out.scope || "always";
  out.mode = out.mode || "shadow";
  out.on_scope_miss = out.on_scope_miss || "pending";
  out.requires = out.requires ?? [];
  out.priority = out.priority || 100;
  out.trigger = out.trigger?.on ? out.trigger : { on: "on_enter" };
  out.guards = out.guards ?? {};
  return out;
}

/** add_rule's validation, mirrored: the save is refused
 * with the backend's error lines when a field is unknown,
 * a reference does not resolve, or the hard-stop floor is
 * breached (applying rules may not select hard-stop
 * classes — by flat match or by a where leaf). */
function validateRule(rule: RuleRecord): string[] {
  const errors: string[] = [];
  const fields = new Set(state.registries.fields.map((f) => f.name));
  const codes = new Set(state.registries.status_codes.map((c) => c.code));
  const classes = new Map(state.registries.wait_classes.map((c) => [c.name, c.hard_stop]));
  const templates = new Set(state.registries.templates.map((t) => t.kind));
  const actionTypes = new Set(state.registries.actions.map((a) => a.type));
  const triggerKinds = new Set(state.registries.triggers.map((t) => t.on));
  if (!rule.id) errors.push("id is required");
  const action = rule.action ?? ({ type: "auto_apply" } as RuleRecord["action"]);
  if (!actionTypes.has(action.type)) errors.push("action unknown action type");
  if (!["always", "away", "active"].includes(rule.scope))
    errors.push("scope unknown scope");
  if (!["active", "shadow"].includes(rule.mode)) errors.push("mode unknown mode");
  if (!["pending", "fallthrough"].includes(rule.on_scope_miss))
    errors.push("on_scope_miss unknown behaviour");
  if (!triggerKinds.has(rule.trigger?.on ?? "on_enter"))
    errors.push("trigger unknown trigger");
  const m = rule.match ?? ({} as RuleRecord["match"]);
  if (m.wait_class != null && !classes.has(m.wait_class))
    errors.push("match.wait_class unregistered class");
  if (m.status_code != null) {
    const list = Array.isArray(m.status_code) ? m.status_code : [m.status_code];
    if (list.some((c) => !codes.has(c)))
      errors.push("match.status_code unregistered status code");
  }
  const unknownRequires = (rule.requires ?? []).filter((f) => !fields.has(f));
  if (unknownRequires.length)
    errors.push(`requires unknown fields: ${unknownRequires.join(", ")}`);
  for (const leaf of rule.where?.all ?? []) {
    if (!fields.has(leaf.field)) errors.push(`where unknown field: ${leaf.field}`);
  }
  if (["post", "post_and_apply"].includes(action.type)) {
    const kinds = new Set<string>(
      [
        action.template,
        ...Object.values(action.variants?.presence ?? {}),
        ...Object.values(action.variants?.attempt ?? {}),
      ].filter((k): k is string => Boolean(k)),
    );
    const missing = [...kinds].filter((k) => !templates.has(k));
    if (missing.length)
      errors.push(`action.template unknown templates: ${missing.join(", ")}`);
  }
  if (!errors.length && ["auto_apply", "post_and_apply"].includes(action.type)) {
    const selected = new Set<string>();
    if (m.wait_class) selected.add(m.wait_class);
    for (const leaf of rule.where?.all ?? []) {
      if (leaf.field !== "wait_class") continue;
      if (leaf.op === "eq") selected.add(String(leaf.value));
      if (leaf.op === "in" && Array.isArray(leaf.value))
        for (const v of leaf.value) selected.add(String(v));
    }
    if ([...selected].some((name) => classes.get(name)))
      errors.push("rule hard-stop classes may not be applied");
  }
  return errors;
}

function renderTemplate(kind: string, facts: Record<string, unknown>): string {
  const entry = state.registries.templates.find((t) => t.kind === kind);
  if (!entry) return "";
  return entry.text.replace(/\{(\w+)\}/g, (whole, slot: string) =>
    slot in facts ? String(facts[slot] ?? "") : whole,
  );
}

/** The facts a wait carries for rule matching: the wait's
 * registered class + its item's kind, the handler's
 * status, programme membership (the poster flags the
 * scenario carries), and the derived age. */
function waitFacts(wait: WaitRow): Record<string, unknown> {
  const item = state.items.find((i) => i.wait_id === wait.id);
  const status = state.statuses[wait.handle];
  const programme = state.programmes.find((p) => p.handles.includes(wait.handle));
  return {
    wait_class: wait.wait_class,
    status_code: status?.status_code ?? null,
    kind: item?.kind ?? null,
    handle: wait.handle,
    program_approved: Boolean(programme),
    reversible: true,
    in_budget: true,
    only_blocker: false,
    age_minutes: Math.max(0, Math.floor((nowMs() - Date.parse(wait.at)) / 60_000)),
    repeat_count: 1,
    presence: state.presence.mode,
    handler_status_code: status?.status_code ?? null,
    summary: wait.summary,
    scope: programme?.label ?? "",
  };
}

function leafHolds(leaf: { field: string; op: string; value: unknown }, facts: Record<string, unknown>): boolean {
  const actual = facts[leaf.field];
  switch (leaf.op) {
    case "eq": return actual === leaf.value;
    case "ne": return actual !== leaf.value;
    case "in": return Array.isArray(leaf.value) && leaf.value.includes(actual);
    case "not_in": return Array.isArray(leaf.value) && !leaf.value.includes(actual);
    case "gt": return typeof actual === "number" && typeof leaf.value === "number" && actual > leaf.value;
    case "gte": return typeof actual === "number" && typeof leaf.value === "number" && actual >= leaf.value;
    case "lt": return typeof actual === "number" && typeof leaf.value === "number" && actual < leaf.value;
    case "lte": return typeof actual === "number" && typeof leaf.value === "number" && actual <= leaf.value;
    case "exists": return actual !== null && actual !== undefined;
    default: return false;
  }
}

/** Whether the candidate rule matches this wait under the
 * mock's presence scope (trigger kinds that need an event
 * stream — state change, presence enter — never fire in a
 * preview, as in the backend's dry run over stored waits). */
function ruleMatchesWait(rule: RuleRecord, facts: Record<string, unknown>): boolean {
  const m = rule.match;
  if (m?.wait_class && facts.wait_class !== m.wait_class) return false;
  if (m?.kind && facts.kind !== m.kind) return false;
  if (m?.handle && facts.handle !== m.handle) return false;
  if (m?.status_code) {
    const wanted = Array.isArray(m.status_code) ? m.status_code : [m.status_code];
    if (!wanted.includes(facts.status_code as string)) return false;
  }
  for (const leaf of rule.where?.all ?? []) {
    if (!leafHolds(leaf, facts)) return false;
  }
  for (const field of rule.requires ?? []) {
    if (facts[field] !== true) return false;
  }
  if (rule.scope === "away" && state.presence.mode !== "away") return false;
  if (rule.scope === "active" && state.presence.mode === "away") return false;
  const trig = rule.trigger ?? { on: "on_enter" };
  if (trig.on === "on_age") {
    return (facts.age_minutes as number) >= (trig.after_minutes ?? 0);
  }
  if (trig.on === "on_repeat") {
    return (facts.repeat_count as number) >= (trig.count ?? 1);
  }
  if (trig.on !== "on_enter") return false;
  return true;
}

// ---------- the seam ----------

  const api: AttentionDataSource = {
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    getVersion: () => version,
    now: () => new Date(nowMs()),

    getPresence: () => resolvePresence(state.presence),

    setPresence(mode, expiry, customExpiresAt) {
      const p = wallParts(new Date(nowMs()));
      let expires: string | null = null;
      if (expiry === "1h") expires = new Date(nowMs() + 3_600_000).toISOString();
      if (expiry === "17:00") expires = new Date(scenarioInstant(p.y, p.mo, p.da, 17, 0)).toISOString();
      if (expiry === "tomorrow-08:00") {
        const t = new Date(scenarioInstant(p.y, p.mo, p.da, 8, 0) + 86_400_000);
        expires = t.toISOString();
      }
      // A custom expiry arrives as the absolute instant the
      // owner picked — the same expires_at the backend's
      // presence write accepts verbatim.
      if (expiry === "custom") expires = customExpiresAt ?? null;
      state.presence = { mode, expires_at: expires, expectation: EXPECTATIONS[mode] };
      lastPresenceWrite = { choice: expiry, expires_at: expires };
      bump();
    },

    getGlance(night = false) {
      const open = openItems();
      const breakthroughs = open.filter((i) => i.kind === "breakthrough");
      const presence = night
        ? ({
            mode: "away" as PresenceMode,
            expires_at: null,
            expiry_choice: "tomorrow-08:00" as ExpiryChoice,
            expectation: "held for the morning window unless it breaks through",
            chip_label: "Away · until 8:00 AM",
            chip_severity: "warn" as Severity,
          } satisfies PresenceView)
        : resolvePresence(state.presence);
      const nd = nextDigest();
      const dueRows = open
        .filter((i) => i.due_at)
        .sort((a, b) => Date.parse(a.due_at as string) - Date.parse(b.due_at as string))
        .map((i) => ({ label: `${handlerOf(i.handle).label} lease decision`, value: timeLabel(i.due_at as string) }));

      const heldCount = waitingItems(open).length;
      const heldLabel =
        heldCount > 0
          ? `${heldCount} held for your return — everything held surfaces at the next digest, or when you're Active again`
          : null;
      if (night) {
        return {
          clock_label: "11:48",
          date_label: dateFmt.format(new Date(nowMs())),
          presence,
          count: breakthroughs.length,
          count_label: `${breakthroughs.length} needs you`,
          sub_label: presence.expectation,
          next: breakthroughs.map(toItemView),
          rows_label: "Tomorrow",
          rows: [{ label: "Digest window", value: "8:00 AM" }],
          down_sources: [],
          held_label: heldLabel,
        };
      }
      if (presence.mode === "away") {
        // Presence-filtered (contract 09): breakthrough
        // listed, next-due withheld.
        return {
          clock_label: clockFmt.format(new Date(nowMs())),
          date_label: dateFmt.format(new Date(nowMs())),
          presence,
          count: breakthroughs.length,
          count_label: `${breakthroughs.length} needs you`,
          sub_label: presence.expectation,
          next: breakthroughs.map(toItemView),
          rows_label: "Today",
          rows: [{ label: "Digest window", value: nd.time }],
          down_sources: [],
          held_label: heldLabel,
        };
      }
      const waiting = waitingItems(open);
      const pool = [...waiting].sort(
        (a, b) => Date.parse(a.waiting_since) - Date.parse(b.waiting_since),
      );
      const oldest = waiting.length
        ? durationLabel(nowMs() - Math.min(...waiting.map((d) => Date.parse(d.waiting_since))))
        : null;
      return {
        clock_label: clockFmt.format(new Date(nowMs())),
        date_label: dateFmt.format(new Date(nowMs())),
        presence,
        count: waiting.length,
        count_label: `${waiting.length} need you`,
        sub_label:
          presence.mode === "focus"
            ? presence.expectation
            : `decisions waiting${oldest ? ` · oldest ${oldest}` : ""}`,
        next: pool.slice(0, 2).map(toItemView),
        rows_label: "Today",
        rows: [{ label: "Digest window", value: nd.time }, ...dueRows],
        down_sources: [],
        held_label:
          presence.mode === "focus" && waiting.length > 0
            ? `${waiting.length} held while you focus — everything held surfaces at the next digest, or when you're Active again`
            : null,
      };
    },

    getToday(): TodayView {
      const open = openItems();
      const decisions = open
        .filter((i) => i.kind === "decision" || i.kind === "rule_proposal")
        .sort((a, b) => Date.parse(a.waiting_since) - Date.parse(b.waiting_since));
      const nd = nextDigest();
      const fyiVisible = open.filter((i) => {
        if (i.kind !== "fyi") return false;
        const muted = state.handlerSurfaces[i.handle]?.muted_types.find((m) => m.type === i.notice_type);
        return !muted?.muted;
      });
      return {
        date_label: dateFmt.format(new Date(nowMs())),
        subtitle: `${dateFmt.format(new Date(nowMs()))} · next digest window ${nd.time}`,
        presence: resolvePresence(state.presence),
        decision_count: waitingItems(open).length,
        breakthrough: open.filter((i) => i.kind === "breakthrough").map(toItemView),
        decisions: decisions.map(toItemView),
        awaiting: state.items.filter((i) => i.decision).map(toAwaitingView),
        due_today: [
          { label: "Digest window", sub: "All handlers", value: nd.time },
          ...open
            .filter((i) => i.due_at)
            .map((i) => ({ label: i.title, sub: handlerOf(i.handle).label, value: timeLabel(i.due_at as string) })),
        ],
        due_decidable: [],
        waiting_on_others: open.filter((i) => i.kind === "waiting").map(toItemView),
        fyi: {
          count: fyiVisible.length,
          newest_title: fyiVisible.length
            ? [...fyiVisible].sort((a, b) => Date.parse(b.waiting_since) - Date.parse(a.waiting_since))[0].title
            : null,
          items: fyiVisible.map(toItemView),
        },
        unavailable: [],
      };
    },

    getSurfaceHealth(): SurfaceHealth {
      // The mock is in-process: its portions never fail.
      const ok = { state: "ok" as const, last_good_at: null };
      return { glance: ok, today: ok, digest: ok };
    },

    getWriteNotice(): string | null {
      // The mock applies its writes synchronously and
      // returns their real verdicts; nothing is refused
      // behind the caller's back.
      return null;
    },

    getHandlers(): HandlersView {
      const rows = state.handlers
        .filter((h) => !h.retired)
        .map((h) => {
          const open = state.items.filter(
            (i) => i.handle === h.handle && !i.decision && !state.mutedItems.has(i.id),
          );
          const waiting = waitingItems(open).length;
          const surface = state.handlerSurfaces[h.handle];
          const clearable = surface?.agent_clearable ?? 0;
          const mutedCount = surface?.muted_types.filter((m) => m.muted).length ?? 0;
          let sub: string;
          if (waiting > 0) {
            sub = `${waiting} decision${waiting === 1 ? "" : "s"} waiting${clearable ? ` · ${clearable} agent-clearable` : ""}`;
          } else if (open.length > 0) {
            sub = `${open.length} item${open.length === 1 ? "" : "s"} open`;
          } else {
            sub = `Nothing waiting${mutedCount ? ` · ${mutedCount} muted type${mutedCount === 1 ? "" : "s"}` : ""}`;
          }
          return {
            handle: h.handle,
            label: h.label,
            color_slot: h.color_slot,
            icon: h.icon,
            sub_label: sub,
            severity: handlerSeverity(h.handle),
            trailing:
              waiting > 0
                ? { label: `${waiting} waiting`, severity: handlerSeverity(h.handle) }
                : open.length > 0
                  ? { label: `${open.length} open`, severity: "idle" as Severity }
                  : null,
          };
        });
      // The subtitle total is the per-row waiting set
      // summed over the same rows — the one waitingItems
      // derivation, partitioned by handler.
      const totalWaiting = rows.reduce(
        (n, r) =>
          n +
          waitingItems(state.items.filter((i) => i.handle === r.handle && !i.decision)).length,
        0,
      );
      return {
        subtitle: `${rows.length} handlers · ${totalWaiting} decisions waiting`,
        rows,
      };
    },

    getHandlerDetail(handle) {
      const h = state.handlers.find((x) => x.handle === handle);
      if (!h) return null;
      const surface = state.handlerSurfaces[handle];
      const open = state.items.filter(
        (i) => i.handle === handle && !i.decision && !state.mutedItems.has(i.id),
      );
      const waiting = waitingItems(open).length;
      return {
        handler: h,
        subtitle: `${h.label} · ${waiting} decision${waiting === 1 ? "" : "s"} waiting`,
        open_items: open.filter((i) => i.kind !== "fyi" && i.kind !== "waiting").map(toItemView),
        awaiting: state.items.filter((i) => i.handle === handle && i.decision).map(toAwaitingView),
        agent_clearable_label: `${surface?.agent_clearable ?? 0} items`,
        breakthrough_hit_rate: surface?.breakthrough_hit_rate ?? "—",
        muted_types: surface?.muted_types ?? [],
        status: statusViewOf(handle),
        handler_verbs: handlerVerbsFor(handle),
        owner_actions: ownerActionsFor(handle),
        sends: clone(state.sends.filter((s) => s.handle === handle)),
        // The mock's evaluator records no auto-applied
        // log; its rules surface and preview only.
        auto_applied: [],
      };
    },

    getProgrammes(): ProgrammeCardView[] {
      return state.programmes
        .filter((p) => !p.retired)
        .map((p) => {
          const open = state.items.filter(
            (i) => p.handles.includes(i.handle) && !i.decision && !state.mutedItems.has(i.id),
          );
          return {
            slug: p.slug,
            label: p.label,
            handles: p.handles.map((handle) => {
              const h = handlerOf(handle);
              return { handle, label: h.label, color_slot: h.color_slot };
            }),
            cadence_label: `${p.cadence_minutes} min cadence`,
            band_label: `staffing band ${p.staffing_band.min}–${p.staffing_band.max}`,
            escalation_label: `escalates after ${p.escalation_hours} h`,
            venue_label: p.venue === "colab" ? "Colab venue" : "No venue",
            open_decisions: waitingItems(open).length,
            awaiting: state.items.filter((i) => p.handles.includes(i.handle) && i.decision).length,
            rule_text: p.rule_text,
          };
        });
    },

    getDigest(): DigestView {
      const at = nextDigestAt();
      const nd = nextDigest();
      const open = openItems();
      const counts = {
        decisions: waitingItems(open).length,
        waiting: open.filter((i) => i.kind === "waiting").length,
        fyi: api.getToday().fyi.count,
      };
      const parts: string[] = [];
      if (state.digest.include.decisions) parts.push(`${counts.decisions} decisions`);
      if (state.digest.include.waiting) parts.push(`${counts.waiting} waiting`);
      if (state.digest.include.fyi) parts.push(`${counts.fyi} FYI`);
      return {
        windows: state.digest.windows,
        next_label: at ? nd.detail : "No window enabled",
        next_detail: at ? digestDetail(at) : "",
        include: state.digest.include,
        preview_label: parts.length ? `Will include: ${parts.join(" · ")}` : "Will include: nothing — all sections off",
        content: digestContent(),
      };
    },

    setDigestWindow(id, enabled) {
      const w = state.digest.windows.find((x) => x.id === id);
      if (w) {
        w.enabled = enabled;
        bump();
      }
    },

    setDigestInclude(key, enabled) {
      state.digest.include[key] = enabled;
      bump();
    },

    setMutedType(handle, type, muted) {
      const surface = state.handlerSurfaces[handle];
      const row = surface?.muted_types.find((m) => m.type === type);
      if (row) row.muted = muted;
      // The flag and the held items move together (backend
      // triage): muting holds every open item of the type,
      // unmuting releases them back to the queue.
      const heldBefore = state.mutedItems.size;
      for (const item of state.items) {
        if (item.handle !== handle || item.notice_type !== type) continue;
        if (muted) state.mutedItems.add(item.id);
        else state.mutedItems.delete(item.id);
      }
      if (row || state.mutedItems.size !== heldBefore) bump();
    },

    decide(itemId, input: DecideInput): DecideResult {
      // Replay guard 1: an idempotency key short-circuits.
      const seen = state.idempotency[input.idempotency_key];
      if (seen) return seen;

      const item = state.items.find((i) => i.id === itemId);
      if (!item) return { ok: false, error: `unknown item ${itemId}` };
      // Replay guard 2: a repeated tap on a standing decision
      // records and sends nothing. A fulfilled decision is
      // never changed — the item has cleared, so it is not
      // found above and a fresh item would carry a new id.
      if (item.decision) {
        const replayed: DecideResult = { ok: true, decision: item.decision, replayed: true };
        state.idempotency[input.idempotency_key] = replayed;
        return replayed;
      }
      // The verb is validated against the served verb set.
      if (!item.verbs.includes(input.verb)) {
        return { ok: false, error: `verb "${input.verb}" is not served for ${itemId}` };
      }
      if (input.verb === "decide" || input.verb === "rule_it") {
        if (!item.options?.some((o) => o.id === input.option_id)) {
          return { ok: false, error: `option required for ${itemId}` };
        }
      } else if (input.option_id) {
        return { ok: false, error: `option not accepted for verb "${input.verb}"` };
      }
      // Promotion validations run before any effect (the
      // backend's messages, mirrored): approve_rule already
      // promotes, and a hard-stop approval is approved
      // once, never ruled.
      if (input.make_rule && input.verb === "approve_rule") {
        return { ok: false, error: "make_rule: approve_rule already promotes" };
      }
      const wait = waitOf(item);
      const waitClass = wait
        ? state.registries.wait_classes.find((c) => c.name === wait.wait_class)
        : undefined;
      if (input.verb === "approve_rule") {
        if (!wait) {
          return { ok: false, error: "approve_rule: no wait stands behind this item" };
        }
        if (waitClass?.hard_stop) {
          return {
            ok: false,
            error: "hard-stop approvals are approved once, never ruled",
          };
        }
      }
      if (input.make_rule && wait && waitClass?.hard_stop) {
        return {
          ok: false,
          error: "make_rule: a hard-stop approval can never become a rule",
        };
      }

      const at = nowIso();

      // mute_type is a bookmark, not a decision (backend
      // triage): the item and every open item of its type
      // from its handler are held until the type unmutes
      // on the handler's page. No decision is recorded and
      // nothing is sent; the returned record is the tap's
      // receipt only.
      if (input.verb === "mute_type") {
        if (!item.notice_type) {
          return { ok: false, error: "mute_type: this item carries no type" };
        }
        const surface = state.handlerSurfaces[item.handle];
        if (surface) {
          const row = surface.muted_types.find((m) => m.type === item.notice_type);
          if (row) row.muted = true;
          else surface.muted_types.push({ type: item.notice_type, muted: true });
        }
        for (const other of state.items) {
          if (other.handle === item.handle && other.notice_type === item.notice_type) {
            state.mutedItems.add(other.id);
          }
        }
        const result: DecideResult = {
          ok: true,
          decision: {
            verb: "mute_type",
            at,
            option_id: null,
            note: input.note ?? "",
            send_id: null,
          },
          replayed: false,
        };
        state.idempotency[input.idempotency_key] = result;
        bump();
        return result;
      }

      // Proposal verdicts (the learning loop's other
      // half): accepting creates the rule in shadow and
      // resets the counter for its next cycle; rejecting
      // only resets it. Recorded acts — no send is minted.
      if (input.verb === "accept_proposal" || input.verb === "reject_proposal") {
        if (item.kind !== "rule_proposal" || !item.proposal) {
          return { ok: false, error: `${input.verb}: not a rule proposal` };
        }
        const proposal = item.proposal;
        if (input.verb === "accept_proposal") {
          createActionRule({
            match: { handle: item.handle, kind: proposal.cls },
            verb: proposal.verb,
            mode: "shadow",
            created_from: "proposal",
          });
        }
        const entry = state.tapCounts[proposal.key];
        if (entry) {
          entry.count = 0;
          entry.cycles += 1;
        }
        const decision: DecisionRecord = {
          verb: input.verb,
          at,
          option_id: null,
          note: input.note ?? "",
          send_id: null,
        };
        item.decision = decision;
        state.recordedResolveAt[item.id] = {
          tick: state.tickCount + 1,
          effect:
            input.verb === "accept_proposal"
              ? `Rule created · ${verbLabel(proposal.verb)} on ${proposal.cls} items from ${handlerOf(item.handle).label} stands in shadow`
              : "Proposal dismissed · the tap count restarts",
        };
        const result: DecideResult = { ok: true, decision, replayed: false };
        state.idempotency[input.idempotency_key] = result;
        bump();
        return result;
      }

      // approve_rule promotes first, then applies as the
      // approval itself (the backend's verb_effective).
      let verb = input.verb;
      if (verb === "approve_rule") {
        createActionRule({
          match: { handle: item.handle, wait_class: (wait as WaitRow).wait_class },
          verb: "approve",
          mode: "active",
          created_from: "approve_rule",
        });
        verb = "approve";
      }

      const decision: DecisionRecord = {
        verb,
        at,
        option_id:
          input.verb === "decide" || input.verb === "rule_it"
            ? (input.option_id as string)
            : null,
        note: input.note ?? "",
        send_id: null,
      };

      if (input.verb === "snooze") {
        // The snooze payload (backend triage): the return
        // instant must be one of the served times; activity
        // and the resume note ride the item until it
        // resurfaces. Recorded fulfillment: no send.
        const options = snoozeOptionsFor();
        let returnAt = options.times[0]?.at ?? at;
        if (input.return_at) {
          const served = options.times.find(
            (t) => Date.parse(t.at) === Date.parse(input.return_at as string),
          );
          if (!served) {
            return {
              ok: false,
              error: "snooze: the return time is not one of the served times",
            };
          }
          returnAt = served.at;
        }
        const onActivity = input.return_on_activity ?? options.on_activity;
        const resumeNote = input.resume_note ?? (input.note ? input.note : null);
        item.snooze_return_at = returnAt;
        item.snooze_on_activity = onActivity;
        item.resume_note = resumeNote;
        state.recordedResolveAt[item.id] = {
          tick: state.tickCount + 1,
          effect:
            `Snoozed · resurfaces ${snoozeTimeLabel(returnAt)}` +
            (onActivity ? " · or on new activity" : ""),
        };
      } else if (item.fulfillment === "push_needed") {
        // Fulfillment derives from the push-fact feed.
        state.pushFact.flipAtTick = state.tickCount + 2;
      } else {
        // Send-backed: mint through record_send (owner verbs
        // producer class). Reply routing (ATT3): direct to
        // the owning thread; main copied unless the owning
        // handle IS main, which gets the single send.
        const h = handlerOf(item.handle);
        const optLabel = decision.option_id
          ? item.options?.find((o) => o.id === decision.option_id)?.label
          : null;
        const text = `${optLabel ?? verbLabel(verb)} — ${item.title}${decision.note ? ` · ${decision.note}` : ""}`;
        decision.send_id = recordSend({
          handle: item.handle,
          target: h.thread_id,
          template: "decision-reply",
          text,
          wait_id: item.wait_id,
        });
        if (item.handle !== "main") {
          recordSend({
            handle: item.handle,
            target: MAIN_THREAD,
            template: "owner:reply-copy",
            text,
            wait_id: item.wait_id,
          });
        }
        // The decision lands on the wait through the item.
        if (item.wait_id) {
          const wait = state.waits.find((w) => w.id === item.wait_id);
          if (wait) {
            wait.decision = decision.option_id === "hold" ? "owner_denied" : "owner_approved";
            wait.decided_at = at;
            wait.owner_note = decision.note ?? "";
          }
        }
      }

      // rule_it: the pick lands (the send above carries
      // the option's verdict) and the rule stands in
      // shadow from this tap (D-A8's sibling act).
      if (input.verb === "rule_it") {
        createActionRule({
          match: { handle: item.handle, kind: item.kind },
          verb: "decide",
          mode: "shadow",
          created_from: "rule_it",
          option_id: decision.option_id,
        });
      }
      // The deliberate make_rule tap (D-A8): a wait
      // approval promotes to an active rule on its class;
      // anything else promotes to a shadow rule on the
      // item's kind. Hard-stop classes were refused above,
      // and bookmarks never promote (triage consumes them
      // first in the backend, as here).
      if (input.make_rule && !["snooze", "done", "leave_it"].includes(input.verb)) {
        if (wait) {
          createActionRule({
            match: { handle: item.handle, wait_class: wait.wait_class },
            verb: "approve",
            mode: "active",
            created_from: "make_rule",
          });
        } else {
          createActionRule({
            match: { handle: item.handle, kind: item.kind },
            verb: verb,
            mode: "shadow",
            created_from: "make_rule",
            option_id: decision.option_id,
          });
        }
      }

      item.decision = decision;
      item.failure = undefined;
      // Repetition proposes the rule: the tap counts
      // after it lands (bookmarks and promotions are not
      // in the counted set).
      countTap(item, input.verb);
      const result: DecideResult = { ok: true, decision, replayed: false };
      state.idempotency[input.idempotency_key] = result;
      bump();
      return result;
    },

    handlerAction(handle, verb, idempotencyKey): HandlerActionResult {
      // A replayed key returns the standing act: nothing is
      // recorded or sent twice.
      const seen = state.handlerIdempotency[idempotencyKey];
      if (seen) return seen;
      if (!state.handlers.some((h) => h.handle === handle)) {
        return { ok: false, error: "No such handler." };
      }
      const served =
        (HANDLER_VERBS as readonly string[]).includes(verb) ||
        (STATUS_QUICK_VERBS as readonly string[]).includes(verb);
      if (!served) return { ok: false, error: "verb not served for a handler" };
      const h = handlerOf(handle);
      const status = state.statuses[handle];
      const summary = status?.summary || handle;
      // The ping cooldown is checked before anything is
      // recorded: a second ping inside the digest window is
      // a conflict, exactly as the backend raises it.
      if (verb === "status_ping") {
        const mine = state.pings[handle];
        if (mine?.last_at != null && mine.last_at >= windowStartMs()) {
          return {
            ok: false,
            error: "A status ping already went out this digest window.",
          };
        }
      }
      state.actionCounter += 1;
      const actionId = `oa${String(state.actionCounter).padStart(4, "0")}`;
      if (verb === "status_ping") {
        const mine = state.pings[handle] ?? { count: 0, last_at: null };
        mine.count += 1;
        mine.last_at = nowMs();
        state.pings[handle] = mine;
        const kind = mine.count === 1 ? "status-ping" : "status-ping-urgent";
        recordSend({
          handle,
          target: h.thread_id,
          template: kind,
          text: renderTemplate(kind, { summary }),
          wait_id: null,
        });
      } else if (verb === "parallelize") {
        state.ownerDirected[topicOf(handle)] = { at: nowIso(), handle };
        recordSend({
          handle,
          target: h.thread_id,
          template: "parallelize",
          text: renderTemplate("parallelize", { summary }),
          wait_id: null,
        });
      } else if (verb in PASS_VERBS) {
        // A pass commission lands as an agent-clearable
        // action item on the handler, decidable like any
        // other item.
        const title = `${PASS_VERBS[verb]} — ${h.label}`;
        state.items.push({
          id: `${handle}:commission:${verb}:${actionId}`,
          handle,
          wait_id: null,
          kind: "action",
          title,
          detail: "Owner commission",
          waiting_since: nowIso(),
          due_at: null,
          notice_type: null,
          verbs: ["continue", "reply", "snooze", "done", "leave_it"],
          options: null,
          fulfillment: "send",
          clears_at_source: false,
          decision: null,
          decision_history: [],
        });
        recordSend({
          handle,
          target: h.thread_id,
          template: "commission",
          text: renderTemplate("commission", { summary: title }),
          wait_id: null,
        });
      } else if (verb === "leave_it") {
        // A bookmark even at status level: recorded, sends nothing.
      } else {
        // Directed control + the status quick verbs ride the
        // verdict template; the lane's answering status post
        // lands on the next tick.
        recordSend({
          handle,
          target: h.thread_id,
          template: "verdict",
          text: renderTemplate("verdict", {
            summary,
            verb: verbLabel(verb),
            note: "",
          }),
          wait_id: null,
        });
        const next = DIRECTED_STATUS[verb];
        if (next) state.pendingStatus[handle] = next;
      }
      state.ownerActions.push({
        id: actionId,
        handle,
        verb,
        note: "",
        at: nowIso(),
        actor: "owner",
        rule_id: null,
      });
      const result: HandlerActionResult = { ok: true, action_id: actionId, verb };
      state.handlerIdempotency[idempotencyKey] = result;
      bump();
      return result;
    },

    getRegistries(): RegistriesView {
      return {
        status_codes: clone(state.registries.status_codes),
        fields: state.registries.fields.map((f) => ({
          ...f,
          label: classLabel(f.name),
        })),
        wait_classes: state.registries.wait_classes.map((c) => ({
          ...c,
          label: classLabel(c.name),
        })),
        operators: clone(state.registries.operators),
        triggers: clone(state.registries.triggers),
        actions: clone(state.registries.actions),
        templates: clone(state.registries.templates),
        item_kinds: state.registries.item_kinds.map((k) => ({
          ...k,
          digest_owner_label: k.digest_owner
            ? (DIGEST_OWNER_LABELS[k.digest_owner] ?? k.digest_owner)
            : "",
        })),
        handlers: state.handlers
          .filter((h) => !h.retired)
          .map((h) => ({ handle: h.handle, label: h.label, thread_id: h.thread_id })),
      };
    },

    getRules(): RuleView[] {
      return [...state.rules]
        .sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id))
        .map(ruleViewOf);
    },

    saveRule(rule: RuleRecord): RuleSaveResult {
      const stored = normalizeRule(rule);
      const errors = validateRule(stored);
      if (errors.length) {
        return {
          ok: false,
          error: `Rule failed validation. ${errors.join("; ")}`,
        };
      }
      const at = state.rules.findIndex((r) => r.id === stored.id);
      if (at >= 0) state.rules[at] = stored;
      else state.rules.push(stored);
      bump();
      return { ok: true, rule: ruleViewOf(stored) };
    },

    previewRule(rule: RuleRecord): RulePreviewResult {
      const candidate = normalizeRule(rule);
      const errors = validateRule(candidate);
      if (errors.length) {
        return {
          ok: false,
          error: `Rule failed validation. ${errors.join("; ")}`,
        };
      }
      rule = candidate;
      // A dry run over the open waits: the candidate is
      // evaluated as if active; nothing is sent or decided.
      const wouldFire: WouldFire[] = [];
      for (const wait of state.waits) {
        if (wait.decision !== "surfaced") continue;
        const facts = waitFacts(wait);
        if (!ruleMatchesWait(rule, facts)) continue;
        const item = state.items.find((i) => i.wait_id === wait.id);
        if (rule.action.type === "post" || rule.action.type === "post_and_apply") {
          const template = rule.action.template ?? "";
          wouldFire.push({
            wait_id: wait.id,
            action: "post",
            template,
            target: item ? handlerOf(item.handle).thread_id : null,
            text: renderTemplate(template, facts),
          });
        } else {
          wouldFire.push({
            wait_id: wait.id,
            action:
              rule.action.type === "auto_apply"
                ? "owner_approved"
                : rule.action.type === "hold"
                  ? "held"
                  : "surfaced",
            template: null,
            target: null,
            text: null,
          });
        }
      }
      return { ok: true, would_fire: wouldFire };
    },

    getActionRules(): ActionRuleView[] {
      const createdLabels: Record<string, string> = {
        proposal: "From a proposal",
        rule_it: "Ruled standing",
        approve_rule: "Approve + make rule",
        make_rule: "Made a rule",
      };
      return state.actionRules.map((r) => {
        const parts: string[] = [];
        if (r.match.handle) parts.push(`handler is ${r.match.handle}`);
        if (r.match.wait_class) parts.push(`class is ${classLabel(r.match.wait_class)}`);
        if (r.match.kind) parts.push(`kind is ${kindLabel(r.match.kind)}`);
        return {
          id: r.id,
          match_label: parts.join(" · ") || "Any item",
          verb: r.verb,
          verb_label: verbLabel(r.verb),
          mode: r.mode,
          created_from: r.created_from,
          created_label: createdLabels[r.created_from] ?? r.created_from,
          at_label: timeLabel(r.at),
        };
      });
    },

    // The vocab writes (POST /api/v1/vocab/*), mirrored
    // from the backend's writes: required fields and
    // vocabularies validated with its error lines, and a
    // registration replaces an entry of the same id.
    addStatusCode(entry: StatusCodeInput): VocabResult {
      const errors: string[] = [];
      for (const field of ["code", "short", "label", "need"] as const) {
        if (!entry[field]) errors.push(`${field} is required`);
      }
      const needs = ["owner_actionable", "agent_clearable", "unclassified"];
      if (entry.need && !needs.includes(entry.need)) errors.push("need unknown need");
      if (errors.length) {
        return { ok: false, error: `Status code failed validation. ${errors.join("; ")}` };
      }
      state.registries.status_codes = [
        ...state.registries.status_codes.filter((c) => c.code !== entry.code),
        { ...entry },
      ];
      bump();
      return { ok: true };
    },

    addField(entry: FieldInput): VocabResult {
      const errors: string[] = [];
      if (!entry.name) errors.push("name is required");
      if (!entry.type) errors.push("type is required");
      const types = ["bool", "enum", "number", "datetime", "string"];
      if (entry.type && !types.includes(entry.type)) {
        errors.push("type unknown field type");
      }
      if (errors.length) {
        return { ok: false, error: `Field failed validation. ${errors.join("; ")}` };
      }
      state.registries.fields = [
        ...state.registries.fields.filter((f) => f.name !== entry.name),
        { name: entry.name, type: entry.type, source: "poster", poster_settable: true },
      ];
      bump();
      return { ok: true };
    },

    addWaitClass(entry: WaitClassInput): VocabResult {
      if (!entry.name) {
        return { ok: false, error: "Class failed validation. name is required" };
      }
      const existing = state.registries.wait_classes.find((c) => c.name === entry.name);
      if (existing?.hard_stop) {
        return {
          ok: false,
          error: "Class failed validation. name hard-stop classes are not editable",
        };
      }
      state.registries.wait_classes = [
        ...state.registries.wait_classes.filter((c) => c.name !== entry.name),
        { name: entry.name, hard_stop: false },
      ];
      bump();
      return { ok: true };
    },

    addTemplate(entry: TemplateInput): VocabResult {
      const errors: string[] = [];
      if (!entry.kind) errors.push("kind is required");
      if (!entry.text) errors.push("text is required");
      if (!["chat", "main"].includes(entry.audience)) {
        errors.push("audience must be chat or main");
      }
      if (errors.length) {
        return { ok: false, error: `Template failed validation. ${errors.join("; ")}` };
      }
      const prior = state.registries.templates.find((t) => t.kind === entry.kind);
      state.registries.templates = [
        ...state.registries.templates.filter((t) => t.kind !== entry.kind),
        {
          kind: entry.kind,
          version: prior ? prior.version + 1 : 1,
          audience: entry.audience,
          slots: [...entry.slots],
          text: entry.text,
        },
      ];
      bump();
      return { ok: true };
    },

    addItemKind(entry: ItemKindInput): VocabResult {
      const errors: string[] = [];
      if (!entry.kind) errors.push("kind is required");
      if (!entry.label) errors.push("label is required");
      if (
        entry.digest_owner !== null &&
        !["owner", "lane", "self"].includes(entry.digest_owner)
      ) {
        errors.push("digest_owner must be owner, lane, or self");
      }
      if (errors.length) {
        return { ok: false, error: `Item kind failed validation. ${errors.join("; ")}` };
      }
      state.registries.item_kinds = [
        ...state.registries.item_kinds.filter((k) => k.kind !== entry.kind),
        { ...entry },
      ];
      bump();
      return { ok: true };
    },

    tick() {
      state.tickCount += 1;
      // Directed-control answers land first: the lane's
      // answering status post replaces its standing one.
      let answered = false;
      for (const [handle, next] of Object.entries(state.pendingStatus)) {
        state.statuses[handle] = {
          status_code: next.status_code,
          summary: next.summary,
          at: nowIso(),
        };
        answered = true;
      }
      state.pendingStatus = {};
      const a = runEvaluator();
      const b = runConsumer();
      if (answered || a || b) bump();
    },

    getSends: () => clone(state.sends),
  };

  /** Minting is only through record_send (contract 05). */
  function recordSend(args: {
    handle: string;
    target: string;
    template: string;
    text: string;
    wait_id: string | null;
  }): string {
    state.sendCounter += 1;
    const id = `s${String(state.sendCounter).padStart(4, "0")}`;
    const send: SendRow = {
      id,
      at: nowIso(),
      rule_id: null,
      wait_id: args.wait_id,
      handle: args.handle,
      target: args.target,
      template: args.template,
      version: 1,
      attempt: 1,
      presence: resolvePresence(state.presence).mode,
      text: args.text,
      fact_hash: `mock-${id}`,
      mode: "active",
      outcome: "recorded",
      dispatch: {
        attempts: 0,
        claim_expires_at: null,
        claimed_at: null,
        consumer: null,
        delivered_at: null,
        delivery_ref: null,
      },
      bridge_request_id: `bridge-${id}`,
    };
    state.sends.push(send);
    return id;
  }

  return api;
}
