// Scheduler views — the form model. Pure presentation over
// the served shapes: every label, count, ordering and age
// the server can compute arrives ready in the payloads (the
// backend is the original scheduler's /api/v1, verbatim
// through the bridge envelope); this module carries the
// payload types, the envelope translation, and the
// formatting arithmetic the original client (client/pages/
// scheduler/src/app.js) defined — countdowns and snapshot
// ages are the consumer's arithmetic over served values.
//
// Envelope semantics (INTEGRATION.md §3, RESTORE-NOTES §2):
// the scheduler actions return {status, payload, error} —
// status 0 is a transport failure (BRIDGE down, diagnosis
// in `error`), distinct from any server state; status >=
// 400 is a server answer (SERVER down); otherwise payload
// is the backend JSON verbatim. A throw out of the action
// client itself is a bridge failure under the original's
// rules. `unwrap` folds all of that into one thrown
// SchedulerFailure carrying the kind, so the snapshot
// machine counts failures exactly as app.js's refresh()
// did.

import type { LogRowEntry, LogRowTone } from "@workhorse/kit/components/LogRow";
import { api } from "../../lib/actions";

/** The common envelope every scheduler action returns. */
export type Envelope = Awaited<ReturnType<typeof api.getOverview>>;

export type FailureKind = "bridge" | "server";

export class SchedulerFailure extends Error {
  readonly kind: FailureKind;
  constructor(kind: FailureKind, message: string) {
    super(message);
    this.name = "SchedulerFailure";
    this.kind = kind;
  }
}

/** One bridge call, translated: resolves the payload on a
 *  served answer; throws SchedulerFailure otherwise. */
export async function unwrap<T>(call: Promise<Envelope>): Promise<T> {
  let env: Envelope;
  try {
    env = await call;
  } catch (err) {
    throw new SchedulerFailure("bridge", String(err));
  }
  if (env.status === 0) {
    throw new SchedulerFailure("bridge", env.error ?? "bridge unreachable");
  }
  if (env.status >= 400) {
    throw new SchedulerFailure("server", `server answered ${env.status}`);
  }
  return env.payload as T;
}

/* ---------------- served payload shapes ----------------
 * Field-for-field what the scheduler backend serves (its
 * serving/api.py projections, the original client's
 * consumption). Two naming notes, both verified against
 * both backends: the suspension reason is served as
 * `suspend_reason` (the original client read a
 * `suspended_reason` field its own backend never served,
 * so the reason silently never rendered — the views read
 * the served name); `registry.migrated` is served by the
 * mega backend's overview as the registry entry count,
 * which under admission semantics (contract 13; the
 * migration field family was abolished by contract 14
 * amendment 3) is the migrated count. It stays optional
 * here so payloads without it render as honest absence. */

export interface OverviewPayload {
  served_at: string;
  status: string;
  pid: number;
  uptime_secs: number;
  expected_wake_per_day: number;
  registry: {
    total: number;
    by_kind: Record<string, number>;
    migrated?: number;
  };
  registry_errors?: unknown[];
  totals_24h: {
    runs: number;
    failures: number;
    wakeups_served: number;
    pings_created: number;
  };
  outbox: { depth: number; aged: number };
  running: string[];
  storage: {
    kind: string;
    db_bytes: number;
    events: number;
    retention_days: number;
    last_prune: { ts: string; dropped: number } | null;
  };
}

export interface RunView {
  ts: string;
  label: string;
  matched_pattern: string | null;
  collapsed: number | null;
  stdout_tail?: string | null;
  stderr_tail?: string | null;
}

export interface AgentActivity {
  label: string;
  tone: string;
  ts: string;
}

export interface JobPayload {
  id: string;
  kind: string;
  status: string;
  suspend_reason: string | null;
  owner: string | null;
  cadence_label: string;
  timezone: string;
  next_due: string | null;
  next_due_in_secs: number | null;
  last_run: RunView | null;
  last_activity: AgentActivity | null;
  activity_24h: { dues: number; acked: number; overdue: boolean } | null;
  runs_24h: { total: number; ok: number; failed: number };
  failure_streak: number;
}

export interface JobsPayload {
  served_at: string;
  jobs: JobPayload[];
}

export interface JobDetailPayload {
  id: string;
  detail: {
    timeout_secs: number;
    ok_exit_codes: number[];
    report: { when?: string } | null;
    run: { argv?: string[] } | null;
    state_paths: string[] | null;
    classification: string | null;
  };
  recent_runs: RunView[];
  recent_dues: { ts: string; collapsed: number | null }[];
  ping_history: { ts: string; detail: string }[];
}

export interface PingPayload {
  id: string;
  job_id: string;
  kind: string;
  state?: string;
  due: string;
  created: string;
  acked_at?: string | null;
  overdue: boolean;
  coalesced_count: number;
  body_ref: string | null;
}

export interface PingsPayload {
  served_at: string;
  pings: PingPayload[];
}

export interface LedgerEvent {
  ts: string;
  kind: string;
  job_id: string | null;
  detail: string;
}

export interface LedgerPayload {
  served_at: string;
  events: LedgerEvent[];
}

/** One landed portion of the poll: the payload, the
 *  wall-clock ms when it landed, and the server skew
 *  computed from its own served_at. Portions land
 *  independently — no portion waits for the slowest —
 *  so the assembled state is four of these, not one
 *  all-or-nothing snapshot. */
export interface Portion<T> {
  data: T | null;
  fetchedAt: number | null;
  /** Server clock minus local clock, from served_at. */
  skewMs: number;
}

/* ---------------- snapshot fetch ---------------- */

export const POLL_MS = 30_000;
export const STALE_MS = 60_000;
export const DOWN_AFTER = 2;
/** The Overview feed's window (app.js: getLedger(50)). */
export const LEDGER_FEED_LIMIT = 50;
/** The Ledger view's window — the same call at a
 *  view-level limit (RESTORE-NOTES X-5; schema max 500). */
export const LEDGER_VIEW_LIMIT = 200;
/** The storyboard Pings "Recent" window (the action's own
 *  backend default). */
export const PINGS_RECENT_LIMIT = 20;

/** The poll's calls, one fetcher per portion (app.js's
 *  refresh() set, fired as independent queries — see
 *  hooks.ts): each portion resolves on its own arrival
 *  and renders when it lands. The failure ladder still
 *  reads the four as one machine: a cycle in which any
 *  portion failed counts once, and the first failure in
 *  call order (overview, jobs, pings, ledger) names the
 *  failure kind. A job-detail failure never fails
 *  anything — the detail simply stays null and retries
 *  next poll. */
export function fetchOverview(): Promise<OverviewPayload> {
  return unwrap<OverviewPayload>(api.getOverview({}));
}

export function fetchJobs(): Promise<JobsPayload> {
  return unwrap<JobsPayload>(api.getJobs({}));
}

export function fetchPings(): Promise<PingsPayload> {
  return unwrap<PingsPayload>(api.getPings({}));
}

export function fetchLedgerFeed(): Promise<LedgerPayload> {
  return unwrap<LedgerPayload>(api.getLedger({ limit: LEDGER_FEED_LIMIT }));
}

export async function fetchJobDetail(
  jobId: string,
): Promise<JobDetailPayload | null> {
  try {
    return await unwrap<JobDetailPayload>(api.getJob({ jobId }));
  } catch {
    return null; // list data still refreshes; detail retries next poll
  }
}

/* ---------------- formatting (app.js, verbatim) ---------------- */

export function fmtTime(isoText: string | null | undefined): string {
  if (!isoText) return "—";
  return new Date(isoText).toLocaleString("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function fmtClock(isoText: string | null | undefined): string {
  if (!isoText) return "—";
  return new Date(isoText).toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** The LogRow date token ("Nov 13") for a served instant. */
export function fmtDateToken(isoText: string): string {
  return new Date(isoText).toLocaleDateString("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
  });
}

export function fmtDur(secs: number | null | undefined): string {
  if (secs == null) return "—";
  const s = Math.abs(Math.round(secs));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

/** Age of a served instant against the SERVER clock
 *  (skew-corrected), as app.js's servedAgeSecs. */
export function servedAgeSecs(
  isoText: string | null | undefined,
  skewMs: number,
  nowMs: number,
): number | null {
  if (!isoText) return null;
  const serverNow = nowMs + skewMs;
  return Math.round((serverNow - new Date(isoText).getTime()) / 1000);
}

/** app.js's outcomeClass, as a StatusChip tone: OK and
 *  "· normal" are ok; Failed / Timed out are fail; every
 *  other served label is warn. */
export function outcomeTone(label: string | null | undefined): LogRowTone {
  if (!label) return "idle";
  if (label.startsWith("OK") || label.includes("· normal")) return "ok";
  if (label.startsWith("Failed") || label.startsWith("Timed out")) return "fail";
  return "warn";
}

/* ---------------- ledger presentation ----------------
 * The storyboard's kind chips (Op / Run / Ack / Skip) are
 * presentation over the kind the ledger itself serves —
 * no field is invented (RESTORE-NOTES X-5). Kinds beyond
 * the frame's four carry their own served words. */

export function ledgerKindChip(event: LedgerEvent): { label: string; tone: LogRowTone } {
  switch (event.kind) {
    case "run":
      return { label: "Run", tone: outcomeTone(event.detail) };
    case "ping_acked":
      return { label: "Ack", tone: "ok" };
    case "skipped_overlap":
      return { label: "Skip", tone: "warn" };
    case "op":
      return { label: "Op", tone: "info" };
    case "ping_created":
      return { label: "Ping created", tone: "info" };
    case "ping_woken":
      return { label: "Ping woken", tone: "info" };
    case "ping_coalesced":
      return { label: "Coalesced", tone: "idle" };
    case "ping_voided":
      return { label: "Voided", tone: "idle" };
    case "agent_due":
      return { label: "Due", tone: "info" };
    case "catchup":
      return { label: "Catchup", tone: "info" };
    case "ledger_pruned":
      return { label: "Pruned", tone: "idle" };
    case "registry_error":
      return { label: "Registry error", tone: "fail" };
    case "state_error":
      return { label: "State error", tone: "fail" };
    default:
      return { label: event.kind.replace(/_/g, " "), tone: "idle" };
  }
}

/** A ledger event as the kit's one log row: the served
 *  detail is the headline, the clock leads the meta line,
 *  the job rides after it — the original feed's three
 *  fields (clock, job id, detail) in LogRow's form. */
export function ledgerLogEntry(event: LedgerEvent): LogRowEntry {
  return {
    dateToken: fmtDateToken(event.ts),
    time: fmtClock(event.ts),
    headline: event.detail,
    kind: ledgerKindChip(event),
    meta: event.job_id ?? "—",
  };
}
