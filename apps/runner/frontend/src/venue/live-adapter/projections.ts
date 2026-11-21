// The live adapter's state projections: the served views
// folded from the fetched portions (specs, leases, runs,
// budget, grant, callers, access, orphans), as free
// functions over a LiveContext — the portions and the
// clock the projections read. Split from live-adapter.ts
// along the mapping seam; LiveVenueAdapter delegates.

import type {
  AccessSessionView,
  BudgetAccountView,
  BudgetView,
  CallerView,
  GrantView,
  LeaseDiagnosticsView,
  LeaseView,
  OrphanConflictView,
  OrphanJobView,
  OrphanShapeCandidate,
  OrphanView,
  RunView,
  SpecView,
  Tone,
} from "../types";
import { fmtTime } from "../adapter/format";
import {
  CLASS_LABEL,
  VENUE_LABEL,
  baseName,
  fmtRemaining,
  liveSessionName,
  shapeClass,
  str,
} from "./helpers";
import { EMPTY_BUDGET } from "./served";
import type {
  Parts,
  ServedLeaseRecord,
  ServedRecordEntry,
  ServedSpec,
} from "./served";

/** What the projections read from the adapter: the
 *  fetched portions and the clock. */
export interface LiveContext {
  parts: Parts;
  now(): string;
}

/* ----- served catalog (from the specs portion) ----- */

export function specMap(ctx: LiveContext): Map<string, ServedSpec> {
  return new Map((ctx.parts.specs?.specs ?? []).map((s) => [s.id, s]));
}

export function shapeLabel(ctx: LiveContext, shape: string): string {
  return specMap(ctx).get(shape)?.label ?? shape;
}

export function shapeRateLabel(ctx: LiveContext, shape: string): string {
  const rate = specMap(ctx).get(shape)?.rate_cu_per_hour;
  return rate != null ? `${rate} CU/h` : "Cost unconfirmed";
}

export function specViews(ctx: LiveContext): SpecView[] {
  return (ctx.parts.specs?.specs ?? []).map((rec) => {
    const kind = rec.gpu ? "GPU" : rec.tpu ? "TPU" : "CPU";
    const shape = rec.gpu || rec.tpu || (rec.high_mem ? "High-RAM" : "Standard");
    const descriptor =
      !rec.gpu && !rec.tpu && shape === rec.label ? kind : `${kind} · ${shape}`;
    return {
      id: rec.id,
      label: rec.label,
      descriptor,
      spec: { gpu: rec.gpu, tpu: rec.tpu, high_mem: rec.high_mem },
      rateCuPerHour: rec.rate_cu_per_hour,
      rateLabel:
        rec.rate_cu_per_hour != null ? `${rec.rate_cu_per_hour} CU/h` : "Cost unconfirmed",
      agentStartable: rec.agent_startable,
    };
  });
}

/* ----- projections ----- */

/** The records portion's lease entries — record-
 *  carrying only. A recordless ("no-lease") entry is
 *  not a lease any projection can describe (no shape,
 *  no deadline, no rate); its finding rides the
 *  backend's torn-records portion, not this list.
 *  Every projection enumerates entries through here,
 *  so the admission lives at one seam. */
export function recordEntries(ctx: LiveContext): (ServedRecordEntry & { record: ServedLeaseRecord })[] {
  return (ctx.parts.records?.records ?? []).filter(
    (e): e is ServedRecordEntry & { record: ServedLeaseRecord } => !!e.record,
  );
}

export function leaseView(ctx: LiveContext, entry: ServedRecordEntry & { record: ServedLeaseRecord }): LeaseView {
  const lease = entry.record;
  const nowMs = Date.parse(ctx.now());
  const expired = Date.parse(lease.deadline) <= nowMs;
  return {
    session: lease.session,
    displayName: liveSessionName(lease.session),
    venue: "colab",
    venueLabel: VENUE_LABEL,
    shape: lease.shape,
    shapeLabel: shapeLabel(ctx, lease.shape),
    caller: lease.caller ?? entry.caller ?? null,
    state: expired ? "renewal-due" : "running",
    stateLabel: expired ? "Renewal due" : "Running",
    stateTone: expired ? "warn" : "ok",
    acquiredAt: lease.acquired_at,
    deadline: lease.deadline,
    endsLabel: expired
      ? `ended ${fmtTime(lease.deadline)}`
      : `ends ${fmtTime(lease.deadline)}`,
    remainingLabel: expired
      ? "deadline passed"
      : `${fmtTime(lease.deadline)} · ${fmtRemaining(Date.parse(lease.deadline) - nowMs)}`,
    rateCuPerHour: lease.rate_cu_per_hour,
    reservedCu: lease.budget_at_acquire?.projected ?? lease.budget_at_acquire?.reserved_cu ?? 0,
    envelopeId: lease.envelope_id,
    diagnostics: diagnosticsView(ctx, entry),
  };
}

/** The lease card's diagnostics (V7), from the listeners
 *  portion plus the record's own liveness stamps. A
 *  session neither source carries serves null (honest
 *  absence). A census entry whose probe failed serves its
 *  empty listener list with the heartbeat unreadable —
 *  "unknown", the panel's own word. */
export function diagnosticsView(ctx: LiveContext, entry: ServedRecordEntry & { record: ServedLeaseRecord }): LeaseDiagnosticsView | null {
  const lease = entry.record;
  const census = ctx.parts.listeners?.listeners?.[lease.session];
  if (!census && entry.keepalive_heartbeat_age_s == null && !lease.last_pulse_result && !entry.sync_claim) {
    return null;
  }
  const rate = lease.rate_cu_per_hour ?? specMap(ctx).get(lease.shape)?.rate_cu_per_hour;
  const claim = entry.sync_claim;
  return {
    listeners: (census?.listeners ?? []).map((l) => ({
      port: l.port,
      pid: l.pid,
      cwd: l.cwd,
      suspect: l.suspect ?? [],
    })),
    heartbeatLabel:
      entry.keepalive_heartbeat_age_s == null
        ? "unknown"
        : `${Math.round(entry.keepalive_heartbeat_age_s)}s ago`,
    pulseLabel: lease.last_pulse_result ?? census?.error ?? null,
    burnLabel: rate != null ? `${rate} CU/h` : "Cost unconfirmed",
    syncClaim: claim
      ? {
          caller: claim.caller,
          untilLabel: fmtTime(claim.expires_at ?? claim.until ?? ctx.now()),
        }
      : null,
  };
}

export function runLabel(state: string): { label: string; tone: Tone } {
  const labels: Record<string, { label: string; tone: Tone }> = {
    complete: { label: "Passed", tone: "ok" },
    running: { label: "Running", tone: "info" },
    starting: { label: "Starting", tone: "info" },
    polling: { label: "Running", tone: "info" },
    failed: { label: "Failed", tone: "fail" },
    orphaned: { label: "Orphaned", tone: "warn" },
  };
  return labels[state] ?? { label: state, tone: "idle" as Tone };
}

/** Runs ride the outbox's run-terminal events — the only
 *  run records the surface serves. The event's stamp is
 *  the terminal time (its startedAt here) and no duration
 *  is served, so the duration label serves an honest
 *  absence ("—") rather than a derived figure. */
export function runViews(ctx: LiveContext): RunView[] {
  const events = ctx.parts.outbox?.events ?? [];
  const leaseByBase = new Map(
    recordEntries(ctx).map(
      (e) => [baseName(e.record.session), e.record.session] as const,
    ),
  );
  const out: RunView[] = [];
  for (const ev of events) {
    if (ev.kind !== "run-terminal") continue;
    const d = ev.detail;
    const runId = str(d.run_id);
    const job = str(d.job);
    if (!runId || !job) continue;
    const base = str(d.session) ?? "";
    const state = str(d.state) ?? "complete";
    const l = runLabel(state);
    out.push({
      runId,
      job,
      session: leaseByBase.get(base) ?? (base || null),
      sessionName: base ? liveSessionName(base) : "—",
      caller: str(d.caller),
      state,
      stateLabel: l.label,
      stateTone: l.tone,
      startedAt: ev.ts,
      durationLabel: "—",
      venue: "colab",
    });
  }
  return out.sort((a, b) => Date.parse(b.startedAt) - Date.parse(a.startedAt));
}

export function budgetView(ctx: LiveContext): BudgetView {
  const served = ctx.parts.budget?.budget;
  if (!served) return EMPTY_BUDGET;
  const reserved = recordEntries(ctx)
    .map((e) => leaseView(ctx, e).reservedCu)
    .reduce((a, b) => a + b, 0);
  const balanceCu = Math.round(served.balance * 100) / 100;
  const usedTodayCu = Math.round(served.day_spent * 100) / 100;
  const days = usedTodayCu > 0 ? Math.floor(balanceCu / usedTodayCu) : 0;
  const primary =
    served.accounts.find((a) => a.credential === "live") ?? served.accounts[0];
  const capHeadroom =
    primary && primary.caps.daily != null
      ? Math.max(0, primary.caps.daily - usedTodayCu)
      : Infinity;
  const accounts: BudgetAccountView[] = served.accounts.map((a) => ({
    venue: a.venue,
    account: a.account,
    label: a.label,
    balanceCu: a.balance,
    usedTodayCu: a.day_spent,
    usedMonthCu: a.month_spent,
    standingUsedTodayCu: a.standing_day_spent,
    caps: {
      daily: a.caps.daily,
      monthly: a.caps.monthly,
      standingDaily: a.caps.standing_daily,
    },
    credential: a.credential,
  }));
  return {
    balanceCu,
    usedTodayCu,
    reservedCu: Math.round(reserved * 100) / 100,
    availableCu: Math.round(Math.min(balanceCu - reserved, capHeadroom) * 100) / 100,
    runwayLabel: days > 0 ? `${days} days at today's rate` : "less than a day at today's rate",
    // Spend by caller is not a served portion (the journal
    // stays core-side); the list serves empty rather than
    // an invented split.
    byCaller: [],
    caps: {
      daily: served.caps.daily,
      monthly: served.caps.monthly,
      standingDaily: served.caps.standing_daily,
    },
    accounts,
  };
}

export function grantView(ctx: LiveContext): GrantView | null {
  const grant = ctx.parts.grant?.grant;
  if (!grant || Date.parse(grant.until) <= Date.parse(ctx.now())) return null;
  const envelope = ctx.parts.grant?.envelope;
  const caps = envelope?.caps ?? grant.scope.caps;
  const records =
    envelope?.records ??
    recordEntries(ctx)
      .map((e) => e.record)
      .filter((r) => r.envelope_id === grant.granted_at);
  return {
    id: grant.granted_at,
    until: grant.until,
    untilLabel: fmtTime(grant.until),
    burstShape: grant.burst_shape,
    burstLabel: shapeLabel(ctx, grant.burst_shape),
    standingShape: grant.standing_shape,
    shapes: [...grant.scope.shapes],
    caps: {
      daily: caps.daily,
      monthly: caps.monthly,
      standingDaily: caps.standing_daily,
    },
    spendDayCu: envelope?.spend.day_spent ?? ctx.parts.budget?.budget.day_spent ?? 0,
    spendMonthCu: envelope?.spend.month_spent ?? ctx.parts.budget?.budget.month_spent ?? 0,
    standingDaySpentCu:
      envelope?.spend.standing_day_spent ?? ctx.parts.budget?.budget.standing_day_spent ?? null,
    leases: records.map((r) => ({
      session: r.session,
      displayName: liveSessionName(r.session),
      shapeLabel: shapeLabel(ctx, r.shape),
      caller: r.caller ?? null,
      deadlineLabel: fmtTime(r.deadline),
    })),
  };
}

export function callerViews(ctx: LiveContext): CallerView[] {
  const byCaller = new Map<string, ServedRecordEntry & { record: ServedLeaseRecord }>();
  for (const entry of recordEntries(ctx)) {
    const caller = entry.record.caller ?? entry.caller;
    if (caller && !byCaller.has(caller)) byCaller.set(caller, entry);
  }
  const seen = new Set<string>(byCaller.keys());
  for (const a of ctx.parts.records?.access ?? []) {
    if (a.caller) seen.add(a.caller);
  }
  return [...seen].sort().map((caller) => {
    const entry = byCaller.get(caller);
    if (!entry) {
      return { caller, stateLabel: "Registered", stateTone: "idle" as Tone, sub: "No live session" };
    }
    const view = leaseView(ctx, entry);
    if (view.state === "renewal-due") {
      return {
        caller,
        stateLabel: "Renewal due",
        stateTone: "warn" as Tone,
        sub: `Lease ended ${fmtTime(entry.record.deadline)} · renewal due`,
      };
    }
    return {
      caller,
      stateLabel: "Active",
      stateTone: "ok" as Tone,
      sub: `Riding ${view.displayName} · granted ${fmtTime(entry.record.acquired_at)}`,
    };
  });
}

export function accessViews(ctx: LiveContext): AccessSessionView[] {
  return (ctx.parts.records?.access ?? [])
    .map((a) => ({
      session: a.session,
      displayName: liveSessionName(a.session),
      shapeClass: a.shape_class,
      caller: a.caller,
      firstSeen: a.first_seen,
      sub: `${CLASS_LABEL[a.shape_class] ?? a.shape_class} shape · since ${fmtTime(a.first_seen)}`,
      unattributed: a.unattributed ?? a.caller == null,
    }))
    .sort((x, y) => Date.parse(x.firstSeen) - Date.parse(y.firstSeen));
}

export function orphanViews(ctx: LiveContext): OrphanView[] {
  const nowMs = Date.parse(ctx.now());
  return (ctx.parts.orphans?.orphans ?? []).map((o) => {
    const evidenced = o.shape_evidenced && o.shape != null;
    const cls = o.shape_class ?? (o.shape_spec ? shapeClass(o.shape_spec) : null);
    const shapeDescriptor = evidenced
      ? shapeLabel(ctx, o.shape!)
      : cls
        ? `${CLASS_LABEL[cls] ?? cls} class`
        : "Unknown shape";
    const seenMin = Math.max(
      1,
      Math.round((nowMs - Date.parse(o.first_seen)) / 60000),
    );
    const conflicts: OrphanConflictView[] = (o.conflicts ?? []).map((c) => ({
      field: c.field,
      text: c.values
        .map(
          (v) =>
            `${v.source} says ${/^\d{4}-\d{2}-\d{2}T/.test(v.value) ? fmtTime(v.value) : v.value}`,
        )
        .join(" · "),
    }));
    const candidates: OrphanShapeCandidate[] = evidenced
      ? []
      : (o.shape_candidates ?? []).map((id) => ({
          id,
          label: shapeLabel(ctx, id),
          rateLabel: shapeRateLabel(ctx, id),
        }));
    const jobs: OrphanJobView[] = (o.jobs_in_flight_entries ?? []).map((j) => {
      const l = runLabel(j.state);
      return {
        id: j.id,
        label: j.id,
        sub: `Run · started ${fmtTime(j.started_at)}`,
        stateLabel: l.label,
        tone: l.tone,
      };
    });
    return {
      session: o.session,
      // A nameless row has no name to title-case: the
      // "?" sentinel's label is the panel's vocabulary
      // for a session with no usable name.
      nameless: o.session == null,
      endpoint: o.endpoint ?? null,
      priorSession: o.prior_session ?? null,
      displayName: liveSessionName(o.session ?? "?"),
      venue: "colab" as const,
      venueLabel: VENUE_LABEL,
      shapeLabel: shapeDescriptor,
      sub: `${shapeDescriptor} · seen ${seenMin} min ago · ${o.jobs_in_flight === 0 ? "no jobs in flight" : `${o.jobs_in_flight} job${o.jobs_in_flight > 1 ? "s" : ""} in flight`}`,
      firstSeenLabel: fmtTime(o.first_seen),
      acquiredLabel: o.acquired_at ? fmtTime(o.acquired_at) : null,
      kitInstalled: o.kit_installed,
      shapeEvidenced: evidenced,
      shapeClassLabel: cls ? (CLASS_LABEL[cls] ?? cls) : null,
      shapeCandidates: candidates,
      creatorCaller: o.creator_caller,
      firstClaim: o.first_claim,
      deadlineSource: o.deadline_source,
      deadlineStalePossible: o.deadline_stale_possible,
      conflicts,
      handoverPending: o.handover_pending,
      deadline: o.derived_deadline,
      deadlineLabel: o.derived_deadline ? fmtTime(o.derived_deadline) : null,
      deadlinePast: o.deadline_past,
      deadlineTone: "warn" as Tone,
      jobs,
    };
  });
}
