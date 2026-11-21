// The mock store's rule machinery: the composed rule
// view (When / Then sentences), normalization and
// validation against the registries, template
// rendering, and wait matching.
import type { MockStoreCtx } from "./context";
import type {
  RuleRecord,
  RuleView,
  WaitRow,
} from "../types";
import {
  clone,
} from "./constants";

export function createRules(ctx: MockStoreCtx): MockStoreCtx["rules"] {
  const { state, nowMs } = ctx;

// ---------- rules (rule_view + add_rule + preview) ----------

function titleCaseId(id: string): string {
  return id
    .replace(/-/g, " ")
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** rule_view: the stored rule plus its composed sentences. */
function ruleViewOf(rule: RuleRecord): RuleView {
  const parts: string[] = [];
  const m = rule.match;
  if (m?.wait_class) parts.push(`class is ${ctx.labels.classLabel(m.wait_class)}`);
  if (m?.status_code) {
    const codes = Array.isArray(m.status_code) ? m.status_code : [m.status_code];
    parts.push(`status is ${codes.map(ctx.labels.statusLabelOf).join(" or ")}`);
  }
  if (m?.kind) parts.push(`kind is ${ctx.labels.kindLabel(m.kind)}`);
  if (m?.handle) parts.push(`handler is ${m.handle}`);
  const trig = rule.trigger ?? { on: "on_enter" };
  if (trig.on === "on_age") parts.push(`after ${trig.after_minutes ?? "?"} min`);
  else if (trig.on === "on_repeat") parts.push(`on the ${trig.count ?? "?"}th arrival`);
  else if (trig.on === "on_state_change") parts.push("when the state changes");
  else if (trig.on === "on_presence_enter") parts.push("when the scope is entered");
  if (rule.where) parts.push("+ conditions");
  if (rule.requires?.length) parts.push("with all flags holding");
  const whenLabel = parts.length ? `Wait — ${parts.join(" · ")}` : "Any wait";
  const action = rule.action;
  const head =
    {
      auto_apply: "Auto-apply the decision",
      surface: "Surface it for the owner",
      hold: "Hold it",
      post: "Post",
      post_and_apply: "Post, then auto-apply",
    }[action.type] ?? action.type;
  let thenLabel = action.template ? `${head} · ${action.template}` : head;
  const guards = rule.guards ?? {};
  const bits: string[] = [];
  if (guards.cooldown_minutes != null) bits.push(`cooldown ${guards.cooldown_minutes}m`);
  if (guards.max_posts != null) bits.push(`max posts ${guards.max_posts}`);
  if (guards.escalate_after != null) bits.push(`escalate after ${guards.escalate_after} → Main`);
  if (bits.length) thenLabel += ` · ${bits.join(" · ")}`;
  return {
    ...clone(rule),
    display_name: rule.name || titleCaseId(rule.id),
    when_label: whenLabel,
    then_label: thenLabel,
  };
}

/** normalize_rule, mirrored: a bare-string action becomes
 * {type}; mode defaults to shadow (D-A1: a new rule never
 * acts until it is switched on); trigger, priority, guards
 * and requires take their defaults. */
function normalizeRule(rule: RuleRecord): RuleRecord {
  const out = clone(rule);
  const action = out.action as unknown;
  if (typeof action === "string") out.action = { type: action };
  out.match = {
    wait_class: out.match?.wait_class ?? null,
    status_code: out.match?.status_code ?? null,
    kind: out.match?.kind ?? null,
    handle: out.match?.handle ?? null,
  };
  out.scope = out.scope || "always";
  out.mode = out.mode || "shadow";
  out.on_scope_miss = out.on_scope_miss || "pending";
  out.requires = out.requires ?? [];
  out.priority = out.priority || 100;
  out.trigger = out.trigger?.on ? out.trigger : { on: "on_enter" };
  out.guards = out.guards ?? {};
  return out;
}

/** add_rule's validation, mirrored: the save is refused
 * with the backend's error lines when a field is unknown,
 * a reference does not resolve, or the hard-stop floor is
 * breached (applying rules may not select hard-stop
 * classes — by flat match or by a where leaf). */
function validateRule(rule: RuleRecord): string[] {
  const errors: string[] = [];
  const fields = new Set(state.registries.fields.map((f) => f.name));
  const codes = new Set(state.registries.status_codes.map((c) => c.code));
  const classes = new Map(state.registries.wait_classes.map((c) => [c.name, c.hard_stop]));
  const templates = new Set(state.registries.templates.map((t) => t.kind));
  const actionTypes = new Set(state.registries.actions.map((a) => a.type));
  const triggerKinds = new Set(state.registries.triggers.map((t) => t.on));
  if (!rule.id) errors.push("id is required");
  const action = rule.action ?? ({ type: "auto_apply" } as RuleRecord["action"]);
  if (!actionTypes.has(action.type)) errors.push("action unknown action type");
  if (!["always", "away", "active"].includes(rule.scope))
    errors.push("scope unknown scope");
  if (!["active", "shadow"].includes(rule.mode)) errors.push("mode unknown mode");
  if (!["pending", "fallthrough"].includes(rule.on_scope_miss))
    errors.push("on_scope_miss unknown behaviour");
  if (!triggerKinds.has(rule.trigger?.on ?? "on_enter"))
    errors.push("trigger unknown trigger");
  const m = rule.match ?? ({} as RuleRecord["match"]);
  if (m.wait_class != null && !classes.has(m.wait_class))
    errors.push("match.wait_class unregistered class");
  if (m.status_code != null) {
    const list = Array.isArray(m.status_code) ? m.status_code : [m.status_code];
    if (list.some((c) => !codes.has(c)))
      errors.push("match.status_code unregistered status code");
  }
  const unknownRequires = (rule.requires ?? []).filter((f) => !fields.has(f));
  if (unknownRequires.length)
    errors.push(`requires unknown fields: ${unknownRequires.join(", ")}`);
  for (const leaf of rule.where?.all ?? []) {
    if (!fields.has(leaf.field)) errors.push(`where unknown field: ${leaf.field}`);
  }
  if (["post", "post_and_apply"].includes(action.type)) {
    const kinds = new Set<string>(
      [
        action.template,
        ...Object.values(action.variants?.presence ?? {}),
        ...Object.values(action.variants?.attempt ?? {}),
      ].filter((k): k is string => Boolean(k)),
    );
    const missing = [...kinds].filter((k) => !templates.has(k));
    if (missing.length)
      errors.push(`action.template unknown templates: ${missing.join(", ")}`);
  }
  if (!errors.length && ["auto_apply", "post_and_apply"].includes(action.type)) {
    const selected = new Set<string>();
    if (m.wait_class) selected.add(m.wait_class);
    for (const leaf of rule.where?.all ?? []) {
      if (leaf.field !== "wait_class") continue;
      if (leaf.op === "eq") selected.add(String(leaf.value));
      if (leaf.op === "in" && Array.isArray(leaf.value))
        for (const v of leaf.value) selected.add(String(v));
    }
    if ([...selected].some((name) => classes.get(name)))
      errors.push("rule hard-stop classes may not be applied");
  }
  return errors;
}

function renderTemplate(kind: string, facts: Record<string, unknown>): string {
  const entry = state.registries.templates.find((t) => t.kind === kind);
  if (!entry) return "";
  return entry.text.replace(/\{(\w+)\}/g, (whole, slot: string) =>
    slot in facts ? String(facts[slot] ?? "") : whole,
  );
}

/** The facts a wait carries for rule matching: the wait's
 * registered class + its item's kind, the handler's
 * status, programme membership (the poster flags the
 * scenario carries), and the derived age. */
function waitFacts(wait: WaitRow): Record<string, unknown> {
  const item = state.items.find((i) => i.wait_id === wait.id);
  const status = state.statuses[wait.handle];
  const programme = state.programmes.find((p) => p.handles.includes(wait.handle));
  return {
    wait_class: wait.wait_class,
    status_code: status?.status_code ?? null,
    kind: item?.kind ?? null,
    handle: wait.handle,
    program_approved: Boolean(programme),
    reversible: true,
    in_budget: true,
    only_blocker: false,
    age_minutes: Math.max(0, Math.floor((nowMs() - Date.parse(wait.at)) / 60_000)),
    repeat_count: 1,
    presence: state.presence.mode,
    handler_status_code: status?.status_code ?? null,
    summary: wait.summary,
    scope: programme?.label ?? "",
  };
}

function leafHolds(leaf: { field: string; op: string; value: unknown }, facts: Record<string, unknown>): boolean {
  const actual = facts[leaf.field];
  switch (leaf.op) {
    case "eq": return actual === leaf.value;
    case "ne": return actual !== leaf.value;
    case "in": return Array.isArray(leaf.value) && leaf.value.includes(actual);
    case "not_in": return Array.isArray(leaf.value) && !leaf.value.includes(actual);
    case "gt": return typeof actual === "number" && typeof leaf.value === "number" && actual > leaf.value;
    case "gte": return typeof actual === "number" && typeof leaf.value === "number" && actual >= leaf.value;
    case "lt": return typeof actual === "number" && typeof leaf.value === "number" && actual < leaf.value;
    case "lte": return typeof actual === "number" && typeof leaf.value === "number" && actual <= leaf.value;
    case "exists": return actual !== null && actual !== undefined;
    default: return false;
  }
}

/** Whether the candidate rule matches this wait under the
 * mock's presence scope (trigger kinds that need an event
 * stream — state change, presence enter — never fire in a
 * preview, as in the backend's dry run over stored waits). */
function ruleMatchesWait(rule: RuleRecord, facts: Record<string, unknown>): boolean {
  const m = rule.match;
  if (m?.wait_class && facts.wait_class !== m.wait_class) return false;
  if (m?.kind && facts.kind !== m.kind) return false;
  if (m?.handle && facts.handle !== m.handle) return false;
  if (m?.status_code) {
    const wanted = Array.isArray(m.status_code) ? m.status_code : [m.status_code];
    if (!wanted.includes(facts.status_code as string)) return false;
  }
  for (const leaf of rule.where?.all ?? []) {
    if (!leafHolds(leaf, facts)) return false;
  }
  for (const field of rule.requires ?? []) {
    if (facts[field] !== true) return false;
  }
  if (rule.scope === "away" && state.presence.mode !== "away") return false;
  if (rule.scope === "active" && state.presence.mode === "away") return false;
  const trig = rule.trigger ?? { on: "on_enter" };
  if (trig.on === "on_age") {
    return (facts.age_minutes as number) >= (trig.after_minutes ?? 0);
  }
  if (trig.on === "on_repeat") {
    return (facts.repeat_count as number) >= (trig.count ?? 1);
  }
  if (trig.on !== "on_enter") return false;
  return true;
}

  return { titleCaseId, ruleViewOf, normalizeRule, validateRule, renderTemplate, waitFacts, leafHolds, ruleMatchesWait };
}
