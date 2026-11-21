import type {
  DecisionHistoryEntry,
  DecisionRecord,
  DigestSettings,
  DigestWindow,
  HandlerRow,
  ItemKind,
  ItemOption,
  PresenceMode,
  ProposalPayload,
  SendRow,
} from "./rows";
import type { HandlerStatusView, OwnerActionView, VerbEntry } from "./steering";
import type { DigestContentView } from "./digest";
import type { ExpiryChoice } from "./source";

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
