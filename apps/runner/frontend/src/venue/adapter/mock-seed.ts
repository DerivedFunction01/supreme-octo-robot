// The mock store's shape and its seed: the store record
// types plus createSeedStore, the seeded state the mock
// adapter opens with. Split from adapter.ts along the
// seed seam.

import type {
  AccessEntry,
  BudgetAccountView,
  BudgetCaps,
  GrantRecord,
  LeaseRecord,
  ResolvedOrphanView,
  RunRecord,
  SessionEvidence,
  SpendSegment,
  VenueEvent,
} from "../types";
import leasesSeed from "../seed/leases.json";
import runsSeed from "../seed/runs.json";
import evidenceSeed from "../seed/evidence.json";
import journalSeed from "../seed/journal.json";
import eventsSeed from "../seed/events.json";
import callersSeed from "../seed/callers.json";
import accessSeed from "../seed/access-log.json";

export const SEED_NOW = "2026-11-13T14:02:00-05:00";
/** In-flight run states — the pipeline's pruned-jobs rule
 *  (records.RUN_NONTERMINAL_STATES): an orphan's jobs list
 *  carries only jobs whose backing record is non-terminal. */
export const NONTERMINAL_RUN_STATES = ["starting", "running", "polling"];
export const OPENING_BALANCE_CU = 412; // the storyboard's served balance at seed

/** The orphans census's per-session derivation detail
 *  (V6), adapter-side served data like orphanSeenAt: the
 *  core derives it from renewal-config and the extension
 *  events; the record (SessionEvidence, a closed contract
 *  shape) never carries it. Conflict values ride raw —
 *  the projection formats timestamps as times, as the
 *  panel's orphanConflictValue does. */
export interface OrphanDetailSeed {
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
export interface LeaseDiagSeed {
  listeners: { port: number; pid: number; cwd: string; suspect: string[] }[];
  heartbeatAgeS: number | null;
  lastPulse: string | null;
  syncClaim: { caller: string; expiresAt: string } | null;
}

/** One account's budget state in the fake store (venue
 *  rework): the accounts the venue's config names, with the
 *  caps the budget editor writes. */
export interface BudgetAccountState {
  venue: string;
  account: string;
  label: string;
  credential: BudgetAccountView["credential"];
  caps: BudgetCaps;
}

export interface Store {
  budgetAccounts: BudgetAccountState[];
  /** Venues the core serves with no budget at all (the
   *  local venue): named in the budget view, never accounts. */
  budgetlessVenues: string[];
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

export function createSeedStore(): Store {
  return {
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
    {
      venue: "ec2",
      account: "primary",
      label: "Primary",
      credential: "not-brought-in",
      caps: { daily: 20, monthly: 200, standingDaily: null },
    },
  ],
  budgetlessVenues: ["local"],
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
}
