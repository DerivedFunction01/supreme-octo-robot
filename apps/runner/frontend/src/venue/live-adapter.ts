// The live data seam: the same VenueAdapter interface the
// mock implements, over the venue surface's own HTTP API —
// the routes the original panel's client polls and posts
// (pipeline/venue/ui/server.py): the state portions
// (/api/state/{records,specs,budget,grant,orphans,listeners}),
// the outbox (/api/outbox), and the lease/grant/budget verbs
// (/api/lease/*, /api/grant*, /api/ungrant,
// /api/access/release, /api/config/budget,
// /api/server/restart). Projections mirror the mock's forms
// field for field, composed from the served shapes; where
// the surface serves no equivalent (exec, spend by caller,
// run durations), the adapter says so honestly rather than
// inventing data (see the report notes on each).
//
// Selection: src/venue/index.ts constructs this adapter for
// the integration (published) build; the standalone preview
// keeps the mock. Base URL: same-origin — the surface that
// serves the app also serves the API; the seam honours
// only a same-origin relative base (venue/index.ts's
// sanitizeBaseUrl), never a base another origin names.

import type {
  AccessLogView,
  AccessSessionView,
  AcquireInput,
  BudgetAccountView,
  BudgetCaps,
  BudgetView,
  CallerView,
  EventKind,
  EventView,
  GrantView,
  LeaseDiagnosticsView,
  LeaseView,
  OrphanConflictView,
  OrphanJobView,
  OrphanShapeCandidate,
  OrphanView,
  ResolvedOrphanView,
  RunView,
  ShapeSpec,
  Snapshot,
  SpecView,
  Tone,
} from "./types";
import { AdapterError } from "./types";
import type { VenueAdapter } from "./adapter";
import { fmtDateToken, fmtTime, fmtTimeLong } from "./adapter";

/* ---------- served shapes (the surface's own records) ---------- */

interface ServedSpec {
  id: string;
  label: string;
  gpu: string | null;
  tpu: string | null;
  high_mem: boolean;
  rate_cu_per_hour: number | null;
  agent_startable: boolean;
}

interface ServedLeaseRecord {
  session: string;
  shape: string;
  shape_spec: ShapeSpec;
  rate_cu_per_hour: number | null;
  caller: string | null;
  acquired_at: string;
  deadline: string;
  last_used_at: string;
  jobs: string[];
  budget_at_acquire: { projected?: number; reserved_cu?: number } | null;
  envelope_id?: string;
  last_pulse_result?: string | null;
  shortened_at?: string;
}

interface ServedRecordEntry {
  action: string;
  /** Absent on the backend's "no-lease" verdict — an
   *  entry whose record could not be loaded (torn,
   *  mid-write, or deleted between the records listing
   *  and the per-record load). The panel's own client
   *  reads entry.record || {} for the same reason; the
   *  projections here take record-carrying entries only
   *  (recordEntries). */
  record?: ServedLeaseRecord;
  sync_claim: { caller: string; expires_at?: string; until?: string } | null;
  keepalive_heartbeat_age_s: number | null;
  caller: string | null;
}

interface ServedAccessEntry {
  session: string;
  endpoint?: string;
  shape_class: string;
  caller: string | null;
  first_seen: string;
  unattributed?: boolean;
}

interface ServedBudgetAccount {
  venue: string;
  account: string;
  label: string;
  caps: { daily: number | null; monthly: number | null; standing_daily: number | null };
  balance: number | null;
  day_spent: number;
  month_spent: number;
  standing_day_spent: number | null;
  credential: BudgetAccountView["credential"];
}

interface ServedBudget {
  balance: number;
  day_spent: number;
  month_spent: number;
  standing_day_spent: number;
  caps: { daily: number | null; monthly: number | null; standing_daily: number | null };
  accounts: ServedBudgetAccount[];
}

interface ServedGrant {
  kind: string;
  granted_at: string;
  until: string;
  standing_shape: string;
  burst_shape: string;
  scope: {
    caps: { daily: number | null; monthly: number | null; standing_daily: number | null };
    standing_shape: string;
    burst_shape: string;
    shapes: string[];
  };
}

interface ServedEnvelope {
  id: string;
  caps: { daily: number | null; monthly: number | null; standing_daily: number | null };
  records: ServedLeaseRecord[];
  spend: {
    balance: number | null;
    day_spent: number;
    month_spent: number;
    standing_day_spent: number | null;
  };
}

interface ServedOrphan {
  /** Null on a nameless census row (the backend keys
   *  such a row by endpoint: session None, nameless
   *  True, prior_session the recovered name or None —
   *  the name is lost server-side, and the null is the
   *  honest absence, not a broken string). */
  session: string | null;
  nameless?: boolean;
  prior_session?: string | null;
  endpoint?: string | null;
  shape_class: string | null;
  shape: string | null;
  shape_spec: ShapeSpec | null;
  shape_evidenced: boolean;
  shape_candidates: string[];
  creator_caller: string | null;
  first_claim: string | null;
  derived_deadline: string | null;
  deadline_source: string | null;
  deadline_stale_possible: boolean;
  conflicts: { field: string; values: { source: string; value: string }[] }[];
  acquired_at: string | null;
  jobs_in_flight: number;
  jobs_in_flight_entries: { id: string; kind: string; state: string; started_at: string }[];
  first_seen: string;
  kit_installed: boolean;
  handover_pending: boolean;
  deadline_past: boolean;
}

interface ServedListenerEntry {
  at: string;
  age_s: number | null;
  error: string | null;
  listeners: { port: number; pid: number; cwd: string | null; suspect?: string[] }[];
}

interface OutboxEvent {
  seq: number;
  ts: string;
  kind: string;
  detail: Record<string, unknown>;
}

interface Parts {
  records: { records: ServedRecordEntry[]; access: ServedAccessEntry[] } | null;
  specs: { specs: ServedSpec[] } | null;
  budget: { budget: ServedBudget } | null;
  grant: { grant: ServedGrant | null; envelope: ServedEnvelope | null } | null;
  orphans: { orphans: ServedOrphan[] } | null;
  listeners: { listeners: Record<string, ServedListenerEntry> } | null;
  outbox: { events: OutboxEvent[]; last_seq: number } | null;
}

/* ---------- small served-form helpers ---------- */

const VENUE_LABEL = "Colab";
const TZ = "America/New_York";

const CLASS_LABEL: Record<string, string> = {
  gpu: "GPU",
  tpu: "TPU",
  high_ram: "High-RAM",
  standard: "Standard",
};

/** A catalog entry's shape class, the gate's own rule (the
 *  mock's shapeClass, over the served spec). */
function shapeClass(spec: ShapeSpec | null): string {
  if (spec?.gpu) return "gpu";
  if (spec?.tpu) return "tpu";
  return spec?.high_mem ? "high_ram" : "standard";
}

/** Session display names are served by the adapter, never
 *  derived in the frontend (the mock's rule). Live session
 *  ids carry a renewal suffix (-r<digits>) the display name
 *  drops; the base name title-cases word by word. */
export function liveSessionName(session: string): string {
  if (session === "?") return "Unnamed session";
  const base = session.replace(/-r\d+$/, "");
  return base
    .split("-")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** The base name a run event names its session by (the
 *  outbox's run events carry the base name, not the
 *  renewal-suffixed record id). */
function baseName(session: string): string {
  return session.replace(/-r\d+$/, "");
}

function fmtRemaining(ms: number): string {
  const mins = Math.max(0, Math.round(ms / 60000));
  const h = Math.floor(mins / 60);
  return `${h} h ${String(mins % 60).padStart(2, "0")} min left`;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/* ---------- the adapter ---------- */

type FetchLike = (
  url: string,
  init?: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    signal?: AbortSignal;
  },
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

/** One portion's fetch bound. The records portion's state
 *  build is the surface's slowest (tens of seconds under
 *  load); the bound exists so a wedged request fails and
 *  the next poll retries, never so a slow one is cut. */
const FETCH_TIMEOUT_MS = 150000;

const EMPTY_BUDGET: BudgetView = {
  balanceCu: 0,
  usedTodayCu: 0,
  reservedCu: 0,
  availableCu: 0,
  runwayLabel: "less than a day at today's rate",
  byCaller: [],
  caps: { daily: null, monthly: null, standingDaily: null },
  accounts: [],
};

export class LiveVenueAdapter implements VenueAdapter {
  private readonly baseUrl: string;
  private readonly fetchFn: FetchLike;
  private listeners = new Set<() => void>();
  private version = 0;
  private parts: Parts = {
    records: null,
    specs: null,
    budget: null,
    grant: null,
    orphans: null,
    listeners: null,
    outbox: null,
  };
  private reachable = true;
  private simulatedDown = false;
  /** Portions currently loading, by part — a refresh that
   *  finds its portion already in flight shares that load
   *  instead of firing a duplicate. The surface builds its
   *  state per request; concurrent duplicates of the slow
   *  records build queue behind each other and starve the
   *  very snapshot they are fetching (measured live: three
   *  overlapping records requests, none answered inside
   *  150 s, while a single uncontended one answered in
   *  ~50 s). One in flight per portion, always. */
  private inflight = new Map<keyof Parts, Promise<boolean>>();
  private lastServedAt: string | null = null;
  private cachedSnapshot: Snapshot | null = null;
  /** The last refresh failure, for diagnostics; the snapshot
   *  on screen stays last-good (the bridge-down rule). */
  lastError: string | null = null;

  constructor(opts: { baseUrl?: string; fetchFn?: FetchLike } = {}) {
    this.baseUrl = (opts.baseUrl ?? "").replace(/\/$/, "");
    this.fetchFn =
      opts.fetchFn ??
      ((url, init) => fetch(url, init) as ReturnType<FetchLike>);
    // The panel's own poll cadences (poll.js PARTS): the fast
    // portions at 15 s, the slow ones at 60 s; a 30 s clock
    // tick keeps countdown labels fresh between polls.
    void this.refreshAll();
    setInterval(() => void this.refreshFast(), 15000);
    setInterval(() => void this.refreshSlow(), 60000);
    setInterval(() => this.emit(), 30000);
  }

  /* ----- subscription plumbing ----- */
  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  getVersion(): number {
    return this.version;
  }
  private emit(): void {
    this.version += 1;
    this.cachedSnapshot = null;
    this.listeners.forEach((fn) => fn());
  }
  now(): string {
    return new Date().toISOString();
  }

  /** The first snapshot load (the integration entry awaits
   *  it before mounting, so live mode never flashes the
   *  empty snapshot). Awaits the FAST loop only — records,
   *  orphans, outbox are what first paint needs; the slow
   *  portions (specs, budget, grant, listeners) land from
   *  the constructor's own refresh on their cadence rather
   *  than gating the mount on the slowest portion. Resolves
   *  even when the surface is down — the snapshot then reads
   *  degraded and polling keeps retrying. */
  async ready(): Promise<void> {
    await this.refreshFast();
  }

  /* ----- fetching ----- */

  private async getJson<T>(path: string): Promise<T> {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await this.fetchFn(`${this.baseUrl}${path}`, {
        signal: ctl.signal,
      });
      if (!res.ok) throw new Error(`GET ${path} → HTTP ${res.status}`);
      return (await res.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  /** POST in the panel's own two forms: a 409 carries the
   *  core's verdict in the body and returns it (apiResult);
   *  any other failure throws with the server's error text
   *  (api). */
  private async post(path: string, bodyObj: unknown): Promise<Record<string, unknown>> {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await this.fetchFn(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyObj),
        signal: ctl.signal,
      });
      const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      if (res.ok || res.status === 409) return data;
      throw new AdapterError(
        `http-${res.status}`,
        str(data.error) ?? `HTTP ${res.status}`,
      );
    } finally {
      clearTimeout(timer);
    }
  }

  private refreshPart<K extends keyof Parts>(
    key: K,
    path: string,
  ): Promise<boolean> {
    const existing = this.inflight.get(key);
    if (existing) return existing;
    const load = (async (): Promise<boolean> => {
      try {
        this.parts[key] = await this.getJson(path);
        return true;
      } catch (err) {
        this.lastError = err instanceof Error ? err.message : String(err);
        return false;
      } finally {
        this.inflight.delete(key);
      }
    })();
    this.inflight.set(key, load);
    return load;
  }

  private async refreshFast(): Promise<void> {
    if (this.simulatedDown) return;
    const results = await Promise.all([
      this.refreshPart("records", "/api/state/records"),
      this.refreshPart("orphans", "/api/state/orphans"),
      this.refreshPart("outbox", "/api/outbox?after=0"),
    ]);
    if (results.some(Boolean)) {
      this.reachable = true;
      this.lastServedAt = this.now();
      this.emit();
    } else if (this.parts.records) {
      // Portions fail alone; only a total fast-loop failure
      // marks the surface down (the degraded frame then
      // serves the last known state).
      this.reachable = false;
      this.emit();
    }
  }

  private async refreshSlow(): Promise<void> {
    if (this.simulatedDown) return;
    const results = await Promise.all([
      this.refreshPart("specs", "/api/state/specs"),
      this.refreshPart("budget", "/api/state/budget"),
      this.refreshPart("grant", "/api/state/grant"),
      this.refreshPart("listeners", "/api/state/listeners"),
    ]);
    if (results.some(Boolean)) this.emit();
  }

  private async refreshAll(): Promise<void> {
    await Promise.all([this.refreshFast(), this.refreshSlow()]);
  }

  /* ----- served catalog (from the specs portion) ----- */

  private specMap(): Map<string, ServedSpec> {
    return new Map((this.parts.specs?.specs ?? []).map((s) => [s.id, s]));
  }

  private shapeLabel(shape: string): string {
    return this.specMap().get(shape)?.label ?? shape;
  }

  private shapeRateLabel(shape: string): string {
    const rate = this.specMap().get(shape)?.rate_cu_per_hour;
    return rate != null ? `${rate} CU/h` : "Cost unconfirmed";
  }

  private specViews(): SpecView[] {
    return (this.parts.specs?.specs ?? []).map((rec) => {
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
  private recordEntries(): (ServedRecordEntry & { record: ServedLeaseRecord })[] {
    return (this.parts.records?.records ?? []).filter(
      (e): e is ServedRecordEntry & { record: ServedLeaseRecord } => !!e.record,
    );
  }

  private leaseView(entry: ServedRecordEntry & { record: ServedLeaseRecord }): LeaseView {
    const lease = entry.record;
    const nowMs = Date.parse(this.now());
    const expired = Date.parse(lease.deadline) <= nowMs;
    return {
      session: lease.session,
      displayName: liveSessionName(lease.session),
      venue: "colab",
      venueLabel: VENUE_LABEL,
      shape: lease.shape,
      shapeLabel: this.shapeLabel(lease.shape),
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
      diagnostics: this.diagnosticsView(entry),
    };
  }

  /** The lease card's diagnostics (V7), from the listeners
   *  portion plus the record's own liveness stamps. A
   *  session neither source carries serves null (honest
   *  absence). A census entry whose probe failed serves its
   *  empty listener list with the heartbeat unreadable —
   *  "unknown", the panel's own word. */
  private diagnosticsView(entry: ServedRecordEntry & { record: ServedLeaseRecord }): LeaseDiagnosticsView | null {
    const lease = entry.record;
    const census = this.parts.listeners?.listeners?.[lease.session];
    if (!census && entry.keepalive_heartbeat_age_s == null && !lease.last_pulse_result && !entry.sync_claim) {
      return null;
    }
    const rate = lease.rate_cu_per_hour ?? this.specMap().get(lease.shape)?.rate_cu_per_hour;
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
            untilLabel: fmtTime(claim.expires_at ?? claim.until ?? this.now()),
          }
        : null,
    };
  }

  private runLabel(state: string): { label: string; tone: Tone } {
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
  private runViews(): RunView[] {
    const events = this.parts.outbox?.events ?? [];
    const leaseByBase = new Map(
      this.recordEntries().map(
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
      const l = this.runLabel(state);
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

  private budgetView(): BudgetView {
    const served = this.parts.budget?.budget;
    if (!served) return EMPTY_BUDGET;
    const reserved = this.recordEntries()
      .map((e) => this.leaseView(e).reservedCu)
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

  private grantView(): GrantView | null {
    const grant = this.parts.grant?.grant;
    if (!grant || Date.parse(grant.until) <= Date.parse(this.now())) return null;
    const envelope = this.parts.grant?.envelope;
    const caps = envelope?.caps ?? grant.scope.caps;
    const records =
      envelope?.records ??
      this.recordEntries()
        .map((e) => e.record)
        .filter((r) => r.envelope_id === grant.granted_at);
    return {
      id: grant.granted_at,
      until: grant.until,
      untilLabel: fmtTime(grant.until),
      burstShape: grant.burst_shape,
      burstLabel: this.shapeLabel(grant.burst_shape),
      standingShape: grant.standing_shape,
      shapes: [...grant.scope.shapes],
      caps: {
        daily: caps.daily,
        monthly: caps.monthly,
        standingDaily: caps.standing_daily,
      },
      spendDayCu: envelope?.spend.day_spent ?? this.parts.budget?.budget.day_spent ?? 0,
      spendMonthCu: envelope?.spend.month_spent ?? this.parts.budget?.budget.month_spent ?? 0,
      standingDaySpentCu:
        envelope?.spend.standing_day_spent ?? this.parts.budget?.budget.standing_day_spent ?? null,
      leases: records.map((r) => ({
        session: r.session,
        displayName: liveSessionName(r.session),
        shapeLabel: this.shapeLabel(r.shape),
        caller: r.caller ?? null,
        deadlineLabel: fmtTime(r.deadline),
      })),
    };
  }

  private callerViews(): CallerView[] {
    const byCaller = new Map<string, ServedRecordEntry & { record: ServedLeaseRecord }>();
    for (const entry of this.recordEntries()) {
      const caller = entry.record.caller ?? entry.caller;
      if (caller && !byCaller.has(caller)) byCaller.set(caller, entry);
    }
    const seen = new Set<string>(byCaller.keys());
    for (const a of this.parts.records?.access ?? []) {
      if (a.caller) seen.add(a.caller);
    }
    return [...seen].sort().map((caller) => {
      const entry = byCaller.get(caller);
      if (!entry) {
        return { caller, stateLabel: "Registered", stateTone: "idle" as Tone, sub: "No live session" };
      }
      const view = this.leaseView(entry);
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

  registeredCallers(): string[] {
    return this.callerViews().map((c) => c.caller);
  }

  private accessViews(): AccessSessionView[] {
    return (this.parts.records?.access ?? [])
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

  private orphanViews(): OrphanView[] {
    const nowMs = Date.parse(this.now());
    return (this.parts.orphans?.orphans ?? []).map((o) => {
      const evidenced = o.shape_evidenced && o.shape != null;
      const cls = o.shape_class ?? (o.shape_spec ? shapeClass(o.shape_spec) : null);
      const shapeDescriptor = evidenced
        ? this.shapeLabel(o.shape!)
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
            label: this.shapeLabel(id),
            rateLabel: this.shapeRateLabel(id),
          }));
      const jobs: OrphanJobView[] = (o.jobs_in_flight_entries ?? []).map((j) => {
        const l = this.runLabel(j.state);
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

  /* ----- the outbox projections (events + access log) ----- */

  private dayKey(iso: string): string {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date(iso));
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
    return `${get("year")}-${get("month")}-${get("day")}`;
  }

  private dayLabel(iso: string): string {
    const key = this.dayKey(iso);
    if (key === this.dayKey(this.now())) return "Today";
    const yesterday = new Date(Date.parse(this.now()) - 86400000).toISOString();
    if (key === this.dayKey(yesterday)) return "Yesterday";
    const weekday = new Intl.DateTimeFormat("en-US", {
      timeZone: TZ,
      weekday: "short",
    }).format(new Date(iso));
    return `${weekday}, ${fmtDateToken(iso)}`;
  }

  private fmtDayTime(iso: string): string {
    const sameDay =
      new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(new Date(iso)) ===
      new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(new Date(this.now()));
    return `${sameDay ? "Today" : fmtDateToken(iso)} · ${fmtTimeLong(iso)}`;
  }

  /** The outbox kind's place in the app's event vocabulary:
   *  kind, tone, and the logs category (the panel's
   *  logCategory rule: grant-* are Grants, budget events are
   *  Budget, the rest are Leases). */
  private eventKindOf(ev: OutboxEvent): { kind: EventKind; tone: Tone } {
    const k = ev.kind;
    if (k === "run-terminal") {
      const state = str(ev.detail.state);
      return { kind: "run", tone: state === "failed" ? "fail" : state === "complete" ? "ok" : "info" };
    }
    if (k.startsWith("grant-") || k.startsWith("envelope-")) {
      return { kind: "grant", tone: k === "grant-started" ? "ok" : "info" };
    }
    if (k.startsWith("budget")) {
      return { kind: "budget", tone: k.includes("refused") ? "fail" : "info" };
    }
    if (k.endsWith("-failed") || k === "budget-refused") {
      return { kind: "error", tone: "fail" };
    }
    if (k === "lease-started" || k === "lease-adopted") return { kind: "lease", tone: "ok" };
    if (k === "approval-needed" || k === "unattributed-session" || k === "keepalive-stale") {
      return { kind: "lease", tone: "warn" };
    }
    return { kind: "lease", tone: "info" };
  }

  /** Compose the event's headline + meta from its served
   *  kind and detail — the panel composes its log rows the
   *  same way (kind phrase + the variable part). */
  private eventText(ev: OutboxEvent): { headline: string; meta?: string } {
    const d = ev.detail;
    const r = (d.result ?? {}) as Record<string, unknown>;
    const rec = (r.record ?? {}) as Record<string, unknown>;
    const session = str(d.session) ?? str(rec.session) ?? str(d.new_session);
    const name = session ? liveSessionName(session) : null;
    const shape = str(d.shape) ?? str(rec.shape);
    const shapeText = shape ? this.shapeLabel(shape) : null;
    switch (ev.kind) {
      case "lease-started":
        return {
          headline: "lease granted",
          meta: [name, str(rec.caller) ?? str(d.caller) ? `→ ${str(rec.caller) ?? str(d.caller)}` : null, shapeText]
            .filter(Boolean)
            .join(" · ") || undefined,
        };
      case "lease-extended":
        return {
          headline: "lease extended",
          meta: [name, str(d.new_deadline) ? `new deadline ${fmtTime(str(d.new_deadline)!)}` : null]
            .filter(Boolean)
            .join(" · ") || undefined,
        };
      case "lease-shortened":
        return {
          headline: "lease shortened",
          meta: [name, str(d.new_deadline) ? `new deadline ${fmtTime(str(d.new_deadline)!)}` : null]
            .filter(Boolean)
            .join(" · ") || undefined,
        };
      case "lease-stopped":
        return { headline: "lease released", meta: name ?? undefined };
      case "lease-adopted":
        return { headline: "orphan adopted", meta: name ?? undefined };
      case "lease-renewed":
        return {
          headline: "lease renewed",
          meta: str(d.new_session) ? liveSessionName(str(d.new_session)!) : undefined,
        };
      case "run-terminal": {
        const state = str(d.state);
        const word = state === "complete" ? "passed" : state === "failed" ? "failed" : state ?? "";
        return {
          headline: `${str(d.job) ?? "run"} ${word}`.trim(),
          meta: name ?? undefined,
        };
      }
      case "approval-needed":
        return { headline: "approval needed", meta: [name, shapeText].filter(Boolean).join(" · ") || undefined };
      case "unattributed-session":
        return {
          headline: "unattributed session",
          meta: [str(d.shape_class) ? `${CLASS_LABEL[str(d.shape_class)!] ?? str(d.shape_class)} class` : null]
            .filter(Boolean)
            .join(" · ") || undefined,
        };
      case "unattributed-cleared":
        return { headline: "unattributed session cleared", meta: name ?? undefined };
      case "session-released":
        return { headline: "session released", meta: name ?? undefined };
      case "budget-caps-changed": {
        const caps = (d.caps ?? {}) as Record<string, unknown>;
        const fmt = (v: unknown) => (v == null ? "no cap" : `${v} CU`);
        return {
          headline: "budget caps changed",
          meta: `daily ${fmt(caps.daily ?? caps.daily_cu_budget)} · monthly ${fmt(caps.monthly ?? caps.monthly_cu_budget)} · standing ${fmt(caps.standing_daily ?? caps.standing_daily_cu_cap)}`,
        };
      }
      case "grant-started":
        return {
          headline: "two-tier grant started",
          meta: [str(d.burst) ? `burst ${this.shapeLabel(str(d.burst)!)}` : null].filter(Boolean).join(" · ") || undefined,
        };
      case "envelope-lease-started":
        return {
          headline: "lease granted · envelope",
          meta: [shapeText, str(d.caller) ? `→ ${str(d.caller)}` : null].filter(Boolean).join(" · ") || undefined,
        };
      case "envelope-lease-released":
        return { headline: "envelope lease released", meta: str(d.reason) ?? undefined };
      default: {
        if (ev.kind.endsWith("-failed")) {
          return {
            headline: ev.kind.replace(/-/g, " "),
            meta: str(d.error) ?? str(r.action) ?? name ?? undefined,
          };
        }
        return { headline: ev.kind.replace(/-/g, " "), meta: name ?? undefined };
      }
    }
  }

  private eventViews(): EventView[] {
    const events = [...(this.parts.outbox?.events ?? [])]
      .sort((a, b) => b.seq - a.seq)
      .slice(0, 500);
    const leaseByBase = new Map(
      this.recordEntries().map(
        (e) => [baseName(e.record.session), e] as const,
      ),
    );
    return events.map((ev) => {
      const { kind, tone } = this.eventKindOf(ev);
      const { headline, meta } = this.eventText(ev);
      const message = meta ? `${headline} · ${meta}` : headline;
      const d = ev.detail;
      const sessionRaw = str(d.session) ?? str(d.new_session);
      const entry = sessionRaw ? leaseByBase.get(baseName(sessionRaw)) : undefined;
      const entity = entry
        ? {
            groupLabel: "Session",
            session: entry.record.session,
            title: liveSessionName(entry.record.session),
            sub: [
              "Lease",
              entry.record.caller ? `held by ${entry.record.caller}` : null,
              this.shapeLabel(entry.record.shape),
            ]
              .filter(Boolean)
              .join(" · "),
          }
        : undefined;
      const kindLabel =
        kind === "lease" ? "Lease" : kind === "run" ? "Run" : kind === "grant" ? "Grant" : kind === "budget" ? "Budget" : "Error";
      return {
        id: `seq-${ev.seq}`,
        at: ev.ts,
        kind,
        kindLabel,
        tone,
        message,
        venue: "colab" as const,
        venueLabel: VENUE_LABEL,
        dateToken: fmtDateToken(ev.ts),
        time: fmtTime(ev.ts),
        headline,
        meta,
        category: kind === "budget" ? "budget" : kind === "grant" ? "grants" : "leases",
        dayKey: this.dayKey(ev.ts),
        dayLabel: this.dayLabel(ev.ts),
        raw: JSON.stringify(ev, null, 2),
        detail: {
          message,
          facts: [
            { label: "Time", value: this.fmtDayTime(ev.ts), mono: true },
            { label: "Kind", value: kindLabel },
            { label: "Venue", value: VENUE_LABEL },
          ],
          ...(entity ? { entity } : {}),
        },
      };
    });
  }

  private accessLogViews(): AccessLogView[] {
    const ACCESS_KINDS = new Set([
      "unattributed-session",
      "unattributed-cleared",
      "lease-adopted",
      "envelope-lease-started",
      "session-released",
      "approval-needed",
    ]);
    const events = [...(this.parts.outbox?.events ?? [])]
      .filter((ev) => ACCESS_KINDS.has(ev.kind))
      .sort((a, b) => b.seq - a.seq)
      .slice(0, 50);
    return events.map((ev) => {
      const d = ev.detail;
      const session = str(d.session) ?? str(d.new_session);
      const name = session ? liveSessionName(session) : null;
      let headline: string;
      let chip: { label: string; tone: Tone } | undefined;
      switch (ev.kind) {
        case "unattributed-session":
          headline = "Unattributed session";
          chip = { label: "Unattributed", tone: "warn" };
          break;
        case "unattributed-cleared":
          headline = "Unattributed cleared";
          break;
        case "lease-adopted":
          headline = "Ride granted";
          break;
        case "envelope-lease-started":
          headline = "Ride granted";
          break;
        case "session-released":
          headline = "Session released";
          break;
        case "approval-needed":
          headline = "Approval needed";
          chip = { label: "Approval", tone: "warn" };
          break;
        default:
          headline = ev.kind;
      }
      const meta = [
        str(d.caller) && ev.kind !== "unattributed-session" ? str(d.caller) : null,
        name,
      ]
        .filter(Boolean)
        .join(" · ");
      return {
        id: `seq-${ev.seq}`,
        at: ev.ts,
        dateToken: fmtDateToken(ev.ts),
        time: fmtTime(ev.ts),
        headline,
        ...(meta ? { meta } : {}),
        ...(chip ? { kind: chip } : {}),
      };
    });
  }

  private resolvedOrphanViews(): ResolvedOrphanView[] {
    const out: ResolvedOrphanView[] = [];
    const events = [...(this.parts.outbox?.events ?? [])].sort((a, b) => b.seq - a.seq);
    for (const ev of events) {
      if (out.length >= 5) break;
      const session = str(ev.detail.session);
      if (!session) continue;
      if (ev.kind === "lease-adopted") {
        out.push({
          session,
          displayName: liveSessionName(session),
          sub: `Adopted by panel · ${this.dayLabel(ev.ts).toLowerCase()}`,
          label: "Adopted",
          tone: "ok",
        });
      } else if (ev.kind === "session-released") {
        out.push({
          session,
          displayName: liveSessionName(session),
          sub: `Released · ${this.dayLabel(ev.ts).toLowerCase()}`,
          label: "Released",
          tone: "idle",
        });
      }
    }
    return out;
  }

  snapshot(): Snapshot {
    if (this.cachedSnapshot) return this.cachedSnapshot;
    const entries = this.recordEntries();
    const leases = entries
      .map((e) => this.leaseView(e))
      .sort((a, b) => Date.parse(a.deadline) - Date.parse(b.deadline));
    const runs = this.runViews();
    const runsBySession: Record<string, RunView[]> = {};
    for (const run of runs) {
      if (!run.session) continue;
      (runsBySession[run.session] ??= []).push(run);
    }
    const degraded = !this.reachable || this.simulatedDown;
    const snap: Snapshot = {
      now: this.now(),
      degraded,
      lastServedAt: degraded ? this.lastServedAt : null,
      leases,
      recentRuns: runs.slice(0, 3),
      runsBySession,
      orphans: this.orphanViews(),
      resolvedOrphans: this.resolvedOrphanViews(),
      events: this.eventViews(),
      budget: this.budgetView(),
      callers: this.callerViews(),
      accessLog: this.accessLogViews(),
      specs: this.specViews(),
      grant: this.grantView(),
      access: this.accessViews(),
      runningCount: leases.filter((l) => l.state === "running").length,
    };
    this.cachedSnapshot = snap;
    return snap;
  }

  /* ----- verbs ----- */

  private assertReachable(): void {
    if (this.simulatedDown || !this.reachable) {
      throw new AdapterError(
        "unreachable",
        "Lease server unreachable — state is frozen at the last served snapshot.",
      );
    }
  }

  async probe(): Promise<{ reachable: boolean; at: string }> {
    try {
      await this.getJson("/api/state/meta");
      return { reachable: true, at: this.now() };
    } catch {
      return { reachable: false, at: this.now() };
    }
  }

  setReachable(reachable: boolean): void {
    this.simulatedDown = !reachable;
    if (!reachable) {
      this.lastServedAt = this.lastServedAt ?? this.now();
      this.emit();
    } else {
      void this.refreshAll();
    }
  }

  async restartServer(): Promise<void> {
    await this.post("/api/server/restart", {});
    await new Promise((r) => setTimeout(r, 800));
    await this.refreshAll();
  }

  private leaseViewFor(session: string): LeaseView {
    const entry = this.recordEntries().find(
      (e) => e.record.session === session,
    );
    if (!entry) {
      throw new AdapterError("no-lease", `No live lease record for ${session}.`);
    }
    return this.leaseView(entry);
  }

  /** Acquire (POST /api/lease/start): a creation on this
   *  surface — the server stamps its own caller (the panel,
   *  the creation authority), so the app's caller choice is
   *  advisory here exactly as it is on the panel. A core
   *  refusal rides the result's action; it throws in the
   *  core's own vocabulary. */
  async acquire(input: AcquireInput): Promise<LeaseView> {
    this.assertReachable();
    const result = await this.post("/api/lease/start", {
      shape: input.shape,
      hours: input.hours,
    });
    const action = str(result.action);
    const rec = (result.record ?? {}) as Record<string, unknown>;
    const session = str(rec.session);
    if ((action === "created" || action === "adopted") && session) {
      await this.refreshFast();
      return this.leaseViewFor(session);
    }
    throw new AdapterError(
      action ?? "acquire-failed",
      str(result.reason) ?? str(result.error) ?? `Acquire refused (${action ?? "no verdict"}).`,
    );
  }

  async extend(
    session: string,
    hours: number,
  ): Promise<{ lease: LeaseView; note: string }> {
    this.assertReachable();
    const result = await this.post("/api/lease/extend", { session, hours });
    const action = str(result.action);
    await this.refreshFast();
    const lease = this.leaseViewFor(session);
    if (action === "extended") {
      const deadline = str(result.new_deadline) ?? lease.deadline;
      return { lease, note: `Extended — new deadline ${fmtTime(deadline)}.` };
    }
    if (action === "extend-standing-managed") {
      return {
        lease,
        note: "Extension refused: the standing lease is grant-managed — extend the grant instead.",
      };
    }
    if (action === "extend-no-lease") {
      return { lease, note: "Extension refused: no live lease record for the session." };
    }
    if (action?.includes("budget")) {
      const projected = num(result.projected);
      return {
        lease,
        note: `Extension refused: budget refused (over cap${projected != null ? `, projected ${projected} CU` : ""}).`,
      };
    }
    return {
      lease,
      note: `Extension refused: ${str(result.reason) ?? action ?? "the core refused"}.`,
    };
  }

  async shorten(
    session: string,
    target: { hours: number } | { deadline: string },
  ): Promise<{ lease: LeaseView; note: string }> {
    this.assertReachable();
    const bodyObj: Record<string, unknown> = { session };
    if ("deadline" in target) bodyObj.deadline = target.deadline;
    else bodyObj.hours = target.hours;
    const result = await this.post("/api/lease/shorten", bodyObj);
    const action = str(result.action);
    await this.refreshFast();
    const lease = this.leaseViewFor(session);
    if (action === "shortened") {
      const deadline = str(result.new_deadline) ?? lease.deadline;
      return { lease, note: `Shortened — new deadline ${fmtTime(deadline)}.` };
    }
    if (action?.includes("standing")) {
      return {
        lease,
        note: "Shorten refused: the standing lease is grant-managed — its deadline follows the grant.",
      };
    }
    if (action?.includes("past")) {
      return {
        lease,
        note: "Shorten refused: that target has already passed — Release ends the lease now.",
      };
    }
    if (action?.includes("earlier") || action?.includes("not-earlier")) {
      return {
        lease,
        note: "Shorten refused: that is not earlier than the current deadline — Extend moves it later.",
      };
    }
    return {
      lease,
      note: `Shorten refused: ${str(result.reason) ?? action ?? "the core refused"}.`,
    };
  }

  async release(session: string): Promise<void> {
    this.assertReachable();
    const result = await this.post("/api/lease/stop", { session });
    const action = str(result.action);
    await this.refreshFast();
    if (action !== "released") {
      throw new AdapterError(
        action ?? "release-failed",
        str(result.reason) ?? `Release refused (${action ?? "no verdict"}).`,
      );
    }
  }

  async startGrant(input: { hours: number; burst: string }): Promise<GrantView> {
    this.assertReachable();
    const result = await this.post("/api/grant", {
      hours: input.hours,
      burst: input.burst,
    });
    const action = str(result.action);
    if (action !== "granted") {
      throw new AdapterError(
        action ?? "grant-failed",
        str(result.reason) ?? str(result.error) ?? `Grant refused (${action ?? "no verdict"}).`,
      );
    }
    await this.refreshSlow();
    const view = this.grantView();
    if (!view) {
      throw new AdapterError("grant-failed", "The grant was recorded but does not read back as active.");
    }
    return view;
  }

  async extendGrant(
    hours: number,
  ): Promise<{ grant: GrantView | null; note: string }> {
    this.assertReachable();
    const result = await this.post("/api/grant/extend", { hours });
    const action = str(result.action);
    await this.refreshSlow();
    if (action === "grant-extended") {
      const grant = this.grantView();
      const until = str(result.new_until) ?? grant?.until;
      return {
        grant,
        note: `Grant extended — until ${until ? fmtTime(until) : "later"}.`,
      };
    }
    if (action === "grant-inactive") {
      return { grant: null, note: "Extension refused: no active grant to extend." };
    }
    if (action?.includes("budget")) {
      const projected = num(result.projected);
      return {
        grant: this.grantView(),
        note: `Extension refused: budget refused (over cap${projected != null ? `, projected ${projected} CU` : ""}).`,
      };
    }
    return {
      grant: this.grantView(),
      note: `Extension refused: ${str(result.reason) ?? action ?? "the core refused"}.`,
    };
  }

  async ungrant(): Promise<void> {
    this.assertReachable();
    await this.post("/api/ungrant", { confirm: true });
    await this.refreshSlow();
  }

  async releaseAccess(session: string): Promise<void> {
    this.assertReachable();
    const result = await this.post("/api/access/release", { session });
    const action = str(result.action);
    await this.refreshFast();
    if (action !== "session-released") {
      throw new AdapterError(
        action ?? "release-failed",
        action?.includes("record")
          ? `${liveSessionName(session)} carries a lease record — release it from its lease, not from Access.`
          : (str(result.reason) ?? `Release refused (${action ?? "no verdict"}).`),
      );
    }
  }

  async setBudgetCaps(input: {
    venue: string;
    account: string;
    caps: BudgetCaps;
  }): Promise<BudgetCaps> {
    this.assertReachable();
    await this.post("/api/config/budget", {
      venue: input.venue,
      account: input.account,
      daily_cu_budget: input.caps.daily,
      monthly_cu_budget: input.caps.monthly,
      standing_daily_cu_cap: input.caps.standingDaily,
    });
    await this.refreshSlow();
    const account = this.budgetView().accounts.find(
      (a) => a.venue === input.venue && a.account === input.account,
    );
    return account ? account.caps : input.caps;
  }

  /** Adopt (POST /api/lease/adopt): the server stamps its
   *  own caller, as with start. A core refusal is a 409
   *  whose verdict action names it — the messages below are
   *  the core's refusal sentences, as the mock serves them. */
  async adoptOrphan(
    session: string,
    caller: string,
    shape?: string,
  ): Promise<LeaseView> {
    this.assertReachable();
    void caller;
    const result = await this.post("/api/lease/adopt", {
      session,
      ...(shape ? { shape } : {}),
    });
    const action = str(result.action);
    if (action === "adopted") {
      await this.refreshFast();
      return this.leaseViewFor(session);
    }
    const MESSAGES: Record<string, string> = {
      "adopt-handover-pending":
        "Adoption refused: a handover child — its parent record takes it over by swap.",
      "adopt-no-deadline":
        "Adoption refused: no deadline evidence and none planted — adoption from the panel needs a derived deadline.",
      "adopt-deadline-past":
        "Adoption refused: the derived deadline has already passed — this orphan needs a planted deadline (CLI).",
      "adopt-shape-ambiguous":
        "Adoption refused: the shape class matches several catalog shapes — pick the shape first.",
      "adopt-shape-conflict":
        "Adoption refused: the picked shape contradicts the evidenced shape.",
      "adopt-shape-unknown":
        "Adoption refused: the picked shape is not in the catalog.",
      "adopt-has-record": `${liveSessionName(session)} already carries a lease record.`,
      "adopt-absent": `${session} is not an orphan session.`,
    };
    throw new AdapterError(
      action ?? "adopt-failed",
      (action && MESSAGES[action]) ??
        str(result.reason) ??
        `Adoption refused (${action ?? "no verdict"}).`,
    );
  }

  /** Adopt a nameless census row (POST /api/lease/adopt
   *  with the endpoint form): the assignment lost its
   *  name server-side, so the core mints a fresh name,
   *  binds it to the endpoint, and restores the record
   *  under it from the endpoint's own evidence. The
   *  verdict vocabulary mirrors the named path's, plus
   *  this flow's own (adopt-nameless-named,
   *  adopt-bind-failed, adopt-unknown). */
  async adoptNamelessOrphan(
    endpoint: string,
    caller: string,
    shape?: string,
  ): Promise<LeaseView> {
    this.assertReachable();
    void caller;
    const result = await this.post("/api/lease/adopt", {
      endpoint,
      ...(shape ? { shape } : {}),
    });
    const action = str(result.action);
    if (action === "adopted") {
      const minted = str(
        (result.adopted_nameless as { session?: unknown } | undefined)
          ?.session,
      );
      await this.refreshFast();
      if (minted) return this.leaseViewFor(minted);
      throw new AdapterError(
        "adopt-failed",
        "Adoption reported success without naming the minted session.",
      );
    }
    const MESSAGES: Record<string, string> = {
      "adopt-handover-pending":
        "Adoption refused: a handover child — its parent record takes it over by swap.",
      "adopt-no-deadline":
        "Adoption refused: no deadline evidence and none planted — adoption from the panel needs a derived deadline.",
      "adopt-deadline-past":
        "Adoption refused: the derived deadline has already passed — this orphan needs a planted deadline (CLI).",
      "adopt-shape-ambiguous":
        "Adoption refused: the shape class matches several catalog shapes — pick the shape first.",
      "adopt-shape-conflict":
        "Adoption refused: the picked shape contradicts the evidenced shape.",
      "adopt-shape-unknown":
        "Adoption refused: the picked shape is not in the catalog.",
      "adopt-has-record":
        "Adoption refused: a prior name for this endpoint already carries a lease record.",
      "adopt-nameless-named":
        "Adoption refused: this endpoint already displays a usable name — the named adoption owns it.",
      "adopt-bind-failed":
        "Adoption refused: the minted name's bind did not verify on a re-read — no record was planted.",
      "adopt-unknown":
        "Adoption refused: the assignment list could not be read.",
      "adopt-absent": `${endpoint} is not an orphan assignment.`,
    };
    throw new AdapterError(
      action ?? "adopt-failed",
      (action && MESSAGES[action]) ??
        str(result.reason) ??
        `Adoption refused (${action ?? "no verdict"}).`,
    );
  }

  async releaseOrphan(session: string): Promise<void> {
    // An orphan is an evidence-only session: its release is
    // the access release (the core's release-session verb),
    // exactly as the panel's access list performs it.
    return this.releaseAccess(session);
  }

  async releaseNamelessOrphan(endpoint: string): Promise<void> {
    // The endpoint form of the access release, for a
    // nameless census row: the endpoint IS the unassign
    // key, so the release rides it directly (the core's
    // release_endpoint, beside release_session).
    this.assertReachable();
    const result = await this.post("/api/access/release", { endpoint });
    const action = str(result.action);
    await this.refreshFast();
    if (action === "session-released") return;
    const MESSAGES: Record<string, string> = {
      "release-absent": `${endpoint} is not an orphan assignment.`,
      "release-unknown":
        "Release refused: the assignment list could not be read.",
      "session-has-record":
        "Release refused: a prior name for this endpoint carries a lease record — records release per session, from the lease.",
      "session-stop-failed":
        "Release refused: the runtime's stop did not verify — the census row is kept.",
    };
    throw new AdapterError(
      action ?? "release-failed",
      (action && MESSAGES[action]) ??
        str(result.reason) ??
        `Release refused (${action ?? "no verdict"}).`,
    );
  }

  /** Exec has no route on the lease surface: runs start
   *  through the venue's runner channel and this surface
   *  serves their records. The refusal is the honest one —
   *  the view surfaces it as the error it is. */
  async exec(session: string, job: string, caller: string): Promise<RunView> {
    void session;
    void job;
    void caller;
    throw new AdapterError(
      "exec-not-served",
      "Exec rides the venue's runner channel, not the lease surface — runs start from the runner and this surface serves their records.",
    );
  }
}
