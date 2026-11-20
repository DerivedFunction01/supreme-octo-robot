// Contract 12 record shapes (contracts/schemas/*.json) and the
// served projections the panel consumes. Records are the store's
// state of record; views are derived by the adapter (the backend
// stand-in) and served display-ready — the frontend renders,
// it does not re-derive.

export type VenueId = "colab"; // the only implemented adapter (D1/D2)

export interface ShapeSpec {
  gpu: string | null;
  tpu: string | null;
  high_mem: boolean;
}

/** schemas/lease-record.schema.json — open shape; lifecycle stamps accrue. */
export interface LeaseRecord {
  session: string;
  venue: VenueId;
  shape: string;
  shape_spec: ShapeSpec;
  rate_cu_per_hour: number | null;
  caller?: string;
  acquired_at: string;
  deadline: string;
  last_used_at: string;
  jobs: string[];
  budget_at_acquire: {
    balance_cu: number;
    /** Legacy records name a duration preset; acquires now
     *  take explicit hours and write only grant_hours. */
    preset?: string;
    grant_hours: number;
    reserved_cu: number;
  } | null;
  envelope_id?: string;
  renew?: boolean;
  /** The standing duty's lease: its lifetime belongs to the
   *  grant, so extend/shorten refuse it while a grant is
   *  active (the core's standing-managed refusal). */
  standing?: boolean;
  shortened_at?: string;
  shortened_by?: string;
  shortened_from?: string;
  host?: string;
  via?: string;
}

/**
 * The two-tier grant record, as the core writes it
 * (grants.write_grant): granted_at is the grant's id and
 * the envelope stamp attributed leases carry; scope is the
 * snapshot taken at grant time — the sanctioned shapes and
 * the budget caps in force then, which later config edits
 * never move.
 */
export interface GrantRecord {
  kind: "two-tier";
  granted_at: string;
  until: string;
  standing_shape: string;
  burst_shape: string;
  scope: {
    caps: {
      daily: number | null;
      monthly: number | null;
      standing_daily: number | null;
    };
    standing_shape: string;
    burst_shape: string;
    shapes: string[];
  };
}

/** schemas/run-record.schema.json — terminal states: complete | failed | orphaned. */
export interface RunRecord {
  run_id: string;
  job: string;
  session?: string;
  venue: VenueId;
  shape?: string;
  caller?: string;
  state: string;
  started_at: string;
  ended_at?: string;
  resumed: boolean;
  error?: string;
  terminal_event_state?: string;
}

/**
 * schemas/session-evidence.schema.json — CLOSED shape
 * (additionalProperties: false). At the pin it carried no
 * venue field; the S5 amendment (2026-11-13, plan §7 V1)
 * added venue as a required property — the projection
 * stamps it at write time and the §10.3 migration stamps
 * the legacy stock — so seed evidence carries it natively
 * and the gap recorded against the pin is closed.
 */
export interface SessionEvidence {
  deadline: string | null;
  acquired_at: string | null;
  shape: string | null;
  spec: ShapeSpec | null;
  caller: string | null;
  venue: VenueId;
}

/** Contract 12 spend journal line: {session, shape, start, end, rate} + caller. */
export interface SpendSegment {
  session: string;
  shape: string;
  start: string;
  end: string;
  rate: number;
  caller?: string;
}

export type EventKind = "lease" | "run" | "grant" | "error" | "budget";
export type Tone = "ok" | "info" | "warn" | "fail" | "idle";

/** The logs surface's filter categories (the original
 *  panel's logCategory over the outbox vocabulary):
 *  grant-* events are Grants, budget events are Budget,
 *  everything else is Leases. Served on the projection;
 *  the frontend filters, it never derives. */
export type EventCategory = "leases" | "grants" | "budget";

export interface VenueEvent {
  id: string;
  at: string;
  kind: EventKind;
  tone: Tone;
  message: string;
  venue: VenueId;
}

/**
 * The served event projection (LogRow entry shape, kit
 * timeline-component study 2026-11-13): the record's one
 * message string split adapter-side into the fields the
 * kit's LogRow renders — date token, time, headline, meta —
 * plus the drawer detail (full message verbatim, the
 * servable facts, and the routing row for the lease the
 * message names). The record (VenueEvent) is unchanged;
 * the split is a view, derived here, never in the frontend.
 */
export interface EventView {
  id: string;
  at: string;
  kind: EventKind;
  kindLabel: string;
  tone: Tone;
  /** The record message, verbatim (search + drawer). */
  message: string;
  venue: VenueId;
  venueLabel: string;
  dateToken: string;
  time: string;
  headline: string;
  meta?: string;
  /** The logs filter category, served (see EventCategory). */
  category: EventCategory;
  /** Day-grouping key + band label for the timeline's
   *  day groups, served — the view groups, it never
   *  derives a day from a timestamp. */
  dayKey: string;
  dayLabel: string;
  /** The raw record, pretty-printed — the logs surface's
   *  raw-JSON expansion renders it verbatim. */
  raw: string;
  detail: {
    message: string;
    facts: { label: string; value: string; mono?: boolean }[];
    entity?: {
      groupLabel: string;
      session: string;
      title: string;
      sub: string;
    };
  };
}

export interface AccessEntry {
  id: string;
  at: string;
  label: string;
  detail: string;
  chip?: { tone: Tone; label: string };
}

/**
 * The served access-log projection (the kit LogRow's entry
 * shape, scoped variant — timeline-component study): the
 * record's label is the headline; the record's detail
 * splits adapter-side into the meta line's content and the
 * served time it ends with; the record's chip, where one is
 * served, is the row's kind — and where none is served the
 * entry carries no kind (honest absence: the scoped variant
 * wears a badge only where a chip is served). The record
 * (AccessEntry) is unchanged; the split is a view, derived
 * in the adapter, never in the frontend.
 */
export interface AccessLogView {
  id: string;
  at: string;
  dateToken: string;
  time: string;
  headline: string;
  meta?: string;
  kind?: { label: string; tone: Tone };
}

/* ---------------- served projections ---------------- */

export interface LeaseView {
  session: string;
  displayName: string;
  venue: VenueId;
  venueLabel: string;
  shape: string;
  shapeLabel: string;
  caller: string | null;
  state: "running" | "renewal-due";
  stateLabel: string;
  stateTone: Tone;
  acquiredAt: string;
  deadline: string;
  endsLabel: string;
  remainingLabel: string;
  rateCuPerHour: number | null;
  reservedCu: number;
  envelopeId?: string;
  /** The lease card's diagnostics (V7), served from the
   *  core's listeners census + the record's liveness
   *  stamps; null when the venue serves no census for the
   *  session (honest absence — the card renders no
   *  diagnostics group). */
  diagnostics: LeaseDiagnosticsView | null;
}

/** One listener of the core's per-session listeners
 *  census: the port/pid/cwd it serves, with the census's
 *  own suspect derivation (deleted-cwd, predates-lease). */
export interface ListenerView {
  port: number;
  pid: number;
  cwd: string | null;
  suspect: string[];
}

/**
 * The served lease diagnostics (V7): the listeners census
 * lines, the keepalive heartbeat age, the last pulse
 * result, the burn rate, and the sync claim (holder +
 * expiry) when one is live. Display-only — no verb rides
 * this projection.
 */
export interface LeaseDiagnosticsView {
  listeners: ListenerView[];
  heartbeatLabel: string;
  pulseLabel: string | null;
  burnLabel: string;
  syncClaim: { caller: string; untilLabel: string } | null;
}

export interface RunView {
  runId: string;
  job: string;
  session: string | null;
  sessionName: string;
  caller: string | null;
  state: string;
  stateLabel: string;
  stateTone: Tone;
  startedAt: string;
  durationLabel: string;
  venue: VenueId;
}

/** One in-flight job on an orphan session, served display-ready
 *  — the view form of the pipeline census's
 *  jobs_in_flight_entries ({id, kind, state, started_at}): the
 *  label is the job's served name where the record carries one,
 *  else its id. Terminal jobs are not in flight and never ride. */
export interface OrphanJobView {
  id: string;
  label: string;
  sub: string;
  stateLabel: string;
  tone: Tone;
}

/** One catalog shape the operator may pick for a
 *  class-ambiguous orphan (V6): the adopt verb posts the
 *  picked id; label + rate are served display-ready. */
export interface OrphanShapeCandidate {
  id: string;
  label: string;
  rateLabel: string;
}

/** One evidence conflict the orphan derivation found,
 *  served display-ready: the field, and the composed
 *  "source says value" text (values formatted
 *  adapter-side — times as times). */
export interface OrphanConflictView {
  field: string;
  text: string;
}

export interface OrphanView {
  /** The orphan's session name — null on a nameless
   *  census row: an assignment that lost its name
   *  server-side, which the census keys by endpoint
   *  instead (the backend's deliberate form — there is
   *  no name to serve). The row's identity is then its
   *  endpoint; adoption and release both take their
   *  endpoint forms — adoption mints a fresh name,
   *  release unassigns by endpoint. */
  session: string | null;
  nameless: boolean;
  endpoint: string | null;
  /** The name the endpoint's identity stamps recovered,
   *  when one exists — evidence, never the row's name. */
  priorSession: string | null;
  displayName: string;
  venue: VenueId;
  venueLabel: string;
  shapeLabel: string;
  sub: string;
  /** V6 adoption depth, served from the orphans census:
   *  the evidence lines the card renders (first seen,
   *  acquired, renewal-kit), the evidenced shape or the
   *  candidate list for its class, the creator caller and
   *  first claim, the derived deadline's source with its
   *  stale flag, the derivation's conflicts, and the
   *  handover-pending state that refuses adoption. */
  firstSeenLabel: string;
  acquiredLabel: string | null;
  kitInstalled: boolean;
  shapeEvidenced: boolean;
  shapeClassLabel: string | null;
  shapeCandidates: OrphanShapeCandidate[];
  creatorCaller: string | null;
  firstClaim: string | null;
  deadlineSource: string | null;
  deadlineStalePossible: boolean;
  conflicts: OrphanConflictView[];
  handoverPending: boolean;
  /** E4 (ruled 2026-11-14): the evidenced deadline and the
   *  served past-deadline determination (the pipeline census's
   *  derived_deadline / deadline_past) — the frontend renders
   *  them, it never derives them. deadlineLabel is the deadline
   *  time the headline carries beside the chip. */
  deadline: string | null;
  deadlineLabel: string | null;
  deadlinePast: boolean;
  deadlineTone: Tone;
  /** The orphan's in-flight jobs, served; the card's Jobs
   *  control opens them in the kit Sheet drawer (E4). */
  jobs: OrphanJobView[];
}

export interface ResolvedOrphanView {
  session: string;
  displayName: string;
  sub: string;
  label: string;
  tone: Tone;
}

export interface CallerView {
  caller: string;
  stateLabel: string;
  stateTone: Tone;
  sub: string;
}

/**
 * One served shape from the core's specs portion (state
 * --part specs): every shape the venue offers, with its
 * served label, the panel descriptor (kind + shape, derived
 * adapter-side exactly as the panel derives it), and its
 * rate — null when the core cannot price the shape, in
 * which case the rate label serves "Cost unconfirmed" and
 * no cost is projected. agentStartable is the session
 * gate's served verdict for agent actors; the panel is a
 * bypass actor and can start any served shape.
 */
export interface SpecView {
  id: string;
  label: string;
  descriptor: string;
  spec: ShapeSpec;
  rateCuPerHour: number | null;
  rateLabel: string;
  agentStartable: boolean;
}

/** One lease attributed to the active grant's envelope. */
export interface GrantLeaseView {
  session: string;
  displayName: string;
  shapeLabel: string;
  caller: string | null;
  deadlineLabel: string;
}

/**
 * The served grant projection (the core's grant portion:
 * the grant record plus its envelope block): the card
 * renders only what this serves — until, burst spec, the
 * snapshot caps, spend versus them, and the attributed
 * lease list. standingDaySpentCu is null when the venue
 * serves no standing spend (honest absence: the card then
 * shows the standing cap alone, as the panel does).
 */
export interface GrantView {
  id: string;
  until: string;
  untilLabel: string;
  burstShape: string;
  burstLabel: string;
  standingShape: string;
  shapes: string[];
  caps: {
    daily: number | null;
    monthly: number | null;
    standingDaily: number | null;
  };
  spendDayCu: number;
  spendMonthCu: number;
  standingDaySpentCu: number | null;
  leases: GrantLeaseView[];
}

/**
 * One entry of the served access list (the records
 * portion's access census): every live session with its
 * attribution. unattributed entries — no lease record, no
 * claim — carry the one-tap release; attributed entries
 * render without it, their lifecycle belonging to their
 * lease record or owning thread.
 */
export interface AccessSessionView {
  session: string;
  displayName: string;
  shapeClass: string;
  caller: string | null;
  firstSeen: string;
  sub: string;
  unattributed: boolean;
}

/** The budget caps in force for one account, in the core's
 *  served shape (venue rework): each cap is a non-negative
 *  number of compute units, or null for no cap. */
export interface BudgetCaps {
  daily: number | null;
  monthly: number | null;
  standingDaily: number | null;
}

/** One account of a venue, as the budget portion serves it
 *  (venue rework): every adapter carries its own budgets and
 *  an adapter can hold several accounts. The balance is null
 *  for an account the venue cannot dial yet — honest absence,
 *  never a fabricated figure. */
export interface BudgetAccountView {
  venue: string;
  account: string;
  label: string;
  balanceCu: number | null;
  usedTodayCu: number | null;
  usedMonthCu: number | null;
  standingUsedTodayCu: number | null;
  caps: BudgetCaps;
  credential: "live" | "credential-present" | "not-brought-in";
}

export interface BudgetView {
  balanceCu: number;
  usedTodayCu: number;
  reservedCu: number;
  availableCu: number;
  runwayLabel: string;
  byCaller: { caller: string; cu: number }[];
  /** The primary account's caps — the caps the figures above
   *  are enforced against. */
  caps: BudgetCaps;
  /** Every account of the venue, primary first. */
  accounts: BudgetAccountView[];
}

export interface Snapshot {
  now: string;
  degraded: boolean;
  lastServedAt: string | null;
  leases: LeaseView[];
  recentRuns: RunView[];
  runsBySession: Record<string, RunView[]>;
  orphans: OrphanView[];
  resolvedOrphans: ResolvedOrphanView[];
  events: EventView[];
  budget: BudgetView;
  callers: CallerView[];
  accessLog: AccessLogView[];
  specs: SpecView[];
  grant: GrantView | null;
  access: AccessSessionView[];
  runningCount: number;
}

export interface AcquireInput {
  shape: string;
  caller: string;
  hours: number;
}

export class AdapterError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}
