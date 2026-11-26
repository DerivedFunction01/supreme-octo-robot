// Rule editor drawer — the original's openDrawer():
// the full rule editor in a sheet — match, conditions,
// requires, trigger, action with template variants,
// guards — with the dry-run Preview. collect() builds
// the rule record exactly as the original's collect()
// did; the backend validates. (The editor's own module:
// rules.tsx carries the grouped tables and the banner,
// this file the editor they open.)

import { useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { LabeledCheckbox } from "@workhorse/kit/components/controls/Checkbox";
import { Field, Input, Select } from "@workhorse/kit/components/controls/Fields";
import { GroupLabel } from "@workhorse/kit/components/display/GroupedList";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";
import {
  type AttentionRule,
  type PreviewPayload,
  type RegistriesPayload,
  type RuleCondition,
} from "./model";
import { api, call } from "./transport";
import { BandHead, useAttentionUi } from "./ui";

/** Presence scopes, in banner order — the view groups
 *  its tables by these and the editor's scope select
 *  offers them. */
export const SCOPES: [string, string][] = [
  ["always", "Always"],
  ["away", "Away only"],
  ["active", "Active only"],
];


interface CondRowState {
  field: string;
  op: string;
  value: string;
}

interface RuleForm {
  id: string;
  name: string;
  priority: string;
  mode: string;
  scope: string;
  waitClass: string;
  statusCodes: string[];
  kind: string;
  handle: string;
  conds: CondRowState[];
  requires: string[];
  triggerOn: string;
  triggerN: string;
  onScopeMiss: string;
  actionType: string;
  template: string;
  varActive: string;
  varFocus: string;
  varAway: string;
  varFirst: string;
  varRepeat: string;
  cooldown: string;
  maxPosts: string;
  escalateAfter: string;
}

const DEFAULT_RULE: AttentionRule = {
  id: "",
  name: null,
  match: {},
  where: null,
  action: { type: "auto_apply" },
  scope: "always",
  requires: [],
  priority: 100,
  on_scope_miss: "pending",
  trigger: { on: "on_enter" },
  guards: {},
  mode: "shadow",
};

function formFrom(rule: AttentionRule | null): RuleForm {
  const r = rule ?? DEFAULT_RULE;
  const a = typeof r.action === "string" ? { type: r.action as string } : r.action;
  const variants = a.variants ?? {};
  const guards = r.guards ?? {};
  const leaves =
    r.where && "all" in r.where && r.where.all
      ? r.where.all
      : r.where
        ? [r.where as RuleCondition]
        : [];
  const codes = Array.isArray(r.match.status_code)
    ? r.match.status_code
    : r.match.status_code
      ? [r.match.status_code]
      : [];
  return {
    id: r.id,
    name: r.name ?? "",
    priority: String(r.priority ?? 100),
    mode: r.mode ?? "shadow",
    scope: r.scope ?? "always",
    waitClass: r.match.wait_class ?? "",
    statusCodes: codes,
    kind: r.match.kind ?? "",
    handle: r.match.handle ?? "",
    conds: (leaves as RuleCondition[]).map((c) => ({
      field: c.field ?? "",
      op: c.op ?? "",
      value: Array.isArray(c.value) ? c.value.join(", ") : c.value == null ? "" : String(c.value),
    })),
    requires: [...(r.requires ?? [])],
    triggerOn: r.trigger?.on ?? "on_enter",
    triggerN: String(r.trigger?.after_minutes ?? r.trigger?.count ?? ""),
    onScopeMiss: r.on_scope_miss ?? "pending",
    actionType: a.type,
    template: a.template ?? "",
    varActive: variants.presence?.active ?? "",
    varFocus: variants.presence?.focus ?? "",
    varAway: variants.presence?.away ?? "",
    varFirst: variants.attempt?.first ?? "",
    varRepeat: variants.attempt?.repeat ?? "",
    cooldown: String(guards.cooldown_minutes ?? ""),
    maxPosts: String(guards.max_posts ?? ""),
    escalateAfter: String(guards.escalate_after ?? ""),
  };
}

export function RuleDrawer({
  rule,
  reg,
  onClose,
}: {
  rule: AttentionRule | null;
  reg: RegistriesPayload;
  onClose: () => void;
}) {
  const ui = useAttentionUi();
  const [form, setForm] = useState<RuleForm>(() => formFrom(rule));
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewPayload | null>(null);
  const set = (patch: Partial<RuleForm>) => setForm((f) => ({ ...f, ...patch }));

  const isPost = ["post", "post_and_apply"].includes(form.actionType);
  const boolFields = reg.fields.filter((f) => f.type === "bool" && f.poster_settable);
  const kindOptions = reg.item_kinds.filter((k) =>
    ["decision", "action", "defect", "approval", "fyi"].includes(k.kind),
  );
  const anyOpt = [{ value: "", label: "Any" }];
  const templateOptions = [
    { value: "", label: "Any" },
    ...reg.templates.map((t) => ({ value: t.kind, label: t.kind })),
  ];

  /** The original's collect(): the record the backend
   *  validates — unknown fields of an edited rule ride
   *  along; the served display labels are stripped. */
  function collect(): Record<string, unknown> {
    const out: Record<string, unknown> = JSON.parse(
      JSON.stringify(rule ?? DEFAULT_RULE),
    ) as Record<string, unknown>;
    const prevAction =
      typeof out.action === "object" && out.action !== null
        ? (out.action as Record<string, unknown>)
        : {};
    const action: Record<string, unknown> = { ...prevAction, type: form.actionType };
    if (isPost) {
      action.template = form.template;
      const presence: Record<string, string> = {};
      if (form.varActive) presence.active = form.varActive;
      if (form.varFocus) presence.focus = form.varFocus;
      if (form.varAway) presence.away = form.varAway;
      const attempt: Record<string, string> = {};
      if (form.varFirst) attempt.first = form.varFirst;
      if (form.varRepeat) attempt.repeat = form.varRepeat;
      const variants: Record<string, unknown> = {};
      if (Object.keys(presence).length) variants.presence = presence;
      if (Object.keys(attempt).length) variants.attempt = attempt;
      if (Object.keys(variants).length) action.variants = variants;
      else delete action.variants;
    }
    const trig: Record<string, unknown> = { on: form.triggerOn };
    if (form.triggerN) {
      if (form.triggerOn === "on_age") trig.after_minutes = Number(form.triggerN);
      if (form.triggerOn === "on_repeat") trig.count = Number(form.triggerN);
    }
    const leaves = form.conds
      .filter((c) => c.field)
      .map((c) => {
        let value: unknown = c.value;
        const fdef = reg.fields.find((f) => f.name === c.field);
        if (c.op === "in" || c.op === "not_in")
          value = c.value.split(",").map((s) => s.trim());
        else if (fdef && fdef.type === "number") value = Number(c.value);
        else if (fdef && fdef.type === "bool") value = c.value === "true";
        return { field: c.field, op: c.op, value };
      });
    const guards: Record<string, number> = {};
    if (form.cooldown !== "") guards.cooldown_minutes = Number(form.cooldown);
    if (form.maxPosts !== "") guards.max_posts = Number(form.maxPosts);
    if (form.escalateAfter !== "") guards.escalate_after = Number(form.escalateAfter);
    const val = (s: string) => (s.trim() === "" ? null : s.trim());
    out.id = form.id.trim();
    out.name = val(form.name);
    out.match = {
      wait_class: val(form.waitClass),
      status_code:
        form.statusCodes.length > 1 ? form.statusCodes : (form.statusCodes[0] ?? null),
      kind: val(form.kind),
      handle: val(form.handle),
    };
    out.where = leaves.length ? { all: leaves } : null;
    out.action = action;
    out.scope = form.scope;
    out.requires = form.requires;
    out.priority = Number(form.priority) || 100;
    out.on_scope_miss = form.onScopeMiss;
    out.trigger = trig;
    out.guards = guards;
    out.mode = form.mode;
    delete out.display_name;
    delete out.when_label;
    delete out.then_label;
    return out;
  }

  async function onPreview() {
    setError(null);
    try {
      const d = await call<PreviewPayload>(api.previewRule({ rule: collect() }));
      setPreview(d);
    } catch (e) {
      setError(`Preview refused: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function onSave() {
    setError(null);
    try {
      const saved = await call<{ id: string; mode: string }>(api.addRule({ body: collect() }));
      ui.notify(`Rule saved — ${saved.id} (${saved.mode})`);
      onClose();
      ui.refresh();
    } catch (e) {
      setError(`Rule refused: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <Sheet
      open
      title={rule ? `Rule — ${rule.display_name || rule.id}` : "New rule"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={() => void onPreview()}>
            Preview
          </Button>
          <Button variant="primary" onClick={() => void onSave()}>
            Save rule
          </Button>
        </>
      }
    >
      <GroupLabel>When</GroupLabel>
      <div className="flex flex-col gap-3">
        <Field label="Rule id">
          {(id) => (
            <Input
              id={id}
              value={form.id}
              readOnly={Boolean(rule)}
              onChange={(e) => set({ id: e.target.value })}
            />
          )}
        </Field>
        <Field label="Display name">
          {(id) => (
            <Input
              id={id}
              value={form.name}
              placeholder="Composed from the id when blank"
              onChange={(e) => set({ name: e.target.value })}
            />
          )}
        </Field>
        <Field label="Priority (lower decides first)">
          {(id) => (
            <Input
              id={id}
              type="number"
              value={form.priority}
              onChange={(e) => set({ priority: e.target.value })}
            />
          )}
        </Field>
        <Field label="Mode">
          {(id) => (
            <Select
              id={id}
              value={form.mode}
              onChange={(e) => set({ mode: e.target.value })}
              options={[
                { value: "shadow", label: "Shadow — records what it would do" },
                { value: "active", label: "Active" },
              ]}
            />
          )}
        </Field>
        <Field label="Presence scope">
          {(id) => (
            <Select
              id={id}
              value={form.scope}
              onChange={(e) => set({ scope: e.target.value })}
              options={SCOPES.map(([v, l]) => ({ value: v, label: l }))}
            />
          )}
        </Field>
        <Field label="Match — wait class">
          {(id) => (
            <Select
              id={id}
              value={form.waitClass}
              onChange={(e) => set({ waitClass: e.target.value })}
              options={[
                ...anyOpt,
                ...reg.wait_classes.map((c) => ({ value: c.name, label: c.label || c.name })),
              ]}
            />
          )}
        </Field>
        <Field label="Match — status codes">
          {() => (
            <div>
              {reg.status_codes.map((c) => (
                <LabeledCheckbox
                  key={c.code}
                  label={c.label}
                  checked={form.statusCodes.includes(c.code)}
                  onChange={(checked) =>
                    set({
                      statusCodes: checked
                        ? [...form.statusCodes, c.code]
                        : form.statusCodes.filter((x) => x !== c.code),
                    })
                  }
                />
              ))}
            </div>
          )}
        </Field>
        <Field label="Match — kind">
          {(id) => (
            <Select
              id={id}
              value={form.kind}
              onChange={(e) => set({ kind: e.target.value })}
              options={[...anyOpt, ...kindOptions.map((k) => ({ value: k.kind, label: k.label }))]}
            />
          )}
        </Field>
        <Field label="Match — handler">
          {(id) => (
            <Select
              id={id}
              value={form.handle}
              onChange={(e) => set({ handle: e.target.value })}
              options={[
                ...anyOpt,
                ...reg.handlers.map((h) => ({ value: h.handle, label: h.label })),
              ]}
            />
          )}
        </Field>
      </div>

      <GroupLabel>Conditions</GroupLabel>
      <div className="flex flex-col gap-3">
        <Field label="All must hold">
          {() => (
            <div className="flex flex-col gap-2">
              {form.conds.map((c, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Select
                    ariaLabel="Field"
                    value={c.field}
                    onChange={(e) =>
                      set({
                        conds: form.conds.map((x, j) =>
                          j === i ? { ...x, field: e.target.value } : x,
                        ),
                      })
                    }
                    options={[
                      ...anyOpt,
                      ...reg.fields.map((f) => ({ value: f.name, label: f.label || f.name })),
                    ]}
                  />
                  <Select
                    ariaLabel="Operator"
                    value={c.op}
                    onChange={(e) =>
                      set({
                        conds: form.conds.map((x, j) =>
                          j === i ? { ...x, op: e.target.value } : x,
                        ),
                      })
                    }
                    options={reg.operators.map((o) => ({ value: o.op, label: o.label }))}
                  />
                  <Input
                    ariaLabel="Value"
                    value={c.value}
                    onChange={(e) =>
                      set({
                        conds: form.conds.map((x, j) =>
                          j === i ? { ...x, value: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <Button
                    variant="ghost"
                    ariaLabel="Remove condition"
                    onClick={() => set({ conds: form.conds.filter((_, j) => j !== i) })}
                  >
                    ×
                  </Button>
                </div>
              ))}
              <div>
                <Button
                  variant="secondary"
                  onClick={() =>
                    set({
                      conds: [
                        ...form.conds,
                        { field: "", op: reg.operators[0]?.op ?? "", value: "" },
                      ],
                    })
                  }
                >
                  Add condition
                </Button>
              </div>
            </div>
          )}
        </Field>
        <Field label="Requires — flags that must all hold">
          {() => (
            <div>
              {boolFields.map((f) => (
                <LabeledCheckbox
                  key={f.name}
                  label={f.label || f.name}
                  checked={form.requires.includes(f.name)}
                  onChange={(checked) =>
                    set({
                      requires: checked
                        ? [...form.requires, f.name]
                        : form.requires.filter((x) => x !== f.name),
                    })
                  }
                />
              ))}
            </div>
          )}
        </Field>
      </div>

      <GroupLabel>Trigger</GroupLabel>
      <div className="flex flex-col gap-3">
        <Field label="Trigger">
          {(id) => (
            <Select
              id={id}
              value={form.triggerOn}
              onChange={(e) => set({ triggerOn: e.target.value })}
              options={reg.triggers.map((t) => ({ value: t.on, label: t.label }))}
            />
          )}
        </Field>
        <Field label="Trigger minutes / count">
          {(id) => (
            <Input
              id={id}
              type="number"
              value={form.triggerN}
              onChange={(e) => set({ triggerN: e.target.value })}
            />
          )}
        </Field>
        <Field label="On scope miss">
          {(id) => (
            <Select
              id={id}
              value={form.onScopeMiss}
              onChange={(e) => set({ onScopeMiss: e.target.value })}
              options={[
                { value: "pending", label: "Hold as pending" },
                { value: "fallthrough", label: "Fall through to the next rule" },
              ]}
            />
          )}
        </Field>
      </div>

      <GroupLabel>Then</GroupLabel>
      <div className="flex flex-col gap-3">
        <Field label="Action">
          {(id) => (
            <Select
              id={id}
              value={form.actionType}
              onChange={(e) => set({ actionType: e.target.value })}
              options={reg.actions.map((t) => ({ value: t.type, label: t.label }))}
            />
          )}
        </Field>
        {isPost ? (
          <>
            <Field label="Template">
              {(id) => (
                <Select
                  id={id}
                  value={form.template}
                  onChange={(e) => set({ template: e.target.value })}
                  options={reg.templates.map((t) => ({ value: t.kind, label: t.kind }))}
                />
              )}
            </Field>
            <Field label="Template when Active">
              {(id) => (
                <Select
                  id={id}
                  value={form.varActive}
                  onChange={(e) => set({ varActive: e.target.value })}
                  options={templateOptions}
                />
              )}
            </Field>
            <Field label="Template when Focus">
              {(id) => (
                <Select
                  id={id}
                  value={form.varFocus}
                  onChange={(e) => set({ varFocus: e.target.value })}
                  options={templateOptions}
                />
              )}
            </Field>
            <Field label="Template when Away">
              {(id) => (
                <Select
                  id={id}
                  value={form.varAway}
                  onChange={(e) => set({ varAway: e.target.value })}
                  options={templateOptions}
                />
              )}
            </Field>
            <Field label="Template on first post">
              {(id) => (
                <Select
                  id={id}
                  value={form.varFirst}
                  onChange={(e) => set({ varFirst: e.target.value })}
                  options={templateOptions}
                />
              )}
            </Field>
            <Field label="Template on repeat posts">
              {(id) => (
                <Select
                  id={id}
                  value={form.varRepeat}
                  onChange={(e) => set({ varRepeat: e.target.value })}
                  options={templateOptions}
                />
              )}
            </Field>
          </>
        ) : null}
      </div>

      <GroupLabel>Guards</GroupLabel>
      <div className="flex flex-col gap-3">
        <Field label="Cooldown (minutes between posts)">
          {(id) => (
            <Input
              id={id}
              type="number"
              value={form.cooldown}
              onChange={(e) => set({ cooldown: e.target.value })}
            />
          )}
        </Field>
        <Field label="Max posts per wait">
          {(id) => (
            <Input
              id={id}
              type="number"
              value={form.maxPosts}
              onChange={(e) => set({ maxPosts: e.target.value })}
            />
          )}
        </Field>
        <Field label="Escalate to Main after N posts">
          {(id) => (
            <Input
              id={id}
              type="number"
              value={form.escalateAfter}
              onChange={(e) => set({ escalateAfter: e.target.value })}
            />
          )}
        </Field>
      </div>

      {error ? (
        <p className="mt-4 text-sm" style={{ color: "var(--ui-status-hard-gate-text)" }} role="alert">
          {error}
        </p>
      ) : null}

      {preview ? (
        <div className="mt-4">
          <BandHead label="Preview — dry run, nothing was sent or decided" />
          {preview.would_fire.length ? (
            preview.would_fire.map((w, i) => (
              <p key={i} className="mb-2 text-sm [overflow-wrap:anywhere]">
                <b>{w.wait_id}</b> · {w.action}
                {w.template ? ` · ${w.template}` : ""}
                {w.text ? (
                  <span className="block" style={{ color: "var(--ui-content-secondary)" }}>
                    {w.text}
                  </span>
                ) : null}
              </p>
            ))
          ) : (
            <p className="text-sm" style={{ color: "var(--ui-content-secondary)" }}>
              This rule would not fire on anything currently waiting.
            </p>
          )}
        </div>
      ) : null}
    </Sheet>
  );
}
