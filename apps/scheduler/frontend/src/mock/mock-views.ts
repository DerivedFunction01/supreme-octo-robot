// Contract 09 view projections for the mock adapter
// (split from mock-adapter.ts): every label is computed
// here, server-side, including the ledger detail
// projection — pure functions over the store, called by
// the adapter's SchedulerApi surface.
import type {
  ActivityView,
  JobDetailView,
  JobView,
  LedgerEventRaw,
  LedgerView,
  OverviewView,
  PingHistoryRow,
  PingRecord,
  PingView,
} from "../types";
import {
  cadenceLabel,
  expectedWakesPerDay,
  CLASSIFICATION,
  type JobRuntime,
  type Store,
  DEFAULT_TZ,
} from "./seeds";
import { CONFIG, configView, iso } from "./mock-config";

export function activityFor(store: Store, rt: JobRuntime, now: number): ActivityView | null {
  if (rt.entry.kind !== "agent") return null;
  const pings = store.pings
    .filter((p) => p.job_id === rt.entry.id)
    .sort((a, b) => Date.parse(b.created) - Date.parse(a.created));
  const latest = pings[0];
  if (!latest) return null;
  let state: ActivityView["state"];
  let label: string;
  if (latest.state === "acked") {
    state = "served_acked";
    label = "Served · acked";
  } else if (
    (now - Date.parse(latest.created)) / 1000 >
    CONFIG.outbox_ack_timeout_secs
  ) {
    state = "overdue";
    label = "Overdue past ack timeout";
  } else if (latest.last_woken_at) {
    state = "served";
    label = "Served";
  } else {
    state = "pending";
    label = "Pending";
  }
  return { state, label, ping_id: latest.id, since: latest.created };
}

export function jobView(store: Store, rt: JobRuntime, now: number): JobView {
  const entry = rt.entry;
  const lastRun =
    rt.history.find((r) => r.status !== "skipped_overlap") ?? null;
  let failureStreak = 0;
  for (const run of rt.history) {
    if (run.status === "skipped_overlap") continue;
    if (run.status === "failed" || run.status === "timeout") failureStreak++;
    else break;
  }
  const suspended = entry.status === "suspended";
  // The served classification (contract 09, amendment
  // 2026-11-13): projected from the store's classification
  // table; the client never derives it. The schema checker
  // proves the table covers every seeded entry.
  const cls = CLASSIFICATION[entry.id] ?? {
    audience: "operator" as const,
    family: null,
    open_in: null,
  };
  return {
    id: entry.id,
    kind: entry.kind,
    status: entry.status,
    suspend_reason: entry.suspend_reason ?? null,
    owner: entry.owner,
    audience: cls.audience,
    family: cls.family,
    open_in: cls.open_in,
    cadence: entry.cadence,
    cadence_label: cadenceLabel(entry.cadence),
    timezone: entry.timezone ?? DEFAULT_TZ,
    next_due: !suspended && rt.nextDue !== null ? iso(rt.nextDue) : null,
    next_due_in_secs:
      !suspended && rt.nextDue !== null
        ? Math.max(0, Math.round((rt.nextDue - now) / 1000))
        : null,
    last_run: lastRun,
    last_activity: activityFor(store, rt, now),
    runs_24h: rt.stats.runs24h,
    failures_24h: rt.stats.failures24h,
    failure_streak: failureStreak,
    expected_wakes_per_day: expectedWakesPerDay(entry.cadence),
    report_mode: entry.report?.when ?? "never",
  };
}

export function listJobs(store: Store): JobView[] {
  const now = Date.now();
  return [...store.jobs.values()]
    .map((rt) => jobView(store, rt, now))
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function getJobDetail(store: Store, id: string): JobDetailView | null {
  const rt = store.jobs.get(id);
  if (!rt) return null;
  const now = Date.now();
  const entry = rt.entry;
  const base = jobView(store, rt, now);
  const pendingDue =
    entry.status === "active" && rt.nextDue !== null
      ? [{ due: iso(rt.nextDue), outcome: "pending" as const, collapsed: 0 }]
      : [];
  return {
    ...base,
    title: entry.title,
    suspended_on: entry.suspended_on ?? null,
    timeout_secs: entry.timeout_secs ?? null,
    ok_exit_codes: entry.report?.ok_exit_codes ?? [0],
    run: entry.run ?? null,
    body: entry.body ?? null,
    escalate_body: entry.escalate_body ?? null,
    state_paths: entry.state_paths ?? [],
    report: entry.report ?? null,
    classification: entry.classification,
    config: configView(rt),
    lifetime: entry.lifetime,
    self_removal: entry.self_removal ?? null,
    catalog: entry.catalog ?? null,
    recent_runs: rt.history.slice(0, 50),
    recent_dues: [...pendingDue, ...rt.dues].slice(0, 50),
    ping_history: pingHistoryRows(store, id),
  };
}

/** Job detail's ping-history window in the server's row
 *  form (S8 conformance): the job's last 20 ping ledger
 *  events, newest first, each reduced to the served row;
 *  the detail string is the server's own projection
 *  ("ping <kind> <id>", contract 09's ledger reduction). */
export function pingHistoryRows(store: Store, jobId: string): PingHistoryRow[] {
  const KINDS = new Set([
    "ping_created",
    "ping_woken",
    "ping_acked",
    "ping_coalesced",
    "ping_voided",
  ]);
  return [...store.ledger]
    .reverse()
    .filter((e) => e.job_id === jobId && KINDS.has(e.kind))
    .slice(0, 20)
    .map((e) => ({
      ts: e.ts,
      kind: e.kind,
      ping_id: typeof e.ping_id === "string" ? e.ping_id : null,
      ping_kind: typeof e.ping_kind === "string" ? e.ping_kind : null,
      detail:
        `ping ${typeof e.ping_kind === "string" ? e.ping_kind : ""} ${typeof e.ping_id === "string" ? e.ping_id : ""}`.trim(),
    }));
}

export function pingView(ping: PingRecord, now: number): PingView {
  const age = Math.max(0, Math.floor((now - Date.parse(ping.created)) / 1000));
  const summary =
    typeof ping.detail.summary === "string" ? ping.detail.summary : ping.job_id;
  return {
    ...ping,
    age_secs: age,
    overdue: ping.state === "pending" && age > CONFIG.outbox_ack_timeout_secs,
    summary,
  };
}

export function listPings(store: Store): PingView[] {
  const now = Date.now();
  return store.pings
    .filter((p) => p.state === "pending")
    .sort((a, b) => Date.parse(a.created) - Date.parse(b.created))
    .map((p) => pingView(p, now));
}

export function listRecentPings(store: Store): PingView[] {
  const now = Date.now();
  return store.pings
    .filter((p) => p.state === "acked")
    .sort((a, b) => Date.parse(b.created) - Date.parse(a.created))
    .map((p) => pingView(p, now));
}

export function ledgerDetail(store: Store, event: LedgerEventRaw): string {
  const jobId = typeof event.job_id === "string" ? event.job_id : null;
  switch (event.kind) {
    case "run": {
      const rt = jobId ? store.jobs.get(jobId) : undefined;
      const run = rt?.history.find((r) => r.due === event.due);
      if (event.status === "failed") return `${jobId} failed · exit ${event.exit_code}`;
      if (event.status === "timeout") return `${jobId} timed out`;
      if (event.status === "could_not_start") return `${jobId} could not start`;
      const detail = run?.detail ?? null;
      if (detail?.startsWith("Skipped · ")) {
        return `${jobId} ${detail.charAt(0).toLowerCase()}${detail.slice(1)}`;
      }
      if (detail?.startsWith("Completed · ") && detail !== "Completed · exit 0") {
        return `${jobId} completed · ${detail.slice("Completed · ".length)}`;
      }
      return `${jobId} completed${run?.duration_label ? ` · ${run.duration_label}` : ""}`;
    }
    case "op": {
      if (event.op === "config") {
        const label =
          typeof event.label === "string" ? event.label : String(event.knob);
        const unit = typeof event.unit === "string" ? ` ${event.unit}` : "";
        return `${jobId} config · ${label} ${event.old} → ${event.new}${unit}`;
      }
      const what =
        typeof event.path === "string"
          ? event.path
          : Array.isArray(event.argv)
            ? (event.argv as string[]).join(" ")
            : "";
      const note = typeof event.note === "string" ? ` (${event.note})` : "";
      return `${event.op} · ${what}${note}`;
    }
    case "ping_created":
    case "ping_acked":
    case "ping_coalesced": {
      const ping = store.pings.find((p) => p.id === event.ping_id);
      const summary =
        ping && typeof ping.detail.summary === "string"
          ? ping.detail.summary
          : (jobId ?? "ping");
      const verb =
        event.kind === "ping_created"
          ? "Ping created"
          : event.kind === "ping_acked"
            ? "Ping acknowledged"
            : "Ping coalesced";
      return `${verb} · ${summary}`;
    }
    case "catchup":
      return `${jobId} catchup · ${event.collapsed} points collapsed`;
    case "skipped_overlap":
      return `${jobId} skipped · previous run still active`;
    case "agent_due":
      return `${jobId} due · agent ping minted`;
    case "entry_removed":
      return `${jobId} entry removed`;
    default:
      return jobId ?? event.kind;
  }
}

export function getLedger(store: Store, limit: number): LedgerView {
  const now = Date.now();
  const events = [...store.ledger]
    .sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))
    .slice(0, Math.min(500, Math.max(1, limit)))
    .map((event) => ({
      ts: event.ts,
      kind: event.kind,
      job_id: typeof event.job_id === "string" ? event.job_id : null,
      detail: ledgerDetail(store, event),
    }));
  return { served_at: iso(now), events };
}

export function overviewView(store: Store, now: number): OverviewView {
  const jobs = [...store.jobs.values()];
  const pending = store.pings.filter((p) => p.state === "pending");
  const outboxByKind: Record<string, number> = {};
  for (const ping of pending) {
    outboxByKind[ping.kind] = (outboxByKind[ping.kind] ?? 0) + 1;
  }
  return {
    served_at: iso(now),
    server_now: iso(now),
    server_status: "running",
    state_error: null,
    registry_errors: [],
    pid: store.pid,
    uptime_secs: Math.floor((now - store.bootAt) / 1000),
    last_tick: iso(store.lastTick),
    running_jobs: jobs.filter((rt) => rt.running).map((rt) => rt.entry.id),
    totals_by_kind: {
      scripted: jobs.filter((rt) => rt.entry.kind === "scripted").length,
      agent: jobs.filter((rt) => rt.entry.kind === "agent").length,
    },
    totals_by_status: {
      active: jobs.filter((rt) => rt.entry.status === "active").length,
      suspended: jobs.filter((rt) => rt.entry.status === "suspended").length,
    },
    outbox_by_kind: outboxByKind,
    outbox_aged: pending.filter(
      (p) => (now - Date.parse(p.created)) / 1000 > CONFIG.outbox_ack_timeout_secs,
    ).length,
    totals_24h: {
      runs: jobs.reduce((sum, rt) => sum + rt.stats.runs24h, 0),
      failures: jobs.reduce((sum, rt) => sum + rt.stats.failures24h, 0),
      wakeups_served: store.wakeupsServed24h,
      pings_created: store.pingsCreated24h,
    },
    expected_wakes_per_day: jobs
      .filter((rt) => rt.entry.status === "active")
      .reduce((sum, rt) => sum + expectedWakesPerDay(rt.entry.cadence), 0),
    storage: {
      // The server's served form (S8 conformance — the app
      // type carries the pinned storage block, not the
      // storyboard's state/disk figures). db_bytes is the
      // S1 overlay inventory's figure for the live ledger
      // store (40,361,984 B); the range spans the seeded
      // ledger.
      kind: "sqlite",
      events: store.ledger.length,
      db_bytes: 40_361_984,
      oldest: store.ledger[0]?.ts ?? null,
      newest: store.ledger[store.ledger.length - 1]?.ts ?? null,
      retention_days: 90,
      last_prune: null,
    },
    config: {
      port: CONFIG.port,
      tick_secs: CONFIG.tick_secs,
      default_timezone: CONFIG.default_timezone,
      outbox_ack_timeout_secs: CONFIG.outbox_ack_timeout_secs,
    },
    notice: store.flapActive
      ? {
          tone: "warn",
          title: "Write-denial flap active.",
          text: "File writes are degraded; shell-class writes route through the ops bin.",
        }
      : null,
  };
}
