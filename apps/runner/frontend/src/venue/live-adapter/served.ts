// The served shapes: the surface's own records, in the
// forms the state portions and the outbox carry them,
// plus the fetch seam's type and the empty budget the
// adapter serves before the budget portion lands. Split
// from live-adapter.ts along the served-shape seam.

import type { BudgetAccountView, BudgetView, ShapeSpec } from "../types";

export interface ServedSpec {
  id: string;
  label: string;
  gpu: string | null;
  tpu: string | null;
  high_mem: boolean;
  rate_cu_per_hour: number | null;
  agent_startable: boolean;
}

export interface ServedLeaseRecord {
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

export interface ServedRecordEntry {
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

export interface ServedAccessEntry {
  session: string;
  endpoint?: string;
  shape_class: string;
  caller: string | null;
  first_seen: string;
  unattributed?: boolean;
}

export interface ServedBudgetAccount {
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

export interface ServedGrant {
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

export interface ServedEnvelope {
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

export interface ServedOrphan {
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

export interface ServedListenerEntry {
  at: string;
  age_s: number | null;
  error: string | null;
  listeners: { port: number; pid: number; cwd: string | null; suspect?: string[] }[];
}

export interface OutboxEvent {
  seq: number;
  ts: string;
  kind: string;
  detail: Record<string, unknown>;
}

export interface Parts {
  records: { records: ServedRecordEntry[]; access: ServedAccessEntry[] } | null;
  specs: { specs: ServedSpec[] } | null;
  budget: { budget: ServedBudget } | null;
  grant: { grant: ServedGrant | null; envelope: ServedEnvelope | null } | null;
  orphans: { orphans: ServedOrphan[] } | null;
  listeners: { listeners: Record<string, ServedListenerEntry> } | null;
  outbox: { events: OutboxEvent[]; last_seq: number } | null;
}

export type FetchLike = (
  url: string,
  init?: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    signal?: AbortSignal;
  },
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

export const EMPTY_BUDGET: BudgetView = {
  balanceCu: 0,
  usedTodayCu: 0,
  reservedCu: 0,
  availableCu: 0,
  runwayLabel: "less than a day at today's rate",
  byCaller: [],
  caps: { daily: null, monthly: null, standingDaily: null },
  accounts: [],
};
