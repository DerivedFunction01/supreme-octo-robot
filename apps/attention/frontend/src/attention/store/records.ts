// Internal record shapes for the mock store: the
// seeded state tree, the registries/digest seed shapes,
// the action-rule and owner-action records, and the
// injectable scenario clock.

import type {
  DecideResult,
  DigestProgrammeLanes,
  DigestSettings,
  FulfilledEntry,
  HandlerActionResult,
  HandlerRow,
  HandlerSurface,
  OwnerItem,
  PresenceRow,
  ProgrammeRow,
  RegistriesView,
  RuleRecord,
  SendRow,
  WaitRow,
} from "../types";
import {
  SCENARIO_START,
} from "./constants";

/** An action rule record (backend action_rules shape):
 * created by a promotion tap, evaluated for shadow
 * hints and proposal suppression, served composed. */
export interface ActionRuleRecord {
  id: string;
  match: { handle?: string; kind?: string; wait_class?: string };
  verb: string;
  mode: string;
  created_from: string;
  at: string;
  option_id?: string | null;
}

export interface MockClock {
  now(): number;
  advance(ms: number): void;
}

export function manualClock(start: number = SCENARIO_START): MockClock {
  let t = start;
  return {
    now: () => t,
    advance: (ms: number) => {
      t += ms;
    },
  };
}

/** A handler's latest status post, as served (labels are
 * composed at read time from the registries). */
export interface StatusRecord {
  status_code: string;
  summary: string;
  at: string;
  done?: string[];
  ongoing?: string[];
  tail?: { kind: string; title: string; owner: string }[];
  blockers?: { summary: string; clearing_act: string | null; whose: string }[];
}

export interface RegistriesState {
  status_codes: RegistriesView["status_codes"];
  fields: { name: string; type: string; source: string; poster_settable: boolean }[];
  wait_classes: { name: string; hard_stop: boolean }[];
  operators: { op: string; label: string }[];
  triggers: { on: string; label: string }[];
  actions: { type: string; label: string }[];
  templates: RegistriesView["templates"];
  item_kinds: { kind: string; label: string; status_kind: boolean; digest_owner: string | null }[];
}

export interface DigestSeedState {
  sections: {
    kind: string;
    rows: { title: string; handle: string; provenance: string; at: string }[];
  }[];
  staffing: {
    available: boolean;
    reason: string | null;
    idle_minutes_total: number;
    rows: {
      topic: string | null;
      handle: string | null;
      kind: string;
      detail: string;
      escalation: string;
    }[];
  };
  parked_plans: {
    available: boolean;
    reason: string | null;
    plans: { project: string; path: string; title: string; age_days: number | null }[];
  };
  /** The programme lane blocks in the digest's served
   * shape; programmes with no named queue carry none. */
  programme_lanes: DigestProgrammeLanes[];
}

export interface OwnerActionRecord {
  id: string;
  handle: string;
  verb: string;
  note: string;
  at: string;
  actor: string;
  rule_id: string | null;
}

export interface StoreState {
  handlers: HandlerRow[];
  programmes: ProgrammeRow[];
  waits: WaitRow[];
  sends: SendRow[];
  presence: PresenceRow;
  items: OwnerItem[];
  fulfilled: FulfilledEntry[];
  handlerSurfaces: Record<string, HandlerSurface>;
  digest: DigestSettings;
  statuses: Record<string, StatusRecord>;
  registries: RegistriesState;
  rules: RuleRecord[];
  digestContent: DigestSeedState;
  ownerActions: OwnerActionRecord[];
  pings: Record<string, { count: number; last_at: number | null }>;
  ownerDirected: Record<string, { at: string; handle: string }>;
  /** Directed-control status posts land on the next tick —
   * the lane's answering post, simulated. */
  pendingStatus: Record<string, { status_code: string; summary: string }>;
  sendCounter: number;
  actionCounter: number;
  commissionCounter: number;
  ruleCounter: number;
  tickCount: number;
  pushFact: { state: "current" | "pushed"; flipAtTick: number | null };
  /** Recorded decisions (snooze, proposal verdicts) clear
   * on a later pass with the effect composed at the tap:
   * item_id -> {tick, effect}. */
  recordedResolveAt: Record<string, { tick: number; effect: string }>;
  /** The learning loop: tap counts per handle|cls|verb,
   * and the action rules promotions have created. */
  tapCounts: Record<string, { count: number; cycles: number }>;
  actionRules: ActionRuleRecord[];
  /** Items held by a type mute (backend triage "muted"):
   * out of every open derivation until the type unmutes. */
  mutedItems: Set<string>;
  failures: { send_id: string; reason: string; at: string }[];
  idempotency: Record<string, DecideResult>;
  handlerIdempotency: Record<string, HandlerActionResult>;
}
