// Rules (the management surface for the standing rules):
// the stored rules grouped by scope, each row speaking
// its composed When → Then sentences, opening the editor
// on the tap. New rules start in shadow. The hard-stop
// floor is stated on the surface because it is the one
// line no rule may cross — the editor refuses a save
// that would apply a hard-stop class.
import { Fragment, useState } from "react";
import { useDataSource, useStoreVersion } from "../attention/useStore";
import type { RuleRecord } from "../attention/types";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Group, GroupLabel, Row, RowText, RowValue } from "../components/groups";
import { RuleEditor } from "../components/RuleEditor";
import { LargeTitle } from "../components/LargeTitle";

const SCOPES: { scope: string; label: string }[] = [
  { scope: "always", label: "Always" },
  { scope: "away", label: "Away only" },
  { scope: "active", label: "Active only" },
];

export function RulesView() {
  useStoreVersion();
  const ds = useDataSource();
  const rules = ds.getRules();
  const registries = ds.getRegistries();
  // undefined = editor closed; null = a new rule.
  const [editing, setEditing] = useState<RuleRecord | null | undefined>(undefined);
  const [editorRun, setEditorRun] = useState(0);
  const shadowCount = rules.filter((r) => r.mode === "shadow").length;

  const openEditor = (rule: RuleRecord | null) => {
    setEditing(rule);
    setEditorRun((n) => n + 1);
  };

  return (
    <>
      <LargeTitle
        title="Rules"
        subtitle={`${rules.length} standing rules · ${shadowCount} in shadow`}
      />

      <Group>
        <Row padded>
          <Button variant="primary" onClick={() => openEditor(null)}>
            New rule
          </Button>
        </Row>
      </Group>

      {SCOPES.map(({ scope, label }) => {
        const inScope = rules.filter((r) => r.scope === scope);
        if (!inScope.length) return null;
        return (
          // Fragment, not a div: a wrapper div makes the
          // scope label a :first-child and .glabel's
          // first-child rule zeroes its 20px section
          // margin (spacing audit, 2026-11-15).
          <Fragment key={scope}>
            <GroupLabel>{label}</GroupLabel>
            <Group>
              {inScope.map((r) => (
                <Row key={r.id} onClick={() => openEditor(r)}>
                  <RowText
                    label={r.display_name}
                    sub={`Priority ${r.priority} · ${r.when_label} → ${r.then_label}`}
                  />
                  <RowValue>{r.mode === "shadow" ? "Shadow" : "Active"}</RowValue>
                </Row>
              ))}
            </Group>
          </Fragment>
        );
      })}

      <GroupLabel>The floor</GroupLabel>
      <Group>
        <Row>
          <RowText
            label="Hard-stop classes are never applied by a rule"
            sub="Permission cards, logins, external sends, purchases and schedule changes always wait for the owner."
          />
        </Row>
      </Group>

      {editing !== undefined ? (
        <RuleEditor
          key={`${editing?.id ?? "new"}-${editorRun}`}
          rule={editing}
          registries={registries}
          onClose={() => setEditing(undefined)}
        />
      ) : null}
    </>
  );
}
