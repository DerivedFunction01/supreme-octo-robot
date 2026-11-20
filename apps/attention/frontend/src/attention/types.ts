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

// ---------- View models (served ready by the adapter) ----------

export type Severity = "ok" | "info" | "warn" | "fail" | "idle";

/** The snooze choices served on every item view (backend
 * snooze_options): the return times the panel may pick,
 * and whether return-on-activity is offered. */
export interface SnoozeOptionsView {
  times: { at: string; label: string }[];
  on_activity: boolean;
}

export interface ItemView {
  id: string;
  handle: string;
  handler_label: string;
  color_slot: number;
  kind: ItemKind;
  title: string;
  waiting_label: string;
  severity: Severity;
  verbs: string[];
  options: ItemOption[] | null;
  failure: string | null;
  history: DecisionHistoryEntry[];
  due_label: string | null;
  clears_at_source: boolean;
  snooze_options: SnoozeOptionsView;
  /** Set when a shadow action rule would fire on this
   * item (backend _shadow_hint): the tap applies it once. */
  rule_hint: string | null;
  proposal: ProposalPayload | null;
}

export type BandState = "queued" | "sent" | "recorded";

export interface AwaitingView extends ItemView {
  band_state: BandState;
  band_label: string;
  decided_label: string;
  decision: DecisionRecord;
}

export interface PresenceView {
  /** Effective mode — expiry resolved at read time. */
  mode: PresenceMode;
  expires_at: string | null;
  /** Which storyboard expiry option the current expires_at
   * corresponds to (drives the radio checkmarks). */
  expiry_choice: ExpiryChoice;
  expectation: string;
  chip_label: string;
  chip_severity: Severity;
}

export interface GlanceView {
  clock_label: string;
  date_label: string;
  presence: PresenceView;
  count: number;
  count_label: string;
  sub_label: string;
  next: ItemView[];
  rows_label: string;
  rows: { label: string; value: string }[];
  /** Sources the backend reports down (api/1 glance
   * down_sources): their items may be missing from this
   * picture, and the view must say so — never silently. */
  down_sources: string[];
  /** The held picture for a filtered presence (AC-11):
   * how much waits behind the away/focus filter and when
   * it surfaces, in the original page's words. Null in
   * Active, where nothing is held. */
  held_label: string | null;
}

/** One fetched portion's health, the original page's
 * portion() semantics: a portion that has never loaded is
 * "down" (its surface is unreachable, never an empty queue);
 * a portion failing after a successful load is "stale" (the
 * view shows the last good copy, tagged); otherwise "ok". */
export interface PortionHealth {
  state: "ok" | "stale" | "down";
  /** ISO instant of the last successful load, or null. */
  last_good_at: string | null;
}

export interface SurfaceHealth {
  glance: PortionHealth;
  today: PortionHealth;
  digest: PortionHealth;
}

export interface DueRow {
  label: string;
  sub: string;
  value: string;
}

export interface TodayView {
  date_label: string;
  subtitle: string;
  presence: PresenceView;
  /** The one waiting-on-the-owner total (open decisions +
   * breakthroughs) — the headline/badge count, mirroring
   * backend api/1's decision_count / headline_count
   * (owner-actionable live items, breakthrough included).
   * The band lists below carry their own lengths; this
   * field is never a single band's count. */
  decision_count: number;
  breakthrough: ItemView[];
  decisions: ItemView[];
  awaiting: AwaitingView[];
  due_today: DueRow[];
  /** Due-today items that carry decision verbs (AC-3):
   * the server's bands are exclusive, so a decidable item
   * due today stands in the due_today band, not in
   * decisions — it renders as a full decision card in the
   * Due today group, never an inert text row. The mock's
   * due items already stand in its decisions list, so it
   * serves this empty. */
  due_decidable: ItemView[];
  waiting_on_others: ItemView[];
  fyi: { count: number; newest_title: string | null; items: ItemView[] };
  /** Per-band source unavailability the backend serves
   * (api/1 today bands' unavailable): the band is showing
   * its last good copy and the view renders the warning —
   * the original's "showing the last good copy from …"
   * card. Empty when every source is up. */
  unavailable: { reason: string; last_good_label: string }[];
}

export interface HandlerListRow {
  handle: string;
  label: string;
  color_slot: number;
  icon: string;
  sub_label: string;
  severity: Severity;
  trailing: { label: string; severity: Severity } | null;
}

export interface HandlersView {
  subtitle: string;
  rows: HandlerListRow[];
}

/** One auto-applied log entry on a handler (api/1
 * build_handler's auto_applied: the engine's action log
 * for the handler, labels composed by the backend). */
export interface AutoAppliedRow {
  at: string;
  wait_class: string;
  decision_label: string;
  rule_id: string | null;
  shadow: boolean;
}

export interface HandlerDetailView {
  handler: HandlerRow;
  subtitle: string;
  open_items: ItemView[];
  awaiting: AwaitingView[];
  agent_clearable_label: string;
  breakthrough_hit_rate: string;
  muted_types: { type: string; muted: boolean }[];
  /** The handler's latest status post, classified (api/1
   * build_handler's status), or null when the lane has
   * never posted. */
  status: HandlerStatusView | null;
  /** The steering verbs the backend serves for a handler
   * (HANDLER_VERBS minus the status's quick verbs). */
  handler_verbs: VerbEntry[];
  /** The owner's recent steering acts on this handler. */
  owner_actions: OwnerActionView[];
  /** The handler's send ledger (api/1 build_handler's
   * sends): what was dispatched for this handler and how
   * each send stands — delivered, suppressed, failed, or
   * still queued — so fulfillment is answerable here. */
  sends: SendRow[];
  /** The engine's auto-applied log for this handler. */
  auto_applied: AutoAppliedRow[];
}

export interface ProgrammeCardView {
  slug: string;
  label: string;
  handles: { handle: string; label: string; color_slot: number }[];
  cadence_label: string;
  band_label: string;
  escalation_label: string;
  venue_label: string;
  open_decisions: number;
  awaiting: number;
  rule_text: string;
}

export interface DigestView {
  windows: DigestWindow[];
  next_label: string;
  next_detail: string;
  include: { decisions: boolean; waiting: boolean; fyi: boolean };
  preview_label: string;
  /** The assembled digest itself (api/1 build_digest):
   * what the next window will carry, computed by the
   * adapter from the same state the other surfaces read. */
  content: DigestContentView;
}

// ---------- Handler steering (api/1: handler payload) ----------

/** A served verb: the verb plus its registry label. The
 * frontend renders the label, never a local mapping. */
export interface VerbEntry {
  verb: string;
  label: string;
  primary?: boolean;
  rule_hint?: string | null;
}

export interface StatusBlockerView {
  summary: string;
  clearing_act: string | null;
  /** "hard stop" when whose is hard, else "yours". */
  whose_label: string;
}

export interface StatusTailView {
  kind: string;
  kind_label: string;
  title: string;
  /** "your tap" for owner items, "closeout" otherwise. */
  owner_label: string;
}

export interface HandlerStatusView {
  status_code: string;
  status_label: string;
  need: "owner_actionable" | "agent_clearable" | "unclassified";
  summary: string;
  /** When the status was posted, scenario-local. */
  at_label: string;
  /** Whole hours since the post (the stall measure). */
  age_hours: number;
  done: string[] | null;
  ongoing: string[] | null;
  tail: StatusTailView[] | null;
  blockers: StatusBlockerView[] | null;
  quick_verbs: VerbEntry[];
  /** The status's derived workbench line (api/1
   * build_handler's status.derived), composed from the
   * served block in the original page's words, with any
   * conflict messages verbatim. Null when the status
   * carries no refs to derive from. */
  derived: { label: string; conflicts: string[] } | null;
}

export interface OwnerActionView {
  id: string;
  verb: string;
  verb_label: string;
  at_label: string;
  note: string;
  /** "owner", or "rule <id>" for rule-applied acts. */
  actor_label: string;
  /** The act was a shadow rule's — it recorded what it
   * would do and did nothing (served on the backend's
   * owner-action entries; the original page marked it). */
  shadow: boolean;
}

export type HandlerActionResult =
  | { ok: true; action_id: string; verb: string }
  | { ok: false; error: string };

// ---------- Registries (api/1: build_registries) ----------

export interface StatusCodeEntry {
  code: string;
  short: string;
  label: string;
  need: string;
  terminal: boolean;
}

export interface FieldEntry {
  name: string;
  label: string;
  type: string;
  source: string;
  poster_settable: boolean;
}

export interface WaitClassEntry {
  name: string;
  label: string;
  hard_stop: boolean;
}

export interface TemplateEntry {
  kind: string;
  version: number;
  audience: string;
  slots: string[];
  text: string;
}

export interface ItemKindEntry {
  kind: string;
  label: string;
  status_kind: boolean;
  digest_owner: string | null;
  digest_owner_label: string;
}

export interface RegistriesView {
  status_codes: StatusCodeEntry[];
  fields: FieldEntry[];
  wait_classes: WaitClassEntry[];
  operators: { op: string; label: string }[];
  triggers: { on: string; label: string }[];
  actions: { type: string; label: string }[];
  templates: TemplateEntry[];
  item_kinds: ItemKindEntry[];
  handlers: { handle: string; label: string; thread_id: string }[];
}

// ---------- Rules (api/1: rules + rule_view) ----------

export interface RuleMatch {
  wait_class: string | null;
  status_code: string | string[] | null;
  kind: string | null;
  handle: string | null;
}

export interface RuleCondition {
  field: string;
  op: string;
  value: unknown;
}

export interface RuleAction {
  type: string;
  template?: string;
  variants?: {
    presence?: Record<string, string>;
    attempt?: Record<string, string>;
  };
}

/** The stored rule record — the editor's working shape and
 * the POST /api/v1/rules body, verbatim field set. */
export interface RuleRecord {
  id: string;
  name: string | null;
  match: RuleMatch;
  where: { all: RuleCondition[] } | null;
  action: RuleAction;
  scope: string;
  requires: string[];
  priority: number;
  on_scope_miss: string;
  trigger: { on: string; after_minutes?: number; count?: number };
  guards: {
    cooldown_minutes?: number;
    max_posts?: number;
    escalate_after?: number;
  };
  mode: string;
}

/** A stored rule plus its composed When / Then sentences
 * (rule_view): the row speaks sentences with registry
 * labels resolved, never raw codes. */
export interface RuleView extends RuleRecord {
  display_name: string;
  when_label: string;
  then_label: string;
}

export interface WouldFire {
  wait_id: string;
  /** "post" for a rendered post; otherwise the decision
   * the wait would land (owner_approved / held / surfaced). */
  action: string;
  template: string | null;
  target: string | null;
  text: string | null;
}

export type RuleSaveResult =
  | { ok: true; rule: RuleView }
  | { ok: false; error: string };

export type RulePreviewResult =
  | { ok: true; would_fire: WouldFire[] }
  | { ok: false; error: string };

// ---------- Action rules (the learning loop's rules) ----------

/** A standing action rule, created by a promotion tap
 * (rule_it / approve_rule / make_rule / an accepted
 * proposal) — the backend's action_rules record, served
 * composed: the match and the provenance speak in labels. */
export interface ActionRuleView {
  id: string;
  match_label: string;
  verb: string;
  verb_label: string;
  mode: string;
  created_from: string;
  created_label: string;
  at_label: string;
}

// ---------- Vocabulary writes (POST /api/v1/vocab/*) ----------

export type VocabResult = { ok: true } | { ok: false; error: string };

export interface StatusCodeInput {
  code: string;
  short: string;
  label: string;
  need: string;
  terminal: boolean;
}

export interface FieldInput {
  name: string;
  type: string;
}

export interface WaitClassInput {
  name: string;
}

export interface TemplateInput {
  kind: string;
  audience: string;
  slots: string[];
  text: string;
}

export interface ItemKindInput {
  kind: string;
  label: string;
  status_kind: boolean;
  digest_owner: string | null;
}

// ---------- Digest content (api/1: build_digest) ----------

export interface DigestSectionRow {
  title: string;
  handle: string;
  handler_label: string;
  provenance_label: string;
  at_label: string;
  age_label: string;
}

export interface DigestSection {
  kind: string;
  kind_label: string;
  owner_label: string;
  rows: DigestSectionRow[];
}

export interface DigestStall {
  handle: string;
  handler_label: string;
  summary: string;
  clearing_act: string | null;
  status_label: string;
  age_hours: number;
  age_label: string;
}

export interface DigestStaffingRow {
  topic: string | null;
  handle: string | null;
  handler_label: string;
  kind: string;
  kind_label: string;
  detail: string;
  /** "Escalated to Main" when the row escalated, else null. */
  escalation_label: string | null;
}

export interface DigestStaffing {
  available: boolean;
  reason: string | null;
  idle_minutes_total: number;
  rows: DigestStaffingRow[];
}

export interface DigestTopicLane {
  handle: string;
  label: string;
  status_label: string | null;
  stale: boolean;
  quick_verbs: VerbEntry[];
}

export interface DigestTopic {
  topic: string;
  worst_label: string | null;
  stalls: number;
  open_counts: { kind: string; kind_label: string; count: number }[];
  lanes: DigestTopicLane[];
}

export interface DigestParkedPlans {
  available: boolean;
  reason: string | null;
  plans: { title: string; project: string; age_label: string }[];
}

export interface DigestContentView {
  sections: DigestSection[];
  stalls: DigestStall[];
  staffing: DigestStaffing;
  topics: DigestTopic[];
  parked_plans: DigestParkedPlans;
}

export type DecideResult =
  | { ok: true; decision: DecisionRecord; replayed: boolean }
  | { ok: false; error: string };

export interface DecideInput {
  verb: string;
  option_id?: string | null;
  note?: string;
  idempotency_key: string;
  /** Snooze payload (backend triage fields): the chosen
   * return instant from the item's served snooze_options,
   * whether new activity returns it sooner, and the note
   * it resumes with. */
  return_at?: string | null;
  return_on_activity?: boolean;
  resume_note?: string | null;
  /** The deliberate promotion flag (backend D-A8): the
   * tap also makes a standing action rule. Refused with
   * approve_rule, which already promotes. */
  make_rule?: boolean;
}

export type ExpiryChoice = "1h" | "17:00" | "tomorrow-08:00" | "none" | "custom";

/** The data seam. The mock adapter below implements it over a
 * stateful in-memory store; at S8 the live adapter implements
 * the same interface over the attention app's api/1 shapes,
 * with no frontend change. */
export interface AttentionDataSource {
  subscribe(fn: () => void): () => void;
  getVersion(): number;
  now(): Date;
  getPresence(): PresenceView;
  /** Presence write — the same path every expiry option
   * uses. The record itself carries only the absolute
   * expires_at (the backend's POST /api/v1/presence shape);
   * the presets resolve to instants at write time, and a
   * "custom" choice carries its instant in customExpiresAt
   * (an ISO timestamp, or null to clear). */
  setPresence(mode: PresenceMode, expiry: ExpiryChoice, customExpiresAt?: string | null): void;
  getGlance(night?: boolean): GlanceView;
  getToday(): TodayView;
  /** Fetch health per surface portion (the honest-failure
   * seam): views render unreachable/stale states from this,
   * never an affirmative empty queue for a down surface. */
  getSurfaceHealth(): SurfaceHealth;
  /** The latest write verdict the server refused, in
   * words, or null. Live writes return their optimistic
   * result synchronously (the seam's shape); when the
   * server then refuses the write, the refusal lands here
   * and the shell renders it — a refused decision, rule,
   * or vocab act never stands as accepted. Cleared when a
   * later write is accepted. */
  getWriteNotice(): string | null;
  getHandlers(): HandlersView;
  getHandlerDetail(handle: string): HandlerDetailView | null;
  getProgrammes(): ProgrammeCardView[];
  getDigest(): DigestView;
  setDigestWindow(id: string, enabled: boolean): void;
  setDigestInclude(key: "decisions" | "waiting" | "fyi", enabled: boolean): void;
  setMutedType(handle: string, type: string, muted: boolean): void;
  decide(itemId: string, input: DecideInput): DecideResult;
  /** Handler steering (POST /api/v1/handlers/{h}/action):
   * the verb is validated against the served handler +
   * status quick verb sets; the act records an owner
   * action and dispatches through the send ledger. */
  handlerAction(handle: string, verb: string, idempotencyKey: string): HandlerActionResult;
  /** The vocabularies the rule editor's pickers serve. */
  getRegistries(): RegistriesView;
  /** Stored rules as rule views (When / Then composed). */
  getRules(): RuleView[];
  /** POST /api/v1/rules: validated against the registries;
   * a saved rule replaces a stored rule of the same id. */
  saveRule(rule: RuleRecord): RuleSaveResult;
  /** POST /api/v1/rules/preview: a dry run over the open
   * waits — nothing is sent or decided. */
  previewRule(rule: RuleRecord): RulePreviewResult;
  /** The standing action rules the learning loop has
   * created (served with the registries in the backend). */
  getActionRules(): ActionRuleView[];
  /** POST /api/v1/vocab/status-codes: validated and
   * registered; an existing code is replaced. */
  addStatusCode(entry: StatusCodeInput): VocabResult;
  /** POST /api/v1/vocab/fields: a poster-settable field. */
  addField(entry: FieldInput): VocabResult;
  /** POST /api/v1/vocab/classes: a new wait class is
   * never a hard stop; hard-stop classes are not editable. */
  addWaitClass(entry: WaitClassInput): VocabResult;
  /** POST /api/v1/vocab/templates: saving a kind again
   * stores its next version. */
  addTemplate(entry: TemplateInput): VocabResult;
  /** POST /api/v1/vocab/kinds: a new item kind. */
  addItemKind(entry: ItemKindInput): VocabResult;
  /** One simulated dispatch/evaluator pass. The browser
   * drives it on an interval; tests drive it by hand. */
  tick(): void;
  /** Test/inspection surface: the send ledger as it stands. */
  getSends(): SendRow[];
}
