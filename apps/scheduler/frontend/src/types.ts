// Served shapes for the scheduler app, frozen by contract 09
// (the /api/v1 view set) over contract 14 (entry format),
// contract 13 (engine semantics) and contract 07 (catalog axes).
// The client derives nothing beyond presentation and arithmetic
// over these served values (contract 06: labels are served,
// never re-derived). Fields the storyboard requires but the
// contracts do not freeze are marked GAP where they are
// declared, each with its S8 disposition (contract 09's S8
// section) — they were the reconciliation list, never silent
// inventions.

// ----------------------------------------------------------------
// Contract 14 — the registry entry (target form; the migration
// field family does not exist, amendment 3).

export type Cadence =
  | { type: "interval"; every: string }
  | { type: "daily"; at: string }
  | { type: "weekly"; dow: string[]; at: string };

export type ReportBlock = {
  when?: "never" | "on_failure" | "always" | "on_output";
  ok_exit_codes?: number[];
  fail_patterns?: string[];
  report_patterns?: string[];
  quiet_patterns?: string[];
};

export type CatalogBlock = {
  origin: "hand" | "machine" | "per-session";
  generality: "generalized" | "parameterized" | "deployment-specific";
  use_case: string;
  [key: string]: unknown;
};

export type JobEntry = {
  id: string;
  title: string;
  kind: "scripted" | "agent";
  status: "active" | "suspended";
  suspend_reason?: string;
  suspended_on?: string;
  cadence: Cadence;
  timezone?: string;
  owner: string;
  owner_reason?: string;
  run?: {
    argv: string[];
    cwd?: string;
    env_names?: string[];
    shell?: boolean;
    shell_reason?: string;
  };
  body?: string;
  escalate_body?: string;
  timeout_secs?: number;
  report?: ReportBlock;
  state_paths?: string[];
  classification: string;
  lifetime: "permanent" | "until_complete";
  self_removal?: string;
  catalog?: CatalogBlock;
  [key: string]: unknown;
};

// ----------------------------------------------------------------
// Contract 09 — the run view and the agent activity view.

export type RunStatus =
  | "ok"
  | "failed"
  | "timeout"
  | "could_not_start"
  | "running"
  | "skipped_overlap";

export type RunView = {
  ts: string;
  due: string;
  status: RunStatus;
  exit_code: number | null;
  /** Server-computed outcome label (contract 06's outcome_label()). */
  label: string;
  matched_pattern: string | null;
  collapsed: number;
  error: string | null;
  stdout_tail: string | null;
  stderr_tail: string | null;
  // GAP 1 (S8 disposition: DROPPED on the live surface) — the
  // approved storyboard renders a run duration ("Ran · 1:47 PM ·
  // 3.2 s") but contract 09's frozen run view carries no
  // duration and the pipeline serves none: the live adapter
  // serves null. The mock adapter still serves its plans'
  // durations for the demo persona.
  duration_label: string | null;
  // GAP 2 (S8 disposition: DROPPED on the live surface) — the
  // storyboard's run-history rows carry a prose detail ("Wake
  // fired · 1 ping posted"). No prose field is frozen on the
  // run view and the pipeline serves none: the live adapter
  // serves null and the rows render the served outcome label.
  // The mock still serves its prose in demo mode.
  detail: string | null;
};

export type ActivityState = "pending" | "overdue" | "served" | "served_acked";

/** The app form of the activity view. Contract 09 freezes the
 *  four states; the remaining fields were unfrozen (gap G7).
 *  S8 disposition: the pipeline serves its own projection
 *  ({ts, due, state, label, tone, acked_at, collapsed}, state
 *  "acked"); the live adapter projects it into this form —
 *  state acked → served_acked, the label verbatim (labels are
 *  served, contract 06), since = the served ts, and ping_id
 *  joined from the served pending pings for the same job
 *  ("" when no pending ping exists — the field is carried for
 *  the mock's form; no view renders it). */
export type ActivityView = {
  /** One of contract 09's four named activity states. */
  state: ActivityState;
  /** The served phrase for the state ("Overdue past ack timeout", …). */
  label: string;
  ping_id: string;
  since: string;
};

// ----------------------------------------------------------------
// Contract 09 — the job view and job detail.

// The served classification (contract 09, amendment;
// schema: contracts/schemas/job-view.schema.json).
// Every job is the operator's own or a built-in; built-ins
// are either family built-ins (they live under an app or
// pipeline service — family + the "Open in" target are
// served) or direct built-ins (the app's own machinery —
// both fields null; group placement is the whole statement).
export type JobAudience = "operator" | "builtin";
export type JobFamily =
  | "venue"
  | "arming"
  | "attention"
  | "workbench"
  | "dispatch";
export type OpenInTarget = "runner" | "workbench" | "attention" | "dispatch";

// Entry config (the same amendment): a knob-bearing entry's
// config block, served on job detail with the store's
// version stamp. The frontend renders this form as served —
// it hardcodes no knob. config is null on knobless entries.
export type ConfigKnob = {
  key: string;
  label: string;
  type: "integer" | "number";
  unit: string;
  value: number;
  min: number;
  max: number;
};

export type ConfigConstraint = {
  kind: "lt";
  left: string;
  right: string;
  message: string;
};

export type ConfigView = {
  version: number;
  knobs: ConfigKnob[];
  constraints: ConfigConstraint[];
};

export type JobView = {
  id: string;
  kind: "scripted" | "agent";
  status: "active" | "suspended";
  suspend_reason: string | null;
  owner: string;
  cadence: Cadence;
  cadence_label: string;
  timezone: string;
  next_due: string | null;
  next_due_in_secs: number | null;
  last_run: RunView | null;
  last_activity: ActivityView | null;
  runs_24h: number;
  failures_24h: number;
  failure_streak: number;
  expected_wakes_per_day: number;
  report_mode: string;
  audience: JobAudience;
  family: JobFamily | null;
  open_in: OpenInTarget | null;
};

export type DueView = {
  due: string;
  outcome: "fired" | "collapsed" | "skipped_overlap" | "pending";
  collapsed: number;
};

/** One row of job detail's ping-history window — the server's
 *  own row form (contract 09: the window is the detail's last
 *  20 ping ledger events, each reduced to ts / kind / ping_id /
 *  ping_kind / server-computed detail). S8 conformed the app
 *  to this served row; the mock adapter projects the same rows
 *  from its ledger. (The richer record-based history the
 *  storyboard drew is not served by /api/v1 — named in the S8
 *  dispositions, contract 09.) */
export type PingHistoryRow = {
  ts: string;
  kind: string;
  ping_id: string | null;
  ping_kind: string | null;
  detail: string;
};

export type JobDetailView = JobView & {
  title: string;
  suspended_on: string | null;
  timeout_secs: number | null;
  ok_exit_codes: number[];
  run: JobEntry["run"] | null;
  body: string | null;
  escalate_body: string | null;
  state_paths: string[];
  report: ReportBlock | null;
  classification: string;
  lifetime: string;
  self_removal: string | null;
  catalog: CatalogBlock | null;
  /** The entry's config block as served (null = the entry
   *  takes no knobs; no config form renders). The pipeline
   *  serves the blocks (contract 09 amendment, pipeline
   *  serving) — version stamp included; a store whose
   *  entries carry no blocks serves null honestly. */
  config: ConfigView | null;
  recent_runs: RunView[];
  recent_dues: DueView[];
  ping_history: PingHistoryRow[];
};

// ----------------------------------------------------------------
// The outbox ping record — contracts/schemas/outbox-ping.schema.json
// (additionalProperties: false; this is the whole field set).

export type PingRecord = {
  id: string;
  job_id: string;
  due: string;
  kind: "agent-due" | "escalation" | "report";
  body_ref: string | null;
  detail: Record<string, unknown>;
  created: string;
  state: string;
  coalesced_count: number;
  last_woken_at: string | null;
  acked_at?: string;
  void_reason?: string;
};

/** Contract 09's pings view: each pending ping + age + overdue. */
export type PingView = PingRecord & {
  age_secs: number;
  overdue: boolean;
  /** The ping's display summary, carried in detail.summary by the
   *  writer (detail is the schema's free-form field). */
  summary: string;
};

// ----------------------------------------------------------------
// Contract 09's ledger view over contract 05's ledger events
// (contracts/schemas/ledger-event.schema.json).

export type LedgerEventRaw = {
  ts: string;
  kind: string;
  job_id?: string;
  status?: string;
  [key: string]: unknown;
};

/** A ledger event before the store stamps its ts. */
export type LedgerEventInput = {
  kind: string;
  job_id?: string;
  status?: string;
  [key: string]: unknown;
};

export type LedgerEventView = {
  ts: string;
  kind: string;
  job_id: string | null;
  /** Server-computed human detail (contract 09). */
  detail: string;
};

export type LedgerView = {
  served_at: string;
  events: LedgerEventView[];
};

// ----------------------------------------------------------------
// Contract 09's overview.

export type OverviewView = {
  served_at: string;
  server_now: string;
  server_status: string;
  state_error: string | null;
  registry_errors: string[];
  pid: number;
  uptime_secs: number;
  last_tick: string;
  running_jobs: string[];
  totals_by_kind: { scripted: number; agent: number };
  totals_by_status: { active: number; suspended: number };
  outbox_by_kind: Record<string, number>;
  outbox_aged: number;
  totals_24h: {
    runs: number;
    failures: number;
    wakeups_served: number;
    pings_created: number;
  };
  expected_wakes_per_day: number;
  /** The storage summary in the server's own served form
   *  (contract 09 names "the storage summary" without freezing
   *  its fields; the pinned server's block is the shape of
   *  record — S8 conformed the app to it. The mock's earlier
   *  state/disk figures were storyboard dressing no route
   *  serves.) */
  storage: {
    kind: string;
    events: number;
    db_bytes: number;
    oldest: string | null;
    newest: string | null;
    retention_days: number;
    last_prune: { ts: string; dropped: number } | null;
  };
  /** The overview's served config values — exactly the four
   *  the pipeline serves in this view. */
  config: {
    port: number;
    tick_secs: number;
    default_timezone: string;
    outbox_ack_timeout_secs: number;
  };
  // GAP 3 (S8 disposition: NOT FROZEN — dropped on the live
  // surface) — the storyboard's Overview carries the flap
  // NoticeRow; contract 09's overview field list names no
  // notice and the pipeline serves none, so the live adapter
  // serves null. The mock still computes its flap notice in
  // demo mode.
  notice: { tone: "warn" | "info"; title: string; text: string } | null;
};

// ----------------------------------------------------------------
// Action results — contract 04's /ops response envelope
// ({ok: true, ...} | {ok: false, error: <closed-set name>, detail}).

export type ActionResult =
  | { ok: true }
  | { ok: false; error: string; detail: string };
