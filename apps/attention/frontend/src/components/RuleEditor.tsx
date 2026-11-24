// The rule editor: one sheet over the stored rule record.
// Every picker serves the registries (classes, codes,
// kinds, fields, operators, triggers, actions, templates)
// — nothing is typed freehand that a registry names. Save
// and Preview both go through the store's validation,
// which mirrors the backend's: an unknown reference or a
// hard-stop breach is refused with the error in the sheet
// and nothing is stored. Preview is a dry run over the
// open waits — it sends nothing and decides nothing.
import { useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";
import { Field, Input, Select } from "@workhorse/kit/components/controls/Fields";
import { LabeledCheckbox } from "@workhorse/kit/components/controls/Checkbox";
import { useDataSource } from "../attention/useStore";
import type {
  RegistriesView,
  RuleRecord,
  WouldFire,
} from "../attention/types";

interface ConditionDraft {
  field: string;
  op: string;
  value: string;
}

const BLANK: RuleRecord = {
  id: "",
  name: null,
  match: { wait_class: null, status_code: null, kind: null, handle: null },
  where: null,
  action: { type: "surface" },
  scope: "always",
  requires: [],
  priority: 100,
  on_scope_miss: "pending",
  trigger: { on: "on_enter" },
  guards: {},
  mode: "shadow",
};

function codesOf(rule: RuleRecord): string[] {
  const sc = rule.match.status_code;
  if (!sc) return [];
  return Array.isArray(sc) ? sc : [sc];
}

function conditionsOf(rule: RuleRecord): ConditionDraft[] {
  return (rule.where?.all ?? []).map((leaf) => ({
    field: leaf.field,
    op: leaf.op,
    value: Array.isArray(leaf.value)
      ? leaf.value.join(", ")
      : String(leaf.value ?? ""),
  }));
}

const WOULD_LABEL: Record<string, string> = {
  post: "Would post",
  owner_approved: "Would approve",
  owner_denied: "Would deny",
  held: "Would hold",
  surfaced: "Would surface",
};

export function RuleEditor({
  rule,
  registries,
  onClose,
}: {
  /** The rule being edited, or null for a new rule. */
  rule: RuleRecord | null;
  registries: RegistriesView;
  onClose: () => void;
}) {
  const ds = useDataSource();
  const base = rule ?? BLANK;
  const [id, setId] = useState(base.id);
  const [name, setName] = useState(base.name ?? "");
  const [priority, setPriority] = useState(String(base.priority));
  const [mode, setMode] = useState(base.mode);
  const [scope, setScope] = useState(base.scope);
  const [waitClass, setWaitClass] = useState(base.match.wait_class ?? "");
  const [kind, setKind] = useState(base.match.kind ?? "");
  const [handle, setHandle] = useState(base.match.handle ?? "");
  const [codes, setCodes] = useState<string[]>(codesOf(base));
  const [conditions, setConditions] = useState<ConditionDraft[]>(conditionsOf(base));
  const [requires, setRequires] = useState<string[]>(base.requires);
  const [triggerOn, setTriggerOn] = useState(base.trigger.on);
  const [afterMinutes, setAfterMinutes] = useState(
    base.trigger.after_minutes != null ? String(base.trigger.after_minutes) : "",
  );
  const [count, setCount] = useState(
    base.trigger.count != null ? String(base.trigger.count) : "",
  );
  const [onMiss, setOnMiss] = useState(base.on_scope_miss);
  const [actionType, setActionType] = useState(base.action.type);
  const [template, setTemplate] = useState(base.action.template ?? "");
  const [presenceVar, setPresenceVar] = useState<Record<string, string>>(
    base.action.variants?.presence ?? {},
  );
  const [attemptVar, setAttemptVar] = useState<Record<string, string>>(
    base.action.variants?.attempt ?? {},
  );
  const [cooldown, setCooldown] = useState(
    base.guards.cooldown_minutes != null ? String(base.guards.cooldown_minutes) : "",
  );
  const [maxPosts, setMaxPosts] = useState(
    base.guards.max_posts != null ? String(base.guards.max_posts) : "",
  );
  const [escalateAfter, setEscalateAfter] = useState(
    base.guards.escalate_after != null ? String(base.guards.escalate_after) : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<WouldFire[] | null>(null);

  const isPost = actionType === "post" || actionType === "post_and_apply";
  const boolFields = registries.fields.filter(
    (f) => f.type === "bool" && f.poster_settable,
  );
  const templateOptions = [
    { value: "", label: "Default — the wait's own template" },
    ...registries.templates.map((t) => ({ value: t.kind, label: t.kind })),
  ];

  const parseValue = (c: ConditionDraft): unknown => {
    const field = registries.fields.find((f) => f.name === c.field);
    if (c.op === "exists") return true;
    const one = (text: string): unknown => {
      if (field?.type === "number") return Number(text);
      if (field?.type === "bool") return text === "true";
      return text;
    };
    if (c.op === "in" || c.op === "not_in") {
      return c.value.split(",").map((part) => one(part.trim()));
    }
    return one(c.value.trim());
  };

  const collect = (): RuleRecord => {
    const variants: RuleRecord["action"]["variants"] = {};
    const presence = Object.fromEntries(
      Object.entries(presenceVar).filter(([, v]) => v),
    );
    const attempt = Object.fromEntries(
      Object.entries(attemptVar).filter(([, v]) => v),
    );
    if (Object.keys(presence).length) variants.presence = presence;
    if (Object.keys(attempt).length) variants.attempt = attempt;
    const guards: RuleRecord["guards"] = {};
    if (cooldown !== "") guards.cooldown_minutes = Number(cooldown);
    if (maxPosts !== "") guards.max_posts = Number(maxPosts);
    if (escalateAfter !== "") guards.escalate_after = Number(escalateAfter);
    const trigger: RuleRecord["trigger"] = { on: triggerOn };
    if (triggerOn === "on_age" && afterMinutes !== "")
      trigger.after_minutes = Number(afterMinutes);
    if (triggerOn === "on_repeat" && count !== "") trigger.count = Number(count);
    return {
      id: id.trim(),
      name: name.trim() || null,
      match: {
        wait_class: waitClass || null,
        status_code: codes.length === 0 ? null : codes.length === 1 ? codes[0] : codes,
        kind: kind || null,
        handle: handle || null,
      },
      where: conditions.length
        ? { all: conditions.map((c) => ({ field: c.field, op: c.op, value: parseValue(c) })) }
        : null,
      action: {
        type: actionType,
        ...(isPost && template ? { template } : {}),
        ...(isPost && Object.keys(variants).length ? { variants } : {}),
      },
      scope,
      requires,
      priority: Number(priority) || 100,
      on_scope_miss: onMiss,
      trigger,
      guards,
      mode,
    };
  };

  const runPreview = () => {
    const result = ds.previewRule(collect());
    if (!result.ok) {
      setError(result.error);
      setPreview(null);
      return;
    }
    setError(null);
    setPreview(result.would_fire);
  };

  const save = () => {
    const result = ds.saveRule(collect());
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onClose();
  };

  const footer = (
    <>
      <Button variant="ghost" onClick={onClose}>
        Cancel
      </Button>
      <Button variant="secondary" onClick={runPreview}>
        Preview
      </Button>
      <Button variant="primary" onClick={save}>
        Save rule
      </Button>
    </>
  );

  return (
    <Sheet
      open
      title={rule ? `Rule — ${rule.name || rule.id}` : "New rule"}
      onClose={onClose}
      footer={footer}
    >
      {/* The kit Sheet's content region scrolls natively
          (kit cure); the form rides it directly. */}
      <div className="flex flex-col gap-4">
        <Field label="Rule id">
          {(fid) => (
            <Input
              id={fid}
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="e.g. lease-renewals-surface"
            />
          )}
        </Field>
        <Field label="Name (optional)">
          {(fid) => (
            <Input
              id={fid}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Falls back to the id"
            />
          )}
        </Field>
        <div className="grid grid-cols-1 gap-3 min-[481px]:grid-cols-3">
          <Field label="Priority">
            {(fid) => (
              <Input
                id={fid}
                type="number"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              />
            )}
          </Field>
          <Field label="Mode">
            {(fid) => (
              <Select
                id={fid}
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                options={[
                  { value: "shadow", label: "Shadow — log only, never acts" },
                  { value: "active", label: "Active — acts" },
                ]}
              />
            )}
          </Field>
          <Field label="Scope">
            {(fid) => (
              <Select
                id={fid}
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                options={[
                  { value: "always", label: "Always" },
                  { value: "away", label: "Away only" },
                  { value: "active", label: "Active only" },
                ]}
              />
            )}
          </Field>
        </div>

        <div className="glabel">When — the wait</div>
        <div className="grid grid-cols-1 gap-3 min-[481px]:grid-cols-3">
          <Field label="Wait class">
            {(fid) => (
              <Select
                id={fid}
                value={waitClass}
                onChange={(e) => setWaitClass(e.target.value)}
                options={[
                  { value: "", label: "Any class" },
                  ...registries.wait_classes.map((c) => ({
                    value: c.name,
                    label: c.hard_stop ? `${c.label} — hard stop` : c.label,
                  })),
                ]}
              />
            )}
          </Field>
          <Field label="Item kind">
            {(fid) => (
              <Select
                id={fid}
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                options={[
                  { value: "", label: "Any kind" },
                  ...registries.item_kinds.map((k) => ({
                    value: k.kind,
                    label: k.label,
                  })),
                ]}
              />
            )}
          </Field>
          <Field label="Handler">
            {(fid) => (
              <Select
                id={fid}
                value={handle}
                onChange={(e) => setHandle(e.target.value)}
                options={[
                  { value: "", label: "Any handler" },
                  ...registries.handlers.map((h) => ({
                    value: h.handle,
                    label: `${h.label} (${h.handle})`,
                  })),
                ]}
              />
            )}
          </Field>
        </div>
        <Field label="Thread status is one of">
          {() => (
            <div className="flex flex-col gap-1">
              {registries.status_codes.map((c) => (
                <LabeledCheckbox
                  key={c.code}
                  label={c.label}
                  checked={codes.includes(c.code)}
                  onChange={(checked) =>
                    setCodes(
                      checked
                        ? [...codes, c.code]
                        : codes.filter((x) => x !== c.code),
                    )
                  }
                />
              ))}
            </div>
          )}
        </Field>

        <div className="glabel">Conditions</div>
        {conditions.map((c, i) => (
          <div key={i} className="flex flex-wrap items-end gap-2">
            <Field label="Field" className="min-w-[8.5rem] flex-1">
              {(fid) => (
                <Select
                  id={fid}
                  value={c.field}
                  onChange={(e) =>
                    setConditions(
                      conditions.map((x, j) =>
                        j === i ? { ...x, field: e.target.value } : x,
                      ),
                    )
                  }
                  options={registries.fields.map((f) => ({
                    value: f.name,
                    label: f.label,
                  }))}
                />
              )}
            </Field>
            <Field label="Is" className="min-w-[8.5rem] flex-1">
              {(fid) => (
                <Select
                  id={fid}
                  value={c.op}
                  onChange={(e) =>
                    setConditions(
                      conditions.map((x, j) =>
                        j === i ? { ...x, op: e.target.value } : x,
                      ),
                    )
                  }
                  options={registries.operators.map((o) => ({
                    value: o.op,
                    label: o.label,
                  }))}
                />
              )}
            </Field>
            <Field label="Value" className="min-w-[8.5rem] flex-1">
              {(fid) => (
                <Input
                  id={fid}
                  value={c.value}
                  onChange={(e) =>
                    setConditions(
                      conditions.map((x, j) =>
                        j === i ? { ...x, value: e.target.value } : x,
                      ),
                    )
                  }
                />
              )}
            </Field>
            <Button
              variant="ghost"
              onClick={() => setConditions(conditions.filter((_, j) => j !== i))}
            >
              Remove
            </Button>
          </div>
        ))}
        <div>
          <Button
            variant="secondary"
            onClick={() =>
              setConditions([
                ...conditions,
                { field: registries.fields[0]?.name ?? "", op: "eq", value: "" },
              ])
            }
          >
            Add condition
          </Button>
        </div>

        {boolFields.length > 0 ? (
          <Field label="Requires — all must hold">
            {() => (
              <div className="flex flex-col gap-1">
                {boolFields.map((f) => (
                  <LabeledCheckbox
                    key={f.name}
                    label={f.label}
                    checked={requires.includes(f.name)}
                    onChange={(checked) =>
                      setRequires(
                        checked
                          ? [...requires, f.name]
                          : requires.filter((x) => x !== f.name),
                      )
                    }
                  />
                ))}
              </div>
            )}
          </Field>
        ) : null}

        <div className="grid grid-cols-1 gap-3 min-[481px]:grid-cols-2">
          <Field label="Trigger">
            {(fid) => (
              <Select
                id={fid}
                value={triggerOn}
                onChange={(e) => setTriggerOn(e.target.value)}
                options={registries.triggers.map((t) => ({
                  value: t.on,
                  label: t.label,
                }))}
              />
            )}
          </Field>
          {triggerOn === "on_age" ? (
            <Field label="After (minutes)">
              {(fid) => (
                <Input
                  id={fid}
                  type="number"
                  value={afterMinutes}
                  onChange={(e) => setAfterMinutes(e.target.value)}
                />
              )}
            </Field>
          ) : null}
          {triggerOn === "on_repeat" ? (
            <Field label="On the Nth arrival">
              {(fid) => (
                <Input
                  id={fid}
                  type="number"
                  value={count}
                  onChange={(e) => setCount(e.target.value)}
                />
              )}
            </Field>
          ) : null}
          <Field label="When the scope doesn't hold">
            {(fid) => (
              <Select
                id={fid}
                value={onMiss}
                onChange={(e) => setOnMiss(e.target.value)}
                options={[
                  { value: "pending", label: "Surface to me and wait" },
                  { value: "fallthrough", label: "Fall through to the next rule" },
                ]}
              />
            )}
          </Field>
        </div>

        <div className="glabel">Then</div>
        <Field label="Action">
          {(fid) => (
            <Select
              id={fid}
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              options={registries.actions.map((a) => ({
                value: a.type,
                label: a.label,
              }))}
            />
          )}
        </Field>
        {isPost ? (
          <>
            <Field label="Template">
              {(fid) => (
                <Select
                  id={fid}
                  value={template}
                  onChange={(e) => setTemplate(e.target.value)}
                  options={templateOptions}
                />
              )}
            </Field>
            <div className="grid grid-cols-1 gap-3 min-[481px]:grid-cols-3">
              {(["active", "focus", "away"] as const).map((mode) => (
                <Field key={mode} label={`When ${mode}`}>
                  {(fid) => (
                    <Select
                      id={fid}
                      value={presenceVar[mode] ?? ""}
                      onChange={(e) =>
                        setPresenceVar({ ...presenceVar, [mode]: e.target.value })
                      }
                      options={[
                        { value: "", label: "Use the action template" },
                        ...registries.templates.map((t) => ({
                          value: t.kind,
                          label: t.kind,
                        })),
                      ]}
                    />
                  )}
                </Field>
              ))}
            </div>
            <div className="grid grid-cols-1 gap-3 min-[481px]:grid-cols-3">
              {(
                [
                  ["attempt1", "First attempt"],
                  ["attempt2", "Second attempt"],
                  ["final", "Final attempt"],
                ] as const
              ).map(([key, label]) => (
                <Field key={key} label={label}>
                  {(fid) => (
                    <Select
                      id={fid}
                      value={attemptVar[key] ?? ""}
                      onChange={(e) =>
                        setAttemptVar({ ...attemptVar, [key]: e.target.value })
                      }
                      options={[
                        { value: "", label: "Use the action template" },
                        ...registries.templates.map((t) => ({
                          value: t.kind,
                          label: t.kind,
                        })),
                      ]}
                    />
                  )}
                </Field>
              ))}
            </div>
          </>
        ) : null}

        <div className="glabel">Guards</div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Cooldown (minutes)">
            {(fid) => (
              <Input
                id={fid}
                type="number"
                value={cooldown}
                onChange={(e) => setCooldown(e.target.value)}
              />
            )}
          </Field>
          <Field label="Max posts">
            {(fid) => (
              <Input
                id={fid}
                type="number"
                value={maxPosts}
                onChange={(e) => setMaxPosts(e.target.value)}
              />
            )}
          </Field>
          <Field label="Escalate to Main after">
            {(fid) => (
              <Input
                id={fid}
                type="number"
                value={escalateAfter}
                onChange={(e) => setEscalateAfter(e.target.value)}
              />
            )}
          </Field>
        </div>

        {preview !== null ? (
          <div>
            <div className="glabel">Preview — against the open waits now</div>
            {preview.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
                This rule would not fire on any open wait.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {preview.map((w) => (
                  <div key={w.wait_id} className="text-sm">
                    <span style={{ color: "var(--wb-content-primary)" }}>
                      {WOULD_LABEL[w.action] ?? w.action}
                    </span>
                    <span style={{ color: "var(--wb-content-secondary)" }}>
                      {" "}
                      · {w.wait_id}
                      {w.target ? ` · to ${w.target}` : ""}
                    </span>
                    {w.text ? (
                      <div style={{ color: "var(--wb-content-secondary)" }}>{w.text}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}

        {error ? (
          <p
            className="text-sm"
            role="alert"
            style={{ color: "var(--wb-status-hard-gate-text)" }}
          >
            {error}
          </p>
        ) : null}
      </div>
    </Sheet>
  );
}
