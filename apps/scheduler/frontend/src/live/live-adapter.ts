// The LIVE scheduler adapter (S8) — SchedulerApi over the
// pipeline's /api/v1 (contract 09), fed by the moved
// scheduling server's view projections over the pipeline
// registry + scheduling stores.
//
// The server's payloads are the shapes of record (contract
// 09 §2 payloads; the served-payload diff against the pinned
// app over the S1-capture fixture store is EMPTY except the
// dispositioned amendment-3 removals — tools/live/). This
// adapter projects those payloads into the app's view types;
// where an app field encodes something no route serves, the
// app conformed to the served shape (types.ts carries the
// per-field dispositions). Labels pass verbatim — they are
// server-computed (contract 06); the only translations are
// the run-status vocabulary (server failure / spawn_error →
// the app's failed / could_not_start) and the activity state
// acked → served_acked.
//
// The pipeline serving the S8 lane named as its remaining
// home has landed (contract 09's pipeline-serving section):
// the classification axis rides every job view, config
// blocks ride the job detail with their version stamp, the
// guarded config save is POST /api/v1/jobs/<id>/config, and
// the acked-pings window is GET /api/v1/pings/recent. This
// adapter consumes all of it from the payloads — it carries
// no classification table and no config seed (the mock's
// seed copies live with the mock). Where the served detail
// carries config: null (a knobless entry, or a store whose
// entries carry no blocks) the adapter serves null —
// honest absence, exactly as served.
//
// Refresh model: the getters are synchronous over a snapshot
// cache, exactly like the mock. refresh() pulls the five
// list views in parallel and prefetches every job detail;
// subscribe() polls on an interval. A failed refresh keeps
// the last-good snapshot on screen (contract 09's
// bridge-down rule: stale data, never a blank or a false
// "server down") and records lastError for diagnostics.

import type { SchedulerApi } from "../api";
import type {
  ActionResult,
  ActivityState,
  ActivityView,
  Cadence,
  CatalogBlock,
  ConfigView,
  DueView,
  JobAudience,
  JobDetailView,
  JobFamily,
  JobView,
  LedgerEventView,
  LedgerView,
  OpenInTarget,
  OverviewView,
  PingHistoryRow,
  PingRecord,
  PingView,
  ReportBlock,
  RunStatus,
  RunView,
} from "../types";

// ---------------------------------------------------------------
// The served payloads (the pipeline server's own forms).

type ServerRun = {
  ts: string;
  due: string | null;
  status: string;
  exit_code: number | null;
  label: string;
  matched_pattern: string | null;
  collapsed: number;
  error: string | null;
  stdout_tail: string;
  stderr_tail: string;
};

type ServerActivity = {
  ts: string;
  due: string;
  state: string;
  label: string;
  tone: string;
  acked_at: string | null;
  collapsed: number;
};

type ServerJob = {
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
  last_run: ServerRun | null;
  last_activity: ServerActivity | null;
  activity_24h: { dues: number; acked: number; overdue: boolean } | null;
  runs_24h: { total: number; ok: number; failed: number };
  failure_streak: number;
  expected_wake_per_day: number;
  report_when: string;
  // The classification axis, served on every job view
  // (contract 09 amendment; pipeline classification.py).
  audience: JobAudience;
  family: JobFamily | null;
  open_in: OpenInTarget | null;
};

type ServerJobDetail = ServerJob & {
  detail: {
    title: string | null;
    timeout_secs: number;
    ok_exit_codes: number[];
    run: JobDetailView["run"];
    body: string | null;
    escalate_body: string | null;
    state_paths: string[] | null;
    report: ReportBlock;
    classification: string | null;
    lifetime: string | null;
    // The detail projections the pipeline serving added:
    // the entry's own fields, served (null where the entry
    // carries none). catalog is projected to the view axis
    // only ({origin, generality, use_case}).
    suspended_on: string | null;
    self_removal: string | null;
    catalog: CatalogBlock | null;
    config: ConfigView | null;
  };
  recent_runs: ServerRun[];
  recent_dues: { ts: string; due: string; collapsed: number }[];
  ping_history: PingHistoryRow[];
};

type ServerPing = PingRecord & { age_secs: number; overdue: boolean };

/** The G5 window's served form: the acked outbox records
 *  themselves, newest ack first — no age/overdue projection
 *  rides this route (it serves the records, contract 09). */
type ServerRecentPingsPayload = { served_at: string; pings: PingRecord[] };

type ServerOverview = {
  served_at: string;
  server_now: string;
  status: string;
  state_error: string | null;
  registry_errors: string[];
  pid: number;
  uptime_secs: number;
  last_tick: string;
  running: string[];
  registry: {
    total: number;
    by_kind: Record<string, number>;
    by_status: Record<string, number>;
  };
  outbox: { depth: number; by_kind: Record<string, number>; aged: number };
  totals_24h: OverviewView["totals_24h"];
  expected_wake_per_day: number;
  storage: OverviewView["storage"];
  config: OverviewView["config"];
};

type ServerJobsPayload = { served_at: string; jobs: ServerJob[] };
type ServerPingsPayload = { served_at: string; pings: ServerPing[] };
type ServerLedgerPayload = { served_at: string; events: LedgerEventView[] };

// ---------------------------------------------------------------
// Projections — server payload → app view. Exported for the
// adapter-contract tests (tools/check-live.ts).

const RUN_STATUS: Record<string, RunStatus> = {
  ok: "ok",
  failure: "failed",
  timeout: "timeout",
  spawn_error: "could_not_start",
  skipped_overlap: "skipped_overlap",
};

export function mapRun(rec: ServerRun): RunView {
  return {
    ts: rec.ts,
    due: rec.due ?? "",
    status: RUN_STATUS[rec.status] ?? "failed",
    exit_code: rec.exit_code,
    label: rec.label,
    matched_pattern: rec.matched_pattern,
    collapsed: rec.collapsed,
    error: rec.error,
    stdout_tail: rec.stdout_tail,
    stderr_tail: rec.stderr_tail,
    // Gaps G1/G2: dropped on the live surface (no duration or
    // run prose is served) — the rows render the served label.
    duration_label: null,
    detail: null,
  };
}

export function mapActivity(
  activity: ServerActivity,
  pendingPingId: string | undefined,
): ActivityView {
  const state = (
    activity.state === "acked" ? "served_acked" : activity.state
  ) as ActivityState;
  return {
    state,
    label: activity.label,
    ping_id: pendingPingId ?? "",
    since: activity.ts,
  };
}

/** Pending ping id per job, joined from the served pending
 *  pings (the activity projection names no ping; contract 09
 *  gap G7's join). */
export function pendingIndex(
  payload: ServerPingsPayload,
): Map<string, string> {
  const index = new Map<string, string>();
  for (const ping of payload.pings) {
    if (!index.has(ping.job_id)) index.set(ping.job_id, ping.id);
  }
  return index;
}

export function mapJobView(
  job: ServerJob,
  pendingByJob: Map<string, string>,
): JobView {
  return {
    id: job.id,
    kind: job.kind,
    status: job.status,
    suspend_reason: job.suspend_reason,
    owner: job.owner,
    cadence: job.cadence,
    cadence_label: job.cadence_label,
    timezone: job.timezone,
    next_due: job.next_due,
    next_due_in_secs: job.next_due_in_secs,
    last_run: job.last_run ? mapRun(job.last_run) : null,
    last_activity: job.last_activity
      ? mapActivity(job.last_activity, pendingByJob.get(job.id))
      : null,
    runs_24h: job.runs_24h.total,
    failures_24h: job.runs_24h.failed,
    failure_streak: job.failure_streak,
    expected_wakes_per_day: job.expected_wake_per_day,
    report_mode: job.report_when,
    // The served classification axis, verbatim (the server
    // applies the operator default for unlisted ids itself).
    audience: job.audience,
    family: job.family,
    open_in: job.open_in,
  };
}

export function mapRecentDues(detail: ServerJobDetail): DueView[] {
  // The served window is the engine's agent_due records,
  // projected with the app's established reading (the mock's
  // own due projection): a record that folded cadence points
  // (collapsed > 0) reads collapsed, else fired.
  // skipped_overlap dues are run records, not due records —
  // they surface in the Ledger view, as on the pinned app.
  const rows: DueView[] = detail.recent_dues.map((row) => ({
    due: row.due,
    outcome: row.collapsed > 0 ? "collapsed" : "fired",
    collapsed: row.collapsed,
  }));
  if (detail.status === "active" && detail.next_due) {
    rows.unshift({ due: detail.next_due, outcome: "pending", collapsed: 0 });
  }
  return rows.slice(0, 50);
}

export function mapJobDetail(
  detail: ServerJobDetail,
  pendingByJob: Map<string, string>,
): JobDetailView {
  const block = detail.detail;
  return {
    ...mapJobView(detail, pendingByJob),
    title: block.title ?? "",
    suspended_on: block.suspended_on,
    timeout_secs: block.timeout_secs,
    ok_exit_codes: block.ok_exit_codes,
    run: block.run,
    body: block.body,
    escalate_body: block.escalate_body,
    state_paths: block.state_paths ?? [],
    report: block.report,
    classification: block.classification ?? "",
    lifetime: block.lifetime ?? "",
    self_removal: block.self_removal,
    catalog: block.catalog,
    // The served config block (null as served — knobless
    // entry, or a store whose entries carry no blocks).
    config: block.config,
    recent_runs: detail.recent_runs.map(mapRun),
    recent_dues: mapRecentDues(detail),
    ping_history: detail.ping_history,
  };
}

function summarize(ping: PingRecord): string {
  const summary = ping.detail?.summary;
  return typeof summary === "string" ? summary : ping.job_id;
}

export function mapPing(ping: ServerPing): PingView {
  return { ...ping, summary: summarize(ping) };
}

/** The G5 window's records → the app's ping view. The route
 *  serves the outbox records bare; age is arithmetic over
 *  served values (created vs the overview's server_now —
 *  the same arithmetic the mock performs), and an acked
 *  record is never overdue. */
export function mapRecentPing(ping: PingRecord, serverNow: string): PingView {
  const nowMs = Date.parse(serverNow);
  const createdMs = Date.parse(ping.created);
  const age =
    Number.isFinite(nowMs) && Number.isFinite(createdMs)
      ? Math.max(0, Math.floor((nowMs - createdMs) / 1000))
      : 0;
  return { ...ping, age_secs: age, overdue: false, summary: summarize(ping) };
}

export function mapOverview(overview: ServerOverview): OverviewView {
  return {
    served_at: overview.served_at,
    server_now: overview.server_now,
    server_status: overview.status,
    state_error: overview.state_error,
    registry_errors: overview.registry_errors,
    pid: overview.pid,
    uptime_secs: overview.uptime_secs,
    last_tick: overview.last_tick,
    running_jobs: overview.running,
    totals_by_kind: {
      scripted: overview.registry.by_kind.scripted ?? 0,
      agent: overview.registry.by_kind.agent ?? 0,
    },
    totals_by_status: {
      active: overview.registry.by_status.active ?? 0,
      suspended: overview.registry.by_status.suspended ?? 0,
    },
    outbox_by_kind: overview.outbox.by_kind,
    outbox_aged: overview.outbox.aged,
    totals_24h: overview.totals_24h,
    expected_wakes_per_day: overview.expected_wake_per_day,
    storage: overview.storage,
    config: overview.config,
    // Gap G3: not frozen, not served — honest absence.
    notice: null,
  };
}

// ---------------------------------------------------------------

/** The served timeout: a request that has not answered
 *  within it counts as a failed attempt. It is sized to the
 *  slowest legitimate view, not to the poll interval — inside
 *  the bound the state is "connecting", never "unreachable". */
const SERVED_TIMEOUT_MS = 30_000;

export type FetchLike = (
  url: string,
  init?: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
  },
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

/** Reachability is a three-state read of the refresh cycle,
 *  never a verdict on an in-flight request: "connecting"
 *  while an attempt is running (or none has completed yet),
 *  the server's own status once a snapshot has landed, and
 *  "unreachable" only once an attempt has actually failed —
 *  a slow view (the jobs list above all) is slow, not down.
 *  The empty snapshot therefore starts at "connecting". */
const EMPTY_OVERVIEW: OverviewView = {
  served_at: "",
  server_now: "",
  server_status: "connecting",
  state_error: null,
  registry_errors: [],
  pid: 0,
  uptime_secs: 0,
  last_tick: "",
  running_jobs: [],
  totals_by_kind: { scripted: 0, agent: 0 },
  totals_by_status: { active: 0, suspended: 0 },
  outbox_by_kind: {},
  outbox_aged: 0,
  totals_24h: { runs: 0, failures: 0, wakeups_served: 0, pings_created: 0 },
  expected_wakes_per_day: 0,
  storage: {
    kind: "",
    events: 0,
    db_bytes: 0,
    oldest: null,
    newest: null,
    retention_days: 0,
    last_prune: null,
  },
  config: { port: 0, tick_secs: 0, default_timezone: "", outbox_ack_timeout_secs: 0 },
  notice: null,
};

/** G8's refusal for the verbs that do not graduate: contract
 *  09's preserve-listed read-only rule stands — the shell
 *  renders the registry and the outbox; the verbs live in the
 *  operator CLIs and chat. `outside_scope` is the app
 *  envelope's name for a refusal outside the shell's scope,
 *  refused before anything is staged (contract 04's closed
 *  error set, applied to the shell's surface). */
function readOnlyRefusal(verb: string, home: string): ActionResult {
  return {
    ok: false,
    error: "outside_scope",
    detail:
      `${verb} does not graduate to the live shell: contract 09's ` +
      `read-only rule stands — ${home}. The mock adapter exercises ` +
      `the verb against its fake store for the demo persona.`,
  };
}

/** The live base rule (the ?api= cure, 2026-11-16 — the
 *  runner entry's HIGH finding, cured there at b54ebb2 and
 *  here to the same standard): the live adapter answers
 *  from the serving origin, and an injected base is
 *  honoured only when it stays on that origin — "" (the
 *  origin root) or a same-origin path ("/...", never
 *  "//..."). An absolute, protocol-relative, scheme, or
 *  bare-relative base is refused to the origin root, so no
 *  injection — a crafted link, a foreign embed — can point
 *  the adapter's traffic, including the graduated config
 *  write, at another origin. The cure refuses the base,
 *  not the surface. */
export function sanitizeBaseUrl(base: string): string {
  if (base === "") return "";
  if (base.startsWith("/") && !base.startsWith("//")) return base;
  return "";
}

export class LiveSchedulerApi implements SchedulerApi {
  private readonly baseUrl: string;
  private readonly fetchFn: FetchLike;
  private readonly pollMs: number;
  private readonly listeners = new Set<() => void>();
  private timer: ReturnType<typeof setInterval> | null = null;

  private overview: OverviewView = EMPTY_OVERVIEW;
  private jobs: JobView[] = [];
  private pings: PingView[] = [];
  private recentPings: PingView[] = [];
  private ledger: LedgerView = { served_at: "", events: [] };
  private readonly details = new Map<string, JobDetailView>();
  private pendingByJob = new Map<string, string>();
  private readonly inflightDetails = new Set<string>();
  /** The last refresh failure, for diagnostics; the snapshot
   *  on screen stays last-good (bridge-down rule). */
  lastError: string | null = null;
  /** True once any refresh has landed a snapshot; before
   *  that, the empty snapshot's status tracks the attempt
   *  (connecting in flight, unreachable on a failed attempt). */
  private everLive = false;

  constructor(
    opts: { baseUrl?: string; fetchFn?: FetchLike; pollMs?: number } = {},
  ) {
    this.baseUrl = sanitizeBaseUrl(opts.baseUrl ?? "").replace(/\/$/, "");
    this.fetchFn =
      opts.fetchFn ??
      ((url: string, init?: Parameters<FetchLike>[1]) =>
        fetch(url, init) as ReturnType<FetchLike>);
    this.pollMs = opts.pollMs ?? 5000;
  }

  /** The first snapshot load. Resolves even when the bridge
   *  is down — a failed attempt reads "unreachable", an
   *  attempt in flight reads "connecting", and polling keeps
   *  retrying either way. */
  async ready(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    if (!this.everLive && this.overview.server_status === "unreachable") {
      // A retry is now in flight: the pending state, not the
      // last attempt's verdict, is what the snapshot reads.
      this.overview = EMPTY_OVERVIEW;
      this.emit();
    }
    try {
      const [overview, jobs, pings, ledger, recent] = await Promise.all([
        this.getJson<ServerOverview>("/api/v1/overview"),
        this.getJson<ServerJobsPayload>("/api/v1/jobs"),
        this.getJson<ServerPingsPayload>("/api/v1/pings"),
        this.getJson<ServerLedgerPayload>("/api/v1/ledger?limit=500"),
        // The G5 window is additive: a server without the
        // route degrades to the last-good window, never to a
        // failed refresh.
        this.getJson<ServerRecentPingsPayload>("/api/v1/pings/recent").catch(
          () => null,
        ),
      ]);
      this.pendingByJob = pendingIndex(pings);
      this.overview = mapOverview(overview);
      this.jobs = jobs.jobs.map((job) => mapJobView(job, this.pendingByJob));
      this.pings = pings.pings.map(mapPing);
      if (recent !== null) {
        this.recentPings = recent.pings.map((ping) =>
          mapRecentPing(ping, overview.server_now),
        );
      }
      // The ledger feed is served in the app's own event form
      // (detail strings included) — pass-through.
      this.ledger = { served_at: ledger.served_at, events: ledger.events };
      this.lastError = null;
      this.everLive = true;
      this.emit();
      await this.prefetchDetails();
    } catch (err) {
      this.lastError = err instanceof Error ? err.message : String(err);
      if (!this.everLive) {
        // The attempt has completed and failed: only now is
        // "unreachable" a true read. (With a snapshot landed,
        // the bridge-down rule keeps last-good on screen.)
        this.overview = { ...EMPTY_OVERVIEW, server_status: "unreachable" };
        this.emit();
      }
    }
  }

  private async prefetchDetails(): Promise<void> {
    let stored = false;
    await Promise.all(
      this.jobs.map(async (job) => {
        try {
          const payload = await this.getJson<ServerJobDetail>(
            `/api/v1/jobs/${encodeURIComponent(job.id)}`,
          );
          this.details.set(job.id, mapJobDetail(payload, this.pendingByJob));
          stored = true;
        } catch {
          // A detail that fails keeps its last-good copy; the
          // list views already refreshed.
        }
      }),
    );
    if (stored) this.emit();
  }

  private async getJson<T>(path: string): Promise<T> {
    const res = await new Promise<Awaited<ReturnType<FetchLike>>>(
      (resolve, reject) => {
        const timer = setTimeout(
          () =>
            reject(
              new Error(
                `GET ${path} → no answer within ${SERVED_TIMEOUT_MS / 1000}s`,
              ),
            ),
          SERVED_TIMEOUT_MS,
        );
        this.fetchFn(`${this.baseUrl}${path}`).then(
          (r) => {
            clearTimeout(timer);
            resolve(r);
          },
          (err: unknown) => {
            clearTimeout(timer);
            reject(err instanceof Error ? err : new Error(String(err)));
          },
        );
      },
    );
    if (!res.ok) throw new Error(`GET ${path} → HTTP ${res.status}`);
    return (await res.json()) as T;
  }

  private emit(): void {
    for (const listener of [...this.listeners]) listener();
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    if (this.listeners.size === 1 && this.timer === null) {
      this.timer = setInterval(() => {
        void this.refresh();
      }, this.pollMs);
    }
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0 && this.timer !== null) {
        clearInterval(this.timer);
        this.timer = null;
      }
    };
  }

  getOverview(): OverviewView {
    return this.overview;
  }

  listJobs(): JobView[] {
    return this.jobs;
  }

  getJob(id: string): JobDetailView | null {
    const cached = this.details.get(id);
    if (cached) return cached;
    if (!this.inflightDetails.has(id)) {
      this.inflightDetails.add(id);
      this.getJson<ServerJobDetail>(`/api/v1/jobs/${encodeURIComponent(id)}`)
        .then((payload) => {
          this.details.set(id, mapJobDetail(payload, this.pendingByJob));
          this.emit();
        })
        .catch(() => {
          // Stays uncached; the next render retries.
        })
        .finally(() => {
          this.inflightDetails.delete(id);
        });
    }
    return null;
  }

  listPings(): PingView[] {
    return this.pings;
  }

  /** The G5 acked window (GET /api/v1/pings/recent): acked
   *  outbox records, newest ack first, as served. */
  listRecentPings(): PingView[] {
    return this.recentPings;
  }

  getLedger(limit: number): LedgerView {
    return {
      served_at: this.ledger.served_at,
      events: this.ledger.events.slice(0, Math.max(0, limit)),
    };
  }

  runNow(_jobId: string): ActionResult {
    return readOnlyRefusal(
      "Run now",
      "jobs fire on their cadence under the engine; there is no shell fire verb",
    );
  }

  setJobEnabled(_jobId: string, _enabled: boolean): ActionResult {
    return readOnlyRefusal(
      "Suspend / resume",
      "suspend and resume are registry writes, and registry writes ride the one writer path from the operator CLI, not the shell",
    );
  }

  ackPing(_pingId: string, _ackedBy: string): ActionResult {
    return readOnlyRefusal(
      "Acknowledge",
      "acks land through bin/sched ack or the operator chat; the shell renders the outbox, it does not write it",
    );
  }

  /** The graduated verb (contract 09 amendment): the
   *  guarded config save, POST /api/v1/jobs/<id>/config.
   *  The server is the writer — validation, the stale-stamp
   *  CAS, and the ledgering all happen there; this adapter
   *  presents the loaded version and the typed values and
   *  surfaces the served envelope whole, exactly as the
   *  mock surfaces its refusals (bad_request whole-refusal,
   *  no_match stale-stamp, not_found unknown job). On
   *  success the response carries the new served config,
   *  which replaces the cached detail's block before this
   *  resolves, so the form's post-save read is already
   *  fresh. A bridge failure is an io_error refusal —
   *  nothing was written that the adapter knows of, and the
   *  typed values stay in the form. */
  async saveConfig(
    jobId: string,
    version: number,
    values: Record<string, number>,
  ): Promise<ActionResult> {
    type SavePayload = {
      ok: boolean;
      error?: string;
      detail?: string;
      config?: ConfigView | null;
    };
    let payload: SavePayload;
    try {
      const res = await this.fetchFn(
        `${this.baseUrl}/api/v1/jobs/${encodeURIComponent(jobId)}/config`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ version, values }),
        },
      );
      payload = (await res.json()) as SavePayload;
    } catch (err) {
      return {
        ok: false,
        error: "io_error",
        detail:
          "The config save did not reach the server " +
          `(${err instanceof Error ? err.message : String(err)}) — ` +
          "nothing was applied; the typed values are still in the form.",
      };
    }
    if (!payload.ok) {
      return {
        ok: false,
        error: payload.error ?? "io_error",
        detail: payload.detail ?? "The server refused the save.",
      };
    }
    const cached = this.details.get(jobId);
    if (cached && payload.config !== undefined) {
      this.details.set(jobId, { ...cached, config: payload.config });
    }
    this.emit();
    return { ok: true };
  }
}
