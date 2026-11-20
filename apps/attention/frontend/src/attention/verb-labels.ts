// The backend's verb vocabulary (domain VERB_LABELS):
// every verb the surfaces serve, with its label. Kept
// apart from the mock store so live surfaces can render
// verb labels without pulling the mock store (and its
// seed data) into their bundle.

export const VERB_LABELS: Record<string, string> = {
  approve_once: "Approve",
  approve_rule: "Approve + make rule",
  deny: "Deny",
  pick: "Pick",
  rule_it: "Rule it standing",
  accept: "Accept",
  reject: "Reject",
  modify: "Modify",
  push: "Push",
  close_on_verify: "Close — verified",
  reply: "Reply",
  snooze: "Snooze",
  done: "Done",
  mute_type: "Mute type",
  leave_it: "Leave it",
  continue: "Continue",
  go: "Go",
  accept_review: "Accept review",
  reject_incomplete: "Reject as incomplete",
  park: "Park",
  close: "Close",
  status_ping: "Status ping",
  parallelize: "Parallelize",
  critic_pass: "Critic pass",
  perf_pass: "Performance pass",
  consolidation_pass: "Consolidation pass",
  organize_pass: "Organize pass",
  stop: "Stop",
  resume: "Resume",
  accept_proposal: "Accept — create the rule",
  reject_proposal: "Reject proposal",
  decide: "Decide",
  renew: "Renew",
  approve: "Approve",
};

export function verbLabel(verb: string): string {
  return VERB_LABELS[verb] ?? verb;
}
