// Runner view model — the panel of record's served contracts
// and pure helpers, ported from the restored original
// (client/pages/runner: app.js, logs.js, orphans.js, poll.js).
// The server actions return the backend JSON verbatim inside
// the common envelope {status, payload, error}; the payload
// shapes below are the panel's own contracts, read exactly
// as the panel read them. Nothing here invents a field.
//
// State portions and their poll cadences (app.js PARTS):
// records 15s · specs 60s · budget 30s · grant 60s ·
// orphans 15s · listeners 60s · outbox 15s.

export interface RawEnvelope {
  status: number;
  payload: unknown;
  error: string | null;
}

export interface Spec {
  id: string;
  label?: string;
  gpu?: string | null;
  tpu?: string | null;
  high_mem?: boolean;
  rate_cu_per_hour?: number | null;
}

export interface LeaseRecord {
  session?: string;
  shape?: string;
  caller?: string;
  deadline?: string | null;
  standing?: boolean;
  last_pulse_result?: string | null;
  /** Served on some records; the panel never rendered it. */
  acquired_at?: string;
}

export interface LeaseEntry {
  session?: string;
  record?: LeaseRecord;
  action?: string;
  channel?: { verdict?: string };
  keepalive_heartbeat_age_s?: number | null;
  sync_claim?: { caller?: string; expires_at?: string } | null;
  /** The served lease card (Step 1 of the lease-card
   *  unification): every records entry with a deadline
   *  carries one. The lease views render it as served —
   *  no client-side lease derivation beside it. */
  card?: LeaseCard | null;
}

/** One verb's served capability: whether the lease core
 *  would accept the action on this lease, and the reason
 *  class where it would refuse. The lease views disable
 *  from it (Step 4 of the unification): a not-applicable
 *  action renders disabled, never removed. */
export interface LeaseCardCapability {
  applicable: boolean;
  reason: string | null;
}

/** One verb's capability on a lease's card, or null
 *  where the card serves none (an entry without a card,
 *  or a card served before the verb joined the set):
 *  no served statement disables nothing — the core's
 *  refusal remains the backstop. */
export function leaseCapability(
  card: LeaseCard | null | undefined,
  verb: string,
): LeaseCardCapability | null {
  return card?.capabilities?.[verb] ?? null;
}

export interface LeaseCardDiagnostics {
  heartbeat_label: string;
  pulse_label?: string | null;
  burn_label: string;
  sync_claim: { caller?: string | null; until_label: string } | null;
}

/** The served lease card, exactly as the backend's card
 *  assembly serves it (snake_case, verbatim): identity,
 *  state, deadline presentation, rate, diagnostics and
 *  the capability set — all labels derived server-side. */
export interface LeaseCard {
  session?: string | null;
  display_name: string;
  venue: string;
  venue_label: string;
  target?: string | null;
  shape?: string | null;
  shape_label?: string | null;
  shape_descriptor: string;
  caller?: string | null;
  account?: string | null;
  state: string;
  state_label: string;
  state_tone: string;
  action?: string | null;
  standing: boolean;
  acquired_at?: string | null;
  /** The acquired stamp's served label (the card's
   *  fmt_time form), or null when the stamp is absent
   *  or unparseable — honest absence: the detail's
   *  Acquired row renders the label, never a
   *  client-side formatting of the raw stamp. */
  acquired_label: string | null;
  deadline?: string | null;
  deadline_label: string;
  ends_label: string;
  expired: boolean;
  remaining_ms: number;
  remaining_label: string;
  rate_cu_per_hour?: number | null;
  rate_label: string;
  reserved_cu: number;
  envelope_id?: string | null;
  diagnostics: LeaseCardDiagnostics | null;
  capabilities: Record<string, LeaseCardCapability>;
}

export interface AccessEntry {
  session?: string;
  shape_class?: string;
  caller?: string | null;
  first_seen?: string;
  unattributed?: boolean;
}

export interface RecordsPayload {
  records?: LeaseEntry[];
  access?: AccessEntry[];
}

export interface SpecsPayload {
  specs?: Spec[];
}

export interface BudgetCaps {
  daily?: number | null;
  monthly?: number | null;
  standing_daily?: number | null;
}

/** One budget's figures: a balance, the day/month spend
 *  attributed to it, and its own caps. Every field is the
 *  backend's served number or null (honest absence — a figure
 *  the backend cannot serve is null, never zero). */
export interface BudgetFigures {
  balance?: number | null;
  day_spent?: number | null;
  month_spent?: number | null;
  standing_day_spent?: number | null;
  caps?: BudgetCaps;
}

/** A per-account entry of the budget snapshot: the account's
 *  identity plus its own figures. */
export interface BudgetAccountFigures extends BudgetFigures {
  venue: string;
  account: string;
  label: string;
  credential?: string | null;
}

/** One entry of the served budget set (FU-2): budgets are per
 *  venue and per account, never one mass. A budgeted entry
 *  carries its (venue, account) identity and its own figures;
 *  a budget-less venue kind (a local machine venue — unmetered,
 *  unlimited) carries the venue alone with budget: null, and
 *  renders as nothing budget-shaped at all. */
export interface BudgetEntry {
  venue: string;
  account?: string;
  label?: string;
  credential?: string | null;
  budget: BudgetFigures | null;
}

export interface BudgetPayload {
  venue?: string;
  /** The home venue's snapshot (compat projection): its
   *  top-level figures are the primary account's, and its
   *  accounts array carries every home-venue account. */
  budget?: BudgetFigures & { accounts?: BudgetAccountFigures[] };
  /** The budget set of record, spanning every venue the
   *  config names. */
  budgets?: BudgetEntry[];
}

export interface GrantPayload {
  grant?: {
    until?: string;
    scope?: { burst_shape?: string };
  } | null;
  envelope?: {
    caps?: BudgetCaps;
    records?: Array<{ shape?: string; caller?: string; deadline?: string }>;
    spend?: { day_spent?: number | null; month_spent?: number | null };
  } | null;
}

export interface OrphanConflict {
  field: string;
  values?: Array<{ source: string; value: unknown }>;
}

export interface Orphan {
  session?: string;
  first_seen?: string;
  acquired_at?: string;
  jobs_in_flight?: number;
  jobs_in_flight_entries?: Array<{
    id: string;
    kind: string;
    state: string;
    started_at?: string;
  }>;
  kit_installed?: boolean;
  shape_evidenced?: boolean;
  shape?: string;
  shape_class?: string;
  shape_candidates?: string[];
  creator_caller?: string;
  first_claim?: string;
  derived_deadline?: string | null;
  deadline_source?: string;
  deadline_stale_possible?: boolean;
  conflicts?: OrphanConflict[];
  handover_pending?: boolean;
}

export interface OrphansPayload {
  orphans?: Orphan[];
}

export interface ListenerEntry {
  port: number;
  pid: number;
  cwd?: string;
  suspect?: string[];
}

export interface ListenersPayload {
  listeners?: Record<
    string,
    { error?: string; listeners?: ListenerEntry[] } | null
  >;
}

export interface LogEvent {
  seq: number;
  ts: string;
  kind: string;
  detail?: Record<string, unknown>;
}

export interface OutboxPayload {
  events?: LogEvent[];
}

/** Per-part poll cadences (ms), the panel's PARTS table. */
export const PART_CADENCE: Record<string, number> = {
  records: 15000,
  specs: 60000,
  budget: 30000,
  grant: 60000,
  orphans: 15000,
  listeners: 60000,
  logs: 15000,
};

/** The shared duration set for the extend / shorten pickers. */
export const EXT_DURATIONS = [1, 2, 4, 8, 12, 16, 24, 48, 72];

/* ---------------- formatting (panel helpers) ---------------- */

export function fmtNum(v: unknown): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return String(Math.round(Number(v) * 100) / 100);
}

export function fmtTime(iso: string | undefined | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function fmtClock(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
}

export function fmtDur(hours: number): string {
  const h = Number(hours);
  if (!Number.isFinite(h)) return "—";
  return h >= 24 && h % 24 === 0 ? `${h / 24}d` : `${h}h`;
}

/** Countdown to a served deadline, minute-granular.
 *  Non-card duties only (the orphans view): the lease
 *  card family renders the served remaining_label. */
export function countdownText(iso: string | undefined | null, now: number): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - now;
  if (Number.isNaN(ms)) return "—";
  if (ms <= 0) return "expired";
  const mins = Math.round(ms / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h left`;
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}m left` : `${m}m left`;
}

/** Age of a served timestamp, in countdownText's grammar
 *  without the "left" (orphans.js fmtAge). */
export function fmtAge(iso: string | undefined | null, now: number): string {
  if (!iso) return "—";
  const ms = now - new Date(iso).getTime();
  if (Number.isNaN(ms) || ms < 0) return "—";
  const mins = Math.round(ms / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`;
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

/** "3m ago" / "2h ago" — logs.js fmtAge. */
export function fmtAgeAgo(iso: string, now: number): string {
  const s = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function capText(v: number | null | undefined): string {
  return v == null ? "no cap" : `${fmtNum(v)} CU`;
}

/* ---------------- specs ---------------- */

export function specById(specs: Spec[], id: string | undefined | null): Spec | null {
  if (!id) return null;
  return specs.find((s) => s.id === id) || null;
}

export function specLabel(specs: Spec[], id: string | undefined | null): string {
  const spec = specById(specs, id);
  return spec ? spec.label || spec.id : id || "—";
}

export function specDescriptor(spec: Spec): string {
  const kind = spec.gpu ? "GPU" : spec.tpu ? "TPU" : "CPU";
  const shape = spec.gpu || spec.tpu || (spec.high_mem ? "High-RAM" : "Standard");
  return !spec.gpu && !spec.tpu && shape === (spec.label || spec.id)
    ? kind
    : `${kind} · ${shape}`;
}

export function specTitle(spec: Spec): string {
  return `${spec.label || spec.id} · ${specDescriptor(spec)}`;
}

export function specRateText(spec: Spec): string {
  return spec.rate_cu_per_hour != null
    ? `${fmtNum(spec.rate_cu_per_hour)} CU/h`
    : "Cost unconfirmed";
}

/* ---------------- verdict refusal texts (panel tables) ---------------- */

/** A capability's served reason class in plain voice —
 *  the form a disabled control states (the ArmConfirm
 *  disabledReason idiom). The vocabulary is the card
 *  assembly's closed set; an unknown class states
 *  nothing rather than echoing the class string. */
export function capabilityReasonText(reason: string | null): string | null {
  switch (reason) {
    case "grant-managed":
      return "the standing lease is grant-managed";
    case "venue":
      return "this venue registers its sessions directly";
    case "unserved":
      return "no route serves this action";
    default:
      return null;
  }
}

export function extendRefusalText(res: Record<string, unknown>): string {
  const budget = (res.budget ?? {}) as Record<string, unknown>;
  switch (res.action) {
    case "refused-budget":
      return `budget refused (${(budget.reason as string) || "over cap"}${budget.projected != null ? `, projected ${fmtNum(budget.projected)} CU` : ""})`;
    case "extend-unknown":
      return "session state unreadable — nothing changed";
    case "extend-no-lease":
      return "no live lease to extend";
    case "extend-standing-managed":
      return "the standing lease is grant-managed";
    case "grant-inactive":
      return "no active grant to extend";
    default:
      return (res.action as string) || "failed";
  }
}

export function shortenRefusalText(res: Record<string, unknown>): string {
  switch (res.action) {
    case "shorten-deadline-past":
      return "that target has already passed";
    case "shorten-not-earlier":
      return "that is not earlier than the current deadline";
    case "shorten-standing-managed":
      return "the standing lease is grant-managed";
    case "shorten-unknown":
      return "session state unreadable — nothing changed";
    case "shorten-no-lease":
      return "no live lease to shorten";
    case "lease-disabled":
      return "the lease is disabled in config";
    default:
      return (res.action as string) || "failed";
  }
}

export function adoptRefusalText(res: Record<string, unknown>): string {
  switch (res.action) {
    case "adopt-deadline-past":
      return "the derived deadline has already passed";
    case "adopt-deadline-shortens":
      return "a planted deadline may not precede the evidenced one";
    case "adopt-no-deadline":
      return "no deadline evidence and none planted";
    case "adopt-shape-ambiguous":
      return "the shape class matches several catalog shapes";
    case "adopt-shape-conflict":
      return "the picked shape contradicts the evidenced shape";
    case "adopt-shape-unknown":
      return "the picked shape is not in the catalog";
    case "adopt-has-record":
      return "a lease record now exists for this session";
    case "adopt-absent":
      return "the session is no longer live";
    case "adopt-unknown":
      return "session state unreadable — nothing changed";
    case "adopt-handover-pending":
      return "a handover child";
    case "adopt-bridge-managed":
      return "bridge-managed — not the lease system's to adopt";
    case "refused-budget":
      return "budget refused the planted extension";
    case "lease-disabled":
      return "the lease is disabled in config";
    default:
      return (res.action as string) || "failed";
  }
}

/* ---------------- logs form model (logs.js, pure) ---------------- */

/** The logs vocabulary is closed: exactly the contract's
 *  eight kinds (owner's ruling). */
export const LOG_LEVEL_BY_KIND: Record<string, "ok" | "info" | "warn" | "error"> = {
  "lease-started": "ok",
  "lease-adopted": "ok",
  "grant-started": "ok",
  "lease-extended": "info",
  "envelope-lease-released": "info",
  "ui-restored": "info",
  "keepalive-stale": "warn",
  "budget-refused": "error",
};

export const LOG_KINDS = new Set(Object.keys(LOG_LEVEL_BY_KIND));

export type LogFilter = "all" | "leases" | "grants" | "budget" | "errors";

export function logLevel(ev: LogEvent): "ok" | "info" | "warn" | "error" {
  return LOG_LEVEL_BY_KIND[ev.kind] || "info";
}

function detailOf(ev: LogEvent): Record<string, unknown> {
  return (ev.detail ?? {}) as Record<string, unknown>;
}

function resultOf(ev: LogEvent): Record<string, unknown> {
  return (detailOf(ev).result ?? {}) as Record<string, unknown>;
}

export function logShape(ev: LogEvent): string | null {
  const d = detailOf(ev);
  const r = resultOf(ev);
  const rec = (r.record ?? {}) as Record<string, unknown>;
  return (
    (d.shape as string) ||
    (d.profile as string) ||
    (rec.shape as string) ||
    (rec.profile as string) ||
    (r.shape as string) ||
    (r.profile as string) ||
    null
  );
}

export function logSession(ev: LogEvent): string | null {
  const d = detailOf(ev);
  const r = resultOf(ev);
  const rec = (r.record ?? {}) as Record<string, unknown>;
  return (
    (d.session as string) ||
    (rec.session as string) ||
    (d.new_session as string) ||
    null
  );
}

export function logCategory(ev: LogEvent): "grants" | "budget" | "leases" {
  if (/^grant-/.test(ev.kind)) return "grants";
  if (/^budget/.test(ev.kind)) return "budget";
  return "leases";
}

export function logDayKey(iso: string): string {
  const t = new Date(iso);
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(
    t.getDate(),
  ).padStart(2, "0")}`;
}

export function logDayLabel(key: string, now: number): string {
  const today = logDayKey(new Date(now).toISOString());
  const yesterday = logDayKey(new Date(now - 86400000).toISOString());
  if (key === today) return "Today";
  if (key === yesterday) return "Yesterday";
  return new Date(`${key}T12:00:00`).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export interface LogDayGroup {
  key: string;
  label: string;
  events: LogEvent[];
}

export function groupByDay(events: LogEvent[], now: number): LogDayGroup[] {
  const groups = new Map<string, LogEvent[]>();
  events.forEach((ev) => {
    const key = logDayKey(ev.ts);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(ev);
  });
  return [...groups.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([key, evs]) => ({
      key,
      label: logDayLabel(key, now),
      events: evs.slice().sort((a, b) => b.seq - a.seq),
    }));
}

/** The variable part of an event — the kind is its own
 *  column and the shape its own column. */
export function logDetailText(ev: LogEvent, specs: Spec[]): string {
  const d = detailOf(ev);
  const r = resultOf(ev);
  switch (ev.kind) {
    case "lease-started": {
      const rec = (r.record ?? {}) as Record<string, unknown>;
      return [
        d.hours != null ? fmtDur(Number(d.hours)) : null,
        rec.deadline ? `deadline ${fmtTime(rec.deadline as string)}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    case "lease-extended":
      return `+${fmtDur(Number(d.hours))} · new deadline ${fmtTime(d.new_deadline as string)}`;
    case "lease-adopted":
      return d.deadline ? `deadline ${fmtTime(d.deadline as string)}` : "";
    case "keepalive-stale":
      return [
        d.stale_s != null ? `${d.stale_s}s stale` : null,
        d.pulse ? `pulse ${d.pulse}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    case "budget-refused":
      return [
        d.projected_cu != null ? `${fmtNum(d.projected_cu)} CU projected` : null,
        d.daily_cap_cu != null
          ? `daily ${fmtNum(d.daily_used_cu)} / ${fmtNum(d.daily_cap_cu)} CU`
          : null,
      ]
        .filter(Boolean)
        .join(" · ");
    case "grant-started":
      return `${fmtDur(Number(d.hours))}, burst ${specLabel(
        specs,
        (d.burst as string) || (r.burst_shape as string) || (r.burst_profile as string),
      )}`;
    case "envelope-lease-released":
      return d.reason ? String(d.reason) : "";
    case "ui-restored":
      return [
        d.active_leases != null ? `${d.active_leases} active` : null,
        d.balance_cu != null ? `balance ${fmtNum(d.balance_cu)} CU` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    default:
      return "";
  }
}

export function logCaller(ev: LogEvent): string | null {
  const d = detailOf(ev);
  const r = resultOf(ev);
  const rec = (r.record ?? {}) as Record<string, unknown>;
  return (d.caller as string) || (r.caller as string) || (rec.caller as string) || null;
}
