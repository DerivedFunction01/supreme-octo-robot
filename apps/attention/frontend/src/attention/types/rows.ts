// Served shapes for the attention app.
//
// The registry / ledger / presence rows are the frozen S0
// contract shapes (contracts 01, 05, 06; schemas in
// contracts/schemas/) and are seeded as JSON under ./seed,
// validated against those schemas by scripts/validate-mocks.mjs.
//
// The owner ITEM has no schema at S0: its shape below is
// constructed from contract 05's decision machinery — the id
// scheme (handle:source_ref), the decision subrecord
// {verb, at, option_id, note, send_id}, the wait_id link, and
// decision_history on the item's face — plus the fields the
// storyboard presents (title, detail, waiting_since, the
// served verb set). Recorded as a gap in the lane report.

export type PresenceMode = "active" | "focus" | "away";

export interface HandlerRow {
  handle: string;
  label: string;
  color_slot: number;
  icon: string;
  thread_id: string;
  ui_surface: boolean;
  retired: boolean;
}

export interface ProgrammeRow {
  slug: string;
  label: string;
  handles: string[];
  cadence_minutes: number;
  staffing_band: { min: number; max: number };
  escalation_hours: number;
  venue: "colab" | "none";
  rule_text: string;
  settled: string[];
  commissions: Record<string, unknown>[];
  worktree_roots: string[];
  record_locations: string[];
  contract_path: string | null;
  idle_classes: string[];
  wb_projects: string[];
  retired: boolean;
}

export interface WaitRow {
  id: string;
  handle: string;
  wait_class: string;
  summary: string;
  /** Engine disposition, e.g. "surfaced"; a landed owner
   * decision reads owner_approved / owner_denied. */
  decision: string;
  at: string;
  decided_at?: string;
  owner_note?: string;
}

export interface SendDispatch {
  attempts: number;
  claim_expires_at: string | null;
  claimed_at: string | null;
  consumer: string | null;
  delivered_at: string | null;
  delivery_ref: string | null;
  suppress_reason?: string;
}

export interface SendRow {
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
  text: string;
  fact_hash: string;
  mode: "active" | "shadow";
  outcome: string;
  dispatch: SendDispatch;
  bridge_request_id?: string;
}

export interface PresenceRow {
  mode: PresenceMode;
  expires_at: string | null;
  expectation: string;
}

/** Contract 05's decision subrecord, verbatim field set. */
export interface DecisionRecord {
  verb: string;
  at: string;
  option_id: string | null;
  note: string | null;
  send_id: string | null;
}

export interface DecisionHistoryEntry extends DecisionRecord {
  /** The mock's history closes at a terminal outcome;
   * the live ledger also carries the in-flight outcomes
   * (queued / sent / recorded) of a decision that later
   * returned — the sheet tones all six. */
  outcome: "fulfilled" | "failed" | "stalled" | "queued" | "sent" | "recorded";
  failure?: string;
}

export type ItemKind =
  | "decision"
  | "breakthrough"
  | "waiting"
  | "fyi"
  | "action"
  | "rule_proposal";
export type FulfillmentKind = "send" | "push_needed" | "recorded";

export interface ItemOption {
  id: string;
  label: string;
}

/** A rule proposal's payload (backend proposal subrecord):
 * the class + verb the tap counter read, the count that
 * surfaced it, and the counter key it resets on a verdict. */
export interface ProposalPayload {
  cls: string;
  verb: string;
  count: number;
  key: string;
}

export interface OwnerItem {
  /** handle:source_ref (contract 05, ATT5). */
  id: string;
  handle: string;
  wait_id: string | null;
  kind: ItemKind;
  title: string;
  detail: string;
  waiting_since: string;
  due_at: string | null;
  notice_type: string | null;
  /** The served verb set for this item; a decision verb is
   * validated against it at the tap (contract 05, ATT2). */
  verbs: string[];
  options: ItemOption[] | null;
  fulfillment: FulfillmentKind;
  /** Whether marking this item done here also clears it
   * at the source system of record (backend item field).
   * When false, a Done tap asks first — the source keeps
   * its own copy. */
  clears_at_source: boolean;
  /** The proposal payload on a rule_proposal item. */
  proposal?: ProposalPayload;
  /** Snooze state, written by the snooze tap (backend item
   * fields): when it resurfaces, whether activity brings
   * it back sooner, and the note it resumes with. */
  snooze_return_at?: string | null;
  snooze_on_activity?: boolean;
  resume_note?: string | null;
  decision: DecisionRecord | null;
  decision_history: DecisionHistoryEntry[];
  /** Visible failure text when a failed/stalled decision has
   * returned this item to the queue. */
  failure?: string;
}

export interface FulfilledEntry {
  item_id: string;
  title: string;
  handle: string;
  decision: DecisionRecord;
  /** The effect, shown on the item's face after it clears. */
  effect: string;
  at: string;
  fulfilled_at: string;
}

export interface HandlerSurface {
  chat_label: string;
  agent_clearable: number;
  breakthrough_hit_rate: string;
  muted_types: { type: string; muted: boolean }[];
}

export interface DigestWindow {
  id: string;
  label: string;
  time: string; // "HH:MM" scenario-local
  enabled: boolean;
}

export interface DigestSettings {
  windows: DigestWindow[];
  include: { decisions: boolean; waiting: boolean; fyi: boolean };
}
