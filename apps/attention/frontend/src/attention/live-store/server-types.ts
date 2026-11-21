// Server payload shapes for the live attention store
// (api/1 responses, verbatim), plus the verb-name mapping
// between the backend's vocabulary and the frontend's.

import type {
  HandlerStatusView,
  PresenceMode,
  RegistriesView,
  RuleRecord,
} from "../types";

// ---------------------------------------------------------------
// The served payloads (api/1, the backend's own forms).

export interface ServerPresence {
  mode: PresenceMode;
  mode_label: string;
  expires_at: string | null;
  expectation: string;
}

export interface ServerVerb {
  verb: string;
  label: string;
  primary?: boolean;
  rule_hint?: string | null;
  sends?: boolean;
}

export interface ServerItem {
  id: string;
  handler: { handle: string; label: string; color_slot: number; icon: string };
  kind: string;
  kind_label: string;
  title: string;
  due_at: string | null;
  waiting_since: string;
  waiting_label: string;
  tier: string;
  need: string;
  triage: string;
  verbs: ServerVerb[];
  options: { id: string; label: string }[] | null;
  wait_id: string | null;
  snooze_options: { times: string[]; on_activity: boolean };
  clears_at_source: boolean;
  decision: {
    verb: string;
    verb_label: string;
    at: string;
    option_id: string | null;
    note: string | null;
    send_id: string | null;
    evidence: string | null;
  } | null;
  fulfillment: { state: string; label: string } | null;
  decision_history: {
    verb: string;
    verb_label: string;
    at: string;
    outcome: string | null;
    option_id: string | null;
    note: string | null;
    send_id: string | null;
  }[];
  resume_note: string | null;
  snooze_return_at: string | null;
  snooze_on_activity: boolean;
  proposal: { cls: string; verb: string; count: number; key: string } | null;
  provenance: string;
  provenance_label: string;
}

export interface ServerBand {
  band: string;
  band_label: string;
  collapsed: boolean;
  items: ServerItem[];
  unavailable: { reason: string; last_good_at: string | null } | null;
}

export interface ServerToday {
  presence: ServerPresence;
  bands: ServerBand[];
  headline_count: number;
  decided_count: number;
  generated_at: string;
}

export interface ServerGlance {
  presence: ServerPresence;
  clock: { now: string; next_window_at: string };
  next_due: { title: string; handler_handle: string; handler_label: string; due_label: string } | null;
  decision_count: number;
  handler_dots: { handle: string; color_slot: number; needs_decision: number }[];
  held_count: number;
  breakthrough_count: number;
  breakthrough_items: { id: string; title: string; handler_label: string }[];
  down_sources: string[];
}

export interface ServerDigest {
  generated_at: string;
  window: { next_at: string | null; times?: string[]; enabled_times?: string[] };
  include?: { decisions: boolean; waiting: boolean; fyi: boolean };
  sections: {
    kind: string;
    kind_label: string;
    owner: string;
    owner_label: string;
    rows: {
      title: string;
      handle: string;
      handler_label: string;
      provenance_label: string;
      at: string;
      age_label: string;
    }[];
  }[];
  stalls: {
    handle: string;
    handler_label: string;
    summary: string;
    clearing_act: string | null;
    status_label: string;
    age_hours: number;
    age_label: string;
  }[];
  staffing: {
    available: boolean;
    reason: string | null;
    idle_minutes_total: number;
    rows: {
      topic: string | null;
      handle: string | null;
      handler_label: string;
      kind: string;
      kind_label: string;
      detail: string;
      escalation: string | null;
    }[];
  };
  topics: {
    topic: string;
    worst_label: string | null;
    stalls: number;
    open_counts: { kind: string; kind_label: string; count: number }[];
    lanes: {
      handle: string;
      label: string;
      status_label: string | null;
      stale: boolean;
      quick_verbs: ServerVerb[];
    }[];
  }[];
  parked_plans: {
    available: boolean;
    reason: string | null;
    plans: { title: string | null; path: string | null; project: string; age_days: number | null }[];
  };
}

export interface ServerHandlerRow {
  handle: string;
  label: string;
  thread_id: string | null;
  color_slot: number;
  icon: string;
  ui_surface: boolean;
  retired: boolean;
}

export interface ServerRegistries {
  status_codes: RegistriesView["status_codes"];
  fields: RegistriesView["fields"];
  wait_classes: RegistriesView["wait_classes"];
  operators: { op: string; label: string }[];
  triggers: { on: string; label: string }[];
  actions: { type: string; label: string }[];
  templates: RegistriesView["templates"];
  item_kinds: RegistriesView["item_kinds"];
  handlers: ServerHandlerRow[];
  action_rules: {
    id: string;
    match: { handle?: string; kind?: string; wait_class?: string; status_code?: string | string[] };
    verb: string;
    mode: string;
    created_from: string;
    at?: string;
    note?: string;
  }[];
}

export interface ServerRuleView extends RuleRecord {
  display_name: string;
  when_label: string;
  then_label: string;
}

export interface ServerProgramme {
  slug: string;
  label: string;
  handles: string[];
  cadence_minutes: number;
  staffing_band: { min: number; max: number } | null;
  escalation_hours: number;
  venue: string;
  rule_text: string;
  retired: boolean;
}

export interface ServerHandlerDetail {
  handle: string;
  label: string;
  items: ServerItem[];
  agent_clearable_count: number;
  muted_types: { kind: string; label: string }[];
  breakthrough_hit_rate: number | null;
  status: (Record<string, unknown> & {
    status_code: string;
    status_label: string;
    need: HandlerStatusView["need"];
    summary: string;
    at: string;
    done?: string[];
    ongoing?: string[];
    tail?: { kind: string; kind_label: string; title: string; owner: string }[];
    blockers?: { summary: string; clearing_act: string | null; whose: string }[];
    quick_verbs: ServerVerb[];
    derived?: {
      available: boolean;
      reason?: string | null;
      last_good_at?: string | null;
      todos: { total: number; done: number; doing: number; blocked: number } | null;
      conflicts?: { message: string }[];
    } | null;
  }) | null;
  handler_verbs: ServerVerb[];
  owner_actions: {
    id: string;
    at: string;
    verb: string;
    verb_label: string;
    note: string;
    actor: string;
    rule_id: string | null;
    shadow?: boolean;
  }[];
  thread_id: string | null;
  sends: ServerSend[];
  auto_applied: {
    at: string;
    wait_id: string | null;
    wait_class: string;
    decision: string;
    decision_label: string;
    rule_id: string | null;
    shadow: boolean;
  }[];
}

export interface ServerSend {
  id: string;
  at: string;
  rule_id: string | null;
  wait_id: string | null;
  handle: string;
  target: string;
  template: string;
  version: number;
  attempt: number;
  presence: string;
  fact_hash: string | null;
  text: string;
  mode: "active" | "shadow";
  outcome: string | null;
  dispatch: {
    attempts: number;
    claim_expires_at: string | null;
    claimed_at: string | null;
    consumer: string | null;
    delivered_at: string | null;
    delivery_ref: string | null;
    suppressed_reason?: string | null;
    bridge_request_id?: string | null;
  };
}

export interface ServerWait {
  wait_id: string;
  handle: string;
  wait_class: string;
  summary: string;
  decision: string;
  posted_at: string;
  decided_at: string | null;
  owner_note: string | null;
}

// ---------------------------------------------------------------
// Verb vocabulary translation. The frontend's taxonomy is
// the storyboard's ("decide", "approve"); the backend's is
// contract 05's ("pick", "approve_once"). Every other verb
// is spelled the same on both sides.

const TO_FRONTEND_VERB: Record<string, string> = {
  pick: "decide",
  approve_once: "approve",
};
const TO_BACKEND_VERB: Record<string, string> = {
  decide: "pick",
  approve: "approve_once",
};
export const frontendVerb = (v: string): string => TO_FRONTEND_VERB[v] ?? v;
export const backendVerb = (v: string): string => TO_BACKEND_VERB[v] ?? v;

/** Handler steering verbs (backend HANDLER_VERBS +
 * STATUS_QUICK_VERBS, mirrored as the mock mirrors them). */
export const HANDLER_VERBS = new Set([
  "status_ping",
  "parallelize",
  "critic_pass",
  "perf_pass",
  "consolidation_pass",
  "organize_pass",
  "stop",
  "park",
  "resume",
  "continue",
  "go",
  "accept_review",
  "reject_incomplete",
  "close",
  "leave_it",
]);
