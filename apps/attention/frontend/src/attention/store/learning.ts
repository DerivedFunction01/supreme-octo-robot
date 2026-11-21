// The mock store's learning loop: tap counts per
// (handle, class, verb), proposal surfacing at the
// threshold, action-rule creation/matching, and the
// shadow hint served on an item.
import type { MockStoreCtx } from "./context";
import type {
  OwnerItem,
  ProposalPayload,
  WaitRow,
} from "../types";
import type {
  ActionRuleRecord,
} from "./records";
import {
  COUNTED_VERBS,
  PROPOSAL_THRESHOLD,
} from "./constants";
import { VERB_LABELS, verbLabel } from "../verb-labels";

export function createLearning(ctx: MockStoreCtx): MockStoreCtx["learning"] {
  const { state, nowIso } = ctx;

// ---------- the learning loop (tap counts + action rules) ----------

function waitOf(item: OwnerItem): WaitRow | undefined {
  return item.wait_id
    ? state.waits.find((w) => w.id === item.wait_id)
    : undefined;
}

/** The class a tap counts under: the wait's class when a
 * wait stands behind the item, else the item's kind
 * (backend _count_tap). */
function classOf(item: OwnerItem): string {
  return waitOf(item)?.wait_class ?? item.kind;
}

function createActionRule(args: {
  match: ActionRuleRecord["match"];
  verb: string;
  mode: string;
  created_from: string;
  option_id?: string | null;
}): ActionRuleRecord {
  state.ruleCounter += 1;
  const rule: ActionRuleRecord = {
    id: `tap-${String(state.ruleCounter).padStart(4, "0")}`,
    match: args.match,
    verb: args.verb,
    mode: args.mode,
    created_from: args.created_from,
    at: nowIso(),
    option_id: args.option_id ?? null,
  };
  state.actionRules.push(rule);
  return rule;
}

/** Backend _rule_matches: a stored rule covers this
 * item + verb (a wait_class on the rule never matches
 * here — proposals count under classes, not waits). */
function actionRuleMatches(rule: ActionRuleRecord, item: OwnerItem, verb: string): boolean {
  if (rule.verb !== verb) return false;
  if (rule.match.handle && rule.match.handle !== item.handle) return false;
  if (rule.match.kind && rule.match.kind !== item.kind) return false;
  return true;
}

/** Backend _shadow_hint: a shadow rule that would fire
 * on this item speaks on the item's face. */
function shadowHintFor(item: OwnerItem): string | null {
  for (const rule of state.actionRules) {
    if (rule.mode !== "shadow") continue;
    if (!item.verbs.includes(rule.verb)) continue;
    if (rule.match.wait_class) continue;
    if (rule.match.handle && rule.match.handle !== item.handle) continue;
    if (rule.match.kind && rule.match.kind !== item.kind) continue;
    return `A shadow rule would ${verbLabel(rule.verb).toLowerCase()} this — the tap applies it once.`;
  }
  return null;
}

/** Repetition proposes the rule (D-A7): identical taps
 * counted per handler + class + verb; at the threshold
 * a rule_proposal item surfaces — unless a stored rule
 * already covers the pattern or the proposal is open. */
function countTap(item: OwnerItem, verb: string): void {
  if (!COUNTED_VERBS.has(verb)) return;
  const cls = classOf(item);
  const key = `${item.handle}|${cls}|${verb}`;
  const entry = (state.tapCounts[key] ??= { count: 0, cycles: 0 });
  entry.count += 1;
  if (entry.count < PROPOSAL_THRESHOLD) return;
  if (state.actionRules.some((r) => actionRuleMatches(r, item, verb))) return;
  const id = `${item.handle}:rule-proposal:${cls}:${verb}:${entry.cycles}`;
  if (state.items.some((i) => i.id === id)) return;
  const proposal: ProposalPayload = { cls, verb, count: entry.count, key };
  state.items.push({
    id,
    handle: item.handle,
    wait_id: null,
    kind: "rule_proposal",
    title: `You have tapped ${verbLabel(verb)} on ${cls} items from this lane ${entry.count} times — make it a rule?`,
    detail: "Standing-rule proposal · from your repeated taps",
    waiting_since: nowIso(),
    due_at: null,
    notice_type: null,
    verbs: ["accept_proposal", "reject_proposal"],
    options: null,
    fulfillment: "recorded",
    clears_at_source: false,
    proposal,
    decision: null,
    decision_history: [],
  });
}

  return { waitOf, classOf, createActionRule, actionRuleMatches, shadowHintFor, countTap };
}
