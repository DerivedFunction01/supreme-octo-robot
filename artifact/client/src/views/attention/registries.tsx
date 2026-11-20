// Registries — the original's renderRegistries(): the
// vocabulary the rules match over, in five sections —
// status codes, condition fields, wait classes, post
// templates, item kinds — each a table (or cards, for
// templates) plus its add form. Adds post to the vocab
// actions, note, and reload the portion; refusals note
// "Refused: …" (the original's forms, verbatim in
// substance).

import { useState, type ReactNode } from "react";
import { Button } from "@workhorse/kit/components/Button";
import { Card } from "@workhorse/kit/components/Card";
import { LabeledCheckbox } from "@workhorse/kit/components/Checkbox";
import { DataTable } from "@workhorse/kit/components/DataTable";
import { EmptyState } from "@workhorse/kit/components/EmptyState";
import { Field, Input, Select } from "@workhorse/kit/components/Fields";
import { StatusChip } from "@workhorse/kit/components/StatusChip";
import type { RegistriesPayload } from "./model";
import { api, call, staleText, usePortion } from "./transport";
import { BandHead, PageColumn, ScopeLine, useAttentionUi } from "./ui";

export function RegistriesView() {
  const ui = useAttentionUi();
  const portion = usePortion<RegistriesPayload>(
    "registries",
    () => call(api.getRegistries({})),
    ui.refreshKey,
  );

  if (!portion.data) {
    return (
      <PageColumn>
        {portion.loading ? (
          <ScopeLine>Loading…</ScopeLine>
        ) : (
          <EmptyState message="Registries could not be loaded." />
        )}
      </PageColumn>
    );
  }

  const d = portion.data;

  async function post(
    result: Promise<{ status: number; payload: unknown; error: string | null }>,
    msg: string,
  ) {
    try {
      await call(result);
      ui.notify(msg);
      portion.refresh();
    } catch (e) {
      ui.notify(`Refused: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <PageColumn>
      <ScopeLine>
        The vocabulary the rules match over — added here, never in code{staleText(portion.stale)}
      </ScopeLine>

      <section>
        <BandHead label="Status codes" />
        <DataTable
          ariaLabel="Status codes"
          columns={[
            { key: "code", header: "Code", render: (c) => <b>{c.code}</b> },
            { key: "short", header: "Short" },
            { key: "label", header: "Label" },
            { key: "need", header: "Need" },
            { key: "terminal", header: "Terminal", render: (c) => (c.terminal ? "yes" : "—") },
          ]}
          rows={d.status_codes}
          rowKey={(c) => c.code}
        />
        <AddCard>
          <StatusCodeForm onAdd={(body, msg) => void post(api.addVocabStatusCode({ body }), msg)} />
        </AddCard>
      </section>

      <section>
        <BandHead label="Condition fields" />
        <DataTable
          ariaLabel="Condition fields"
          columns={[
            { key: "name", header: "Field", render: (f) => <b>{f.name}</b> },
            { key: "type", header: "Type" },
            { key: "source", header: "Source" },
            {
              key: "poster_settable",
              header: "Poster-settable",
              render: (f) => (f.poster_settable ? "yes" : "never"),
            },
          ]}
          rows={d.fields}
          rowKey={(f) => f.name}
        />
        <AddCard>
          <FieldForm onAdd={(body, msg) => void post(api.addVocabField({ body }), msg)} />
        </AddCard>
      </section>

      <section>
        <BandHead label="Wait classes" />
        <DataTable
          ariaLabel="Wait classes"
          columns={[
            { key: "name", header: "Class", render: (c) => <b>{c.name}</b> },
            {
              key: "hard_stop",
              header: "Hard stop",
              render: (c) =>
                c.hard_stop ? <StatusChip tone="fail" label="hard stop" /> : "—",
            },
          ]}
          rows={d.wait_classes}
          rowKey={(c) => c.name}
        />
        <AddCard>
          <ClassForm onAdd={(body, msg) => void post(api.addVocabClass({ body }), msg)} />
        </AddCard>
      </section>

      <section>
        <BandHead label="Post templates" />
        {d.templates.map((t) => (
          <Card key={t.kind} className="mb-3">
            <p className="text-sm">
              <b>{t.kind}</b>{" "}
              <span style={{ color: "var(--wb-content-secondary)" }}>
                v{t.version} · {t.audience} · slots: {t.slots.join(", ") || "none"}
              </span>
            </p>
            <p className="mt-1 text-sm [overflow-wrap:anywhere]">{t.text}</p>
          </Card>
        ))}
        <AddCard>
          <TemplateForm onAdd={(body, msg) => void post(api.addVocabTemplate({ body }), msg)} />
        </AddCard>
      </section>

      <section>
        <BandHead label="Item kinds" />
        <DataTable
          ariaLabel="Item kinds"
          columns={[
            { key: "kind", header: "Kind", render: (k) => <b>{k.kind}</b> },
            { key: "label", header: "Label" },
            {
              key: "status_kind",
              header: "Status kind",
              render: (k) => (k.status_kind ? "yes" : "—"),
            },
            {
              key: "digest_owner_label",
              header: "Digest placement",
              render: (k) => k.digest_owner_label || "—",
            },
          ]}
          rows={d.item_kinds ?? []}
          rowKey={(k) => k.kind}
        />
        <AddCard>
          <KindForm onAdd={(body, msg) => void post(api.addVocabKind({ body }), msg)} />
        </AddCard>
      </section>
    </PageColumn>
  );
}

function AddCard({ children }: { children: ReactNode }) {
  return <Card className="mt-3 mb-2">{children}</Card>;
}

type AddFn = (body: Record<string, unknown>, msg: string) => void;

function StatusCodeForm({ onAdd }: { onAdd: AddFn }) {
  const [code, setCode] = useState("");
  const [short, setShort] = useState("");
  const [label, setLabel] = useState("");
  const [need, setNeed] = useState("owner_actionable");
  const [terminal, setTerminal] = useState(false);
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Input ariaLabel="New code" placeholder="CODE" value={code} onChange={(e) => setCode(e.target.value)} />
      <Input ariaLabel="Short" placeholder="Short" value={short} onChange={(e) => setShort(e.target.value)} />
      <Input ariaLabel="Label" placeholder="Label" value={label} onChange={(e) => setLabel(e.target.value)} />
      <Select
        ariaLabel="Need"
        value={need}
        onChange={(e) => setNeed(e.target.value)}
        options={[
          { value: "owner_actionable", label: "owner_actionable" },
          { value: "agent_clearable", label: "agent_clearable" },
          { value: "unclassified", label: "unclassified" },
        ]}
      />
      <LabeledCheckbox label="terminal" checked={terminal} onChange={setTerminal} />
      <Button
        variant="secondary"
        onClick={() =>
          onAdd(
            { code: code.trim(), short: short.trim(), label: label.trim(), need, terminal },
            "Status code added",
          )
        }
      >
        Add code
      </Button>
    </div>
  );
}

function FieldForm({ onAdd }: { onAdd: AddFn }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("bool");
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Input
        ariaLabel="New field name"
        placeholder="field_name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Select
        ariaLabel="Field type"
        value={type}
        onChange={(e) => setType(e.target.value)}
        options={["bool", "enum", "number", "string", "datetime"].map((t) => ({
          value: t,
          label: t,
        }))}
      />
      <Button
        variant="secondary"
        onClick={() => onAdd({ name: name.trim(), type }, "Field added")}
      >
        Add field
      </Button>
    </div>
  );
}

function ClassForm({ onAdd }: { onAdd: AddFn }) {
  const [name, setName] = useState("");
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Input
        ariaLabel="New class name"
        placeholder="class_name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Button
        variant="secondary"
        onClick={() => onAdd({ name: name.trim() }, "Class added")}
      >
        Add class
      </Button>
    </div>
  );
}

function TemplateForm({ onAdd }: { onAdd: AddFn }) {
  const [kind, setKind] = useState("");
  const [audience, setAudience] = useState("chat");
  const [slots, setSlots] = useState("");
  const [text, setText] = useState("");
  return (
    <div className="flex max-w-[560px] flex-col gap-3">
      <Field label="Kind">
        {(id) => <Input id={id} value={kind} onChange={(e) => setKind(e.target.value)} />}
      </Field>
      <Field label="Audience">
        {(id) => (
          <Select
            id={id}
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
            options={[
              { value: "chat", label: "chat" },
              { value: "main", label: "main" },
            ]}
          />
        )}
      </Field>
      <Field label="Slots (comma-separated)">
        {(id) => <Input id={id} value={slots} onChange={(e) => setSlots(e.target.value)} />}
      </Field>
      <Field label="Text — {slot} placeholders">
        {(id) => <Input id={id} value={text} onChange={(e) => setText(e.target.value)} />}
      </Field>
      <div>
        <Button
          variant="secondary"
          onClick={() =>
            onAdd(
              {
                kind: kind.trim(),
                audience,
                slots: slots.trim()
                  ? slots.split(",").map((s) => s.trim())
                  : [],
                text: text.trim(),
              },
              "Template saved",
            )
          }
        >
          Save template
        </Button>
      </div>
    </div>
  );
}

function KindForm({ onAdd }: { onAdd: AddFn }) {
  const [kind, setKind] = useState("");
  const [label, setLabel] = useState("");
  const [statusKind, setStatusKind] = useState(false);
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Input
        ariaLabel="New kind"
        placeholder="kind_name"
        value={kind}
        onChange={(e) => setKind(e.target.value)}
      />
      <Input
        ariaLabel="Kind label"
        placeholder="Label"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />
      <LabeledCheckbox label="status kind" checked={statusKind} onChange={setStatusKind} />
      <Button
        variant="secondary"
        onClick={() =>
          onAdd(
            { kind: kind.trim(), label: label.trim(), status_kind: statusKind },
            "Kind added",
          )
        }
      >
        Add kind
      </Button>
    </div>
  );
}
