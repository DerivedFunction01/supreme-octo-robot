// ---------- Rules (api/1: rules + rule_view) ----------

export interface RuleMatch {
  wait_class: string | null;
  status_code: string | string[] | null;
  kind: string | null;
  handle: string | null;
}

export interface RuleCondition {
  field: string;
  op: string;
  value: unknown;
}

export interface RuleAction {
  type: string;
  template?: string;
  variants?: {
    presence?: Record<string, string>;
    attempt?: Record<string, string>;
  };
}

/** The stored rule record — the editor's working shape and
 * the POST /api/v1/rules body, verbatim field set. */
export interface RuleRecord {
  id: string;
  name: string | null;
  match: RuleMatch;
  where: { all: RuleCondition[] } | null;
  action: RuleAction;
  scope: string;
  requires: string[];
  priority: number;
  on_scope_miss: string;
  trigger: { on: string; after_minutes?: number; count?: number };
  guards: {
    cooldown_minutes?: number;
    max_posts?: number;
    escalate_after?: number;
  };
  mode: string;
}

/** A stored rule plus its composed When / Then sentences
 * (rule_view): the row speaks sentences with registry
 * labels resolved, never raw codes. */
export interface RuleView extends RuleRecord {
  display_name: string;
  when_label: string;
  then_label: string;
}

export interface WouldFire {
  wait_id: string;
  /** "post" for a rendered post; otherwise the decision
   * the wait would land (owner_approved / held / surfaced). */
  action: string;
  template: string | null;
  target: string | null;
  text: string | null;
}

export type RuleSaveResult =
  | { ok: true; rule: RuleView }
  | { ok: false; error: string };

export type RulePreviewResult =
  | { ok: true; would_fire: WouldFire[] }
  | { ok: false; error: string };

// ---------- Action rules (the learning loop's rules) ----------

/** A standing action rule, created by a promotion tap
 * (rule_it / approve_rule / make_rule / an accepted
 * proposal) — the backend's action_rules record, served
 * composed: the match and the provenance speak in labels. */
export interface ActionRuleView {
  id: string;
  match_label: string;
  verb: string;
  verb_label: string;
  mode: string;
  created_from: string;
  created_label: string;
  at_label: string;
}
