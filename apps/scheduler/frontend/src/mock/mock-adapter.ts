// The stateful mock adapter — the mock "server" behind the
// SchedulerApi seam.
//
// It owns a store seeded from the real fleet (26 entries in
// contract 14's target form), a small engine implementing
// contract 13's semantics (consume-before-run, missed-point
// collapse ledgered as catchup, no self-overlap ledgered as
// skipped_overlap, firing iff status is active), and the
// contract 09 view projections — every label is computed here,
// server-side, including outcome_label() (contract 06). At S8
// the live HTTP adapter replaces this class wholesale; no view
// code changes.
import type { SchedulerApi } from "../api";
import type {
  ActionResult,
  JobDetailView,
  JobView,
  LedgerEventInput,
  LedgerEventRaw,
  LedgerView,
  OverviewView,
  PingRecord,
  PingView,
  RunView,
} from "../types";
import {
  buildStore,
  cadenceStepMs,
  fmtDuration,
  nextDueFor,
  outcomeLabel,
  planFor,
  type JobRuntime,
  type PlannedOutcome,
  type Store,
  DEFAULT_TZ,
} from "./seeds";
import { iso, saveConfig as saveConfigImpl } from "./mock-config";
import {
  getJobDetail,
  getLedger as getLedgerView,
  listJobs as listJobsView,
  listPings as listPingsView,
  listRecentPings as listRecentPingsView,
  overviewView,
} from "./mock-views";

const HISTORY_CAP = 60;

export class MockSchedulerAdapter implements SchedulerApi {
  private store: Store;
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(now: number = Date.now()) {
    this.store = buildStore(now);
  }

  // ---------------------------------------------------------
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    if (this.timer === null) {
      this.timer = setInterval(() => this.tick(), 1000);
    }
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0 && this.timer !== null) {
        clearInterval(this.timer);
        this.timer = null;
      }
    };
  }

  private emit() {
    for (const listener of [...this.listeners]) listener();
  }
  // ---------------------------------------------------------
  // Engine (contract 13)

  private tick() {
    const now = Date.now();
    this.store.lastTick = now;
    for (const rt of this.store.jobs.values()) {
      if (rt.running && now >= rt.running.completesAt) {
        this.completeRun(rt, now);
      }
    }
    for (const rt of this.store.jobs.values()) {
      if (rt.entry.status !== "active" || rt.nextDue === null) continue;
      if (rt.nextDue <= now) {
        if (rt.entry.kind === "agent") this.fireAgentDue(rt, now);
        else this.fireDue(rt, now);
      }
    }
    // The keeper's wake half (contract 04/05): bridge-wake pings
    // are woken on mint and acked once their item's work is done;
    // the mock keeper closes them after a minute so the outbox
    // behaves like the live one instead of filling with wakes.
    for (const ping of this.store.pings) {
      if (
        ping.job_id === "bridge-wake" &&
        ping.state === "pending" &&
        now - Date.parse(ping.created) > 60_000
      ) {
        ping.state = "acked";
        ping.acked_at = iso(now);
        ping.detail = { ...ping.detail, acked_by: "keeper" };
        this.ledger(now, {
          kind: "ping_acked",
          job_id: "bridge-wake",
          ping_id: ping.id,
          ping_kind: ping.kind,
        });
      }
    }
    this.emit();
  }

  /** Advance next_due past every missed point (consume-before-
   *  run, EC-4/EC-1). Returns the fired due + collapse count. */
  private consumeDue(rt: JobRuntime, now: number): { due: number; collapsed: number } {
    const step = cadenceStepMs(rt.entry.cadence);
    const due = rt.nextDue!;
    let next = due + step;
    let collapsed = 0;
    while (next <= now) {
      collapsed++;
      next += step;
    }
    rt.nextDue = next;
    if (collapsed > 0) {
      this.ledger(now, { kind: "catchup", job_id: rt.entry.id, collapsed });
    }
    return { due, collapsed };
  }

  private fireDue(rt: JobRuntime, now: number) {
    const { due, collapsed } = this.consumeDue(rt, now);
    if (rt.running) {
      // No self-overlap: the point skips, and the skip is ledgered.
      this.ledger(now, { kind: "skipped_overlap", job_id: rt.entry.id });
      rt.history.unshift(this.skipRow(now, due));
      rt.dues.unshift({ due: iso(due), outcome: "skipped_overlap", collapsed: 0 });
      this.trim(rt);
      return;
    }
    rt.dues.unshift({
      due: iso(due),
      outcome: collapsed > 0 ? "collapsed" : "fired",
      collapsed,
    });
    this.startRun(rt, due, collapsed, now);
  }

  private fireAgentDue(rt: JobRuntime, now: number) {
    const { due } = this.consumeDue(rt, now);
    void due;
    const existing = this.store.pings.find(
      (p) => p.job_id === rt.entry.id && p.kind === "agent-due" && p.state === "pending",
    );
    if (existing) {
      existing.coalesced_count++;
      this.ledger(now, {
        kind: "ping_coalesced",
        job_id: rt.entry.id,
        ping_id: existing.id,
        ping_kind: existing.kind,
      });
      return;
    }
    this.mintPing(now, {
      job_id: rt.entry.id,
      kind: "agent-due",
      body_ref: rt.entry.body ?? null,
      detail: { summary: `${rt.entry.id} — drain episode open`, queue: 3 },
    });
    this.ledger(now, { kind: "agent_due", job_id: rt.entry.id });
  }

  private skipRow(at: number, due: number): RunView {
    return {
      ts: iso(at),
      due: iso(due),
      status: "skipped_overlap",
      exit_code: null,
      label: "Skipped",
      matched_pattern: null,
      collapsed: 0,
      error: null,
      stdout_tail: null,
      stderr_tail: null,
      duration_label: null,
      detail: "Skipped · previous run still active",
    };
  }

  private startRun(rt: JobRuntime, due: number, collapsed: number, now: number) {
    const plans = planFor(rt.entry.id);
    const plan = plans[rt.planIdx % plans.length]!;
    rt.planIdx++;
    const run: RunView = {
      ts: iso(now),
      due: iso(due),
      status: "running",
      exit_code: null,
      label: "Running",
      matched_pattern: null,
      collapsed,
      error: null,
      stdout_tail: null,
      stderr_tail: null,
      duration_label: null,
      detail: null,
    };
    // The mock compresses the wait (a 4-minute job completes in
    // 3 s of wall time) but serves the plan's true duration label.
    rt.running = {
      plan,
      completesAt: now + Math.min(plan.duration_secs, 3) * 1000,
      run,
    };
    rt.history.unshift(run);
    this.trim(rt);
  }

  private completeRun(rt: JobRuntime, now: number) {
    const running = rt.running!;
    rt.running = null;
    const { plan, run } = running;
    run.status = plan.status;
    run.exit_code = plan.exit_code;
    run.label = outcomeLabel(plan.status, plan.exit_code);
    run.matched_pattern = plan.matched_pattern ?? null;
    run.error = plan.error ?? null;
    run.stdout_tail = plan.stdout_tail ?? null;
    run.stderr_tail = plan.stderr_tail ?? null;
    run.duration_label = fmtDuration(plan.duration_secs);
    run.detail = plan.detail;
    if (rt.entry.id === "storage-watch" && rt.config) {
      // Fire-time read, demonstrated: the tier verdict is
      // computed from the config values in the store record
      // at the moment the run completes — a config save
      // lands in the same record, so the next run speaks
      // the new tiers. 62 = the mock's served free figure
      // (62 GiB, the 2026-11-11 storage cleanup record).
      const freeGb = 62;
      const low = rt.config.values["home_low_free_gb"]!;
      const crit = rt.config.values["home_critical_free_gb"]!;
      run.detail =
        freeGb < crit
          ? `Completed · CRITICAL tier · ${freeGb}G free`
          : freeGb < low
            ? `Completed · LOW tier · ${freeGb}G free`
            : `Completed · home tier OK · ${freeGb}G free`;
    }
    rt.stats.runs24h++;
    if (plan.status === "failed" || plan.status === "timeout") {
      rt.stats.failures24h++;
    }
    this.ledger(now, {
      kind: "run",
      job_id: rt.entry.id,
      status: plan.status,
      exit_code: plan.exit_code,
      due: run.due,
      collapsed: run.collapsed,
    });
    if (rt.entry.id === "flap-watch") {
      this.store.flapActive = plan.detail.includes("flap active");
    }
    if (plan.mint_pings) {
      for (let i = 0; i < plan.mint_pings; i++) {
        this.mintPing(now, {
          job_id: "bridge-wake",
          kind: "agent-due",
          body_ref: "bodies/bridge-wake-item.md",
          detail: {
            summary: "chat wake — bridge item queued",
            caller: "bridge",
            tool: "chat_send",
          },
        });
      }
    }
  }

  private mintPing(
    now: number,
    init: { job_id: string; kind: PingRecord["kind"]; body_ref: string | null; detail: Record<string, unknown> },
  ): PingRecord {
    const ping: PingRecord = {
      id: (this.store.pingSeq++).toString(16).padStart(12, "0"),
      job_id: init.job_id,
      due: iso(now),
      kind: init.kind,
      body_ref: init.body_ref,
      detail: init.detail,
      created: iso(now),
      state: "pending",
      coalesced_count: 1,
      last_woken_at: iso(now),
    };
    this.store.pings.push(ping);
    this.store.pingsCreated24h++;
    this.ledger(now, {
      kind: "ping_created",
      job_id: init.job_id,
      ping_id: ping.id,
      ping_kind: init.kind,
    });
    return ping;
  }

  private ledger(now: number, event: LedgerEventInput) {
    this.store.ledger.push({ ...event, ts: iso(now) });
  }

  private trim(rt: JobRuntime) {
    if (rt.history.length > HISTORY_CAP) rt.history.length = HISTORY_CAP;
    if (rt.dues.length > HISTORY_CAP) rt.dues.length = HISTORY_CAP;
  }
  // ---------------------------------------------------------
  // Actions

  runNow(jobId: string): ActionResult {
    const rt = this.store.jobs.get(jobId);
    if (!rt) return { ok: false, error: "not_found", detail: `No job ${jobId}.` };
    if (rt.entry.status !== "active") {
      return {
        ok: false,
        error: "bad_request",
        detail: `${jobId} is suspended — resume it before a manual run.`,
      };
    }
    const now = Date.now();
    if (rt.entry.kind === "agent") {
      this.fireAgentDueNow(rt, now);
      this.emit();
      return { ok: true };
    }
    if (rt.running) {
      // A manual fire during a run follows the engine's rule:
      // the point skips and is ledgered, never duplicated.
      this.ledger(now, { kind: "skipped_overlap", job_id: jobId });
      rt.history.unshift(this.skipRow(now, now));
      this.trim(rt);
      this.emit();
      return { ok: true };
    }
    this.startRun(rt, now, 0, now);
    this.emit();
    return { ok: true };
  }

  private fireAgentDueNow(rt: JobRuntime, now: number) {
    const existing = this.store.pings.find(
      (p) => p.job_id === rt.entry.id && p.kind === "agent-due" && p.state === "pending",
    );
    if (existing) {
      existing.coalesced_count++;
      this.ledger(now, {
        kind: "ping_coalesced",
        job_id: rt.entry.id,
        ping_id: existing.id,
        ping_kind: existing.kind,
      });
      return;
    }
    this.mintPing(now, {
      job_id: rt.entry.id,
      kind: "agent-due",
      body_ref: rt.entry.body ?? null,
      detail: { summary: `${rt.entry.id} — drain episode open`, queue: 3 },
    });
    this.ledger(now, { kind: "agent_due", job_id: rt.entry.id });
  }

  setJobEnabled(jobId: string, enabled: boolean): ActionResult {
    const rt = this.store.jobs.get(jobId);
    if (!rt) return { ok: false, error: "not_found", detail: `No job ${jobId}.` };
    if (enabled && rt.entry.status === "active") {
      return { ok: false, error: "bad_request", detail: `${jobId} is already active.` };
    }
    if (!enabled && rt.entry.status === "suspended") {
      return { ok: false, error: "bad_request", detail: `${jobId} is already suspended.` };
    }
    const now = Date.now();
    if (enabled) {
      rt.entry.status = "active";
      delete rt.entry.suspend_reason;
      delete rt.entry.suspended_on;
      if (rt.nextDue === null) rt.nextDue = nextDueFor(rt.entry, now);
    } else {
      rt.entry.status = "suspended";
      rt.entry.suspend_reason = "Suspended from the scheduler app (mock)";
      rt.entry.suspended_on = new Intl.DateTimeFormat("en-CA", {
        timeZone: DEFAULT_TZ,
      }).format(new Date(now));
    }
    // The write is ledgered as an op event (contract 04: every
    // delegated write attempt is an op event with caller/target).
    this.ledger(now, {
      kind: "op",
      op: enabled ? "resume" : "suspend",
      caller: "scheduler-app",
      path: `jobs/${jobId}.yaml`,
      status: "ok",
    });
    this.emit();
    return { ok: true };
  }

  ackPing(pingId: string, ackedBy: string): ActionResult {
    const ping = this.store.pings.find((p) => p.id === pingId);
    if (!ping) return { ok: false, error: "not_found", detail: `No ping ${pingId}.` };
    if (ping.state !== "pending") {
      return { ok: false, error: "bad_request", detail: "Ping is not pending." };
    }
    const now = Date.now();
    ping.state = "acked";
    ping.acked_at = iso(now);
    ping.detail = { ...ping.detail, acked_by: ackedBy };
    this.ledger(now, {
      kind: "ping_acked",
      job_id: ping.job_id,
      ping_id: ping.id,
      ping_kind: ping.kind,
    });
    if (ping.kind === "agent-due" || ping.kind === "escalation") {
      this.store.wakeupsServed24h++;
    }
    this.emit();
    return { ok: true };
  }
  // ---------------------------------------------------------
  // Entry config — the one writer path (contract 09,
  // amendment 2026-11-13). The writer lives in
  // ./mock-config; the adapter lends it the store, the
  // ledger, and the emit.

  async saveConfig(
    jobId: string,
    version: number,
    values: Record<string, number>,
  ): Promise<ActionResult> {
    return saveConfigImpl(
      {
        store: this.store,
        ledger: (now, event) => this.ledger(now, event),
        emit: () => this.emit(),
      },
      jobId,
      version,
      values,
    );
  }

  // ---------------------------------------------------------
  // Views (contract 09 projections) — computed over the
  // store in ./mock-views; these methods are the
  // SchedulerApi surface over them.

  listJobs(): JobView[] {
    return listJobsView(this.store);
  }

  getJob(id: string): JobDetailView | null {
    return getJobDetail(this.store, id);
  }

  listPings(): PingView[] {
    return listPingsView(this.store);
  }

  listRecentPings(): PingView[] {
    return listRecentPingsView(this.store);
  }

  getLedger(limit: number): LedgerView {
    return getLedgerView(this.store, limit);
  }

  getOverview(): OverviewView {
    return overviewView(this.store, Date.now());
  }

  /** Raw store records for the schema checker (mock-only; not
   *  part of the SchedulerApi seam). */
  debugSnapshot(): { pings: PingRecord[]; ledger: LedgerEventRaw[] } {
    return {
      pings: structuredClone(this.store.pings),
      ledger: structuredClone(this.store.ledger),
    };
  }
}

export const mockApi = new MockSchedulerAdapter();
