// The mock adapter: the stateful MockVenueAdapter — the
// store, the mock clock, the subscription plumbing, and
// the D1 verbs with their pinned semantics. The catalog
// data, formatting, seed, and projections live in the
// sibling modules (catalog / format / mock-seed /
// mock-projections); this class delegates to them.

import type {
  AccessEntry,
  AccessLogView,
  AcquireInput,
  BudgetCaps,
  BudgetView,
  EventView,
  GrantRecord,
  GrantView,
  LeaseRecord,
  LeaseView,
  OrphanShapeCandidate,
  RunRecord,
  RunView,
  SessionEvidence,
  Snapshot,
  Tone,
  VenueEvent,
} from "../types";
import { AdapterError } from "../types";
import type { VenueAdapter } from "./interface";
import {
  CONFIG_CAPS,
  NAME_A,
  NAME_B,
  SESSION_NAMES,
  STANDING_SHAPE,
  shapeInfo,
  specRecord,
} from "./catalog";
import { fmtDuration, fmtTime } from "./format";
import { SEED_NOW, createSeedStore } from "./mock-seed";
import type { Store } from "./mock-seed";
import {
  activeGrant,
  accessLogView,
  budget,
  composeSnapshot,
  currentBalance,
  eventView,
  grantView,
  leaseView,
  orphanCandidates,
  runView,
  syncEvidence,
} from "./mock-projections";
import type { MockContext } from "./mock-projections";

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
    this.store = createSeedStore();
    // The mock clock advances one minute every 15 s of wall time,
    // so deadlines, durations, and "seen … ago" stay live.
    setInterval(() => this.tick(), 15000);
  }

  /* ----- projection delegation ----- */

  private context(): MockContext {
    return {
      store: this.store,
      clockMs: this.clockMs,
      now: () => this.now(),
      name: (session: string) => this.name(session),
    };
  }
  private syncEvidence(lease: LeaseRecord): void {
    syncEvidence(this.context(), lease);
  }
  private leaseView(lease: LeaseRecord): LeaseView {
    return leaseView(this.context(), lease);
  }
  private runView(run: RunRecord): RunView {
    return runView(this.context(), run);
  }
  private currentBalance(): number {
    return currentBalance(this.context());
  }
  private budget(): BudgetView {
    return budget(this.context());
  }
  private grantView(): GrantView | null {
    return grantView(this.context());
  }
  private activeGrant(): GrantRecord | null {
    return activeGrant(this.context());
  }
  private orphanCandidates(ev: SessionEvidence): OrphanShapeCandidate[] {
    return orphanCandidates(this.context(), ev);
  }
  accessLogView(a: AccessEntry): AccessLogView {
    return accessLogView(this.context(), a);
  }
  eventView(e: VenueEvent): EventView {
    return eventView(this.context(), e);
  }

  snapshot(): Snapshot {
    if (!this.reachable && this.lastSnapshot) {
      // Degraded: serve the last known state, frozen (frame 8).
      return { ...this.lastSnapshot, degraded: true, lastServedAt: this.lastServedAt };
    }
    const snap = composeSnapshot(this.context());
    this.lastSnapshot = snap;
    return snap;
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
}
