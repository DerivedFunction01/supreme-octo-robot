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
//
// Split along its seams (served shapes / transport /
// mapping); the class below keeps the transport and the
// verbs, and delegates the projections to the
// live-adapter/ modules. This module's public surface is
// unchanged (see the live-adapter.ts barrel).

import type {
  AcquireInput,
  BudgetCaps,
  BudgetView,
  CallerView,
  GrantView,
  LeaseView,
  RunView,
  Snapshot,
} from "../types";
import { AdapterError } from "../types";
import type { VenueAdapter } from "../adapter";
import { fmtTime } from "../adapter/format";
import { liveSessionName, num, str } from "./helpers";
import type { FetchLike, Parts, ServedLeaseRecord, ServedRecordEntry } from "./served";
import {
  accessViews,
  budgetView,
  callerViews,
  grantView,
  leaseView,
  orphanViews,
  recordEntries,
  runViews,
  specViews,
} from "./projections";
import type { LiveContext } from "./projections";
import { accessLogViews, eventViews, resolvedOrphanViews } from "./events";

/** One portion's fetch bound. The records portion's state
 *  build is the surface's slowest (tens of seconds under
 *  load); the bound exists so a wedged request fails and
 *  the next poll retries, never so a slow one is cut. */
const FETCH_TIMEOUT_MS = 150000;

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


  /* ----- projection delegation ----- */

  private context(): LiveContext {
    return { parts: this.parts, now: () => this.now() };
  }
  private recordEntries(): (ServedRecordEntry & { record: ServedLeaseRecord })[] {
    return recordEntries(this.context());
  }
  private leaseView(entry: ServedRecordEntry & { record: ServedLeaseRecord }): LeaseView {
    return leaseView(this.context(), entry);
  }
  private budgetView(): BudgetView {
    return budgetView(this.context());
  }
  private grantView(): GrantView | null {
    return grantView(this.context());
  }
  private callerViews(): CallerView[] {
    return callerViews(this.context());
  }
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

  registeredCallers(): string[] {
    return this.callerViews().map((c) => c.caller);
  }

  snapshot(): Snapshot {
    if (this.cachedSnapshot) return this.cachedSnapshot;
    const ctx = this.context();
    const entries = recordEntries(ctx);
    const leases = entries
      .map((e) => leaseView(ctx, e))
      .sort((a, b) => Date.parse(a.deadline) - Date.parse(b.deadline));
    const runs = runViews(ctx);
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
      orphans: orphanViews(ctx),
      resolvedOrphans: resolvedOrphanViews(ctx),
      events: eventViews(ctx),
      budget: this.budgetView(),
      callers: this.callerViews(),
      accessLog: accessLogViews(ctx),
      specs: specViews(ctx),
      grant: this.grantView(),
      access: accessViews(ctx),
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
