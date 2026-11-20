// The data seam. The frontend consumes ONLY this interface and
// its served projections. Today the implementation is the
// stateful mock below, seeded with contract-12-shaped data;
// at S8 the live adapter replaces it behind the same seam
// with no frontend rewrite (plan §8, mock-first amendment).
//
// The mock implements the D1 adapter verbs against its store —
// acquire / extend / shorten / release / exec / probe, the
// two-tier grant lifecycle (grant / extend-grant / ungrant),
// and the access release — with the pinned semantics contract
// 12 / contract 01 name: placement by latest-deadline
// adoption, adoption-only pins, spend counted from the
// store's own lease segments (never balance deltas), exactly
// one run-terminal event per terminal transition, and caller
// attribution (presented-but-unregistered refused, absent =
// unattributed).

import type {
  AccessEntry,
  AccessLogView,
  AccessSessionView,
  AcquireInput,
  BudgetAccountView,
  BudgetCaps,
  BudgetView,
  CallerView,
  EventKind,
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
  ResolvedOrphanView,
  RunRecord,
  RunView,
  SessionEvidence,
  ShapeSpec,
  Snapshot,
  SpecView,
  SpendSegment,
  Tone,
  VenueEvent,
  VenueId,
} from "./types";
import { AdapterError } from "./types";
import leasesSeed from "./seed/leases.json";
import runsSeed from "./seed/runs.json";
import evidenceSeed from "./seed/evidence.json";
import journalSeed from "./seed/journal.json";
import eventsSeed from "./seed/events.json";
import callersSeed from "./seed/callers.json";
import accessSeed from "./seed/access-log.json";
import specsSeed from "./seed/specs.json";

export interface VenueAdapter {
  subscribe(fn: () => void): () => void;
  getVersion(): number;
  now(): string;
  snapshot(): Snapshot;
  registeredCallers(): string[];
  probe(): Promise<{ reachable: boolean; at: string }>;
  restartServer(): Promise<void>;
  setReachable(reachable: boolean): void;
  acquire(input: AcquireInput): Promise<LeaseView>;
  extend(session: string, hours: number): Promise<{ lease: LeaseView; note: string }>;
  shorten(
    session: string,
    target: { hours: number } | { deadline: string },
  ): Promise<{ lease: LeaseView; note: string }>;
  release(session: string): Promise<void>;
  startGrant(input: { hours: number; burst: string }): Promise<GrantView>;
  extendGrant(hours: number): Promise<{ grant: GrantView | null; note: string }>;
  ungrant(): Promise<void>;
  releaseAccess(session: string): Promise<void>;
  /** Update one account's budget caps (venue rework): each cap
   *  is a non-negative number or null (no cap). Resolves with
   *  the caps in force after the write. */
  setBudgetCaps(input: { venue: string; account: string; caps: BudgetCaps }): Promise<BudgetCaps>;
  adoptOrphan(session: string, caller: string, shape?: string): Promise<LeaseView>;
  /** The endpoint form of adoption, for a nameless census
   *  row (an assignment that lost its name server-side):
   *  a fresh name is minted and bound to the endpoint,
   *  and the record restores under it. */
  adoptNamelessOrphan(endpoint: string, caller: string, shape?: string): Promise<LeaseView>;
  /** The endpoint form of release, for a nameless census
   *  row: the endpoint is the unassign key. */
  releaseNamelessOrphan(endpoint: string): Promise<void>;
  releaseOrphan(session: string): Promise<void>;
  exec(session: string, job: string, caller: string): Promise<RunView>;
}

/* ---------- served catalog data (adapter-side, per venue) ---------- */

const VENUE_LABEL: Record<VenueId, string> = { colab: "Colab" };

/** One shape of the core's served specs portion, in the
 *  portion's own record shape (seed/specs.json). */
interface SpecRecord {
  id: string;
  label: string;
  gpu: string | null;
  tpu: string | null;
  high_mem: boolean;
  rate_cu_per_hour: number | null;
  agent_startable: boolean;
}
const SPEC_CATALOG: SpecRecord[] = (
  specsSeed as { specs: SpecRecord[] }
).specs.map((s) => ({ ...s }));

function specRecord(shape: string): SpecRecord | null {
  return SPEC_CATALOG.find((s) => s.id === shape) ?? null;
}

/** The catalog entry for a shape, with the core's own
 *  fallbacks for a shape the catalog does not carry: the
 *  label falls back to the id, the rate stays unconfirmed
 *  (null — projects nothing, never a fabricated cost). */
interface ShapeInfo {
  label: string;
  rateCuPerHour: number | null;
  spec: ShapeSpec;
}
export function shapeInfo(shape: string): ShapeInfo {
  const rec = specRecord(shape);
  if (rec) {
    return {
      label: rec.label,
      rateCuPerHour: rec.rate_cu_per_hour,
      spec: { gpu: rec.gpu, tpu: rec.tpu, high_mem: rec.high_mem },
    };
  }
  return {
    label: shape,
    rateCuPerHour: null,
    spec: { gpu: null, tpu: null, high_mem: false },
  };
}

/** The panel descriptor ("CPU · High-RAM" / "GPU · T4"):
 *  kind + shape, except that a CPU shape already named by
 *  the label is not repeated — the panel's own derivation,
 *  served display-ready. */
function specDescriptor(rec: SpecRecord): string {
  const kind = rec.gpu ? "GPU" : rec.tpu ? "TPU" : "CPU";
  const shape = rec.gpu || rec.tpu || (rec.high_mem ? "High-RAM" : "Standard");
  return !rec.gpu && !rec.tpu && shape === rec.label ? kind : `${kind} · ${shape}`;
}

function specView(rec: SpecRecord): SpecView {
  return {
    id: rec.id,
    label: rec.label,
    descriptor: specDescriptor(rec),
    spec: { gpu: rec.gpu, tpu: rec.tpu, high_mem: rec.high_mem },
    rateCuPerHour: rec.rate_cu_per_hour,
    rateLabel:
      rec.rate_cu_per_hour != null ? `${rec.rate_cu_per_hour} CU/h` : "Cost unconfirmed",
    agentStartable: rec.agent_startable,
  };
}

/** The shared duration set the pickers offer (the panel's
 *  one set for start, extend, shorten, and grant), plus a
 *  custom-hours input wherever it renders. Labels follow
 *  the panel's fmtDur, with 24 served as "24h". */
export const DURATION_OPTIONS: { hours: number; label: string }[] = [
  { hours: 1, label: "1h" },
  { hours: 2, label: "2h" },
  { hours: 4, label: "4h" },
  { hours: 8, label: "8h" },
  { hours: 12, label: "12h" },
  { hours: 16, label: "16h" },
  { hours: 24, label: "24h" },
  { hours: 48, label: "2d" },
  { hours: 72, label: "3d" },
];
export function fmtDurHours(hours: number): string {
  return hours >= 24 && hours % 24 === 0 ? `${hours / 24}d` : `${hours}h`;
}

/** The mock venue's standing shape (config standing.shape,
 *  absent → the plain CPU shape, the core's own default)
 *  and its config budget caps — the values a grant
 *  snapshots at grant time. Adapter-side config data, like
 *  the opening balance below. */
const STANDING_SHAPE = "cpu";
const CONFIG_CAPS = { daily: 250, monthly: 1000, standing_daily: 40 };

// Session display names are served by the adapter (the venue's
// session catalog), never derived in the frontend.
const SESSION_NAMES: Record<string, string> = {
  "cozy-pilot-61": "Cozy Pilot 61",
  "ember-comet-32": "Ember Comet 32",
  "storm-compass-26": "Storm Compass 26",
  "session-44": "Unnamed session 44",
  "session-52": "Unnamed session 52",
  "session-58": "Session 58",
  "session-39": "Session 39",
  "session-35": "Session 35",
};
const NAME_A = ["Amber", "Brave", "Calm", "Daring", "Eager", "Fleet", "Golden", "Harbor", "Ivory", "Juniper"];
const NAME_B = ["Falcon", "Voyager", "Compass", "Pilot", "Comet", "Lantern", "Summit", "Harbor", "Beacon", "Drift"];

/* ---------- formatting (served display-ready) ---------- */

const TZ = "America/New_York";
export function fmtTime(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: TZ,
  }).format(new Date(iso));
}

/** Served kind labels (labels are backend work; the frontend
 *  never maps a kind to its display word). */
export const KIND_LABEL: Record<EventKind, string> = {
  lease: "Lease",
  run: "Run",
  grant: "Grant",
  error: "Error",
  budget: "Budget",
};

/** Compact served date token ("Nov 13") for the LogRow column. */
export function fmtDateToken(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

/** Time with seconds, for the event drawer's Time fact. */
export function fmtTimeLong(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(iso));
}
export function fmtDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${String(m % 60).padStart(2, "0")}m`;
  }
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}
function fmtRemaining(ms: number): string {
  const mins = Math.max(0, Math.round(ms / 60000));
  const h = Math.floor(mins / 60);
  return `${h} h ${String(mins % 60).padStart(2, "0")} min left`;
}

/* ---------- the mock store + adapter ---------- */

const SEED_NOW = "2026-11-13T14:02:00-05:00";
/** In-flight run states — the pipeline's pruned-jobs rule
 *  (records.RUN_NONTERMINAL_STATES): an orphan's jobs list
 *  carries only jobs whose backing record is non-terminal. */
const NONTERMINAL_RUN_STATES = ["starting", "running", "polling"];
const OPENING_BALANCE_CU = 412; // the storyboard's served balance at seed

/** The orphans census's per-session derivation detail
 *  (V6), adapter-side served data like orphanSeenAt: the
 *  core derives it from renewal-config and the extension
 *  events; the record (SessionEvidence, a closed contract
 *  shape) never carries it. Conflict values ride raw —
 *  the projection formats timestamps as times, as the
 *  panel's orphanConflictValue does. */
interface OrphanDetailSeed {
  deadlineSource: string | null;
  deadlineStalePossible: boolean;
  conflicts: { field: string; values: { source: string; value: string }[] }[];
  handoverPending: boolean;
  creatorCaller: string | null;
  firstClaim: string | null;
  kitInstalled: boolean;
}

/** The listeners census + liveness stamps per lease
 *  (V7), adapter-side served data: the core serves the
 *  census keyed by session (state --part listeners) and
 *  the record carries the pulse result; a session with
 *  no entry serves no diagnostics (honest absence). */
interface LeaseDiagSeed {
  listeners: { port: number; pid: number; cwd: string; suspect: string[] }[];
  heartbeatAgeS: number | null;
  lastPulse: string | null;
  syncClaim: { caller: string; expiresAt: string } | null;
}

/** One account's budget state in the fake store (venue
 *  rework): the accounts the venue's config names, with the
 *  caps the budget editor writes. */
interface BudgetAccountState {
  venue: string;
  account: string;
  label: string;
  credential: BudgetAccountView["credential"];
  caps: BudgetCaps;
}

interface Store {
  budgetAccounts: BudgetAccountState[];
  leases: LeaseRecord[];
  runs: RunRecord[];
  evidence: Record<string, SessionEvidence>;
  journal: SpendSegment[];
  events: VenueEvent[];
  accessLog: AccessEntry[];
  callers: string[];
  grant: GrantRecord | null;
  resolvedOrphans: ResolvedOrphanView[];
  releasedSessions: Set<string>;
  deadlineNotified: Set<string>;
  orphanSeenAt: Record<string, string>;
  orphanDetail: Record<string, OrphanDetailSeed>;
  leaseDiag: Record<string, LeaseDiagSeed>;
  seededSegmentCount: number;
}

export class MockVenueAdapter implements VenueAdapter {
  private store: Store;
  private listeners = new Set<() => void>();
  private version = 0;
  private clockMs: number;
  private reachable = true;
  private lastSnapshot: Snapshot | null = null;
  private lastServedAt: string | null = null;
  private seq = 100;

  constructor() {
    this.clockMs = Date.parse(SEED_NOW);
    this.store = {
      // The venue's accounts (venue rework): the primary
      // account — the fake's one dialable credential — plus a
      // second account of the same adapter that is configured
      // but not brought in, so the per-account shape renders
      // honestly (no balance, no spend, its own caps).
      budgetAccounts: [
        {
          venue: "colab",
          account: "primary",
          label: "Primary",
          credential: "live",
          caps: { daily: 320, monthly: 5200, standingDaily: 48 },
        },
        {
          venue: "colab",
          account: "backup",
          label: "Backup",
          credential: "not-brought-in",
          caps: { daily: null, monthly: null, standingDaily: null },
        },
      ],
      leases: structuredClone(leasesSeed) as LeaseRecord[],
      runs: structuredClone(runsSeed) as RunRecord[],
      evidence: structuredClone(evidenceSeed) as Record<string, SessionEvidence>,
      journal: structuredClone(journalSeed) as SpendSegment[],
      events: structuredClone(eventsSeed) as VenueEvent[],
      accessLog: structuredClone(accessSeed) as AccessEntry[],
      callers: [...(callersSeed as { callers: string[] }).callers],
      grant: null,
      resolvedOrphans: [
        { session: "session-39", displayName: "Session 39", sub: "Adopted by beta-main · yesterday", label: "Adopted", tone: "ok" },
        { session: "session-35", displayName: "Session 35", sub: "Released · Monday", label: "Released", tone: "idle" },
      ],
      releasedSessions: new Set(),
      deadlineNotified: new Set(["storm-compass-26"]),
      // Session 44 was detected and marked at 1:36 PM (Access log);
      // session 52 was marked at 12:47 PM.
      orphanSeenAt: { "session-44": "2026-11-13T13:36:00-05:00", "session-52": "2026-11-13T12:47:00-05:00", "session-58": "2026-11-13T13:05:00-05:00" },
      // The orphans census's derivation detail (V6): session
      // 44's deadline derivation found its two sources in
      // conflict (the renewal config's value won); session
      // 52's deadline rides extension events alone and may
      // be stale; session 58 is a handover child.
      orphanDetail: {
        "session-44": {
          deadlineSource: "renewal config",
          deadlineStalePossible: false,
          conflicts: [
            {
              field: "deadline",
              values: [
                { source: "renewal config", value: "2026-11-13T23:36:00-05:00" },
                { source: "extension events", value: "2026-11-13T22:36:00-05:00" },
              ],
            },
          ],
          handoverPending: false,
          creatorCaller: "beta-main",
          firstClaim: "beta-main",
          kitInstalled: true,
        },
        "session-52": {
          deadlineSource: "extension events",
          deadlineStalePossible: true,
          conflicts: [],
          handoverPending: false,
          creatorCaller: null,
          firstClaim: null,
          kitInstalled: false,
        },
        "session-58": {
          deadlineSource: "renewal config",
          deadlineStalePossible: false,
          conflicts: [],
          handoverPending: true,
          creatorCaller: "alpha-thread",
          firstClaim: "workhorse",
          kitInstalled: true,
        },
      },
      // The listeners census + liveness stamps (V7): Cozy
      // Pilot carries a second listener whose cwd is
      // deleted (the census's suspect derivation flags
      // it); Ember Comet's session is under a sync claim;
      // Storm Compass's keepalive heartbeat is unreadable
      // and its last pulse timed out on a busy kernel.
      leaseDiag: {
        "cozy-pilot-61": {
          listeners: [
            { port: 8793, pid: 2411, cwd: "/content/workhorse", suspect: [] },
            { port: 6006, pid: 1877, cwd: "/content/legacy-serve (deleted)", suspect: ["deleted-cwd"] },
          ],
          heartbeatAgeS: 41,
          lastPulse: "ok",
          syncClaim: null,
        },
        "ember-comet-32": {
          listeners: [{ port: 8793, pid: 3120, cwd: "/content/workhorse", suspect: [] }],
          heartbeatAgeS: 63,
          lastPulse: "ok",
          syncClaim: { caller: "beta-main", expiresAt: "2026-11-13T14:20:00-05:00" },
        },
        "storm-compass-26": {
          listeners: [],
          heartbeatAgeS: null,
          lastPulse: "timeout — kernel busy",
          syncClaim: null,
        },
      },
      seededSegmentCount: (journalSeed as SpendSegment[]).length,
    };
    // The mock clock advances one minute every 15 s of wall time,
    // so deadlines, durations, and "seen … ago" stay live.
    setInterval(() => this.tick(), 15000);
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
    this.listeners.forEach((fn) => fn());
  }
  now(): string {
    return new Date(this.clockMs).toISOString();
  }

  private tick(): void {
    this.clockMs += 60000;
    // Deadline crossings surface exactly one renewal-due event.
    for (const lease of this.store.leases) {
      if (
        Date.parse(lease.deadline) <= this.clockMs &&
        !this.store.deadlineNotified.has(lease.session)
      ) {
        this.store.deadlineNotified.add(lease.session);
        this.pushEvent("lease", "warn", `${this.name(lease.session)} deadline passed — renewal due`);
      }
    }
    this.emit();
  }

  /* ----- helpers ----- */
  private name(session: string): string {
    if (SESSION_NAMES[session]) return SESSION_NAMES[session];
    const n = [...session].reduce((a, c) => a + c.charCodeAt(0), 0);
    const num = session.match(/(\d+)$/)?.[1] ?? String(40 + (n % 50));
    return `${NAME_A[n % NAME_A.length]} ${NAME_B[(n >> 3) % NAME_B.length]} ${num}`;
  }
  private pushEvent(kind: VenueEvent["kind"], tone: Tone, message: string): void {
    this.store.events.unshift({
      id: `ev-${++this.seq}`,
      at: this.now(),
      kind,
      tone,
      message,
      venue: "colab",
    });
  }
  private pushAccess(label: string, detail: string, chip?: AccessEntry["chip"]): void {
    this.store.accessLog.unshift({
      id: `al-${++this.seq}`,
      at: this.now(),
      label,
      detail,
      chip,
    });
  }
  private assertReachable(): void {
    if (!this.reachable) {
      throw new AdapterError("unreachable", "Lease server unreachable — state is frozen at the last served snapshot.");
    }
  }
  private assertCaller(caller: string): void {
    // Contract 01: a presented-but-unregistered caller is refused.
    const base = caller.split(":")[0];
    if (!this.store.callers.includes(base)) {
      throw new AdapterError("unregistered-caller", `Caller "${caller}" is not registered — the grant is refused.`);
    }
  }
  private liveSegmentStart(lease: LeaseRecord): number {
    // A live record's running segment starts at its last journal
    // seam for that session, else at acquire (contract 12).
    let start = Date.parse(lease.acquired_at);
    for (const seg of this.store.journal) {
      if (seg.session === lease.session) {
        start = Math.max(start, Date.parse(seg.end));
      }
    }
    return start;
  }
  private journalSegment(lease: LeaseRecord, endMs: number): void {
    const start = this.liveSegmentStart(lease);
    if (endMs <= start) return;
    this.store.journal.push({
      session: lease.session,
      shape: lease.shape,
      start: new Date(start).toISOString(),
      end: new Date(endMs).toISOString(),
      rate: lease.rate_cu_per_hour ?? shapeInfo(lease.shape).rateCuPerHour ?? 0,
      caller: lease.caller,
    });
  }

  /* ----- verbs ----- */

  async probe(): Promise<{ reachable: boolean; at: string }> {
    return { reachable: this.reachable, at: this.now() };
  }

  setReachable(reachable: boolean): void {
    this.reachable = reachable;
    if (!reachable) this.lastServedAt = this.now();
    this.emit();
  }

  async restartServer(): Promise<void> {
    await new Promise((r) => setTimeout(r, 700));
    this.reachable = true;
    this.pushEvent("lease", "info", "lease server restarted — service restored");
    this.emit();
  }

  registeredCallers(): string[] {
    return [...this.store.callers];
  }

  /** The active grant, on the core's own activity rule
   *  (grant_active: a record whose until is still ahead). */
  private activeGrant(): GrantRecord | null {
    const grant = this.store.grant;
    if (!grant || Date.parse(grant.until) <= this.clockMs) return null;
    return grant;
  }

  async acquire(input: AcquireInput): Promise<LeaseView> {
    this.assertReachable();
    this.assertCaller(input.caller);
    const info = shapeInfo(input.shape);
    // An unconfirmed rate projects nothing: the acquire is
    // not priced and reserves nothing, never a fabricated
    // cost (the venue's standing rule).
    const cost = info.rateCuPerHour != null ? info.rateCuPerHour * input.hours : 0;
    const budget = this.budget();
    if (info.rateCuPerHour != null && cost > budget.availableCu) {
      // The core journals a budget refusal in the outbox
      // (budget-refused) before the act fails.
      this.pushEvent("budget", "fail", `budget refused · acquire for ${input.caller} — ${cost} CU projected over ${budget.availableCu} CU available`);
      this.emit();
      throw new AdapterError(
        "insufficient-budget",
        `Acquire needs ${cost} CU but only ${budget.availableCu} CU is available (balance ${budget.balanceCu} CU, ${budget.reservedCu} CU reserved).`,
      );
    }
    // Envelope attribution (the core's acquire): an in-scope
    // acquire under an active grant carries the grant's id —
    // its granted_at — and prices against the snapshot.
    const grant = this.activeGrant();
    const inScope = grant !== null && grant.scope.shapes.includes(input.shape);
    // Placement (contract 12): latest-deadline adoption first —
    // a live lease at the requested shape is adopted, not duplicated.
    const pool = this.store.leases
      .filter((l) => l.shape === input.shape && Date.parse(l.deadline) > this.clockMs)
      .sort((a, b) => {
        const own = Number(b.caller === input.caller) - Number(a.caller === input.caller);
        if (own !== 0) return own;
        return Date.parse(b.deadline) - Date.parse(a.deadline);
      });
    if (pool.length > 0) {
      const adopted = pool[0];
      adopted.caller = input.caller;
      adopted.last_used_at = this.now();
      if (inScope && grant) adopted.envelope_id = grant.granted_at;
      this.syncEvidence(adopted);
      this.pushEvent("grant", "info", `lease adopted · ${this.name(adopted.session)} → ${input.caller} (${info.label})`);
      this.pushAccess("Ride granted", `${input.caller} → ${this.name(adopted.session)} · ${fmtTime(this.now())}`);
      this.emit();
      return this.leaseView(adopted);
    }
    const num = 40 + (this.seq % 55);
    const session = `${NAME_A[this.seq % NAME_A.length].toLowerCase()}-${NAME_B[(this.seq >> 2) % NAME_B.length].toLowerCase()}-${num}`;
    this.seq += 1;
    const lease: LeaseRecord = {
      session,
      venue: "colab",
      shape: input.shape,
      shape_spec: { ...info.spec },
      rate_cu_per_hour: info.rateCuPerHour,
      caller: input.caller,
      acquired_at: this.now(),
      deadline: new Date(this.clockMs + input.hours * 3600000).toISOString(),
      last_used_at: this.now(),
      jobs: [],
      budget_at_acquire: {
        balance_cu: this.currentBalance(),
        grant_hours: input.hours,
        reserved_cu: cost,
      },
      ...(inScope && grant ? { envelope_id: grant.granted_at } : {}),
    };
    this.store.leases.push(lease);
    this.syncEvidence(lease);
    this.pushEvent("grant", "info", `lease granted · ${this.name(session)} → ${input.caller} (${info.label})`);
    this.pushAccess("Ride granted", `${input.caller} → ${this.name(session)} · ${fmtTime(this.now())}`);
    this.emit();
    return this.leaseView(lease);
  }

  /**
   * Extend (POST /api/lease/extend): the deadline moves
   * later by the chosen hours — the core prices only the
   * delta (the lease's rate × hours) before anything
   * changes, and a refusal changes nothing. Refusals ride
   * the note, as the panel's notice line carries them:
   * standing-managed and refused-budget.
   */
  async extend(session: string, hours: number): Promise<{ lease: LeaseView; note: string }> {
    this.assertReachable();
    const lease = this.store.leases.find((l) => l.session === session);
    if (!lease) throw new AdapterError("no-lease", `No live lease record for ${session}.`);
    if (lease.standing && this.activeGrant()) {
      return {
        lease: this.leaseView(lease),
        note: "Extension refused: the standing lease is grant-managed — extend the grant instead.",
      };
    }
    const rate = lease.rate_cu_per_hour ?? shapeInfo(lease.shape).rateCuPerHour;
    if (rate != null) {
      const projected = Math.round(rate * hours * 100) / 100;
      if (projected > this.budget().availableCu) {
        this.pushEvent("budget", "fail", `budget refused · extension of ${this.name(session)} — ${projected} CU projected`);
        this.emit();
        return {
          lease: this.leaseView(lease),
          note: `Extension refused: budget refused (over cap, projected ${projected} CU).`,
        };
      }
    }
    lease.deadline = new Date(Date.parse(lease.deadline) + hours * 3600000).toISOString();
    lease.renew = true;
    // An operator extension is the latest action on the
    // deadline: it clears any operator shorten stamp.
    delete lease.shortened_at;
    delete lease.shortened_by;
    delete lease.shortened_from;
    this.store.deadlineNotified.delete(session);
    this.syncEvidence(lease);
    this.pushEvent("lease", "info", `lease extended · ${this.name(session)} — new deadline ${fmtTime(lease.deadline)}`);
    this.emit();
    return { lease: this.leaseView(lease), note: `Extended — new deadline ${fmtTime(lease.deadline)}.` };
  }

  /**
   * Shorten (POST /api/lease/shorten): extend's mirror —
   * the deadline moves earlier to the chosen target (a
   * pull-in by hours, or an absolute deadline), prices
   * nothing, and stamps the record; while the stamp stands
   * the extend guard defers, and a later operator extend
   * clears it. Refusals ride the note: a target that has
   * passed, one not earlier than the current deadline, and
   * the standing-managed lease.
   */
  async shorten(
    session: string,
    target: { hours: number } | { deadline: string },
  ): Promise<{ lease: LeaseView; note: string }> {
    this.assertReachable();
    const lease = this.store.leases.find((l) => l.session === session);
    if (!lease) throw new AdapterError("no-lease", `No live lease record for ${session}.`);
    if (lease.standing && this.activeGrant()) {
      return {
        lease: this.leaseView(lease),
        note: "Shorten refused: the standing lease is grant-managed — its deadline follows the grant.",
      };
    }
    const current = Date.parse(lease.deadline);
    const targetMs =
      "deadline" in target ? Date.parse(target.deadline) : current - target.hours * 3600000;
    if (Number.isNaN(targetMs) || targetMs >= current) {
      return {
        lease: this.leaseView(lease),
        note: "Shorten refused: that is not earlier than the current deadline — Extend moves it later.",
      };
    }
    if (targetMs <= this.clockMs) {
      return {
        lease: this.leaseView(lease),
        note: "Shorten refused: that target has already passed — Release ends the lease now.",
      };
    }
    const oldDeadline = lease.deadline;
    lease.deadline = new Date(targetMs).toISOString();
    lease.shortened_at = this.now();
    lease.shortened_by = "panel";
    lease.shortened_from = oldDeadline;
    this.syncEvidence(lease);
    this.pushEvent("lease", "info", `lease shortened · ${this.name(session)} — new deadline ${fmtTime(lease.deadline)}`);
    this.emit();
    return { lease: this.leaseView(lease), note: `Shortened — new deadline ${fmtTime(lease.deadline)}.` };
  }

  async release(session: string): Promise<void> {
    this.assertReachable();
    const idx = this.store.leases.findIndex((l) => l.session === session);
    if (idx < 0) throw new AdapterError("no-lease", `No live lease record for ${session}.`);
    const [lease] = this.store.leases.splice(idx, 1);
    // The segment ends at the seam; spend journals from the
    // record's own segments (contract 12), never balance deltas.
    this.journalSegment(lease, this.clockMs);
    delete this.store.evidence[session];
    this.store.releasedSessions.add(session);
    for (const run of this.store.runs) {
      if (run.session === session && (run.state === "running" || run.state === "starting")) {
        run.state = "orphaned";
        run.ended_at = this.now();
        run.terminal_event_state = "sent"; // exactly one run-terminal event
        this.pushEvent("run", "warn", `${run.job} orphaned — lease released (${this.name(session)})`);
      }
    }
    this.pushEvent("lease", "info", `lease released · ${this.name(session)} (${lease.caller ?? "unattributed"})`);
    this.emit();
  }

  /**
   * Grant (POST /api/grant): record a two-tier grant for
   * the chosen hours — its scope snapshots the sanctioned
   * shapes (the standing shape plus the chosen burst
   * shape) and the budget caps in force at grant time.
   * The snapshot is the authorization the tap granted:
   * later cap changes move future grants, never this one.
   */
  async startGrant(input: { hours: number; burst: string }): Promise<GrantView> {
    this.assertReachable();
    const standing = STANDING_SHAPE;
    const burst = input.burst;
    const shapes = standing === burst ? [standing] : [standing, burst];
    this.store.grant = {
      kind: "two-tier",
      granted_at: this.now(),
      until: new Date(this.clockMs + input.hours * 3600000).toISOString(),
      standing_shape: standing,
      burst_shape: burst,
      scope: {
        caps: { ...CONFIG_CAPS },
        standing_shape: standing,
        burst_shape: burst,
        shapes,
      },
    };
    this.pushEvent(
      "grant",
      "info",
      `two-tier grant started · until ${fmtTime(this.store.grant.until)} — burst ${shapeInfo(burst).label}`,
    );
    this.emit();
    return this.grantView()!;
  }

  /**
   * Extend grant (POST /api/grant/extend): the grant's
   * until moves later by the chosen hours. Only the
   * standing lease's delta is priced — against the
   * available budget here — and an absent or expired grant
   * refuses (grant-inactive): a new window is a new grant.
   */
  async extendGrant(hours: number): Promise<{ grant: GrantView | null; note: string }> {
    this.assertReachable();
    const grant = this.activeGrant();
    if (!grant) {
      return { grant: null, note: "Extension refused: no active grant to extend." };
    }
    const rate = shapeInfo(grant.standing_shape).rateCuPerHour;
    if (rate != null) {
      const projected = Math.round(rate * hours * 100) / 100;
      if (projected > this.budget().availableCu) {
        this.pushEvent("budget", "fail", `budget refused · grant extension — ${projected} CU projected`);
        this.emit();
        return {
          grant: this.grantView(),
          note: `Extension refused: budget refused (over cap, projected ${projected} CU).`,
        };
      }
    }
    grant.until = new Date(Date.parse(grant.until) + hours * 3600000).toISOString();
    this.pushEvent("grant", "info", `grant extended · until ${fmtTime(grant.until)}`);
    this.emit();
    return { grant: this.grantView(), note: `Grant extended — until ${fmtTime(grant.until)}.` };
  }

  /**
   * Ungrant (POST /api/ungrant): revoke the grant. The
   * envelope leases keep their attribution stamps — the
   * envelope is history — but no new acquire prices
   * against it.
   */
  async ungrant(): Promise<void> {
    this.assertReachable();
    if (!this.store.grant) return;
    this.store.grant = null;
    this.pushEvent("grant", "info", "two-tier grant revoked");
    this.emit();
  }

  /**
   * Access release (POST /api/access/release): one-tap
   * release of an unattributed session — the safety act
   * for a session nobody owns. A record-backed session is
   * refused here, exactly as the core refuses it: it
   * releases per its lease, from the lease's own surface.
   */
  async releaseAccess(session: string): Promise<void> {
    this.assertReachable();
    if (this.store.leases.some((l) => l.session === session)) {
      throw new AdapterError(
        "record-backed",
        `${this.name(session)} carries a lease record — release it from its lease, not from Access.`,
      );
    }
    if (!this.store.evidence[session]) {
      throw new AdapterError("no-session", `${session} is not a live session.`);
    }
    delete this.store.evidence[session];
    this.store.releasedSessions.add(session);
    this.store.resolvedOrphans.unshift({
      session,
      displayName: this.name(session).replace(/^Unnamed /, ""),
      sub: "Released · just now",
      label: "Released",
      tone: "idle",
    });
    this.pushEvent("lease", "info", `session released · ${this.name(session)}`);
    this.pushAccess("Session released", `${this.name(session)} · ${fmtTime(this.now())}`);
    this.emit();
  }

  /** The catalog shapes of the evidenced class — the
   *  orphans census's candidate list for a shape the
   *  evidence carries only as a class (V6). */
  private orphanCandidates(ev: SessionEvidence): OrphanShapeCandidate[] {
    const cls = this.shapeClass(ev.spec);
    return SPEC_CATALOG.filter(
      (rec) =>
        this.shapeClass({ gpu: rec.gpu, tpu: rec.tpu, high_mem: rec.high_mem }) === cls,
    ).map((rec) => {
      const v = specView(rec);
      return { id: v.id, label: v.label, rateLabel: v.rateLabel };
    });
  }

  /**
   * Adopt (POST /api/lease/adopt): the record is restored
   * from evidence — the evidenced shape, or the operator's
   * pick from the evidenced class's candidates — at the
   * derived deadline. The core's refusals, in its own
   * words: a handover child (its parent takes it over by
   * swap), a derived deadline already past or absent, a
   * class-ambiguous shape with no pick, a pick outside
   * the catalog, and a pick contradicting the evidence.
   */
  async adoptOrphan(session: string, caller: string, shape?: string): Promise<LeaseView> {
    this.assertReachable();
    this.assertCaller(caller);
    const ev = this.store.evidence[session];
    if (!ev || this.store.leases.some((l) => l.session === session)) {
      throw new AdapterError("no-orphan", `${session} is not an orphan session.`);
    }
    if (this.store.orphanDetail[session]?.handoverPending) {
      throw new AdapterError(
        "adopt-handover-pending",
        "Adoption refused: a handover child — its parent record takes it over by swap.",
      );
    }
    if (!ev.deadline) {
      throw new AdapterError(
        "adopt-no-deadline",
        "Adoption refused: no deadline evidence and none planted — adoption from the panel needs a derived deadline.",
      );
    }
    if (Date.parse(ev.deadline) <= this.clockMs) {
      throw new AdapterError(
        "adopt-deadline-past",
        "Adoption refused: the derived deadline has already passed — this orphan needs a planted deadline (CLI).",
      );
    }
    let resolved = ev.shape ?? undefined;
    if (resolved) {
      if (shape && shape !== resolved) {
        throw new AdapterError(
          "adopt-shape-conflict",
          "Adoption refused: the picked shape contradicts the evidenced shape.",
        );
      }
    } else {
      const candidates = this.orphanCandidates(ev);
      const pick = shape ?? (candidates.length === 1 ? candidates[0].id : undefined);
      if (!pick) {
        throw new AdapterError(
          "adopt-shape-ambiguous",
          "Adoption refused: the shape class matches several catalog shapes — pick the shape first.",
        );
      }
      if (!specRecord(pick)) {
        throw new AdapterError(
          "adopt-shape-unknown",
          "Adoption refused: the picked shape is not in the catalog.",
        );
      }
      if (!candidates.some((c) => c.id === pick)) {
        throw new AdapterError(
          "adopt-shape-conflict",
          "Adoption refused: the picked shape contradicts the evidenced shape class.",
        );
      }
      resolved = pick;
    }
    const info = shapeInfo(resolved);
    const lease: LeaseRecord = {
      session,
      venue: "colab",
      shape: resolved,
      shape_spec: { ...info.spec },
      rate_cu_per_hour: info.rateCuPerHour,
      caller,
      acquired_at: ev.acquired_at ?? this.now(),
      deadline: ev.deadline,
      last_used_at: this.now(),
      jobs: this.store.runs.filter((r) => r.session === session).map((r) => r.run_id),
      budget_at_acquire: {
        balance_cu: this.currentBalance(),
        grant_hours: 2,
        reserved_cu: info.rateCuPerHour != null ? info.rateCuPerHour * 2 : 0,
      },
    };
    this.store.leases.push(lease);
    this.store.resolvedOrphans.unshift({
      session,
      displayName: this.name(session).replace(/^Unnamed /, ""),
      sub: `Adopted by ${caller} · just now`,
      label: "Adopted",
      tone: "ok",
    });
    this.pushEvent("grant", "info", `orphan adopted · ${this.name(session)} → ${caller} (${info.label})`);
    this.pushAccess("Ride granted", `${caller} → ${this.name(session)} · ${fmtTime(this.now())}`);
    this.emit();
    return this.leaseView(lease);
  }

  async adoptNamelessOrphan(endpoint: string, caller: string, shape?: string): Promise<LeaseView> {
    this.assertReachable();
    this.assertCaller(caller);
    void shape;
    // The mock's census is name-keyed — every assignment
    // it models carries a usable name, so a nameless row
    // cannot arise in it and every endpoint is absent,
    // which is the core's own verdict for an endpoint the
    // server does not hold.
    throw new AdapterError("adopt-absent", `${endpoint} is not an orphan assignment.`);
  }

  async releaseNamelessOrphan(endpoint: string): Promise<void> {
    this.assertReachable();
    // The mock's census is name-keyed — see
    // adoptNamelessOrphan: a nameless row cannot arise
    // in it and every endpoint is absent, which is the
    // core's own verdict for an endpoint the server
    // does not hold.
    throw new AdapterError("release-absent", `${endpoint} is not an orphan assignment.`);
  }

  async releaseOrphan(session: string): Promise<void> {
    this.assertReachable();
    if (!this.store.evidence[session] || this.store.leases.some((l) => l.session === session)) {
      throw new AdapterError("no-orphan", `${session} is not an orphan session.`);
    }
    delete this.store.evidence[session];
    this.store.releasedSessions.add(session);
    this.store.resolvedOrphans.unshift({
      session,
      displayName: this.name(session).replace(/^Unnamed /, ""),
      sub: "Released · just now",
      label: "Released",
      tone: "idle",
    });
    this.pushEvent("lease", "info", `orphan released · ${this.name(session)}`);
    this.emit();
  }

  async exec(session: string, job: string, caller: string): Promise<RunView> {
    this.assertReachable();
    const lease = this.store.leases.find((l) => l.session === session);
    if (!lease) throw new AdapterError("no-lease", `No live lease record for ${session}.`);
    if (Date.parse(lease.deadline) <= this.clockMs) {
      // The storyboard's own error class: an expired lease refuses.
      this.pushEvent("error", "fail", `exec channel refused · lease deadline passed (${this.name(session)})`);
      this.emit();
      throw new AdapterError("lease-expired", "Exec refused — the lease deadline has passed; extend the lease first.");
    }
    const run: RunRecord = {
      run_id: `run-20261113-${String(++this.seq).padStart(4, "0")}`,
      job,
      session,
      venue: "colab",
      shape: lease.shape,
      caller,
      state: "running",
      started_at: this.now(),
      resumed: false,
    };
    this.store.runs.push(run);
    lease.jobs.push(run.run_id);
    lease.last_used_at = this.now();
    this.pushEvent("run", "info", `${job} started — caller ${caller}`);
    this.emit();
    // The mock venue completes the run a few seconds later.
    setTimeout(() => {
      if (run.state !== "running") return; // released meanwhile → already orphaned
      run.state = "complete";
      run.ended_at = this.now();
      run.terminal_event_state = "sent"; // exactly one run-terminal event
      this.pushEvent("run", "ok", `${job} passed (${fmtDuration(Date.parse(run.ended_at) - Date.parse(run.started_at))}) — ${this.name(session)}`);
      this.emit();
    }, 9000);
    return this.runView(run);
  }

  /* ----- projections ----- */

  private syncEvidence(lease: LeaseRecord): void {
    // write_session_evidence: refreshed on every lease save.
    this.store.evidence[lease.session] = {
      deadline: lease.deadline,
      acquired_at: lease.acquired_at,
      shape: lease.shape,
      spec: lease.shape_spec,
      caller: lease.caller ?? null,
      venue: lease.venue,
    };
  }

  private currentBalance(): number {
    // The seeded journal is spend already settled before the
    // storyboard's served balance; segments journaled since
    // (releases, seams) draw the balance down.
    let spent = 0;
    for (const seg of this.store.journal.slice(this.store.seededSegmentCount)) {
      spent += ((Date.parse(seg.end) - Date.parse(seg.start)) / 3600000) * seg.rate;
    }
    return Math.max(0, Math.round(OPENING_BALANCE_CU - spent));
  }

  private leaseView(lease: LeaseRecord): LeaseView {
    const expired = Date.parse(lease.deadline) <= this.clockMs;
    return {
      session: lease.session,
      displayName: this.name(lease.session),
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
        : `${fmtTime(lease.deadline)} · ${fmtRemaining(Date.parse(lease.deadline) - this.clockMs)}`,
      rateCuPerHour: lease.rate_cu_per_hour,
      reservedCu: expired ? 0 : (lease.budget_at_acquire?.reserved_cu ?? 0),
      envelopeId: lease.envelope_id,
      diagnostics: this.diagnosticsView(lease),
    };
  }

  /** The lease card's diagnostics (V7): the listeners
   *  census lines with their suspect flags, the keepalive
   *  heartbeat age ("unknown" when the census cannot read
   *  it — the panel's own word), the last pulse result,
   *  the burn rate, and the sync claim when one is live.
   *  A session the census does not carry serves null. */
  private diagnosticsView(lease: LeaseRecord): LeaseDiagnosticsView | null {
    const seed = this.store.leaseDiag[lease.session];
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

  private runView(run: RunRecord): RunView {
    const end = run.ended_at ? Date.parse(run.ended_at) : this.clockMs;
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
      sessionName: run.session ? this.name(run.session) : "—",
      caller: run.caller ?? null,
      state: run.state,
      stateLabel: l.label,
      stateTone: l.tone,
      startedAt: run.started_at,
      durationLabel: fmtDuration(end - Date.parse(run.started_at)),
      venue: run.venue,
    };
  }

  private budget(): BudgetView {
    const dayStart = new Date(this.now());
    dayStart.setHours(0, 0, 0, 0);
    const monthStart = new Date(this.now());
    monthStart.setDate(1);
    monthStart.setHours(0, 0, 0, 0);
    let used = 0;
    let usedMonth = 0;
    const byCaller = new Map<string, number>();
    for (const seg of this.store.journal) {
      const cu = ((Date.parse(seg.end) - Date.parse(seg.start)) / 3600000) * seg.rate;
      if (Date.parse(seg.start) >= monthStart.getTime()) usedMonth += cu;
      if (Date.parse(seg.start) < dayStart.getTime()) continue;
      used += cu;
      if (seg.caller) byCaller.set(seg.caller, (byCaller.get(seg.caller) ?? 0) + cu);
    }
    const reserved = this.store.leases
      .map((l) => this.leaseView(l).reservedCu)
      .reduce((a, b) => a + b, 0);
    const balanceCu = this.currentBalance();
    const usedTodayCu = Math.round(used);
    const days = usedTodayCu > 0 ? Math.floor(balanceCu / usedTodayCu) : 0;
    // The fake's leases all ride the primary account (the one
    // live credential); the other accounts' figures are their
    // own — zero spend, and a null balance until the account
    // is brought in and can be dialed.
    const primary = this.store.budgetAccounts.find((a) => a.credential === "live") ?? this.store.budgetAccounts[0];
    const capHeadroom = primary.caps.daily != null ? Math.max(0, primary.caps.daily - usedTodayCu) : Infinity;
    const accounts: BudgetAccountView[] = this.store.budgetAccounts.map((a) => {
      const isPrimary = a === primary;
      return {
        venue: a.venue,
        account: a.account,
        label: a.label,
        balanceCu: isPrimary ? balanceCu : null,
        usedTodayCu: isPrimary ? usedTodayCu : 0,
        usedMonthCu: isPrimary ? Math.round(usedMonth) : 0,
        standingUsedTodayCu: isPrimary ? Math.round(byCaller.get("standing") ?? 0) : null,
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
    };
  }

  async setBudgetCaps(input: { venue: string; account: string; caps: BudgetCaps }): Promise<BudgetCaps> {
    this.assertReachable();
    const entry = this.store.budgetAccounts.find(
      (a) => a.venue === input.venue && a.account === input.account,
    );
    if (!entry) {
      throw new AdapterError(
        "unknown-account",
        `No ${input.account} account is configured for the ${input.venue} venue.`,
      );
    }
    // The core's own validation, mirrored: a cap is a
    // non-negative number or null (no cap).
    for (const [name, value] of Object.entries(input.caps)) {
      if (value !== null && (!Number.isFinite(value) || value < 0)) {
        throw new AdapterError("caps-invalid", `${name} cap must be a non-negative number or null`);
      }
    }
    entry.caps = { ...input.caps };
    const fmt = (v: number | null) => (v == null ? "no cap" : `${v} CU`);
    this.pushEvent(
      "budget",
      "info",
      `budget caps changed · ${entry.label} (${entry.account}) — daily ${fmt(entry.caps.daily)}, monthly ${fmt(entry.caps.monthly)}, standing ${fmt(entry.caps.standingDaily)}`,
    );
    this.emit();
    return { ...entry.caps };
  }

  private callers(): CallerView[] {
    return this.store.callers.map((caller) => {
      const lease = this.store.leases.find((l) => l.caller === caller);
      if (!lease) {
        return { caller, stateLabel: "Registered", stateTone: "idle" as Tone, sub: "No live session" };
      }
      const view = this.leaseView(lease);
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

  private knownSessions(): string[] {
    return [
      ...new Set([
        ...Object.keys(SESSION_NAMES),
        ...this.store.leases.map((l) => l.session),
        ...Object.keys(this.store.evidence),
      ]),
    ];
  }

  /** The session whose served display name appears in the
   *  text (longest match wins), or null. */
  private sessionNamedIn(text: string): string | null {
    let best: string | null = null;
    for (const session of this.knownSessions()) {
      const n = this.name(session);
      if (text.includes(n) && (!best || n.length > this.name(best).length)) best = session;
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
  private splitEventMessage(message: string): {
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
      const named = this.knownSessions().find((s) => this.name(s) === inner) ?? null;
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
        const named = this.knownSessions().find((s) => this.name(s) === tail) ?? null;
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
    if (!entitySession) entitySession = this.sessionNamedIn(headline);
    if (meta === undefined && entitySession) {
      const lease = this.store.leases.find((l) => l.session === entitySession);
      if (lease?.caller) meta = `held by ${lease.caller}`;
    }
    return { headline, meta, entitySession };
  }

  private eventEntity(session: string): EventView["detail"]["entity"] {
    const lease = this.store.leases.find((l) => l.session === session);
    const ev = this.store.evidence[session];
    const caller = lease?.caller ?? ev?.caller ?? null;
    const shape = lease?.shape ?? ev?.shape ?? null;
    if (!caller && !shape) return undefined;
    const parts = ["Lease"];
    if (caller) parts.push(`held by ${caller}`);
    if (shape) parts.push(shapeInfo(shape).label);
    return {
      groupLabel: "Session",
      session,
      title: this.name(session),
      sub: parts.join(" · "),
    };
  }

  /** The event drawer facts lead with the day relation, as
   *  frame B3 draws it ("Today · 1:12:00 PM"). */
  private fmtDayTime(iso: string): string {
    const sameDay =
      new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(
        new Date(iso),
      ) ===
      new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(
        new Date(this.clockMs),
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
  accessLogView(a: AccessEntry): AccessLogView {
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

  /** The day band's label, relative to the venue clock:
   *  Today / Yesterday / the weekday + date token. */
  private dayLabel(iso: string): string {
    const key = this.dayKey(iso);
    if (key === this.dayKey(this.now())) return "Today";
    const yesterday = new Date(this.clockMs - 86400000).toISOString();
    if (key === this.dayKey(yesterday)) return "Yesterday";
    const weekday = new Intl.DateTimeFormat("en-US", {
      timeZone: TZ,
      weekday: "short",
    }).format(new Date(iso));
    return `${weekday}, ${fmtDateToken(iso)}`;
  }

  eventView(e: VenueEvent): EventView {
    const kindLabel = KIND_LABEL[e.kind];
    const { headline, meta, entitySession } = this.splitEventMessage(e.message);
    const entity = entitySession ? this.eventEntity(entitySession) : undefined;
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
      dayKey: this.dayKey(e.at),
      dayLabel: this.dayLabel(e.at),
      raw: JSON.stringify(
        { id: e.id, at: e.at, kind: e.kind, tone: e.tone, message: e.message, venue: e.venue },
        null,
        2,
      ),
      detail: {
        message: e.message,
        facts: [
          { label: "Time", value: this.fmtDayTime(e.at), mono: true },
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
  private grantView(): GrantView | null {
    const grant = this.activeGrant();
    if (!grant) return null;
    const leases = this.store.leases.filter((l) => l.envelope_id === grant.granted_at);
    const sessions = new Set(leases.map((l) => l.session));
    const dayStart = new Date(this.now());
    dayStart.setHours(0, 0, 0, 0);
    const monthStart = new Date(this.now());
    monthStart.setDate(1);
    monthStart.setHours(0, 0, 0, 0);
    let day = 0;
    let month = 0;
    for (const seg of this.store.journal) {
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
        displayName: this.name(l.session),
        shapeLabel: shapeInfo(l.shape).label,
        caller: l.caller ?? null,
        deadlineLabel: fmtTime(l.deadline),
      })),
    };
  }

  /** A catalog entry's shape class, the gate's own rule:
   *  an accelerator is its own class even with high_mem. */
  private shapeClass(spec: ShapeSpec | null): string {
    if (spec?.gpu) return "gpu";
    if (spec?.tpu) return "tpu";
    return spec?.high_mem ? "high_ram" : "standard";
  }

  /** The served access list: every live session with its
   *  attribution — record-backed sessions carry their
   *  record's caller; evidence-only sessions with no caller
   *  on their evidence are unattributed and carry the
   *  release. */
  private accessView(): AccessSessionView[] {
    const CLASS_LABEL: Record<string, string> = {
      gpu: "GPU",
      tpu: "TPU",
      high_ram: "High-RAM",
      standard: "Standard",
    };
    const out: AccessSessionView[] = [];
    for (const lease of this.store.leases) {
      const cls = this.shapeClass(lease.shape_spec);
      out.push({
        session: lease.session,
        displayName: this.name(lease.session),
        shapeClass: cls,
        caller: lease.caller ?? null,
        firstSeen: lease.acquired_at,
        sub: `${CLASS_LABEL[cls] ?? cls} shape · since ${fmtTime(lease.acquired_at)}`,
        unattributed: false,
      });
    }
    for (const [session, ev] of Object.entries(this.store.evidence)) {
      if (this.store.leases.some((l) => l.session === session)) continue;
      const cls = this.shapeClass(ev.spec);
      const firstSeen = ev.acquired_at ?? this.now();
      out.push({
        session,
        displayName: this.name(session),
        shapeClass: cls,
        caller: ev.caller,
        firstSeen,
        sub: `${CLASS_LABEL[cls] ?? cls} shape · since ${fmtTime(firstSeen)}`,
        unattributed: ev.caller == null,
      });
    }
    return out.sort((a, b) => Date.parse(a.firstSeen) - Date.parse(b.firstSeen));
  }

  snapshot(): Snapshot {
    if (!this.reachable && this.lastSnapshot) {
      // Degraded: serve the last known state, frozen (frame 8).
      return { ...this.lastSnapshot, degraded: true, lastServedAt: this.lastServedAt };
    }
    const leases = this.store.leases
      .map((l) => this.leaseView(l))
      .sort((a, b) => Date.parse(a.deadline) - Date.parse(b.deadline));
    const runsBySession: Record<string, RunView[]> = {};
    for (const run of this.store.runs) {
      if (!run.session) continue;
      (runsBySession[run.session] ??= []).push(this.runView(run));
    }
    for (const k of Object.keys(runsBySession)) {
      runsBySession[k].sort((a, b) => Date.parse(b.startedAt) - Date.parse(a.startedAt));
    }
    const recentRuns = [...this.store.runs]
      .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
      .slice(0, 3)
      .map((r) => this.runView(r));
    const orphans: OrphanView[] = Object.entries(this.store.evidence)
      .filter(([session]) => !this.store.leases.some((l) => l.session === session))
      .map(([session, ev]) => {
        const seenAt = this.store.orphanSeenAt[session];
        const seenMin = seenAt
          ? Math.max(1, Math.round((this.clockMs - Date.parse(seenAt)) / 60000))
          : 0;
        const runs = this.store.runs.filter((r) => r.session === session).length;
        // E4: the orphan's in-flight jobs, served with the
        // census — non-terminal backing records only, oldest
        // first, in the same view form the census's entries
        // take (the mock's records carry the job's name; the
        // label is that name).
        const jobs: OrphanJobView[] = this.store.runs
          .filter((r) => r.session === session && NONTERMINAL_RUN_STATES.includes(r.state))
          .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at))
          .map((r) => {
            const v = this.runView(r);
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
        const detail = this.store.orphanDetail[session];
        const evidenced = ev.shape != null;
        const cls = this.shapeClass(ev.spec);
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
          displayName: this.name(session),
          venue: "colab" as VenueId,
          venueLabel: VENUE_LABEL.colab,
          shapeLabel: shapeDescriptor,
          sub: `${shapeDescriptor} · seen ${seenMin} min ago · ${runs === 0 ? "no run records" : `${runs} run record${runs > 1 ? "s" : ""}`}`,
          firstSeenLabel: fmtTime(seenAt ?? ev.acquired_at ?? this.now()),
          acquiredLabel: ev.acquired_at ? fmtTime(ev.acquired_at) : null,
          kitInstalled: detail?.kitInstalled ?? false,
          shapeEvidenced: evidenced,
          shapeClassLabel: ev.spec ? (CLASS_LABEL[cls] ?? cls) : null,
          shapeCandidates: evidenced ? [] : this.orphanCandidates(ev),
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
          deadlinePast: ev.deadline !== null && Date.parse(ev.deadline) <= this.clockMs,
          deadlineTone: "warn" as Tone,
          jobs,
        };
      });
    const snap: Snapshot = {
      now: this.now(),
      degraded: false,
      lastServedAt: null,
      leases,
      recentRuns,
      runsBySession,
      orphans,
      resolvedOrphans: this.store.resolvedOrphans,
      events: this.store.events.map((e) => this.eventView(e)),
      budget: this.budget(),
      callers: this.callers(),
      accessLog: this.store.accessLog.map((a) => this.accessLogView(a)),
      specs: SPEC_CATALOG.map((rec) => specView(rec)),
      grant: this.grantView(),
      access: this.accessView(),
      runningCount: leases.filter((l) => l.state === "running").length,
    };
    this.lastSnapshot = snap;
    return snap;
  }
}
