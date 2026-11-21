// The mock store's registries/rules/vocabulary
// surface: registry and rule reads, rule save/preview,
// the vocabulary writes, tick() (one simulated
// evaluator + consumer pass), and the send ledger.
import type { MockStoreCtx } from "./context";
import type {
  ActionRuleView,
  FieldInput,
  ItemKindInput,
  RegistriesView,
  RulePreviewResult,
  RuleRecord,
  RuleSaveResult,
  RuleView,
  StatusCodeInput,
  TemplateInput,
  VocabResult,
  WaitClassInput,
  WouldFire,
  AttentionDataSource,
} from "../types";
import {
  clone,
  DIGEST_OWNER_LABELS,
} from "./constants";
import {
  timeLabel,
} from "./time";
import { VERB_LABELS, verbLabel } from "../verb-labels";

export function createApiRules(ctx: MockStoreCtx): Pick<AttentionDataSource, "getRegistries" | "getRules" | "saveRule" | "previewRule" | "getActionRules" | "addStatusCode" | "addField" | "addWaitClass" | "addTemplate" | "addItemKind" | "tick" | "getSends"> {
  const { state, nowIso, bump, handlerOf } = ctx;

  return {
    getRegistries(): RegistriesView {
      return {
        status_codes: clone(state.registries.status_codes),
        fields: state.registries.fields.map((f) => ({
          ...f,
          label: ctx.labels.classLabel(f.name),
        })),
        wait_classes: state.registries.wait_classes.map((c) => ({
          ...c,
          label: ctx.labels.classLabel(c.name),
        })),
        operators: clone(state.registries.operators),
        triggers: clone(state.registries.triggers),
        actions: clone(state.registries.actions),
        templates: clone(state.registries.templates),
        item_kinds: state.registries.item_kinds.map((k) => ({
          ...k,
          digest_owner_label: k.digest_owner
            ? (DIGEST_OWNER_LABELS[k.digest_owner] ?? k.digest_owner)
            : "",
        })),
        handlers: state.handlers
          .filter((h) => !h.retired)
          .map((h) => ({ handle: h.handle, label: h.label, thread_id: h.thread_id })),
      };
    },

    getRules(): RuleView[] {
      return [...state.rules]
        .sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id))
        .map(ctx.rules.ruleViewOf);
    },

    saveRule(rule: RuleRecord): RuleSaveResult {
      const stored = ctx.rules.normalizeRule(rule);
      const errors = ctx.rules.validateRule(stored);
      if (errors.length) {
        return {
          ok: false,
          error: `Rule failed validation. ${errors.join("; ")}`,
        };
      }
      const at = state.rules.findIndex((r) => r.id === stored.id);
      if (at >= 0) state.rules[at] = stored;
      else state.rules.push(stored);
      bump();
      return { ok: true, rule: ctx.rules.ruleViewOf(stored) };
    },

    previewRule(rule: RuleRecord): RulePreviewResult {
      const candidate = ctx.rules.normalizeRule(rule);
      const errors = ctx.rules.validateRule(candidate);
      if (errors.length) {
        return {
          ok: false,
          error: `Rule failed validation. ${errors.join("; ")}`,
        };
      }
      rule = candidate;
      // A dry run over the open waits: the candidate is
      // evaluated as if active; nothing is sent or decided.
      const wouldFire: WouldFire[] = [];
      for (const wait of state.waits) {
        if (wait.decision !== "surfaced") continue;
        const facts = ctx.rules.waitFacts(wait);
        if (!ctx.rules.ruleMatchesWait(rule, facts)) continue;
        const item = state.items.find((i) => i.wait_id === wait.id);
        if (rule.action.type === "post" || rule.action.type === "post_and_apply") {
          const template = rule.action.template ?? "";
          wouldFire.push({
            wait_id: wait.id,
            action: "post",
            template,
            target: item ? handlerOf(item.handle).thread_id : null,
            text: ctx.rules.renderTemplate(template, facts),
          });
        } else {
          wouldFire.push({
            wait_id: wait.id,
            action:
              rule.action.type === "auto_apply"
                ? "owner_approved"
                : rule.action.type === "hold"
                  ? "held"
                  : "surfaced",
            template: null,
            target: null,
            text: null,
          });
        }
      }
      return { ok: true, would_fire: wouldFire };
    },

    getActionRules(): ActionRuleView[] {
      const createdLabels: Record<string, string> = {
        proposal: "From a proposal",
        rule_it: "Ruled standing",
        approve_rule: "Approve + make rule",
        make_rule: "Made a rule",
      };
      return state.actionRules.map((r) => {
        const parts: string[] = [];
        if (r.match.handle) parts.push(`handler is ${r.match.handle}`);
        if (r.match.wait_class) parts.push(`class is ${ctx.labels.classLabel(r.match.wait_class)}`);
        if (r.match.kind) parts.push(`kind is ${ctx.labels.kindLabel(r.match.kind)}`);
        return {
          id: r.id,
          match_label: parts.join(" · ") || "Any item",
          verb: r.verb,
          verb_label: verbLabel(r.verb),
          mode: r.mode,
          created_from: r.created_from,
          created_label: createdLabels[r.created_from] ?? r.created_from,
          at_label: timeLabel(r.at),
        };
      });
    },

    // The vocab writes (POST /api/v1/vocab/*), mirrored
    // from the backend's writes: required fields and
    // vocabularies validated with its error lines, and a
    // registration replaces an entry of the same id.
    addStatusCode(entry: StatusCodeInput): VocabResult {
      const errors: string[] = [];
      for (const field of ["code", "short", "label", "need"] as const) {
        if (!entry[field]) errors.push(`${field} is required`);
      }
      const needs = ["owner_actionable", "agent_clearable", "unclassified"];
      if (entry.need && !needs.includes(entry.need)) errors.push("need unknown need");
      if (errors.length) {
        return { ok: false, error: `Status code failed validation. ${errors.join("; ")}` };
      }
      state.registries.status_codes = [
        ...state.registries.status_codes.filter((c) => c.code !== entry.code),
        { ...entry },
      ];
      bump();
      return { ok: true };
    },

    addField(entry: FieldInput): VocabResult {
      const errors: string[] = [];
      if (!entry.name) errors.push("name is required");
      if (!entry.type) errors.push("type is required");
      const types = ["bool", "enum", "number", "datetime", "string"];
      if (entry.type && !types.includes(entry.type)) {
        errors.push("type unknown field type");
      }
      if (errors.length) {
        return { ok: false, error: `Field failed validation. ${errors.join("; ")}` };
      }
      state.registries.fields = [
        ...state.registries.fields.filter((f) => f.name !== entry.name),
        { name: entry.name, type: entry.type, source: "poster", poster_settable: true },
      ];
      bump();
      return { ok: true };
    },

    addWaitClass(entry: WaitClassInput): VocabResult {
      if (!entry.name) {
        return { ok: false, error: "Class failed validation. name is required" };
      }
      const existing = state.registries.wait_classes.find((c) => c.name === entry.name);
      if (existing?.hard_stop) {
        return {
          ok: false,
          error: "Class failed validation. name hard-stop classes are not editable",
        };
      }
      state.registries.wait_classes = [
        ...state.registries.wait_classes.filter((c) => c.name !== entry.name),
        { name: entry.name, hard_stop: false },
      ];
      bump();
      return { ok: true };
    },

    addTemplate(entry: TemplateInput): VocabResult {
      const errors: string[] = [];
      if (!entry.kind) errors.push("kind is required");
      if (!entry.text) errors.push("text is required");
      if (!["chat", "main"].includes(entry.audience)) {
        errors.push("audience must be chat or main");
      }
      if (errors.length) {
        return { ok: false, error: `Template failed validation. ${errors.join("; ")}` };
      }
      const prior = state.registries.templates.find((t) => t.kind === entry.kind);
      state.registries.templates = [
        ...state.registries.templates.filter((t) => t.kind !== entry.kind),
        {
          kind: entry.kind,
          version: prior ? prior.version + 1 : 1,
          audience: entry.audience,
          slots: [...entry.slots],
          text: entry.text,
        },
      ];
      bump();
      return { ok: true };
    },

    addItemKind(entry: ItemKindInput): VocabResult {
      const errors: string[] = [];
      if (!entry.kind) errors.push("kind is required");
      if (!entry.label) errors.push("label is required");
      if (
        entry.digest_owner !== null &&
        !["owner", "lane", "self"].includes(entry.digest_owner)
      ) {
        errors.push("digest_owner must be owner, lane, or self");
      }
      if (errors.length) {
        return { ok: false, error: `Item kind failed validation. ${errors.join("; ")}` };
      }
      state.registries.item_kinds = [
        ...state.registries.item_kinds.filter((k) => k.kind !== entry.kind),
        { ...entry },
      ];
      bump();
      return { ok: true };
    },

    tick() {
      state.tickCount += 1;
      // Directed-control answers land first: the lane's
      // answering status post replaces its standing one.
      let answered = false;
      for (const [handle, next] of Object.entries(state.pendingStatus)) {
        state.statuses[handle] = {
          status_code: next.status_code,
          summary: next.summary,
          at: nowIso(),
        };
        answered = true;
      }
      state.pendingStatus = {};
      const a = ctx.engine.runEvaluator();
      const b = ctx.engine.runConsumer();
      if (answered || a || b) bump();
    },

    getSends: () => clone(state.sends),
  };
}
