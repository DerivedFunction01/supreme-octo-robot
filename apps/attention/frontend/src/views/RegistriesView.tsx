// Registries (the vocabulary surface): the status codes,
// fields, wait classes, templates and item kinds the
// rules match over — listed with their add forms, as in
// the original surface ("added here, never in code").
// Every add posts through the seam (POST /api/v1/vocab/*):
// the store validates with the backend's error lines, and
// a registration replaces an entry of the same id, so a
// correction is a re-add. The action rules the learning
// loop has created are listed read-only at the foot —
// they are born from taps, never typed in.
import { useState, type ReactNode } from "react";
import { useDataSource, useStoreVersion } from "../attention/useStore";
import type { VocabResult } from "../attention/types";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Field, Input, Select } from "@workhorse/kit/components/controls/Fields";
import { LabeledCheckbox } from "@workhorse/kit/components/controls/Checkbox";
import { Group, GroupLabel, Row, RowText, RowValue } from "../components/groups";
import { LargeTitle } from "../components/LargeTitle";

function AddForm({
  error,
  submitLabel,
  onSubmit,
  children,
}: {
  error: string | null;
  submitLabel: string;
  onSubmit: () => void;
  children: ReactNode;
}) {
  return (
    <Group>
      <Row padded>
        <div className="flex w-full flex-col gap-3">
          {children}
          {error ? (
            <p
              className="text-sm"
              role="alert"
              style={{ color: "var(--ui-status-hard-gate-text)" }}
            >
              {error}
            </p>
          ) : null}
          <div>
            <Button variant="primary" onClick={onSubmit}>
              {submitLabel}
            </Button>
          </div>
        </div>
      </Row>
    </Group>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <Field label={label}>
      {(id) => (
        <Input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
        />
      )}
    </Field>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <Field label={label}>
      {(id) => (
        <Select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          options={options}
        />
      )}
    </Field>
  );
}

export function RegistriesView() {
  useStoreVersion();
  const ds = useDataSource();
  const registries = ds.getRegistries();
  const actionRules = ds.getActionRules();

  // One form state per vocabulary; each submit posts and
  // either clears (the new entry lists above) or surfaces
  // the store's validation error under its own form.
  const [code, setCode] = useState({ code: "", short: "", label: "", need: "owner_actionable", terminal: false });
  const [codeError, setCodeError] = useState<string | null>(null);
  const [field, setField] = useState({ name: "", type: "string" });
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [cls, setCls] = useState("");
  const [clsError, setClsError] = useState<string | null>(null);
  const [template, setTemplate] = useState({ kind: "", audience: "chat", slots: "", text: "" });
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [kind, setKind] = useState({ kind: "", label: "", status_kind: false, digest_owner: "" });
  const [kindError, setKindError] = useState<string | null>(null);

  const settle = (
    result: VocabResult,
    setError: (e: string | null) => void,
    clear: () => void,
  ) => {
    if (result.ok) {
      setError(null);
      clear();
    } else {
      setError(result.error);
    }
  };

  return (
    <div className="registries-view">
      <LargeTitle
        title="Registries"
        subtitle="The vocabulary the rules match over — added here, never in code"
      />

      <GroupLabel>Status codes · {registries.status_codes.length}</GroupLabel>
      <Group>
        {registries.status_codes.map((c) => (
          <Row key={c.code}>
            <RowText
              label={`${c.label} (${c.code})`}
              sub={`Need · ${c.need}${c.terminal ? " · Terminal" : ""}`}
            />
            <RowValue>{c.short}</RowValue>
          </Row>
        ))}
      </Group>
      <AddForm
        error={codeError}
        submitLabel="Add status code"
        onSubmit={() =>
          settle(ds.addStatusCode(code), setCodeError, () =>
            setCode({ code: "", short: "", label: "", need: "owner_actionable", terminal: false }),
          )
        }
      >
        <TextField label="Code" value={code.code} onChange={(v) => setCode({ ...code, code: v })} placeholder="e.g. stalled" />
        <TextField label="Short" value={code.short} onChange={(v) => setCode({ ...code, short: v })} placeholder="e.g. STL" />
        <TextField label="Label" value={code.label} onChange={(v) => setCode({ ...code, label: v })} />
        <SelectField
          label="Need"
          value={code.need}
          onChange={(v) => setCode({ ...code, need: v })}
          options={[
            { value: "owner_actionable", label: "Owner actionable" },
            { value: "agent_clearable", label: "Agent clearable" },
            { value: "unclassified", label: "Unclassified" },
          ]}
        />
        <LabeledCheckbox
          label="Terminal"
          checked={code.terminal}
          onChange={(checked) => setCode({ ...code, terminal: checked })}
        />
      </AddForm>

      <GroupLabel>Fields · {registries.fields.length}</GroupLabel>
      <Group>
        {registries.fields.map((f) => (
          <Row key={f.name}>
            <RowText
              label={f.label}
              sub={`${f.type} · ${f.source}${f.poster_settable ? " · Poster-settable" : ""}`}
            />
          </Row>
        ))}
      </Group>
      <AddForm
        error={fieldError}
        submitLabel="Add field"
        onSubmit={() =>
          settle(ds.addField(field), setFieldError, () => setField({ name: "", type: "string" }))
        }
      >
        <TextField label="Name" value={field.name} onChange={(v) => setField({ ...field, name: v })} placeholder="e.g. progress" />
        <SelectField
          label="Type"
          value={field.type}
          onChange={(v) => setField({ ...field, type: v })}
          options={[
            { value: "bool", label: "Bool" },
            { value: "enum", label: "Enum" },
            { value: "number", label: "Number" },
            { value: "string", label: "String" },
            { value: "datetime", label: "Datetime" },
          ]}
        />
      </AddForm>

      <GroupLabel>Wait classes · {registries.wait_classes.length}</GroupLabel>
      <Group>
        {registries.wait_classes.map((c) => (
          <Row key={c.name}>
            <RowText label={c.label} sub={c.hard_stop ? "Hard stop" : "Approvable"} />
          </Row>
        ))}
      </Group>
      <AddForm
        error={clsError}
        submitLabel="Add class"
        onSubmit={() => settle(ds.addWaitClass({ name: cls }), setClsError, () => setCls(""))}
      >
        <TextField label="Name" value={cls} onChange={setCls} placeholder="e.g. vendor_reply" />
      </AddForm>

      <GroupLabel>Templates · {registries.templates.length}</GroupLabel>
      <Group>
        {registries.templates.map((t) => (
          <Row key={t.kind}>
            <RowText label={t.kind} sub={`${t.audience} · v${t.version} · ${t.text}`} />
          </Row>
        ))}
      </Group>
      <AddForm
        error={templateError}
        submitLabel="Add template"
        onSubmit={() =>
          settle(
            ds.addTemplate({
              kind: template.kind,
              audience: template.audience,
              slots: template.slots.split(",").map((s) => s.trim()).filter(Boolean),
              text: template.text,
            }),
            setTemplateError,
            () => setTemplate({ kind: "", audience: "chat", slots: "", text: "" }),
          )
        }
      >
        <TextField label="Kind" value={template.kind} onChange={(v) => setTemplate({ ...template, kind: v })} placeholder="e.g. decision-reply" />
        <SelectField
          label="Audience"
          value={template.audience}
          onChange={(v) => setTemplate({ ...template, audience: v })}
          options={[
            { value: "chat", label: "Chat" },
            { value: "main", label: "Main" },
          ]}
        />
        <TextField label="Slots (comma-separated)" value={template.slots} onChange={(v) => setTemplate({ ...template, slots: v })} />
        <TextField label="Text" value={template.text} onChange={(v) => setTemplate({ ...template, text: v })} />
      </AddForm>

      <GroupLabel>Item kinds · {registries.item_kinds.length}</GroupLabel>
      <Group>
        {registries.item_kinds.map((k) => (
          <Row key={k.kind}>
            <RowText
              label={k.label}
              sub={`${k.kind}${k.status_kind ? " · Status kind" : ""} · Digest: ${k.digest_owner_label}`}
            />
          </Row>
        ))}
      </Group>
      <AddForm
        error={kindError}
        submitLabel="Add item kind"
        onSubmit={() =>
          settle(
            ds.addItemKind({
              kind: kind.kind,
              label: kind.label,
              status_kind: kind.status_kind,
              digest_owner: kind.digest_owner === "" ? null : kind.digest_owner,
            }),
            setKindError,
            () => setKind({ kind: "", label: "", status_kind: false, digest_owner: "" }),
          )
        }
      >
        <TextField label="Kind" value={kind.kind} onChange={(v) => setKind({ ...kind, kind: v })} placeholder="e.g. milestone" />
        <TextField label="Label" value={kind.label} onChange={(v) => setKind({ ...kind, label: v })} />
        <SelectField
          label="Digest owner"
          value={kind.digest_owner}
          onChange={(v) => setKind({ ...kind, digest_owner: v })}
          options={[
            { value: "", label: "—" },
            { value: "owner", label: "Owner" },
            { value: "lane", label: "Lane" },
            { value: "self", label: "Self" },
          ]}
        />
        <LabeledCheckbox
          label="Status kind"
          checked={kind.status_kind}
          onChange={(checked) => setKind({ ...kind, status_kind: checked })}
        />
      </AddForm>

      <GroupLabel>Action rules · {actionRules.length}</GroupLabel>
      <Group>
        {actionRules.length > 0 ? (
          actionRules.map((r) => (
            <Row key={r.id}>
              <RowText
                label={`${r.verb_label} — ${r.match_label}`}
                sub={`${r.created_label} · ${r.at_label}`}
              />
              <RowValue>{r.mode === "shadow" ? "Shadow" : "Active"}</RowValue>
            </Row>
          ))
        ) : (
          <Row>
            <RowText
              label="No action rules yet"
              sub="Repeated taps propose them; Rule it, Approve + make rule and the make-a-rule tap create them."
            />
          </Row>
        )}
      </Group>
    </div>
  );
}
