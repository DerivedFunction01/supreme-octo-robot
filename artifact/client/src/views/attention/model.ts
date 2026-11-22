// Served-shape types for the attention views, taken exactly
// from the fields the restored original (pages/attention/
// app.js) reads — nothing the backend does not serve is
// typed here, and nothing the views render is invented.
//
// The action layer returns the common envelope
// {status, payload, error} with payload typed unknown
// (server/src/attention/actions.ts); each view casts the
// payload to the shape below after the transport unwrap.

export type PresenceMode = "active" | "focus" | "away";

export interface PresenceView {
  mode: PresenceMode;
  mode_label: string;
  expectation: string;
  expires_at: string | null;
}

export interface HandlerRef {
  handle: string;
  label: string;
  color_slot: number;
}

export interface ItemVerb {
  verb: string;
  label: string;
  primary?: boolean;
  rule_hint?: string;
}

export interface ItemOption {
  id: string;
  label: string;
}

export interface AttentionItem {
  id: string;
  need: string;
  kind_label: string;
  title: string;
  source_url?: string;
  handler: HandlerRef;
  waiting_label: string;
  due_at?: string;
  resume_note?: string;
  provenance_label?: string;
  verbs: ItemVerb[];
  options?: ItemOption[];
  snooze_options: { times: string[] };
  clears_at_source?: boolean | string;
}

export interface GlancePayload {
  clock: { now: string; next_window_at: string | null };
  presence: PresenceView;
  breakthrough_count: number;
  held_count: number;
  breakthrough_items: { title: string; handler_label: string }[];
  down_sources: string[];
  next_due: { title: string; handler_label: string; due_label: string } | null;
  handler_dots: { handle: string; color_slot: number; needs_decision: number }[];
  decision_count: number;
}

export interface TodayBand {
  band: string;
  band_label: string;
  items: AttentionItem[];
  collapsed: boolean;
  unavailable: { reason: string; last_good_at: string } | null;
}

export interface TodayPayload {
  headline_count: number;
  presence: PresenceView;
  bands: TodayBand[];
  held_owner_count: number;
  held_total_count: number;
}

export interface DigestRow {
  title: string;
  handle: string;
  handler_label: string;
  provenance_label: string;
  at: string;
}

export interface DigestSection {
  kind_label: string;
  owner_label: string;
  rows: DigestRow[];
}

export interface DigestStall {
  summary: string;
  status_label: string;
  handle: string;
  handler_label: string;
  age_hours: number;
}

export interface StaffingRow {
  handler_label?: string;
  kind_label: string;
  escalation?: string;
  handle?: string;
  topic: string;
  detail: string;
}

export interface DigestTopicLane {
  handle: string;
  label: string;
  status_label?: string;
  stale?: boolean;
  quick_verbs?: { verb: string; label: string }[];
}

export interface DigestTopic {
  topic: string;
  worst_label?: string;
  stalls?: number;
  open_counts: { count: number; kind_label: string }[];
  lanes: DigestTopicLane[];
}

export interface DigestPayload {
  window: { next_at: string | null; times: string[]; tz?: string | null; enabled_times: string[] };
  include: { decisions: boolean; waiting: boolean; fyi: boolean };
  sections: DigestSection[];
  stalls: DigestStall[];
  staffing: {
    available: boolean;
    reason?: string;
    rows: StaffingRow[];
    idle_minutes_total?: number;
  };
  topics: DigestTopic[];
  parked_plans: {
    available: boolean;
    reason?: string;
    plans: { title?: string; path: string; project: string; age_days: number | null }[];
  };
}

export interface HandlerStatusTail {
  kind_label: string;
  title: string;
  owner: string;
}

export interface HandlerStatusBlocker {
  summary: string;
  clearing_act: string;
  whose: string;
}

export interface HandlerStatus {
  status_label?: string;
  status_code: string;
  need?: string;
  summary: string;
  at: string;
  done?: string[];
  ongoing?: string[];
  tail?: HandlerStatusTail[];
  blockers?: HandlerStatusBlocker[];
  quick_verbs?: { verb: string; label: string }[];
  derived?: {
    available: boolean;
    reason?: string;
    last_good_at?: string;
    todos?: { done: number; total: number; blocked?: number; doing?: number };
    conflicts?: { message: string }[];
  };
}

export interface HandlerPayload {
  label: string;
  handle: string;
  thread_id?: string;
  status?: HandlerStatus;
  agent_clearable_count: number;
  breakthrough_hit_rate: number | null;
  muted_types: { label: string; kind: string }[];
  handler_verbs?: { verb: string; label: string }[];
  owner_actions?: {
    verb_label: string;
    at: string;
    actor?: string;
    rule_id?: string;
    shadow?: boolean;
    note?: string;
  }[];
  items: AttentionItem[];
  sends?: {
    mode: string;
    outcome_label?: string;
    outcome: string;
    dispatch?: { state: string; state_label: string; delivered_at?: string };
    template: string;
    version: number;
    attempt: number;
    at: string;
    presence_label?: string;
    presence: string;
    text: string;
  }[];
  auto_applied?: {
    decision_label?: string;
    decision: string;
    wait_class?: string;
    rule_id?: string;
    at: string;
    shadow?: boolean;
  }[];
}

export interface RuleMatch {
  wait_class?: string | null;
  status_code?: string | string[] | null;
  kind?: string | null;
  handle?: string | null;
}

export interface RuleCondition {
  field: string;
  op: string;
  value: unknown;
}

export interface AttentionRule {
  id: string;
  name?: string | null;
  display_name?: string;
  match: RuleMatch;
  /** Either {all: [leaves]} or one bare leaf (the
   *  original's collect() reads both forms). */
  where?: ({ all: RuleCondition[] } | RuleCondition) | null;
  action: {
    type: string;
    template?: string;
    variants?: {
      presence?: { active?: string; focus?: string; away?: string };
      attempt?: { first?: string; repeat?: string };
    };
  };
  scope: string;
  requires?: string[];
  priority?: number;
  on_scope_miss?: string;
  trigger?: { on: string; after_minutes?: number; count?: number };
  guards?: { cooldown_minutes?: number; max_posts?: number; escalate_after?: number };
  mode: string;
  when_label?: string;
  then_label?: string;
}

export interface RulesPayload {
  rules: AttentionRule[];
}

export interface RegistryHandler {
  handle: string;
  label: string;
  color_slot?: number;
  icon?: string;
}

export interface RegistriesPayload {
  status_codes: { code: string; short: string; label: string; need: string; terminal?: boolean }[];
  fields: {
    name: string;
    label?: string;
    type: string;
    source: string;
    poster_settable: boolean;
  }[];
  operators: { op: string; label: string }[];
  triggers: { on: string; label: string }[];
  actions: { type: string; label: string }[];
  templates: { kind: string; version: number; audience: string; slots: string[]; text: string }[];
  wait_classes: { name: string; label?: string; hard_stop?: boolean }[];
  item_kinds: { kind: string; label: string; status_kind?: boolean; digest_owner_label?: string }[];
  handlers: RegistryHandler[];
}

export interface PreviewHit {
  wait_id: string;
  action: string;
  template?: string;
  text?: string;
}

export interface PreviewPayload {
  would_fire: PreviewHit[];
}

/* ---------------- formatting: the original's helpers,
 * verbatim semantics (clock/day), plus the small
 * arithmetic the views compute over served values. */

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function day(iso: string): string {
  return new Date(iso).toLocaleString([], {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function dateToken(iso: string): string {
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

/** Minutes from now until an ISO time (negative when past). */
export function minutesUntil(iso: string, now: Date = new Date()): number {
  return Math.round((new Date(iso).getTime() - now.getTime()) / 60000);
}

/** "Today" / "Tomorrow" / weekday for an ISO time. */
export function dayWord(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((startOf(d) - startOf(now)) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

/** Handler colour slots, served as 1–5, rendered on the
 *  kit's Okabe-Ito hues (the kit's status system — the
 *  original's slot palette mapped, not its navy/paper
 *  colours carried). */
export const SLOT_HUES: Record<number, string> = {
  1: "var(--wb-okabe-bluish-green)",
  2: "var(--wb-okabe-blue)",
  3: "var(--wb-okabe-orange)",
  4: "var(--wb-okabe-reddish-purple)",
  5: "var(--wb-okabe-sky-blue)",
};

export function slotHue(slot: number | undefined): string {
  return SLOT_HUES[slot ?? 1] ?? "var(--wb-content-muted)";
}

/** Presence mode dot hues on kit status tokens. */
export const PRESENCE_HUES: Record<PresenceMode, string> = {
  active: "var(--wb-status-done)",
  focus: "var(--wb-status-stale)",
  away: "var(--wb-content-muted)",
};

/** "HH:MM" (24h, served window time) → "8:00 AM" form. */
export function windowClock(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const d = new Date();
  d.setHours(h ?? 0, m ?? 0, 0, 0);
  return clock(d.toISOString());
}

/** Window name by position for the frame's three-window
 *  form (Morning / Midday / Evening); beyond three, the
 *  served time is the name — no invented labels. */
export function windowName(times: string[], index: number): string {
  if (times.length === 3) return ["Morning", "Midday", "Evening"][index] ?? times[index] ?? "";
  return windowClock(times[index] ?? "");
}
