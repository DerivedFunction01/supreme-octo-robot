// The mock adapter's projections: the served views folded
// from the store (lease / run / budget / grant / access /
// event views and the snapshot composition), as free
// functions over a MockContext — the store, the venue
// clock, and the session-name derivation the projections
// read. Split from adapter.ts along the projection seam;
// MockVenueAdapter delegates to these.

import type {
  AccessEntry,
  AccessLogView,
  AccessSessionView,
  BudgetAccountView,
  BudgetView,
  CallerView,
  EventView,
  GrantRecord,
  GrantView,
  LeaseDiagnosticsView,
  LeaseRecord,
  LeaseView,
  OrphanConflictView,
  OrphanJobView,
  OrphanShapeCandidate,
  OrphanView,
  RunRecord,
  RunView,
  SessionEvidence,
  Snapshot,
  Tone,
  VenueEvent,
  VenueId,
} from "../types";
import {
  SESSION_NAMES,
  SPEC_CATALOG,
  VENUE_LABEL,
  shapeClass,
  shapeInfo,
  specView,
} from "./catalog";
import {
  KIND_LABEL,
  TZ,
  fmtDateToken,
  fmtDuration,
  fmtRemaining,
  fmtTime,
  fmtTimeLong,
} from "./format";
import { NONTERMINAL_RUN_STATES, OPENING_BALANCE_CU } from "./mock-seed";
import type { Store } from "./mock-seed";

/** What the projections read from the adapter: the store,
 *  the venue clock, and the session-name derivation. */
export interface MockContext {
  store: Store;
  clockMs: number;
  now(): string;
  name(session: string): string;
}

export function syncEvidence(ctx: MockContext, lease: LeaseRecord): void {
  // write_session_evidence: refreshed on every lease save.
  ctx.store.evidence[lease.session] = {
    deadline: lease.deadline,
    acquired_at: lease.acquired_at,
    shape: lease.shape,
    spec: lease.shape_spec,
    caller: lease.caller ?? null,
    venue: lease.venue,
  };
}

export function currentBalance(ctx: MockContext): number {
  // The seeded journal is spend already settled before the
  // storyboard's served balance; segments journaled since
  // (releases, seams) draw the balance down.
  let spent = 0;
  for (const seg of ctx.store.journal.slice(ctx.store.seededSegmentCount)) {
    spent += ((Date.parse(seg.end) - Date.parse(seg.start)) / 3600000) * seg.rate;
  }
  return Math.max(0, Math.round(OPENING_BALANCE_CU - spent));
}

export function leaseView(ctx: MockContext, lease: LeaseRecord): LeaseView {
  const expired = Date.parse(lease.deadline) <= ctx.clockMs;
  return {
    session: lease.session,
    displayName: ctx.name(lease.session),
    venue: lease.venue,
    venueLabel: VENUE_LABEL[lease.venue],
    shape: lease.shape,
    shapeLabel: shapeInfo(lease.shape).label,
    caller: lease.caller ?? null,
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
      : `${fmtTime(lease.deadline)} · ${fmtRemaining(Date.parse(lease.deadline) - ctx.clockMs)}`,
    rateCuPerHour: lease.rate_cu_per_hour,
    reservedCu: expired ? 0 : (lease.budget_at_acquire?.reserved_cu ?? 0),
    envelopeId: lease.envelope_id,
    diagnostics: diagnosticsView(ctx, lease),
  };
}

/** The lease card's diagnostics (V7): the listeners
 *  census lines with their suspect flags, the keepalive
 *  heartbeat age ("unknown" when the census cannot read
 *  it — the panel's own word), the last pulse result,
 *  the burn rate, and the sync claim when one is live.
 *  A session the census does not carry serves null. */
export function diagnosticsView(ctx: MockContext, lease: LeaseRecord): LeaseDiagnosticsView | null {
  const seed = ctx.store.leaseDiag[lease.session];
  if (!seed) return null;
  const rate = lease.rate_cu_per_hour ?? shapeInfo(lease.shape).rateCuPerHour;
  return {
    listeners: seed.listeners.map((l) => ({ ...l, suspect: [...l.suspect] })),
    heartbeatLabel:
      seed.heartbeatAgeS == null ? "unknown" : `${Math.round(seed.heartbeatAgeS)}s ago`,
    pulseLabel: seed.lastPulse,
    burnLabel: rate != null ? `${rate} CU/h` : "Cost unconfirmed",
    syncClaim: seed.syncClaim
      ? { caller: seed.syncClaim.caller, untilLabel: fmtTime(seed.syncClaim.expiresAt) }
      : null,
  };
}

export function runView(ctx: MockContext, run: RunRecord): RunView {
  const end = run.ended_at ? Date.parse(run.ended_at) : ctx.clockMs;
  const labels: Record<string, { label: string; tone: Tone }> = {
    complete: { label: "Passed", tone: "ok" },
    running: { label: "Running", tone: "info" },
    starting: { label: "Starting", tone: "info" },
    failed: { label: "Failed", tone: "fail" },
    orphaned: { label: "Orphaned", tone: "warn" },
  };
  const l = labels[run.state] ?? { label: run.state, tone: "idle" as Tone };
  return {
    runId: run.run_id,
    job: run.job,
    session: run.session ?? null,
    sessionName: run.session ? ctx.name(run.session) : "—",
    caller: run.caller ?? null,
    state: run.state,
    stateLabel: l.label,
    stateTone: l.tone,
    startedAt: run.started_at,
    durationLabel: fmtDuration(end - Date.parse(run.started_at)),
    venue: run.venue,
  };
}

export function budget(ctx: MockContext): BudgetView {
  const dayStart = new Date(ctx.now());
  dayStart.setHours(0, 0, 0, 0);
  const monthStart = new Date(ctx.now());
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);
  let used = 0;
  let usedMonth = 0;
  const byCaller = new Map<string, number>();
  for (const seg of ctx.store.journal) {
    const cu = ((Date.parse(seg.end) - Date.parse(seg.start)) / 3600000) * seg.rate;
    if (Date.parse(seg.start) >= monthStart.getTime()) usedMonth += cu;
    if (Date.parse(seg.start) < dayStart.getTime()) continue;
    used += cu;
    if (seg.caller) byCaller.set(seg.caller, (byCaller.get(seg.caller) ?? 0) + cu);
  }
  const reserved = ctx.store.leases
    .map((l) => leaseView(ctx, l).reservedCu)
    .reduce((a, b) => a + b, 0);
  const balanceCu = currentBalance(ctx);
  const usedTodayCu = Math.round(used);
  const days = usedTodayCu > 0 ? Math.floor(balanceCu / usedTodayCu) : 0;
  // The fake's leases all ride the primary account (the one
  // live credential); the other accounts' figures are their
  // own — zero spend, and a null balance until the account
  // is brought in and can be dialed.
  const primary = ctx.store.budgetAccounts.find((a) => a.credential === "live") ?? ctx.store.budgetAccounts[0];
  const capHeadroom = primary.caps.daily != null ? Math.max(0, primary.caps.daily - usedTodayCu) : Infinity;
  const accounts: BudgetAccountView[] = ctx.store.budgetAccounts.map((a) => {
    const isPrimary = a === primary;
    const isHome = a.venue === primary.venue;
    // A foreign venue's account serves no figures through
    // this snapshot (null, as the live adapter serves); a
    // same-venue secondary is journal-backed at zero.
    return {
      venue: a.venue,
      venueLabel: VENUE_LABEL[a.venue] ?? a.venue,
      account: a.account,
      label: a.label,
      balanceCu: isPrimary ? balanceCu : null,
      usedTodayCu: isPrimary ? usedTodayCu : isHome ? 0 : null,
      usedMonthCu: isPrimary ? Math.round(usedMonth) : isHome ? 0 : null,
      standingUsedTodayCu: isPrimary ? Math.round(byCaller.get("standing") ?? 0) : isHome ? 0 : null,
      caps: { ...a.caps },
      credential: a.credential,
    };
  });
  return {
    balanceCu,
    usedTodayCu,
    reservedCu: reserved,
    availableCu: Math.min(balanceCu - reserved, capHeadroom),
    runwayLabel: days > 0 ? `${days} days at today's rate` : "less than a day at today's rate",
    byCaller: [...byCaller.entries()]
      .map(([caller, cu]) => ({ caller, cu: Math.round(cu) }))
      .sort((a, b) => b.cu - a.cu),
    caps: { ...primary.caps },
    accounts,
    budgetlessVenues: ctx.store.budgetlessVenues.map((v) => ({
      venue: v,
      venueLabel: VENUE_LABEL[v] ?? v,
    })),
  };
}

/** The active grant, on the core's own activity rule
 *  (grant_active: a record whose until is still ahead). */
export function activeGrant(ctx: MockContext): GrantRecord | null {
  const grant = ctx.store.grant;
  if (!grant || Date.parse(grant.until) <= ctx.clockMs) return null;
  return grant;
}

/** The catalog shapes of the evidenced class — the
 *  orphans census's candidate list for a shape the
 *  evidence carries only as a class (V6). */
export function orphanCandidates(ctx: MockContext, ev: SessionEvidence): OrphanShapeCandidate[] {
  const cls = shapeClass(ev.spec);
  return SPEC_CATALOG.filter(
    (rec) =>
      shapeClass({ gpu: rec.gpu, tpu: rec.tpu, high_mem: rec.high_mem }) === cls,
  ).map((rec) => {
    const v = specView(rec);
    return { id: v.id, label: v.label, rateLabel: v.rateLabel };
  });
}

export function callers(ctx: MockContext): CallerView[] {
  return ctx.store.callers.map((caller) => {
    const lease = ctx.store.leases.find((l) => l.caller === caller);
    if (!lease) {
      return { caller, stateLabel: "Registered", stateTone: "idle" as Tone, sub: "No live session" };
    }
    const view = leaseView(ctx, lease);
    if (view.state === "renewal-due") {
      return {
        caller,
        stateLabel: "Renewal due",
        stateTone: "warn" as Tone,
        sub: `Lease ended ${fmtTime(lease.deadline)} · renewal due`,
      };
    }
    return {
      caller,
      stateLabel: "Active",
      stateTone: "ok" as Tone,
      sub: `Riding ${view.displayName} · granted ${fmtTime(lease.acquired_at)}`,
    };
  });
}

/* ---------- event projection (the LogRow entry shape) ---------- */

export function knownSessions(ctx: MockContext): string[] {
  return [
    ...new Set([
      ...Object.keys(SESSION_NAMES),
      ...ctx.store.leases.map((l) => l.session),
      ...Object.keys(ctx.store.evidence),
    ]),
  ];
}

/** The session whose served display name appears in the
 *  text (longest match wins), or null. */
export function sessionNamedIn(ctx: MockContext, text: string): string | null {
  let best: string | null = null;
  for (const session of knownSessions(ctx)) {
    const n = ctx.name(session);
    if (text.includes(n) && (!best || n.length > ctx.name(best).length)) best = session;
  }
  return best;
}

/**
 * Split the record's one message string into headline +
 * meta, per the forms the venue's messages actually take:
 * a trailing parenthetical that is a shape label or a
 * session name rides the meta line; an em-dash tail that
 * names a session or a caller ("caller X") does the same;
 * anything else stays whole. A session named anywhere
 * resolves the drawer's entity; when the split leaves no
 * meta and the named session is a live lease, the meta is
 * its holder ("held by gamma-thread" — frame B1).
 */
export function splitEventMessage(
  ctx: MockContext,
  message: string,
): {
  headline: string;
  meta?: string;
  entitySession: string | null;
} {
  let headline = message;
  let meta: string | undefined;
  let entitySession: string | null = null;

  const paren = message.match(/^(.*) \(([^()]*)\)$/);
  if (paren) {
    const [, base, inner] = paren;
    const named = knownSessions(ctx).find((s) => ctx.name(s) === inner) ?? null;
    if (SPEC_CATALOG.some((rec) => rec.label === inner)) {
      headline = base;
      meta = inner;
    } else if (named) {
      headline = base;
      meta = inner;
      entitySession = named;
    }
  }
  if (meta === undefined) {
    const dash = headline.match(/^(.*) — (.+)$/);
    if (dash) {
      const [, base, tail] = dash;
      const named = knownSessions(ctx).find((s) => ctx.name(s) === tail) ?? null;
      if (named) {
        headline = base;
        meta = tail;
        entitySession = named;
      } else if (tail.startsWith("caller ")) {
        headline = base;
        meta = tail;
      }
    }
  }
  if (!entitySession) entitySession = sessionNamedIn(ctx, headline);
  if (meta === undefined && entitySession) {
    const lease = ctx.store.leases.find((l) => l.session === entitySession);
    if (lease?.caller) meta = `held by ${lease.caller}`;
  }
  return { headline, meta, entitySession };
}

export function eventEntity(ctx: MockContext, session: string): EventView["detail"]["entity"] {
  const lease = ctx.store.leases.find((l) => l.session === session);
  const ev = ctx.store.evidence[session];
  const caller = lease?.caller ?? ev?.caller ?? null;
  const shape = lease?.shape ?? ev?.shape ?? null;
  if (!caller && !shape) return undefined;
  const parts = ["Lease"];
  if (caller) parts.push(`held by ${caller}`);
  if (shape) parts.push(shapeInfo(shape).label);
  return {
    groupLabel: "Session",
    session,
    title: ctx.name(session),
    sub: parts.join(" · "),
  };
}

/** The event drawer facts lead with the day relation, as
 *  frame B3 draws it ("Today · 1:12:00 PM"). */
export function fmtDayTime(ctx: MockContext, iso: string): string {
  const sameDay =
    new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(
      new Date(iso),
    ) ===
    new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(
      new Date(ctx.clockMs),
    );
  return `${sameDay ? "Today" : fmtDateToken(iso)} · ${fmtTimeLong(iso)}`;
}

/** The access log's served projection (the LogRow scoped
 *  variant's entry shape): the record's detail ends with
 *  the time it was written ("… · 1:36 PM") — the split
 *  lifts that time out to lead the meta line, as the
 *  event split does, and the remainder is the meta. A
 *  record whose detail is only its time serves no meta.
 *  The record's chip, where served, is the row's kind. */
export function accessLogView(ctx: MockContext, a: AccessEntry): AccessLogView {
  const time = fmtTime(a.at);
  const suffix = ` · ${time}`;
  const meta = a.detail.endsWith(suffix)
    ? a.detail.slice(0, -suffix.length)
    : a.detail;
  return {
    id: a.id,
    at: a.at,
    dateToken: fmtDateToken(a.at),
    time,
    headline: a.label,
    ...(meta ? { meta } : {}),
    ...(a.chip ? { kind: { label: a.chip.label, tone: a.chip.tone } } : {}),
  };
}

/** The day-grouping key for a timestamp, in the
 *  venue's timezone (the logs timeline groups by the
 *  day the panel reads, not the UTC day). */
export function dayKey(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** The day band's label, relative to the venue clock:
 *  Today / Yesterday / the weekday + date token. */
export function dayLabel(ctx: MockContext, iso: string): string {
  const key = dayKey(iso);
  if (key === dayKey(ctx.now())) return "Today";
  const yesterday = new Date(ctx.clockMs - 86400000).toISOString();
  if (key === dayKey(yesterday)) return "Yesterday";
  const weekday = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    weekday: "short",
  }).format(new Date(iso));
  return `${weekday}, ${fmtDateToken(iso)}`;
}

export function eventView(ctx: MockContext, e: VenueEvent): EventView {
  const kindLabel = KIND_LABEL[e.kind];
  const { headline, meta, entitySession } = splitEventMessage(ctx, e.message);
  const entity = entitySession ? eventEntity(ctx, entitySession) : undefined;
  return {
    id: e.id,
    at: e.at,
    kind: e.kind,
    kindLabel,
    tone: e.tone,
    message: e.message,
    venue: e.venue,
    venueLabel: VENUE_LABEL[e.venue],
    dateToken: fmtDateToken(e.at),
    time: fmtTime(e.at),
    headline,
    meta,
    // The logs categories (the panel's logCategory over
    // the outbox vocabulary): grant events are Grants,
    // budget events are Budget, the rest are Leases.
    category: e.kind === "budget" ? "budget" : e.kind === "grant" ? "grants" : "leases",
    dayKey: dayKey(e.at),
    dayLabel: dayLabel(ctx, e.at),
    raw: JSON.stringify(
      { id: e.id, at: e.at, kind: e.kind, tone: e.tone, message: e.message, venue: e.venue },
      null,
      2,
    ),
    detail: {
      message: e.message,
      facts: [
        { label: "Time", value: fmtDayTime(ctx, e.at), mono: true },
        { label: "Kind", value: kindLabel },
        { label: "Venue", value: VENUE_LABEL[e.venue] },
      ],
      ...(entity ? { entity } : {}),
    },
  };
}

/** The served grant projection: the active grant record
 *  plus its envelope block — the attributed leases and
 *  spend versus the snapshot caps, folded from the
 *  journal segments of the envelope's own leases (the
 *  same segments the budget folds). No standing lease
 *  rides the mock, so standing spend serves null —
 *  honest absence, as the panel renders it. */
export function grantView(ctx: MockContext): GrantView | null {
  const grant = activeGrant(ctx);
  if (!grant) return null;
  const leases = ctx.store.leases.filter((l) => l.envelope_id === grant.granted_at);
  const sessions = new Set(leases.map((l) => l.session));
  const dayStart = new Date(ctx.now());
  dayStart.setHours(0, 0, 0, 0);
  const monthStart = new Date(ctx.now());
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);
  let day = 0;
  let month = 0;
  for (const seg of ctx.store.journal) {
    if (!sessions.has(seg.session)) continue;
    const cu = ((Date.parse(seg.end) - Date.parse(seg.start)) / 3600000) * seg.rate;
    if (Date.parse(seg.start) >= monthStart.getTime()) month += cu;
    if (Date.parse(seg.start) >= dayStart.getTime()) day += cu;
  }
  return {
    id: grant.granted_at,
    until: grant.until,
    untilLabel: fmtTime(grant.until),
    burstShape: grant.burst_shape,
    burstLabel: shapeInfo(grant.burst_shape).label,
    standingShape: grant.standing_shape,
    shapes: [...grant.scope.shapes],
    caps: {
      daily: grant.scope.caps.daily,
      monthly: grant.scope.caps.monthly,
      standingDaily: grant.scope.caps.standing_daily,
    },
    spendDayCu: Math.round(day * 100) / 100,
    spendMonthCu: Math.round(month * 100) / 100,
    standingDaySpentCu: null,
    leases: leases.map((l) => ({
      session: l.session,
      displayName: ctx.name(l.session),
      shapeLabel: shapeInfo(l.shape).label,
      caller: l.caller ?? null,
      deadlineLabel: fmtTime(l.deadline),
    })),
  };
}

/** The served access list: every live session with its
 *  attribution — record-backed sessions carry their
 *  record's caller; evidence-only sessions with no caller
 *  on their evidence are unattributed and carry the
 *  release. */
export function accessView(ctx: MockContext): AccessSessionView[] {
  const CLASS_LABEL: Record<string, string> = {
    gpu: "GPU",
    tpu: "TPU",
    high_ram: "High-RAM",
    standard: "Standard",
  };
  const out: AccessSessionView[] = [];
  for (const lease of ctx.store.leases) {
    const cls = shapeClass(lease.shape_spec);
    out.push({
      session: lease.session,
      displayName: ctx.name(lease.session),
      shapeClass: cls,
      caller: lease.caller ?? null,
      firstSeen: lease.acquired_at,
      sub: `${CLASS_LABEL[cls] ?? cls} shape · since ${fmtTime(lease.acquired_at)}`,
      unattributed: false,
    });
  }
  for (const [session, ev] of Object.entries(ctx.store.evidence)) {
    if (ctx.store.leases.some((l) => l.session === session)) continue;
    const cls = shapeClass(ev.spec);
    const firstSeen = ev.acquired_at ?? ctx.now();
    out.push({
      session,
      displayName: ctx.name(session),
      shapeClass: cls,
      caller: ev.caller,
      firstSeen,
      sub: `${CLASS_LABEL[cls] ?? cls} shape · since ${fmtTime(firstSeen)}`,
      unattributed: ev.caller == null,
    });
  }
  return out.sort((a, b) => Date.parse(a.firstSeen) - Date.parse(b.firstSeen));
}

/** The snapshot composition: every served view folded
 *  from the store at the venue clock. The degraded form
 *  (last snapshot, frozen) is the adapter's own. */
export function composeSnapshot(ctx: MockContext): Snapshot {
  const leases = ctx.store.leases
    .map((l) => leaseView(ctx, l))
    .sort((a, b) => Date.parse(a.deadline) - Date.parse(b.deadline));
  const runsBySession: Record<string, RunView[]> = {};
  for (const run of ctx.store.runs) {
    if (!run.session) continue;
    (runsBySession[run.session] ??= []).push(runView(ctx, run));
  }
  for (const k of Object.keys(runsBySession)) {
    runsBySession[k].sort((a, b) => Date.parse(b.startedAt) - Date.parse(a.startedAt));
  }
  const recentRuns = [...ctx.store.runs]
    .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
    .slice(0, 3)
    .map((r) => runView(ctx, r));
  const orphans: OrphanView[] = Object.entries(ctx.store.evidence)
    .filter(([session]) => !ctx.store.leases.some((l) => l.session === session))
    .map(([session, ev]) => {
      const seenAt = ctx.store.orphanSeenAt[session];
      const seenMin = seenAt
        ? Math.max(1, Math.round((ctx.clockMs - Date.parse(seenAt)) / 60000))
        : 0;
      const runs = ctx.store.runs.filter((r) => r.session === session).length;
      // E4: the orphan's in-flight jobs, served with the
      // census — non-terminal backing records only, oldest
      // first, in the same view form the census's entries
      // take (the mock's records carry the job's name; the
      // label is that name).
      const jobs: OrphanJobView[] = ctx.store.runs
        .filter((r) => r.session === session && NONTERMINAL_RUN_STATES.includes(r.state))
        .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at))
        .map((r) => {
          const v = runView(ctx, r);
          return {
            id: r.run_id,
            label: r.job,
            sub: `Run · started ${fmtTime(r.started_at)}`,
            stateLabel: v.stateLabel,
            tone: v.stateTone,
          };
        });
      // V6: the census's derivation detail — the
      // evidenced shape or the class's candidate list,
      // the deadline's source and conflicts, the
      // creator claim, and the handover state.
      const detail = ctx.store.orphanDetail[session];
      const evidenced = ev.shape != null;
      const cls = shapeClass(ev.spec);
      const CLASS_LABEL: Record<string, string> = {
        gpu: "GPU",
        tpu: "TPU",
        high_ram: "High-RAM",
        standard: "Standard",
      };
      const shapeDescriptor = evidenced
        ? shapeInfo(ev.shape!).label
        : ev.spec
          ? `${CLASS_LABEL[cls] ?? cls} class`
          : "Unknown shape";
      const conflicts: OrphanConflictView[] = (detail?.conflicts ?? []).map((c) => ({
        field: c.field,
        text: c.values
          .map(
            (v) =>
              `${v.source} says ${/^\d{4}-\d{2}-\d{2}T/.test(v.value) ? fmtTime(v.value) : v.value}`,
          )
          .join(" · "),
      }));
      return {
        session,
        nameless: false,
        endpoint: null,
        priorSession: null,
        displayName: ctx.name(session),
        venue: "colab" as VenueId,
        venueLabel: VENUE_LABEL.colab,
        shapeLabel: shapeDescriptor,
        sub: `${shapeDescriptor} · seen ${seenMin} min ago · ${runs === 0 ? "no run records" : `${runs} run record${runs > 1 ? "s" : ""}`}`,
        firstSeenLabel: fmtTime(seenAt ?? ev.acquired_at ?? ctx.now()),
        acquiredLabel: ev.acquired_at ? fmtTime(ev.acquired_at) : null,
        kitInstalled: detail?.kitInstalled ?? false,
        shapeEvidenced: evidenced,
        shapeClassLabel: ev.spec ? (CLASS_LABEL[cls] ?? cls) : null,
        shapeCandidates: evidenced ? [] : orphanCandidates(ctx, ev),
        creatorCaller: detail?.creatorCaller ?? ev.caller ?? null,
        firstClaim: detail?.firstClaim ?? null,
        deadlineSource: detail?.deadlineSource ?? null,
        deadlineStalePossible: detail?.deadlineStalePossible ?? false,
        conflicts,
        handoverPending: detail?.handoverPending ?? false,
        // E4: the evidenced deadline and the past-deadline
        // determination, served — the headline renders the
        // time and the chip from these, never its own math.
        deadline: ev.deadline,
        deadlineLabel: ev.deadline ? fmtTime(ev.deadline) : null,
        deadlinePast: ev.deadline !== null && Date.parse(ev.deadline) <= ctx.clockMs,
        deadlineTone: "warn" as Tone,
        jobs,
      };
    });
  const snap: Snapshot = {
    now: ctx.now(),
    degraded: false,
    lastServedAt: null,
    leases,
    recentRuns,
    runsBySession,
    orphans,
    resolvedOrphans: ctx.store.resolvedOrphans,
    events: ctx.store.events.map((e) => eventView(ctx, e)),
    budget: budget(ctx),
    callers: callers(ctx),
    accessLog: ctx.store.accessLog.map((a) => accessLogView(ctx, a)),
    specs: SPEC_CATALOG.map((rec) => specView(rec)),
    grant: grantView(ctx),
    access: accessView(ctx),
    runningCount: leases.filter((l) => l.state === "running").length,
  };
  return snap;
}
