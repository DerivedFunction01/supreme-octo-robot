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
  ActivityView,
  ConfigView,
  JobDetailView,
  JobView,
  LedgerEventInput,
  LedgerEventRaw,
  LedgerView,
  OverviewView,
  PingHistoryRow,
  PingRecord,
  PingView,
  RunView,
} from "../types";
import {
  buildStore,
  cadenceLabel,
  cadenceStepMs,
  expectedWakesPerDay,
  fmtDuration,
  nextDueFor,
  outcomeLabel,
  planFor,
  CLASSIFICATION,
  ENTRY_CONFIG,
  type JobRuntime,
  type PlannedOutcome,
  type Store,
  DEFAULT_TZ,
} from "./seeds";

/** From the tracked fictional example, contracts/fixtures/
 *  scheduler-config.example.json (contract 04's seed pattern). */
const CONFIG = {
  port: 8796,
  tick_secs: 20,
  // The example says "UTC"; contract 04 records that as the
  // example's error — the code default is America/New_York.
  default_timezone: "America/New_York",
  outbox_ack_timeout_secs: 3600,
  workbench_base_url: "http://127.0.0.1:8792",
};

const iso = (ms: number) => new Date(ms).toISOString();
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
  // amendment 2026-11-13). The store is the source; the
  // engine reads the same record at fire time.

  private configView(rt: JobRuntime): ConfigView | null {
    const seed = ENTRY_CONFIG[rt.entry.id];
    if (!seed || !rt.config) return null;
    const state = rt.config;
    return {
      version: state.version,
      knobs: seed.knobs.map((knob) => ({
        ...knob,
        value: state.values[knob.key] ?? knob.value,
      })),
      constraints: seed.constraints ?? [],
    };
  }

  async saveConfig(
    jobId: string,
    version: number,
    values: Record<string, number>,
  ): Promise<ActionResult> {
    const rt = this.store.jobs.get(jobId);
    if (!rt) return { ok: false, error: "not_found", detail: `No job ${jobId}.` };
    const seed = ENTRY_CONFIG[jobId];
    if (!seed || !rt.config) {
      return {
        ok: false,
        error: "bad_request",
        detail: `${jobId} carries no editable config.`,
      };
    }
    const state = rt.config;
    // The CAS guard: the save must present the version it
    // loaded. A moved version means another writer saved
    // first — refuse with the closed set's compare-failure
    // name and apply nothing.
    if (version !== state.version) {
      return {
        ok: false,
        error: "no_match",
        detail: `${jobId} config changed since it was loaded (now version ${state.version}) — reload and re-apply.`,
      };
    }
    // Validate everything before applying anything: unknown
    // knob, non-number, non-integer, out of the served range,
    // or a declared constraint violated refuses the whole
    // save — never half-applied, never ledgered.
    const merged: Record<string, number> = { ...state.values };
    for (const [key, value] of Object.entries(values)) {
      const knob = seed.knobs.find((k) => k.key === key);
      if (!knob) {
        return { ok: false, error: "bad_request", detail: `Unknown knob ${key}.` };
      }
      if (typeof value !== "number" || Number.isNaN(value)) {
        return {
          ok: false,
          error: "bad_request",
          detail: `${knob.label} must be a number.`,
        };
      }
      if (knob.type === "integer" && !Number.isInteger(value)) {
        return {
          ok: false,
          error: "bad_request",
          detail: `${knob.label} must be a whole number (${knob.unit}).`,
        };
      }
      if (value < knob.min || value > knob.max) {
        return {
          ok: false,
          error: "bad_request",
          detail: `${knob.label} must be between ${knob.min} and ${knob.max} ${knob.unit}.`,
        };
      }
      merged[key] = value;
    }
    for (const constraint of seed.constraints ?? []) {
      if (
        constraint.kind === "lt" &&
        !(merged[constraint.left]! < merged[constraint.right]!)
      ) {
        return { ok: false, error: "bad_request", detail: constraint.message };
      }
    }
    const now = Date.now();
    let changed = false;
    for (const knob of seed.knobs) {
      const next = merged[knob.key]!;
      const prev = state.values[knob.key]!;
      if (next === prev) continue;
      state.values[knob.key] = next;
      changed = true;
      // One op event per applied knob change (entry, knob,
      // old → new) — visible in the Ledger view like every
      // other delegated write (contract 04's audit rule).
      this.ledger(now, {
        kind: "op",
        op: "config",
        caller: "scheduler-app",
        job_id: jobId,
        knob: knob.key,
        label: knob.label,
        old: prev,
        new: next,
        unit: knob.unit,
        status: "ok",
      });
    }
    if (changed) state.version++;
    this.emit();
    return { ok: true };
  }

  // ---------------------------------------------------------
  // Views (contract 09 projections)

  private activityFor(rt: JobRuntime, now: number): ActivityView | null {
    if (rt.entry.kind !== "agent") return null;
    const pings = this.store.pings
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

  private jobView(rt: JobRuntime, now: number): JobView {
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
      last_activity: this.activityFor(rt, now),
      runs_24h: rt.stats.runs24h,
      failures_24h: rt.stats.failures24h,
      failure_streak: failureStreak,
      expected_wakes_per_day: expectedWakesPerDay(entry.cadence),
      report_mode: entry.report?.when ?? "never",
    };
  }

  listJobs(): JobView[] {
    const now = Date.now();
    return [...this.store.jobs.values()]
      .map((rt) => this.jobView(rt, now))
      .sort((a, b) => a.id.localeCompare(b.id));
  }

  getJob(id: string): JobDetailView | null {
    const rt = this.store.jobs.get(id);
    if (!rt) return null;
    const now = Date.now();
    const entry = rt.entry;
    const base = this.jobView(rt, now);
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
      config: this.configView(rt),
      lifetime: entry.lifetime,
      self_removal: entry.self_removal ?? null,
      catalog: entry.catalog ?? null,
      recent_runs: rt.history.slice(0, 50),
      recent_dues: [...pendingDue, ...rt.dues].slice(0, 50),
      ping_history: this.pingHistoryRows(id),
    };
  }

  /** Job detail's ping-history window in the server's row
   *  form (S8 conformance): the job's last 20 ping ledger
   *  events, newest first, each reduced to the served row;
   *  the detail string is the server's own projection
   *  ("ping <kind> <id>", contract 09's ledger reduction). */
  private pingHistoryRows(jobId: string): PingHistoryRow[] {
    const KINDS = new Set([
      "ping_created",
      "ping_woken",
      "ping_acked",
      "ping_coalesced",
      "ping_voided",
    ]);
    return [...this.store.ledger]
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

  private pingView(ping: PingRecord, now: number): PingView {
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

  listPings(): PingView[] {
    const now = Date.now();
    return this.store.pings
      .filter((p) => p.state === "pending")
      .sort((a, b) => Date.parse(a.created) - Date.parse(b.created))
      .map((p) => this.pingView(p, now));
  }

  listRecentPings(): PingView[] {
    const now = Date.now();
    return this.store.pings
      .filter((p) => p.state === "acked")
      .sort((a, b) => Date.parse(b.created) - Date.parse(a.created))
      .map((p) => this.pingView(p, now));
  }

  private ledgerDetail(event: LedgerEventRaw): string {
    const jobId = typeof event.job_id === "string" ? event.job_id : null;
    switch (event.kind) {
      case "run": {
        const rt = jobId ? this.store.jobs.get(jobId) : undefined;
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
        const ping = this.store.pings.find((p) => p.id === event.ping_id);
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

  getLedger(limit: number): LedgerView {
    const now = Date.now();
    const events = [...this.store.ledger]
      .sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))
      .slice(0, Math.min(500, Math.max(1, limit)))
      .map((event) => ({
        ts: event.ts,
        kind: event.kind,
        job_id: typeof event.job_id === "string" ? event.job_id : null,
        detail: this.ledgerDetail(event),
      }));
    return { served_at: iso(now), events };
  }

  getOverview(): OverviewView {
    const now = Date.now();
    const jobs = [...this.store.jobs.values()];
    const pending = this.store.pings.filter((p) => p.state === "pending");
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
      pid: this.store.pid,
      uptime_secs: Math.floor((now - this.store.bootAt) / 1000),
      last_tick: iso(this.store.lastTick),
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
        wakeups_served: this.store.wakeupsServed24h,
        pings_created: this.store.pingsCreated24h,
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
        events: this.store.ledger.length,
        db_bytes: 40_361_984,
        oldest: this.store.ledger[0]?.ts ?? null,
        newest: this.store.ledger[this.store.ledger.length - 1]?.ts ?? null,
        retention_days: 90,
        last_prune: null,
      },
      config: {
        port: CONFIG.port,
        tick_secs: CONFIG.tick_secs,
        default_timezone: CONFIG.default_timezone,
        outbox_ack_timeout_secs: CONFIG.outbox_ack_timeout_secs,
      },
      notice: this.store.flapActive
        ? {
            tone: "warn",
            title: "Write-denial flap active.",
            text: "File writes are degraded; shell-class writes route through the ops bin.",
          }
        : null,
    };
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
