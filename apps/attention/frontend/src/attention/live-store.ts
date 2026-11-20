// The LIVE attention store: AttentionDataSource over the
// attention backend's api/1 (pipeline/attention, served on
// the platform process). The published form's data source —
// the integration entry constructs this store by default;
// the mock store remains the standalone preview's source.
//
// Shape discipline (the sibling adapters' rule): the
// backend's payloads are the shapes of record; this store
// projects them into the app's view types and derives
// nothing the backend serves. Where a view field encodes
// something no route serves, the field serves its honest
// absence and the lane report names it (item detail, the
// fulfilled ledger, the waits list, digest settings writes).
//
// The interface is synchronous (the verdict-at-the-tap
// form), so writes compose their result at the tap from
// the snapshot — validated against the served verb sets,
// options, and registries with the same checks the mock
// mirrors from the backend — and POST in the background;
// the next poll reconciles from the server's state, which
// is always the truth. Idempotency keys short-circuit
// client-side exactly as the mock's guards do.
//
// Refresh model: getters are synchronous over a snapshot
// cache. Poll cadences follow the surface's own shape —
// the glance portions (glance / today / digest) at 15 s,
// handler details and item waits at 30 s, the slow
// registries (registries / rules / programmes / sends) at
// 60 s. One request per portion in flight; a failed fetch
// keeps the last-good portion (stale data, never a blank).
// now() is the real clock — the mock's scenario clock
// stays with the mock.

import type {
  ActionRuleView,
  AttentionDataSource,
  AwaitingView,
  DecideInput,
  DecideResult,
  DecisionRecord,
  DigestView,
  ExpiryChoice,
  FieldInput,
  GlanceView,
  HandlerActionResult,
  HandlerDetailView,
  HandlerRow,
  HandlerStatusView,
  HandlersView,
  ItemKind,
  ItemKindInput,
  ItemView,
  OwnerActionView,
  PresenceMode,
  PresenceView,
  ProgrammeCardView,
  RegistriesView,
  RulePreviewResult,
  RuleRecord,
  RuleSaveResult,
  RuleView,
  SendRow,
  Severity,
  StatusCodeInput,
  SurfaceHealth,
  TemplateInput,
  TodayView,
  VerbEntry,
  VocabResult,
  WaitClassInput,
  WouldFire,
} from "./types";
import { HttpTransport, sanitizeBaseUrl, type AttentionTransport } from "./transport";

// ---------------------------------------------------------------
// The served payloads (api/1, the backend's own forms).

interface ServerPresence {
  mode: PresenceMode;
  mode_label: string;
  expires_at: string | null;
  expectation: string;
}

interface ServerVerb {
  verb: string;
  label: string;
  primary?: boolean;
  rule_hint?: string | null;
  sends?: boolean;
}

interface ServerItem {
  id: string;
  handler: { handle: string; label: string; color_slot: number; icon: string };
  kind: string;
  kind_label: string;
  title: string;
  due_at: string | null;
  waiting_since: string;
  waiting_label: string;
  tier: string;
  need: string;
  triage: string;
  verbs: ServerVerb[];
  options: { id: string; label: string }[] | null;
  wait_id: string | null;
  snooze_options: { times: string[]; on_activity: boolean };
  clears_at_source: boolean;
  decision: {
    verb: string;
    verb_label: string;
    at: string;
    option_id: string | null;
    note: string | null;
    send_id: string | null;
    evidence: string | null;
  } | null;
  fulfillment: { state: string; label: string } | null;
  decision_history: {
    verb: string;
    verb_label: string;
    at: string;
    outcome: string | null;
    option_id: string | null;
    note: string | null;
    send_id: string | null;
  }[];
  resume_note: string | null;
  snooze_return_at: string | null;
  snooze_on_activity: boolean;
  proposal: { cls: string; verb: string; count: number; key: string } | null;
  provenance: string;
  provenance_label: string;
}

interface ServerBand {
  band: string;
  band_label: string;
  collapsed: boolean;
  items: ServerItem[];
  unavailable: { reason: string; last_good_at: string | null } | null;
}

interface ServerToday {
  presence: ServerPresence;
  bands: ServerBand[];
  headline_count: number;
  decided_count: number;
  generated_at: string;
}

interface ServerGlance {
  presence: ServerPresence;
  clock: { now: string; next_window_at: string };
  next_due: { title: string; handler_handle: string; handler_label: string; due_label: string } | null;
  decision_count: number;
  handler_dots: { handle: string; color_slot: number; needs_decision: number }[];
  held_count: number;
  breakthrough_count: number;
  breakthrough_items: { id: string; title: string; handler_label: string }[];
  down_sources: string[];
}

interface ServerDigest {
  generated_at: string;
  window: { next_at: string | null; times?: string[]; enabled_times?: string[] };
  include?: { decisions: boolean; waiting: boolean; fyi: boolean };
  sections: {
    kind: string;
    kind_label: string;
    owner: string;
    owner_label: string;
    rows: {
      title: string;
      handle: string;
      handler_label: string;
      provenance_label: string;
      at: string;
      age_label: string;
    }[];
  }[];
  stalls: {
    handle: string;
    handler_label: string;
    summary: string;
    clearing_act: string | null;
    status_label: string;
    age_hours: number;
    age_label: string;
  }[];
  staffing: {
    available: boolean;
    reason: string | null;
    idle_minutes_total: number;
    rows: {
      topic: string | null;
      handle: string | null;
      handler_label: string;
      kind: string;
      kind_label: string;
      detail: string;
      escalation: string | null;
    }[];
  };
  topics: {
    topic: string;
    worst_label: string | null;
    stalls: number;
    open_counts: { kind: string; kind_label: string; count: number }[];
    lanes: {
      handle: string;
      label: string;
      status_label: string | null;
      stale: boolean;
      quick_verbs: ServerVerb[];
    }[];
  }[];
  parked_plans: {
    available: boolean;
    reason: string | null;
    plans: { title: string | null; path: string | null; project: string; age_days: number | null }[];
  };
}

interface ServerHandlerRow {
  handle: string;
  label: string;
  thread_id: string | null;
  color_slot: number;
  icon: string;
  ui_surface: boolean;
  retired: boolean;
}

interface ServerRegistries {
  status_codes: RegistriesView["status_codes"];
  fields: RegistriesView["fields"];
  wait_classes: RegistriesView["wait_classes"];
  operators: { op: string; label: string }[];
  triggers: { on: string; label: string }[];
  actions: { type: string; label: string }[];
  templates: RegistriesView["templates"];
  item_kinds: RegistriesView["item_kinds"];
  handlers: ServerHandlerRow[];
  action_rules: {
    id: string;
    match: { handle?: string; kind?: string; wait_class?: string; status_code?: string | string[] };
    verb: string;
    mode: string;
    created_from: string;
    at?: string;
    note?: string;
  }[];
}

interface ServerRuleView extends RuleRecord {
  display_name: string;
  when_label: string;
  then_label: string;
}

interface ServerProgramme {
  slug: string;
  label: string;
  handles: string[];
  cadence_minutes: number;
  staffing_band: { min: number; max: number } | null;
  escalation_hours: number;
  venue: string;
  rule_text: string;
  retired: boolean;
}

interface ServerHandlerDetail {
  handle: string;
  label: string;
  items: ServerItem[];
  agent_clearable_count: number;
  muted_types: { kind: string; label: string }[];
  breakthrough_hit_rate: number | null;
  status: (Record<string, unknown> & {
    status_code: string;
    status_label: string;
    need: HandlerStatusView["need"];
    summary: string;
    at: string;
    done?: string[];
    ongoing?: string[];
    tail?: { kind: string; kind_label: string; title: string; owner: string }[];
    blockers?: { summary: string; clearing_act: string | null; whose: string }[];
    quick_verbs: ServerVerb[];
    derived?: {
      available: boolean;
      reason?: string | null;
      last_good_at?: string | null;
      todos: { total: number; done: number; doing: number; blocked: number } | null;
      conflicts?: { message: string }[];
    } | null;
  }) | null;
  handler_verbs: ServerVerb[];
  owner_actions: {
    id: string;
    at: string;
    verb: string;
    verb_label: string;
    note: string;
    actor: string;
    rule_id: string | null;
    shadow?: boolean;
  }[];
  thread_id: string | null;
  sends: ServerSend[];
  auto_applied: {
    at: string;
    wait_id: string | null;
    wait_class: string;
    decision: string;
    decision_label: string;
    rule_id: string | null;
    shadow: boolean;
  }[];
}

interface ServerSend {
  id: string;
  at: string;
  rule_id: string | null;
  wait_id: string | null;
  handle: string;
  target: string;
  template: string;
  version: number;
  attempt: number;
  presence: string;
  fact_hash: string | null;
  text: string;
  mode: "active" | "shadow";
  outcome: string | null;
  dispatch: {
    attempts: number;
    claim_expires_at: string | null;
    claimed_at: string | null;
    consumer: string | null;
    delivered_at: string | null;
    delivery_ref: string | null;
    suppressed_reason?: string | null;
    bridge_request_id?: string | null;
  };
}

interface ServerWait {
  wait_id: string;
  handle: string;
  wait_class: string;
  summary: string;
  decision: string;
  posted_at: string;
  decided_at: string | null;
  owner_note: string | null;
}

// ---------------------------------------------------------------
// Verb vocabulary translation. The frontend's taxonomy is
// the storyboard's ("decide", "approve"); the backend's is
// contract 05's ("pick", "approve_once"). Every other verb
// is spelled the same on both sides.

const TO_FRONTEND_VERB: Record<string, string> = {
  pick: "decide",
  approve_once: "approve",
};
const TO_BACKEND_VERB: Record<string, string> = {
  decide: "pick",
  approve: "approve_once",
};
const frontendVerb = (v: string): string => TO_FRONTEND_VERB[v] ?? v;
const backendVerb = (v: string): string => TO_BACKEND_VERB[v] ?? v;

/** Handler steering verbs (backend HANDLER_VERBS +
 * STATUS_QUICK_VERBS, mirrored as the mock mirrors them). */
const HANDLER_VERBS = new Set([
  "status_ping",
  "parallelize",
  "critic_pass",
  "perf_pass",
  "consolidation_pass",
  "organize_pass",
  "stop",
  "park",
  "resume",
  "continue",
  "go",
  "accept_review",
  "reject_incomplete",
  "close",
  "leave_it",
]);

// ---------------------------------------------------------------
// Time helpers — the real clock, America/New_York wall
// math (the app's zone; DST-correct via Intl).

const NY = "America/New_York";
const timeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});
const dateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  weekday: "long",
  month: "long",
  day: "numeric",
});
const clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  hour: "numeric",
  minute: "2-digit",
  hour12: false,
});
const weekdayFmt = new Intl.DateTimeFormat("en-US", { timeZone: NY, weekday: "short" });
const partsFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
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

function nyParts(d: Date): { y: number; mo: number; da: number; h: number; mi: number; s: number } {
  const out: Record<string, number> = {};
  for (const p of partsFmt.formatToParts(d)) {
    if (p.type !== "literal") out[p.type] = Number(p.value);
  }
  return {
    y: out.year,
    mo: out.month,
    da: out.day,
    h: out.hour % 24,
    mi: out.minute,
    s: out.second,
  };
}

function nyOffsetMs(instantMs: number): number {
  const p = nyParts(new Date(instantMs));
  return Date.UTC(p.y, p.mo - 1, p.da, p.h, p.mi, p.s) - Math.floor(instantMs / 1000) * 1000;
}

/** The instant of a New York wall time (two-pass offset
 * resolution, correct across DST transitions). */
function nyInstant(y: number, mo: number, da: number, h: number, mi: number): number {
  let guess = Date.UTC(y, mo - 1, da, h, mi);
  for (let i = 0; i < 2; i++) guess = Date.UTC(y, mo - 1, da, h, mi) - nyOffsetMs(guess);
  return guess;
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/** A wait class's display name: the name, title-cased
 * (the backend's class_label, mirrored as the mock's). */
function classLabel(name: string): string {
  const text = name.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const FAST_MS = 15_000;
const DETAIL_MS = 30_000;
const SLOW_MS = 60_000;

export class LiveAttentionStore implements AttentionDataSource {
  private readonly baseUrl: string;
  /** The channel every backend call rides (transport.ts):
   * HTTP against the backend origin by default; the
   * rebuild's frame form passes the shell-relay transport.
   * The store's logic is channel-blind below fetchJson. */
  private readonly transport: AttentionTransport;
  private listeners = new Set<() => void>();
  private version = 0;

  private glance: ServerGlance | null = null;
  private today: ServerToday | null = null;
  private digest: ServerDigest | null = null;
  private registries: ServerRegistries | null = null;
  private rules: ServerRuleView[] = [];
  private programmes: ServerProgramme[] = [];
  private sends: ServerSend[] = [];
  private handlerDetails = new Map<string, ServerHandlerDetail>();
  private waits = new Map<string, ServerWait>();
  /** The presence slice: today's payload carries it; a
   * write overrides it until the next fast fetch lands. */
  private presence: ServerPresence | null = null;
  private presenceOverride = false;
  /** Write-path annotation, the mock's own device: which
   * expiry option produced the current expires_at, keyed
   * by the timestamp it produced (a relative preset is
   * indistinguishable from a custom instant once written). */
  private lastPresenceWrite: { choice: ExpiryChoice; expires_at: string | null } | null = null;

  private inflight = new Map<string, Promise<void>>();
  private portionJson = new Map<string, string>();
  /** Per-portion fetch health (the original page's
   * portion() semantics): when a portion last loaded, and
   * whether its latest attempt failed. A portion that has
   * never loaded is down; one failing after a load is
   * stale — the getters keep serving the last good copy
   * and the views tag it, never an affirmative empty. */
  private portionHealth = new Map<string, { lastOkAt: number | null; failing: boolean }>();
  private decideCache = new Map<string, DecideResult>();
  private handlerCache = new Map<string, HandlerActionResult>();
  private previewCache = new Map<string, WouldFire[]>();
  private ownPings = new Map<string, number>();
  /** The latest server-refused write, in words (AC-2):
   * the seam's write results are synchronous and
   * optimistic, so a refusal that arrives with the POST
   * lands here and the shell renders it — a refused act
   * never stands as accepted. Cleared when a later write
   * is accepted. */
  private writeNotice: { text: string; at: number } | null = null;

  private noteWriteRefusal(text: string): void {
    this.writeNotice = { text, at: Date.now() };
    this.bump();
  }
  private lastFastStart = 0;

  constructor(opts: { baseUrl?: string; transport?: AttentionTransport } = {}) {
    this.baseUrl = sanitizeBaseUrl(opts.baseUrl ?? "").replace(/\/$/, "");
    this.transport = opts.transport ?? new HttpTransport(this.baseUrl);
    setInterval(() => void this.refreshFast(), FAST_MS);
    setInterval(() => void this.refreshDetails(), DETAIL_MS);
    setInterval(() => void this.refreshSlow(), SLOW_MS);
    // The clock tick: labels the backend computed at fetch
    // time stay put between polls; the version still turns
    // over so wall-clock derivations (ages, expiry) move.
    setInterval(() => this.bump(), 30_000);
  }

  // ---------- transport ----------

  /** The store's one channel seam: every read and write
   * rides the configured transport (transport.ts), which
   * answers with the payload on a 2xx and throws the
   * failure's sentence otherwise — identically on the
   * HTTP and shell-relay channels. */
  private async fetchJson(path: string, init?: RequestInit): Promise<unknown> {
    return this.transport.request(path, init);
  }

  /** One load per portion in flight; a changed portion
   * bumps the version, a failed one keeps the last-good. */
  private load(key: string, path: string, apply: (data: never) => void): Promise<void> {
    const existing = this.inflight.get(key);
    if (existing) return existing;
    const run = (async () => {
      const health = this.portionHealth.get(key) ?? { lastOkAt: null, failing: false };
      try {
        const data = await this.fetchJson(path);
        const recovered = health.failing;
        health.lastOkAt = Date.now();
        health.failing = false;
        this.portionHealth.set(key, health);
        const json = JSON.stringify(data);
        if (this.portionJson.get(key) !== json) {
          this.portionJson.set(key, json);
          apply(data as never);
          this.bump();
        } else if (recovered) {
          this.bump();
        }
      } catch {
        /* last-good stands; the next poll retries — and
         * the failure is recorded, so the views can say
         * the surface is stale or unreachable instead of
         * presenting the last good copy (or an empty
         * snapshot) as current truth. */
        if (!health.failing) {
          health.failing = true;
          this.portionHealth.set(key, health);
          this.bump();
        }
      } finally {
        this.inflight.delete(key);
      }
    })();
    this.inflight.set(key, run);
    return run;
  }

  private async refreshFast(): Promise<void> {
    this.lastFastStart = Date.now();
    await Promise.all([
      this.load("glance", "/api/v1/glance", (d: ServerGlance) => {
        this.glance = d;
        if (!this.presenceOverride) this.presence = d.presence;
      }),
      this.load("today", "/api/v1/today", (d: ServerToday) => {
        this.today = d;
        if (!this.presenceOverride) this.presence = d.presence;
      }),
      this.load("digest", "/api/v1/digest", (d: ServerDigest) => {
        this.digest = d;
      }),
    ]);
    this.presenceOverride = false;
  }

  private async refreshSlow(): Promise<void> {
    await Promise.all([
      this.load("registries", "/api/v1/registries", (d: ServerRegistries) => {
        this.registries = d;
      }),
      this.load("rules", "/api/v1/rules", (d: { rules: ServerRuleView[] }) => {
        this.rules = d.rules;
      }),
      this.load("programmes", "/api/v1/programmes", (d: { programmes: ServerProgramme[] }) => {
        this.programmes = d.programmes;
      }),
      this.load("sends", "/api/v1/sends", (d: { sends: ServerSend[] }) => {
        this.sends = d.sends;
      }),
    ]);
  }

  private async refreshDetails(): Promise<void> {
    const handles = (this.registries?.handlers ?? []).map((h) => h.handle);
    const jobs: Promise<void>[] = handles.map((handle) =>
      this.load(`handler:${handle}`, `/api/v1/handlers/${encodeURIComponent(handle)}`, (d: ServerHandlerDetail) => {
        this.handlerDetails.set(handle, d);
      }),
    );
    // The waits behind open items: the decide mirror
    // validates promotions against the wait's class.
    const waitIds = new Set<string>();
    for (const band of this.today?.bands ?? []) {
      if (band.band === "decided") continue;
      for (const item of band.items) if (item.wait_id) waitIds.add(item.wait_id);
    }
    for (const waitId of waitIds) {
      jobs.push(
        this.load(`wait:${waitId}`, `/api/v1/agent/waits/${encodeURIComponent(waitId)}`, (d: ServerWait) => {
          this.waits.set(waitId, d);
        }),
      );
    }
    await Promise.all(jobs);
  }

  /** The first load, awaited by the integration entry so
   * the published app never mounts on an empty snapshot.
   * Resolves even when the surface is down — the getters
   * serve their empty forms and polling keeps retrying. */
  async ready(): Promise<void> {
    await this.refreshSlow().catch(() => undefined);
    await this.refreshFast().catch(() => undefined);
    await this.refreshDetails().catch(() => undefined);
  }

  // ---------- seam plumbing ----------

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getVersion = (): number => this.version;

  private bump(): void {
    this.version += 1;
    this.listeners.forEach((fn) => fn());
  }

  now = (): Date => new Date();

  tick = (): void => {
    // AppMain ticks on a short interval (the mock's
    // simulated consumer driver). Live, the tick is a
    // refresh nudge only — the polls own the cadence.
    if (Date.now() - this.lastFastStart >= 10_000) {
      void this.refreshFast();
    }
  };

  // ---------- shared derivations over the snapshot ----------

  private bandItems(band: string): ServerItem[] {
    return this.today?.bands.find((b) => b.band === band)?.items ?? [];
  }

  private allOpenItems(): ServerItem[] {
    const out: ServerItem[] = [];
    for (const band of this.today?.bands ?? []) {
      if (band.band !== "decided") out.push(...band.items);
    }
    return out;
  }

  private findItem(itemId: string): ServerItem | null {
    for (const band of this.today?.bands ?? []) {
      const found = band.items.find((i) => i.id === itemId);
      if (found) return found;
    }
    for (const detail of this.handlerDetails.values()) {
      const found = detail.items.find((i) => i.id === itemId);
      if (found) return found;
    }
    return null;
  }

  private handlerRow(handle: string): ServerHandlerRow | null {
    return this.registries?.handlers.find((h) => h.handle === handle) ?? null;
  }

  /** Verb labels as served (item verbs, handler verbs,
   * quick verbs all carry theirs); the map is the only
   * label source — an unserved verb labels itself. */
  private verbLabelOf(verb: string): string {
    const map = new Map<string, string>();
    const take = (entries: ServerVerb[] | undefined) => {
      for (const e of entries ?? []) if (!map.has(e.verb)) map.set(e.verb, e.label);
    };
    for (const band of this.today?.bands ?? []) {
      for (const item of band.items) take(item.verbs);
    }
    for (const detail of this.handlerDetails.values()) {
      take(detail.handler_verbs);
      take(detail.status?.quick_verbs);
      for (const item of detail.items) take(item.verbs);
    }
    return map.get(verb) ?? map.get(backendVerb(verb)) ?? map.get(frontendVerb(verb)) ?? verb;
  }

  private itemFailure(item: ServerItem): string | null {
    if (item.fulfillment && (item.fulfillment.state === "failed" || item.fulfillment.state === "stalled")) {
      return item.fulfillment.label;
    }
    return null;
  }

  /** The mock's severity derivation, over served fields:
   * a returned item fails its handler; a breakthrough
   * tier warns (fails inside its due hour); age grades
   * the rest. An item's served severity is its handler's
   * aggregate — the mock's own form. */
  private itemSeverity(item: ServerItem): Severity {
    const nowMs = Date.now();
    if (this.itemFailure(item)) return "fail";
    if (item.tier === "breakthrough") {
      if (item.due_at && Date.parse(item.due_at) - nowMs < 3_600_000) return "fail";
      return "warn";
    }
    const age = nowMs - Date.parse(item.waiting_since);
    if (age >= 3_600_000) return "fail";
    if (age >= 900_000) return "warn";
    return "info";
  }

  private handlerSeverity(handle: string): Severity {
    const open = this.allOpenItems().filter((i) => i.handler.handle === handle);
    if (open.some((i) => this.itemSeverity(i) === "fail")) return "fail";
    if (open.some((i) => this.itemSeverity(i) === "warn")) return "warn";
    if (open.length > 0) return "info";
    return "idle";
  }

  private snoozeLabel(atIso: string, options: ServerItem["snooze_options"]): string {
    const match = options.times.find((t) => Date.parse(t) === Date.parse(atIso));
    const at = match ?? atIso;
    return `${weekdayFmt.format(new Date(at))} · ${timeLabel(at)}`;
  }

  private toItemView(item: ServerItem): ItemView {
    const failure = this.itemFailure(item);
    return {
      id: item.id,
      handle: item.handler.handle,
      handler_label: item.handler.label,
      color_slot: item.handler.color_slot,
      kind: item.kind as ItemKind,
      title: item.title,
      waiting_label: `Waiting ${item.waiting_label}`,
      severity: this.handlerSeverity(item.handler.handle),
      verbs: item.verbs.map((v) => frontendVerb(v.verb)),
      options: item.options && item.options.length > 0 ? item.options : null,
      failure,
      history: (item.decision_history ?? []).map((h) => ({
        verb: frontendVerb(h.verb),
        at: h.at,
        option_id: h.option_id,
        note: h.note,
        send_id: h.send_id,
        outcome: (h.outcome ?? "recorded") as "fulfilled" | "failed" | "stalled" | "queued" | "sent" | "recorded",
        failure: undefined,
      })),
      due_label: item.due_at ? timeLabel(item.due_at) : null,
      clears_at_source: item.clears_at_source,
      snooze_options: {
        times: item.snooze_options.times.map((at) => ({
          at,
          label: `${weekdayFmt.format(new Date(at))} · ${timeLabel(at)}`,
        })),
        on_activity: item.snooze_options.on_activity,
      },
      rule_hint: item.verbs.find((v) => v.rule_hint)?.rule_hint ?? null,
      proposal: item.proposal ?? null,
    };
  }

  private toAwaitingView(item: ServerItem): AwaitingView {
    const base = this.toItemView(item);
    const decision = item.decision;
    const state = (item.fulfillment?.state ?? "recorded") as "queued" | "sent" | "recorded";
    const verb = decision ? frontendVerb(decision.verb) : "";
    const optLabel = decision?.option_id
      ? item.options?.find((o) => o.id === decision.option_id)?.label
      : null;
    let decided = decision
      ? `Decided ${durationLabel(Date.now() - Date.parse(decision.at))} ago · ${optLabel ?? this.verbLabelOf(decision.verb)}`
      : "";
    if (decision?.verb === "snooze" && item.snooze_return_at) {
      decided += ` · until ${this.snoozeLabel(item.snooze_return_at, item.snooze_options)}`;
      if (item.snooze_on_activity) decided += " · or on new activity";
      if (item.resume_note) decided += ` · Resume: ${item.resume_note}`;
    }
    return {
      ...base,
      band_state: state,
      band_label: state === "queued" ? "Queued" : state === "sent" ? "Sent · awaiting delivery" : "Recorded",
      decided_label: decided,
      decision: {
        verb,
        at: decision?.at ?? "",
        option_id: decision?.option_id ?? null,
        note: decision?.note ?? null,
        send_id: decision?.send_id ?? null,
      },
    };
  }

  private resolvePresence(p: ServerPresence): PresenceView {
    const nowMs = Date.now();
    let mode = p.mode;
    let expires = p.expires_at;
    if (expires && Date.parse(expires) <= nowMs && mode === "active") {
      // The served mode already resolved the expiry; the
      // dead window no longer bounds the record.
      expires = null;
    }
    let choice: ExpiryChoice = "none";
    if (expires) {
      if (this.lastPresenceWrite && this.lastPresenceWrite.expires_at === expires) {
        choice = this.lastPresenceWrite.choice;
      } else {
        const at = Date.parse(expires);
        const parts = nyParts(new Date(nowMs));
        if (at === nyInstant(parts.y, parts.mo, parts.da, 17, 0)) choice = "17:00";
        else if (at === nyInstant(parts.y, parts.mo, parts.da, 8, 0) + 86_400_000) choice = "tomorrow-08:00";
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

  private emptyPresence(): PresenceView {
    return {
      mode: "active",
      expires_at: null,
      expiry_choice: "none",
      expectation: "",
      chip_label: "Active",
      chip_severity: "ok",
    };
  }

  // ---------- reads ----------

  getSurfaceHealth = (): SurfaceHealth => {
    const portion = (key: string) => {
      const h = this.portionHealth.get(key);
      if (!h || h.lastOkAt === null) return { state: "down" as const, last_good_at: null };
      return {
        state: h.failing ? ("stale" as const) : ("ok" as const),
        last_good_at: new Date(h.lastOkAt).toISOString(),
      };
    };
    return {
      glance: portion("glance"),
      today: portion("today"),
      digest: portion("digest"),
    };
  };

  getPresence = (): PresenceView => {
    return this.presence ? this.resolvePresence(this.presence) : this.emptyPresence();
  };

  getGlance = (night = false): GlanceView => {
    const now = new Date();
    const glance = this.glance;
    const presence = this.getPresence();
    const clockLabel = clockFmt.format(glance ? new Date(glance.clock.now) : now);
    const dateLabel = dateFmt.format(glance ? new Date(glance.clock.now) : now);
    const nextWindow = glance?.clock.next_window_at ?? this.digest?.window.next_at ?? null;
    const windowRow = nextWindow
      ? [{ label: "Digest window", value: timeLabel(nextWindow) }]
      : [];
    const breakthroughItems = this.bandItems("breakthrough").map((i) => this.toItemView(i));

    if (night || presence.mode === "away") {
      // Presence-filtered (contract 09): breakthroughs
      // listed, next-due withheld. The night frame serves
      // the same live set with the real presence and the
      // real clock — the mock's fabricated night persona
      // (a fixed 11:48, an invented away record) has no
      // live counterpart and is not reproduced.
      const held = glance?.held_count ?? 0;
      return {
        clock_label: clockLabel,
        date_label: dateLabel,
        presence,
        count: glance?.breakthrough_count ?? breakthroughItems.length,
        count_label: `${glance?.breakthrough_count ?? breakthroughItems.length} needs you`,
        sub_label: presence.expectation,
        next: breakthroughItems,
        rows_label: night ? "Tomorrow" : "Today",
        rows: windowRow,
        down_sources: glance?.down_sources ?? [],
        held_label:
          held > 0
            ? `${held} held for your return — everything held surfaces at the next digest, or when you're Active again`
            : null,
      };
    }

    const ownerItems = [...this.bandItems("breakthrough"), ...this.bandItems("needs_decision")].sort(
      (a, b) => Date.parse(a.waiting_since) - Date.parse(b.waiting_since),
    );
    const dueRows = this.allOpenItems()
      .filter((i) => i.due_at)
      .sort((a, b) => Date.parse(a.due_at as string) - Date.parse(b.due_at as string))
      .map((i) => ({ label: i.title, value: timeLabel(i.due_at as string) }));
    const oldest = ownerItems.length
      ? durationLabel(Date.now() - Math.min(...ownerItems.map((i) => Date.parse(i.waiting_since))))
      : null;
    const count = glance?.decision_count ?? ownerItems.length;
    return {
      clock_label: clockLabel,
      date_label: dateLabel,
      presence,
      count,
      count_label: `${count} need you`,
      sub_label:
        presence.mode === "focus"
          ? presence.expectation
          : `decisions waiting${oldest ? ` · oldest ${oldest}` : ""}`,
      next: ownerItems.slice(0, 2).map((i) => this.toItemView(i)),
      rows_label: "Today",
      rows: [...windowRow, ...dueRows],
      down_sources: glance?.down_sources ?? [],
      held_label:
        presence.mode === "focus" && (glance?.held_count ?? 0) > 0
          ? `${glance?.held_count} held while you focus — everything held surfaces at the next digest, or when you're Active again`
          : null,
    };
  };

  getToday = (): TodayView => {
    const now = new Date();
    const nextWindow = this.digest?.window.next_at ?? this.glance?.clock.next_window_at ?? null;
    const dateLabel = dateFmt.format(now);
    const fyiItems = this.bandItems("fyi");
    const newestFyi = fyiItems.length
      ? [...fyiItems].sort((a, b) => Date.parse(b.waiting_since) - Date.parse(a.waiting_since))[0]
      : null;
    return {
      date_label: dateLabel,
      subtitle: `${dateLabel} · next digest window ${nextWindow ? timeLabel(nextWindow) : "—"}`,
      presence: this.getPresence(),
      decision_count: this.today?.headline_count ?? 0,
      breakthrough: this.bandItems("breakthrough").map((i) => this.toItemView(i)),
      decisions: this.bandItems("needs_decision").map((i) => this.toItemView(i)),
      awaiting: this.bandItems("decided").map((i) => this.toAwaitingView(i)),
      // Bands are exclusive: a decidable item due today
      // stands here, not in needs_decision. Items carrying
      // verbs render as decision cards (due_decidable);
      // only the rest stay plain schedule rows.
      due_decidable: this.bandItems("due_today")
        .filter((i) => i.verbs.length > 0)
        .map((i) => this.toItemView(i)),
      due_today: [
        { label: "Digest window", sub: "All handlers", value: nextWindow ? timeLabel(nextWindow) : "—" },
        ...this.bandItems("due_today")
          .filter((i) => i.verbs.length === 0)
          .map((i) => ({
            label: i.title,
            sub: i.handler.label,
            value: i.due_at ? timeLabel(i.due_at) : "",
          })),
      ],
      waiting_on_others: this.bandItems("waiting").map((i) => this.toItemView(i)),
      fyi: {
        count: fyiItems.length,
        newest_title: newestFyi ? newestFyi.title : null,
        items: fyiItems.map((i) => this.toItemView(i)),
      },
      // The bands' served unavailability, verbatim: the
      // view renders the warning where the original did —
      // a down source's items are missing from this
      // picture and the picture must say so.
      unavailable: (this.today?.bands ?? [])
        .filter((b) => b.unavailable)
        .map((b) => ({
          reason: b.unavailable?.reason ?? "",
          last_good_label: b.unavailable?.last_good_at
            ? `${weekdayFmt.format(new Date(b.unavailable.last_good_at))} · ${timeLabel(b.unavailable.last_good_at)}`
            : "an earlier copy",
        })),
    };
  };

  getHandlers = (): HandlersView => {
    const rows = (this.registries?.handlers ?? [])
      .filter((h) => !h.retired)
      .map((h) => {
        const open = this.allOpenItems().filter((i) => i.handler.handle === h.handle);
        const waiting = open.filter(
          (i) => i.tier === "breakthrough" || this.bandItems("needs_decision").includes(i),
        ).length;
        const detail = this.handlerDetails.get(h.handle);
        const clearable = detail?.agent_clearable_count ?? 0;
        const mutedCount = detail?.muted_types.length ?? 0;
        let sub: string;
        if (waiting > 0) {
          sub = `${waiting} decision${waiting === 1 ? "" : "s"} waiting${clearable ? ` · ${clearable} agent-clearable` : ""}`;
        } else if (open.length > 0) {
          sub = `${open.length} item${open.length === 1 ? "" : "s"} open`;
        } else {
          sub = `Nothing waiting${mutedCount ? ` · ${mutedCount} muted type${mutedCount === 1 ? "" : "s"}` : ""}`;
        }
        const severity = this.handlerSeverity(h.handle);
        return {
          handle: h.handle,
          label: h.label,
          color_slot: h.color_slot,
          icon: h.icon,
          sub_label: sub,
          severity,
          trailing:
            waiting > 0
              ? { label: `${waiting} waiting`, severity }
              : open.length > 0
                ? { label: `${open.length} open`, severity: "idle" as Severity }
                : null,
        };
      });
    const totalWaiting = rows.reduce((n, r) => {
      const m = /^(\d+) waiting$/.exec(r.trailing?.label ?? "");
      return n + (m ? Number(m[1]) : 0);
    }, 0);
    return {
      subtitle: `${rows.length} handlers · ${totalWaiting} decisions waiting`,
      rows,
    };
  };

  getHandlerDetail = (handle: string): HandlerDetailView | null => {
    const row = this.handlerRow(handle);
    if (!row) return null;
    const detail = this.handlerDetails.get(handle);
    if (!detail) void this.refreshDetails();
    const openSource = detail?.items ?? this.allOpenItems().filter((i) => i.handler.handle === handle);
    // The backend serves every live item for the handler,
    // FYI tier included — no client-side tier filter.
    const openItems = openSource;
    const waiting = openItems.filter(
      (i) => i.need === "owner_actionable",
    ).length;
    const status: HandlerStatusView | null = detail?.status
      ? {
          status_code: detail.status.status_code,
          status_label: detail.status.status_label,
          need: detail.status.need,
          summary: detail.status.summary,
          at_label: timeLabel(detail.status.at),
          age_hours: Math.round(((Date.now() - Date.parse(detail.status.at)) / 3_600_000) * 10) / 10,
          done: detail.status.done ?? null,
          ongoing: detail.status.ongoing ?? null,
          tail: (detail.status.tail ?? []).map((t) => ({
            kind: t.kind,
            kind_label: t.kind_label,
            title: t.title,
            owner_label: t.owner === "owner" ? "your tap" : "closeout",
          })),
          blockers: (detail.status.blockers ?? []).map((b) => ({
            summary: b.summary,
            clearing_act: b.clearing_act,
            whose_label: b.whose === "hard" ? "hard stop" : "yours",
          })),
          quick_verbs: (detail.status.quick_verbs ?? []).map((v) => ({
            verb: v.verb,
            label: v.label,
            primary: v.primary,
            rule_hint: v.rule_hint ?? null,
          })),
          derived: detail.status.derived
            ? {
                label: !detail.status.derived.available
                  ? `Workbench state unavailable — ${detail.status.derived.reason ?? ""}${
                      detail.status.derived.last_good_at
                        ? ` · last good ${timeLabel(detail.status.derived.last_good_at)}`
                        : ""
                    }`
                  : detail.status.derived.todos
                    ? `Workbench — ${detail.status.derived.todos.done}/${detail.status.derived.todos.total} todos done${
                        detail.status.derived.todos.blocked
                          ? ` · ${detail.status.derived.todos.blocked} blocked`
                          : ""
                      }${
                        detail.status.derived.todos.doing
                          ? ` · ${detail.status.derived.todos.doing} in progress`
                          : ""
                      }`
                    : "",
                conflicts: (detail.status.derived.conflicts ?? []).map((c) => c.message),
              }
            : null,
        }
      : null;
    const ownerActions: OwnerActionView[] = [...(detail?.owner_actions ?? [])]
      .slice(-10)
      .reverse()
      .map((a) => ({
        id: a.id,
        verb: a.verb,
        verb_label: a.verb_label,
        at_label: timeLabel(a.at),
        note: a.note,
        actor_label: a.actor === "rule" ? `rule ${a.rule_id ?? ""}`.trim() : a.actor,
        shadow: a.shadow ?? false,
      }));
    return {
      handler: {
        handle: row.handle,
        label: row.label,
        color_slot: row.color_slot,
        icon: row.icon,
        thread_id: row.thread_id ?? "",
        ui_surface: row.ui_surface,
        retired: row.retired,
      },
      subtitle: `${row.label} · ${waiting} decision${waiting === 1 ? "" : "s"} waiting`,
      open_items: openItems.map((i) => this.toItemView(i)),
      awaiting: this.bandItems("decided")
        .filter((i) => i.handler.handle === handle)
        .map((i) => this.toAwaitingView(i)),
      agent_clearable_label: `${detail?.agent_clearable_count ?? 0} items`,
      breakthrough_hit_rate:
        detail?.breakthrough_hit_rate == null
          ? "—"
          : `${Math.round(detail.breakthrough_hit_rate * 100)}%`,
      muted_types: (detail?.muted_types ?? []).map((m) => ({ type: m.label, muted: true })),
      status,
      handler_verbs: (detail?.handler_verbs ?? []).map((v) => ({
        verb: v.verb,
        label: v.label,
        primary: v.primary,
        rule_hint: v.rule_hint ?? null,
      })),
      owner_actions: ownerActions,
      sends: (detail?.sends ?? []).map((s) => this.toSendRow(s)),
      auto_applied: (detail?.auto_applied ?? []).map((a) => ({
        at: a.at,
        wait_class: a.wait_class,
        decision_label: a.decision_label,
        rule_id: a.rule_id,
        shadow: a.shadow,
      })),
    };
  };

  getProgrammes = (): ProgrammeCardView[] => {
    return this.programmes
      .filter((p) => !p.retired)
      .map((p) => {
        const inProgramme = (i: ServerItem) => p.handles.includes(i.handler.handle);
        const openDecisions = [
          ...this.bandItems("breakthrough"),
          ...this.bandItems("needs_decision"),
        ].filter(inProgramme).length;
        const awaiting = this.bandItems("decided").filter(inProgramme).length;
        return {
          slug: p.slug,
          label: p.label,
          handles: p.handles.map((handle) => {
            const h = this.handlerRow(handle);
            return { handle, label: h?.label ?? handle, color_slot: h?.color_slot ?? 0 };
          }),
          cadence_label: `${p.cadence_minutes} min cadence`,
          band_label: p.staffing_band
            ? `staffing band ${p.staffing_band.min}–${p.staffing_band.max}`
            : "staffing band —",
          escalation_label: `escalates after ${p.escalation_hours} h`,
          venue_label: p.venue === "colab" ? "Colab venue" : "No venue",
          open_decisions: openDecisions,
          awaiting,
          rule_text: p.rule_text,
        };
      });
  };

  getDigest = (): DigestView => {
    const digest = this.digest;
    const nextAt = digest?.window.next_at ?? this.glance?.clock.next_window_at ?? null;
    const times = digest?.window.times ?? [];
    const enabledTimes = digest?.window.enabled_times;
    const windows = times.map((time) => {
      const hour = Number(time.split(":")[0]);
      return {
        id: time,
        label: hour < 11 ? "Morning" : hour < 15 ? "Midday" : "Evening",
        time,
        enabled: enabledTimes ? enabledTimes.includes(time) : true,
      };
    });
    // The next window's label + day, from the served
    // next_at's own wall fields (the server's zone rides
    // the ISO) matched against the served window times.
    let nextLabel = "No window enabled";
    let nextDetail = "";
    if (nextAt) {
      const wall = /T(\d{2}):(\d{2})/.exec(nextAt);
      const match = wall ? windows.find((w) => w.time === `${wall[1]}:${wall[2]}`) : undefined;
      const serverNow = this.glance?.clock.now;
      const sameDay = serverNow ? serverNow.slice(0, 10) === nextAt.slice(0, 10) : true;
      nextLabel = match ? `${sameDay ? "Today" : "Tomorrow"} · ${match.label}` : timeLabel(nextAt);
      nextDetail = `${timeLabel(nextAt)} · in ${durationLabel(Date.parse(nextAt) - Date.now())}`;
    }
    const today = this.getToday();
    const counts = {
      decisions: today.decision_count,
      waiting: today.waiting_on_others.length,
      fyi: today.fyi.count,
    };
    // The include flags are the server's stored prefs
    // (AC-8): the preview composes from the served flags
    // and the live counts — arithmetic over served data.
    const include = digest?.include ?? { decisions: true, waiting: true, fyi: true };
    const parts: string[] = [];
    if (include.decisions) parts.push(`${counts.decisions} decisions`);
    if (include.waiting) parts.push(`${counts.waiting} waiting`);
    if (include.fyi) parts.push(`${counts.fyi} FYI`);
    return {
      windows,
      next_label: nextLabel,
      next_detail: nextDetail,
      include,
      preview_label: parts.length
        ? `Will include: ${parts.join(" · ")}`
        : "Will include: nothing — all sections off",
      content: {
        sections: (digest?.sections ?? []).map((s) => ({
          kind: s.kind,
          kind_label: s.kind_label,
          owner_label: s.owner_label,
          rows: s.rows.map((r) => ({
            title: r.title,
            handle: r.handle,
            handler_label: r.handler_label,
            provenance_label: r.provenance_label,
            at_label: timeLabel(r.at),
            age_label: r.age_label,
          })),
        })),
        stalls: digest?.stalls ?? [],
        staffing: {
          available: digest?.staffing.available ?? false,
          reason: digest?.staffing.reason ?? null,
          idle_minutes_total: digest?.staffing.idle_minutes_total ?? 0,
          rows: (digest?.staffing.rows ?? []).map((r) => ({
            topic: r.topic,
            handle: r.handle,
            handler_label: r.handler_label || r.kind_label,
            kind: r.kind,
            kind_label: r.kind_label,
            detail: r.detail,
            escalation_label: r.escalation === "main" ? "Escalated to Main" : null,
          })),
        },
        topics: (digest?.topics ?? []).map((t) => ({
          topic: t.topic,
          worst_label: t.worst_label,
          stalls: t.stalls,
          open_counts: t.open_counts,
          lanes: t.lanes.map((l) => ({
            handle: l.handle,
            label: l.label,
            status_label: l.status_label,
            stale: l.stale,
            quick_verbs: l.quick_verbs.map((v) => ({
              verb: v.verb,
              label: v.label,
              primary: v.primary,
              rule_hint: v.rule_hint ?? null,
            })),
          })),
        })),
        parked_plans: {
          available: digest?.parked_plans.available ?? false,
          reason: digest?.parked_plans.reason ?? null,
          plans: (digest?.parked_plans.plans ?? []).map((p) => ({
            title: p.title ?? p.path ?? "",
            project: p.project,
            age_label:
              p.age_days === null || p.age_days === undefined
                ? ""
                : `waiting ${p.age_days} day${p.age_days === 1 ? "" : "s"}`,
          })),
        },
      },
    };
  };

  getRegistries = (): RegistriesView => {
    const r = this.registries;
    return {
      status_codes: r?.status_codes ?? [],
      fields: r?.fields ?? [],
      wait_classes: r?.wait_classes ?? [],
      operators: r?.operators ?? [],
      triggers: r?.triggers ?? [],
      actions: r?.actions ?? [],
      templates: r?.templates ?? [],
      item_kinds: r?.item_kinds ?? [],
      handlers: (r?.handlers ?? []).map((h) => ({
        handle: h.handle,
        label: h.label,
        thread_id: h.thread_id ?? "",
      })),
    };
  };

  getRules = (): RuleView[] => {
    return [...this.rules]
      .sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id))
      .map((r) => ({ ...r, name: r.name ?? null }));
  };

  getActionRules = (): ActionRuleView[] => {
    const createdLabels: Record<string, string> = {
      proposal: "From a proposal",
      rule_it: "Ruled standing",
      approve_rule: "Approve + make rule",
      make_rule: "Made a rule",
    };
    const statusLabel = (code: string) =>
      this.registries?.status_codes.find((c) => c.code === code)?.label ?? code;
    const kindLabel = (kind: string) =>
      this.registries?.item_kinds.find((k) => k.kind === kind)?.label ?? kind;
    return (this.registries?.action_rules ?? []).map((r) => {
      const parts: string[] = [];
      if (r.match.handle) parts.push(`handler is ${r.match.handle}`);
      if (r.match.wait_class) parts.push(`class is ${classLabel(r.match.wait_class)}`);
      if (r.match.kind) parts.push(`kind is ${kindLabel(r.match.kind)}`);
      if (r.match.status_code) {
        const codes = Array.isArray(r.match.status_code) ? r.match.status_code : [r.match.status_code];
        parts.push(`status is ${codes.map(statusLabel).join(" or ")}`);
      }
      return {
        id: r.id,
        match_label: parts.join(" · ") || "Any item",
        verb: r.verb,
        verb_label: this.verbLabelOf(r.verb),
        mode: r.mode,
        created_from: r.created_from,
        created_label: createdLabels[r.created_from] ?? r.created_from,
        at_label: r.at ? timeLabel(r.at) : "",
      };
    });
  };

  private toSendRow(s: ServerSend): SendRow {
    return {
      id: s.id,
      at: s.at,
      rule_id: s.rule_id,
      wait_id: s.wait_id,
      handle: s.handle,
      target: s.target,
      template: s.template,
      version: s.version,
      attempt: s.attempt,
      presence: s.presence,
      text: s.text,
      fact_hash: s.fact_hash ?? "",
      mode: s.mode,
      outcome: s.outcome ?? "",
      dispatch: {
        attempts: s.dispatch.attempts,
        claim_expires_at: s.dispatch.claim_expires_at,
        claimed_at: s.dispatch.claimed_at,
        consumer: s.dispatch.consumer,
        delivered_at: s.dispatch.delivered_at,
        delivery_ref: s.dispatch.delivery_ref,
        suppress_reason: s.dispatch.suppressed_reason ?? undefined,
      },
      bridge_request_id: s.dispatch.bridge_request_id ?? undefined,
    };
  }

  getSends = (): SendRow[] => {
    return this.sends.map((s) => this.toSendRow(s));
  };

  // ---------- writes ----------

  /** One write. `act` names the act for the refusal
   * notice ("That decision"); `onRefusal` replaces the
   * default notice when the caller must also unwind its
   * optimistic state (idempotency caches, ping marks). */
  private post(
    path: string,
    body: unknown,
    after?: () => void,
    act = "That write",
    onRefusal?: (message: string) => void,
  ): void {
    void (async () => {
      try {
        await this.fetchJson(path, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        if (this.writeNotice) {
          this.writeNotice = null;
          this.bump();
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (onRefusal) onRefusal(message);
        else this.noteWriteRefusal(`${act} was not saved — the server refused it: ${message}`);
      } finally {
        after?.();
        void this.refreshFast();
      }
    })();
  }

  getWriteNotice = (): string | null => this.writeNotice?.text ?? null;

  setPresence = (mode: PresenceMode, expiry: ExpiryChoice, customExpiresAt?: string | null): void => {
    const nowMs = Date.now();
    const parts = nyParts(new Date(nowMs));
    let expires: string | null = null;
    if (expiry === "1h") expires = new Date(nowMs + 3_600_000).toISOString();
    if (expiry === "17:00") expires = new Date(nyInstant(parts.y, parts.mo, parts.da, 17, 0)).toISOString();
    if (expiry === "tomorrow-08:00") {
      expires = new Date(nyInstant(parts.y, parts.mo, parts.da, 8, 0) + 86_400_000).toISOString();
    }
    if (expiry === "custom") expires = customExpiresAt ?? null;
    // The write carries the owner's standing expectation
    // text verbatim — the backend's write replaces the
    // record, and a mode/expiry change is not an
    // expectation edit.
    const expectation = this.presence?.expectation ?? "";
    this.lastPresenceWrite = { choice: expiry, expires_at: expires };
    this.presence = { mode, mode_label: mode, expires_at: expires, expectation };
    this.presenceOverride = true;
    this.bump();
    this.post("/api/v1/presence", { mode, expires_at: expires, expectation }, () => {
      this.presenceOverride = false;
    }, "That presence change");
  };

  setDigestWindow = (id: string, enabled: boolean): void => {
    // A real server write (AC-8): the prefs live on the
    // backend's state, and the served digest's window —
    // next_at, the glance clock, the snooze times — reads
    // them. The shell Settings row drives this same path.
    this.post("/api/v1/digest/prefs", { window_time: id, window_enabled: enabled }, undefined, "That digest window change");
  };

  setDigestInclude = (key: "decisions" | "waiting" | "fyi", enabled: boolean): void => {
    this.post("/api/v1/digest/prefs", { include_key: key, include_enabled: enabled }, undefined, "That digest include change");
  };

  setMutedType = (handle: string, type: string, muted: boolean): void => {
    const detail = this.handlerDetails.get(handle);
    // The served muted_types carry their kind; an
    // unlisted type resolves through the registries'
    // item-kind labels. Unresolvable is refused aloud.
    const kind =
      detail?.muted_types.find((m) => m.label === type)?.kind ??
      this.registries?.item_kinds.find((k) => k.label === type)?.kind;
    if (!kind) {
      this.noteWriteRefusal(`That type is not served for ${handle}.`);
      return;
    }
    this.post(
      `/api/v1/handlers/${encodeURIComponent(handle)}/${muted ? "mute" : "unmute"}`,
      { kind },
      () => {
        void this.refreshDetails();
      },
      muted ? "That mute" : "That unmute",
    );
  };

  decide = (itemId: string, input: DecideInput): DecideResult => {
    const seen = this.decideCache.get(input.idempotency_key);
    if (seen) return seen;
    const fail = (error: string): DecideResult => ({ ok: false, error });

    const item = this.findItem(itemId);
    if (!item) return fail(`unknown item ${itemId}`);

    // A standing decision in an open fulfillment state
    // replays: the verdict already stands, nothing is
    // recorded or sent twice. A returned item (failed /
    // stalled) is decidable again, as on the backend.
    const standing = item.decision;
    const fulfillmentState = item.fulfillment?.state ?? null;
    if (standing && (fulfillmentState === null || ["queued", "sent", "recorded"].includes(fulfillmentState))) {
      const replayed: DecideResult = {
        ok: true,
        decision: {
          verb: frontendVerb(standing.verb),
          at: standing.at,
          option_id: standing.option_id,
          note: standing.note ?? "",
          send_id: standing.send_id,
        },
        replayed: true,
      };
      this.decideCache.set(input.idempotency_key, replayed);
      return replayed;
    }

    const view = this.toItemView(item);
    if (!view.verbs.includes(input.verb)) {
      return fail(`verb "${input.verb}" is not served for ${itemId}`);
    }
    if (input.verb === "decide" || input.verb === "rule_it") {
      if (!view.options?.some((o) => o.id === input.option_id)) {
        return fail(`option required for ${itemId}`);
      }
    } else if (input.option_id) {
      return fail(`option not accepted for verb "${input.verb}"`);
    }
    if (input.make_rule && input.verb === "approve_rule") {
      return fail("make_rule: approve_rule already promotes");
    }
    const wait = item.wait_id ? this.waits.get(item.wait_id) : undefined;
    const waitClass = wait
      ? this.registries?.wait_classes.find((c) => c.name === wait.wait_class)
      : undefined;
    if (input.verb === "approve_rule") {
      if (!wait) return fail("approve_rule: no wait stands behind this item");
      if (waitClass?.hard_stop) {
        return fail("hard-stop approvals are approved once, never ruled");
      }
    }
    if (input.make_rule && wait && waitClass?.hard_stop) {
      return fail("make_rule: a hard-stop approval can never become a rule");
    }
    if (input.verb === "snooze" && input.return_at) {
      const served = view.snooze_options.times.find(
        (t) => Date.parse(t.at) === Date.parse(input.return_at as string),
      );
      if (!served) return fail("snooze: the return time is not one of the served times");
    }

    const effectiveVerb = input.verb === "approve_rule" ? "approve" : input.verb;
    const decision: DecisionRecord = {
      verb: effectiveVerb,
      at: new Date().toISOString(),
      option_id:
        input.verb === "decide" || input.verb === "rule_it" ? (input.option_id as string) : null,
      note: input.note ?? "",
      send_id: null,
    };
    const result: DecideResult = { ok: true, decision, replayed: false };
    this.decideCache.set(input.idempotency_key, result);
    this.post(`/api/v1/items/${encodeURIComponent(itemId)}/action`, {
      verb: backendVerb(input.verb),
      option_id: input.option_id ?? null,
      note: input.note ?? "",
      idempotency_key: input.idempotency_key,
      return_at: input.return_at ?? null,
      return_on_activity: input.return_on_activity ?? undefined,
      resume_note: input.resume_note ?? undefined,
      make_rule: input.make_rule ?? undefined,
    }, undefined, "That decision", (message) => {
      // The optimistic ok unwinds: the cached result is
      // evicted so the same key can be decided again, and
      // the refusal is stated — the item never recorded.
      this.decideCache.delete(input.idempotency_key);
      this.noteWriteRefusal(`That decision was not recorded — the server refused it: ${message}`);
    });
    this.bump();
    return result;
  };

  handlerAction = (handle: string, verb: string, idempotencyKey: string): HandlerActionResult => {
    const seen = this.handlerCache.get(idempotencyKey);
    if (seen) return seen;
    if (!this.handlerRow(handle)) return { ok: false, error: "No such handler." };
    if (!HANDLER_VERBS.has(verb)) {
      return { ok: false, error: "verb not served for a handler" };
    }
    if (verb === "status_ping") {
      // The ping cooldown (one per digest window),
      // mirrored from this session's own pings against
      // the served window times — the backend raises the
      // same conflict for a ping this session cannot see.
      const last = this.ownPings.get(handle);
      if (last !== undefined && last >= this.windowStartMs()) {
        return { ok: false, error: "A status ping already went out this digest window." };
      }
      this.ownPings.set(handle, Date.now());
    }
    // The server assigns the action id; it arrives with
    // the refreshed owner-actions ledger, where ids are
    // read. The tap's receipt carries the verb only.
    const result: HandlerActionResult = { ok: true, action_id: "", verb };
    this.handlerCache.set(idempotencyKey, result);
    this.post(`/api/v1/handlers/${encodeURIComponent(handle)}/action`, {
      verb,
      idempotency_key: idempotencyKey,
    }, () => {
      void this.refreshDetails();
    }, "That handler action", (message) => {
      // Unwind the optimistic ok: the cached receipt is
      // evicted, a refused status ping frees its window
      // mark, and the refusal is stated.
      this.handlerCache.delete(idempotencyKey);
      if (verb === "status_ping") this.ownPings.delete(handle);
      this.noteWriteRefusal(`That handler action was not recorded — the server refused it: ${message}`);
    });
    this.bump();
    return result;
  };

  /** The most recent digest window instant at or before
   * now, from the served window times in the server's
   * own zone (the offset rides the glance clock's ISO). */
  private windowStartMs(): number {
    const times = this.digest?.window.times ?? [];
    const nowIso = this.glance?.clock.now;
    if (!times.length || !nowIso) return Number.NEGATIVE_INFINITY;
    const offset = /([+-]\d{2}):(\d{2})$/.exec(nowIso);
    const offsetMs = offset
      ? (Number(offset[1]) * 60 + Number(offset[2]) * (offset[1].startsWith("-") ? -1 : 1)) * 60_000
      : 0;
    const nowMs = Date.parse(nowIso);
    const wallNow = new Date(nowMs + offsetMs);
    let best = Number.NEGATIVE_INFINITY;
    for (const dayOff of [0, -1]) {
      for (const time of times) {
        const [h, mi] = time.split(":").map(Number);
        const wall = Date.UTC(
          wallNow.getUTCFullYear(),
          wallNow.getUTCMonth(),
          wallNow.getUTCDate() + dayOff,
          h,
          mi,
        );
        const at = wall - offsetMs;
        if (at <= nowMs && at > best) best = at;
      }
    }
    return best;
  }

  // ---------- rules ----------

  /** normalize_rule, mirrored from the mock (which
   * mirrors the backend): defaults for mode, scope,
   * on_scope_miss, requires, priority, trigger, guards. */
  private normalizeRule(rule: RuleRecord): RuleRecord {
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

  saveRule = (rule: RuleRecord): RuleSaveResult => {
    // Validation and label composition are the server's
    // (AC-13): no mirrored validator, no client-composed
    // sentences. The POST returns the served rule view;
    // it joins the rules portion when it lands, and a
    // refusal surfaces through the write notice. The
    // synchronous receipt carries the served view when
    // the rule already stands, else the record with the
    // name-derived display name — labels arrive with the
    // refresh, composed by the one home that owns them.
    const stored = this.normalizeRule(rule);
    void (async () => {
      try {
        const view = (await this.fetchJson("/api/v1/rules", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(stored),
        })) as ServerRuleView;
        const idx = this.rules.findIndex((r) => r.id === view.id);
        if (idx >= 0) this.rules[idx] = view;
        else this.rules.push(view);
        if (this.writeNotice) this.writeNotice = null;
        this.bump();
        void this.refreshSlow();
      } catch (err) {
        this.noteWriteRefusal(
          `That rule was not saved — the server refused it: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    })();
    const standing = this.rules.find((r) => r.id === stored.id);
    if (standing) return { ok: true, rule: { ...standing, name: standing.name ?? null } };
    return {
      ok: true,
      rule: {
        ...clone(stored),
        display_name:
          stored.name || stored.id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        when_label: "",
        then_label: "",
      },
    };
  };

  previewRule = (rule: RuleRecord): RulePreviewResult => {
    const candidate = this.normalizeRule(rule);
    // The dry run is the server's own evaluation over
    // live waits — it cannot be composed at the tap.
    // The first tap fires it; the result is cached by
    // the candidate's own shape and a second tap on the
    // unchanged rule reads it back.
    const key = JSON.stringify(candidate);
    const cached = this.previewCache.get(key);
    if (cached) return { ok: true, would_fire: cached };
    void (async () => {
      try {
        const data = (await this.fetchJson("/api/v1/rules/preview", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ rule: candidate }),
        })) as { would_fire: WouldFire[] };
        this.previewCache.set(key, data.would_fire);
        this.bump();
      } catch (err) {
        this.noteWriteRefusal(
          `That rule preview failed on the server: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    })();
    return {
      ok: false,
      error: "Preview runs on the server against the live waits — tap Preview again to read its result for this rule.",
    };
  };

  // ---------- vocab writes ----------

  addStatusCode = (entry: StatusCodeInput): VocabResult => {
    const errors: string[] = [];
    for (const field of ["code", "short", "label", "need"] as const) {
      if (!entry[field]) errors.push(`${field} is required`);
    }
    const needs = ["owner_actionable", "agent_clearable", "unclassified"];
    if (entry.need && !needs.includes(entry.need)) errors.push("need unknown need");
    if (errors.length) {
      return { ok: false, error: `Status code failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/status-codes", entry, () => void this.refreshSlow(), "That status code");
    return { ok: true };
  };

  addField = (entry: FieldInput): VocabResult => {
    const errors: string[] = [];
    if (!entry.name) errors.push("name is required");
    if (!entry.type) errors.push("type is required");
    const types = ["bool", "enum", "number", "datetime", "string"];
    if (entry.type && !types.includes(entry.type)) errors.push("type unknown field type");
    if (errors.length) {
      return { ok: false, error: `Field failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/fields", entry, () => void this.refreshSlow(), "That field");
    return { ok: true };
  };

  addWaitClass = (entry: WaitClassInput): VocabResult => {
    if (!entry.name) {
      return { ok: false, error: "Class failed validation. name is required" };
    }
    const existing = this.registries?.wait_classes.find((c) => c.name === entry.name);
    if (existing?.hard_stop) {
      return {
        ok: false,
        error: "Class failed validation. name hard-stop classes are not editable",
      };
    }
    this.post("/api/v1/vocab/classes", entry, () => void this.refreshSlow(), "That wait class");
    return { ok: true };
  };

  addTemplate = (entry: TemplateInput): VocabResult => {
    const errors: string[] = [];
    if (!entry.kind) errors.push("kind is required");
    if (!entry.text) errors.push("text is required");
    if (!["chat", "main"].includes(entry.audience)) {
      errors.push("audience must be chat or main");
    }
    if (errors.length) {
      return { ok: false, error: `Template failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/templates", entry, () => void this.refreshSlow(), "That template");
    return { ok: true };
  };

  addItemKind = (entry: ItemKindInput): VocabResult => {
    const errors: string[] = [];
    if (!entry.kind) errors.push("kind is required");
    if (!entry.label) errors.push("label is required");
    if (entry.digest_owner !== null && !["owner", "lane", "self"].includes(entry.digest_owner)) {
      errors.push("digest_owner must be owner, lane, or self");
    }
    if (errors.length) {
      return { ok: false, error: `Item kind failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/kinds", entry, () => void this.refreshSlow(), "That item kind");
    return { ok: true };
  };
}
