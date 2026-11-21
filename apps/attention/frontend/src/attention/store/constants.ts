// Scenario constants and label tables for the mock
// store: the scenario start, the contract timings, the
// failing-target fixtures, the steering verb sets, and
// the served label maps.

import type { PresenceMode } from "../types";

export const SCENARIO_START = Date.parse("2026-03-04T14:04:00-05:00");
export const STALL_MS = 120 * 60_000; // contract 05: unfulfilled past 120 min reads stalled
export const CLAIM_LEASE_MS = 15 * 60_000; // ATT6: 15-minute claim lease
export const CONSUMER = "attention-service";
/** Mock transport fact: deliveries to this target fail. The
 * seeded failure path (the return leg of the decision loop). */
export const FAILING_TARGETS: Record<string, string> = {
  "thread-quarry": "target thread unreachable (mock transport)",
};
export const MAIN_THREAD = "thread-main";
export const EXPECTATIONS: Record<PresenceMode, string> = {
  active: "",
  focus: "Only breakthroughs and decisions",
  away: "Items hold for the next digest window",
};

export const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

export const HANDLER_VERBS = [
  "status_ping",
  "parallelize",
  "critic_pass",
  "perf_pass",
  "consolidation_pass",
  "organize_pass",
  "stop",
  "park",
  "resume",
] as const;

/** The quick verbs placed on a status ride the handler
 * endpoint too (backend STATUS_QUICK_VERBS). */
export const STATUS_QUICK_VERBS = [
  "continue",
  "go",
  "accept_review",
  "reject_incomplete",
  "close",
  "leave_it",
] as const;

/** The pass commissions: verb -> the item title's name. */
export const PASS_VERBS: Record<string, string> = {
  critic_pass: "Critic pass",
  perf_pass: "Performance pass",
  consolidation_pass: "Consolidation pass",
  organize_pass: "Organize pass",
};

/** The lane's answering status post for a directed verb:
 * the fake simulates the lane replying to the verdict
 * with its new status — it lands on the next tick. */
export const DIRECTED_STATUS: Record<string, { status_code: string; summary: string }> = {
  park: {
    status_code: "PARKED",
    summary: "Parked at the owner's direction — resumes on the word.",
  },
  stop: { status_code: "PARKED", summary: "Stopped at the owner's direction." },
  resume: { status_code: "WORKING", summary: "Resumed — back on the work." },
  accept_review: {
    status_code: "DONE",
    summary: "Review accepted — the work stands as reviewed.",
  },
  reject_incomplete: {
    status_code: "WORKING",
    summary: "Sent back as incomplete — rework under way.",
  },
  close: { status_code: "CLOSED", summary: "Closed by the owner." },
};

export const STALL_AFTER_HOURS = 6; // backend Settings.stall_after_hours

/** The learning loop (backend D-A7/D-A8): verdict taps
 * are counted per handler + class + verb; at the
 * threshold a rule proposal surfaces. The spellings are
 * this store's verb taxonomy — "approve" counts as the
 * backend's approve_once, "decide" as its pick. Bookmarks
 * (snooze, done, mute_type, leave_it) and reply/modify
 * are never counted: their judgment rides the note. */
export const COUNTED_VERBS = new Set([
  "approve",
  "deny",
  "decide",
  "accept",
  "reject",
  "push",
  "close_on_verify",
  "continue",
  "go",
  "accept_review",
  "reject_incomplete",
]);
export const PROPOSAL_THRESHOLD = 3; // backend dom.PROPOSAL_THRESHOLD

export const PROVENANCE_LABELS: Record<string, string> = {
  commission: "Owner commission",
  offer: "Agent offer — awaiting your tap",
};

export const DIGEST_OWNER_LABELS: Record<string, string> = {
  owner: "Waiting on you",
  lane: "Back with the lane",
  self: "Poster closeout",
};

/** Staffing row kind labels (backend staffing KIND_LABELS). */
export const STAFFING_KIND_LABELS: Record<string, string> = {
  understaffed: "Understaffed",
  fleet_idle: "Idle session",
  idle_unlanded: "Idle — work complete",
  no_successor: "No successor staffed",
  record_gap: "Record not moving",
  phantom_stop: "Unverified owner stop",
  unrouted_defect: "Unrouted defect",
  blocked_uncited: "Blocked — no basis",
  blocked_unverified: "Blocked — unverified",
  serial_plan: "Serial plan",
  steer_undeliverable: "Steer undeliverable",
  owner_waiting: "Owner waiting",
  owner_waiting_unanswered: "Owner waiting — ask unanswered",
  armed_unposted: "Armed — no post yet",
};
