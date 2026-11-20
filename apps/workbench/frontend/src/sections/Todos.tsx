import { useMemo, useState } from "react";
import { Button } from "@kit/components/Button";
import { Checkbox } from "@kit/components/Checkbox";
import { Field, Input, Select } from "@kit/components/Fields";
import { SegmentedControl } from "@kit/components/SegmentedControl";
import { Sheet } from "@kit/components/Sheet";
import { ChevronRight, Plus } from "lucide-react";
import {
  armedRowFilename,
  checkpointLine,
  progressEntryId,
  renderArmedRow,
  renderProgressEntry,
} from "../lib/arming";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { FileTodo, TodoStatus } from "../lib/types";
import {
  Group,
  GroupLabel,
  Lab,
  LargeTitle,
  Row,
  Sub,
  Subtitle,
  TodoPill,
  Val,
  relTime,
} from "../components/ui";

// Frame 5 · Todos — the bundle's file todos over the one
// mutation path. The checkbox and the detail sheet both write
// through writeTodo; status transitions arm/retire the
// contract 03 projections in the same call, and the
// supervision strip below is the classification feed's
// derivation, served ready.

function TodoCheckbox({
  todo,
  onToggle,
}: {
  todo: FileTodo;
  onToggle: () => void;
}) {
  const done = todo.status === "done";
  return (
    <Checkbox
      checked={done}
      onChange={() => onToggle()}
      label={`Mark "${todo.title}" ${done ? "not done" : "done"}`}
    />
  );
}

export function TodoDetail({ todo, onClose }: { todo: FileTodo; onClose: () => void }) {
  const a = useAdapter();
  const [title, setTitle] = useState(todo.title);
  const [notes, setNotes] = useState(todo.notes);
  const [checkpoint, setCheckpoint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showRow, setShowRow] = useState(false);

  const rows = a.armedRows();
  const armedRow = rows.find((r) => r.todo === todo.id);
  const cls = a.classification(todo.project).find((c) => c.todo.id === todo.id);
  const entry = armedRow ? renderProgressEntry(todo) : null;

  const guard = (fn: () => unknown) => {
    setError(null);
    Promise.resolve()
      .then(() => fn())
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      });
  };

  return (
    <Sheet
      open
      title="Todo"
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto">
        <Field label="Title">
          {(id) => (
            <Input
              id={id}
              ariaLabel="Todo title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full"
            />
          )}
        </Field>
        <div className="flex gap-2">
          <Button
            variant="primary"
            onClick={() =>
              guard(async () => {
                await a.writeTodo(todo.id, { title, notes });
              })
            }
          >
            Save title + notes
          </Button>
        </div>
        <Field label="Status">
          {() => (
            <SegmentedControl
              ariaLabel="Todo status"
              options={[
                { value: "todo", label: "To do" },
                { value: "doing", label: "Doing" },
                { value: "blocked", label: "Blocked" },
                { value: "done", label: "Done" },
              ]}
              value={todo.status}
              onChange={(v) => guard(() => a.writeTodo(todo.id, { status: v as TodoStatus }))}
            />
          )}
        </Field>
        <Field label="Progress check (cadence)">
          {(id) => (
            <Select
              id={id}
              ariaLabel="Progress check cadence"
              options={[
                { value: "", label: "Default — arms at 15m on doing" },
                { value: "30m", label: "30m" },
                { value: "2h", label: "2h" },
                { value: "off", label: "off — opt out, never arms" },
              ]}
              value={todo.progressCheck ?? ""}
              onChange={(e) =>
                guard(() =>
                  a.writeTodo(todo.id, {
                    progressCheck: e.target.value === "" ? undefined : e.target.value,
                  }),
                )
              }
            />
          )}
        </Field>
        <Field label="Notes (todo body)">
          {() => (
          <textarea
            aria-label="Todo notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            className="w-full rounded-[var(--wb-radius-sm)] px-2.5 py-2 text-sm"
            style={{
              backgroundColor: "var(--wb-surface-1)",
              border: "1px solid var(--wb-border-default)",
              color: "var(--wb-content-primary)",
            }}
          />
          )}
        </Field>

        <div>
          <GroupLabel>Supervision — contract 03 projections</GroupLabel>
          <Group>
            <Row>
              <Lab>Armed</Lab>
              <Val>{armedRow ? `yes · since ${relTime(armedRow.armed_at!)}` : "no"}</Val>
            </Row>
            {armedRow ? (
              <>
                <Row>
                  <Lab>Armed row</Lab>
                  <Val mono>{armedRowFilename(armedRow)}</Val>
                </Row>
                <Row>
                  <Lab>Scheduler entry</Lab>
                  <Val mono>{progressEntryId(todo)}.yaml</Val>
                </Row>
                <Row>
                  <Lab>Cadence</Lab>
                  <Val>
                    {cls?.derivation
                      ? `${cls.derivation.cadenceMinutes} min · last activity ${relTime(cls.derivation.lastActivity)} · ${cls.derivation.missedChecks} missed`
                      : "—"}
                  </Val>
                </Row>
                <Row>
                  <Lab>Stall verdict</Lab>
                  <span className="ml-auto">
                    <span
                      className="inline-flex rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                      style={{
                        backgroundColor:
                          cls?.derivation?.verdict === "stalled"
                            ? "color-mix(in srgb, var(--wb-okabe-vermilion) 12%, transparent)"
                            : "color-mix(in srgb, var(--wb-okabe-bluish-green) 14%, transparent)",
                        color:
                          cls?.derivation?.verdict === "stalled"
                            ? "var(--wb-status-hard-gate-text)"
                            : "var(--wb-status-implemented-text)",
                      }}
                    >
                      {cls?.derivation?.verdict === "stalled" ? "Stalled · 2 missed intervals" : "On track"}
                    </span>
                  </span>
                </Row>
                <Row last>
                  <button
                    type="button"
                    className="inline-flex min-h-[36px] items-center text-[13px] font-semibold"
                    style={{ color: "var(--wb-accent)" }}
                    onClick={() => setShowRow((v) => !v)}
                  >
                    {showRow ? "Hide" : "Show"} the armed row + entry, as written
                  </button>
                </Row>
              </>
            ) : (
              <Row last>
                <span className="text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
                  {todo.status === "doing" && cls?.optOut
                    ? "Opted out (progress_check: off) — no projections are written."
                    : todo.status === "doing"
                      ? "Doing without a cadence stamp — arms at the 15-minute default."
                      : "Arms on the doing transition; a stop status (done / blocked) retires both projections."}
                </span>
              </Row>
            )}
          </Group>
          {showRow && armedRow ? (
            <pre
              className="mt-2 overflow-x-auto p-3 font-mono text-[11.5px] leading-[1.6]"
              style={{
                backgroundColor: "var(--wb-surface-1)",
                border: "1px solid var(--wb-border-default)",
                borderRadius: "var(--wb-radius-md)",
              }}
            >
              {JSON.stringify(renderArmedRow(todo), null, 2)}
              {"\n\n"}
              {`# ${progressEntryId(todo)}.yaml (target form — no migrated stamp, amendment 3)\n`}
              {JSON.stringify(entry, null, 2)}
            </pre>
          ) : null}
        </div>

        <div>
          <GroupLabel>Checkpoints</GroupLabel>
          <Group>
            {todo.checkpoints.map((c, i) => (
              <Row key={i} last={i === todo.checkpoints.length - 1 && false}>
                <span>
                  <span className="block font-mono text-[12px]">{checkpointLine(new Date(c.at), c.text)}</span>
                  <Sub>{relTime(c.at)}</Sub>
                </span>
              </Row>
            ))}
            <Row last>
              <span className="flex w-full items-center gap-2">
                <input
                  value={checkpoint}
                  onChange={(e) => setCheckpoint(e.target.value)}
                  placeholder="Add a checkpoint…"
                  aria-label="Checkpoint text"
                  className="min-w-0 flex-1 rounded-[var(--wb-radius-sm)] px-2.5 py-1.5 text-sm"
                  style={{
                    backgroundColor: "var(--wb-surface-1)",
                    border: "1px solid var(--wb-border-default)",
                    color: "var(--wb-content-primary)",
                  }}
                />
                <Button
                  variant="secondary"
                  onClick={() =>
                    guard(async () => {
                      if (checkpoint.trim().length === 0) {
                        throw new Error("A checkpoint needs text — the line format carries it.");
                      }
                      await a.addCheckpoint(todo.id, checkpoint.trim());
                      setCheckpoint("");
                    })
                  }
                >
                  Add
                </Button>
              </span>
            </Row>
          </Group>
        </div>

        {error ? (
          <p className="text-[13px]" style={{ color: "var(--wb-danger)" }}>
            {error}
          </p>
        ) : null}
        <p className="font-mono text-[11.5px]" style={{ color: "var(--wb-content-muted)" }}>
          {todo.id} · bundle {todo.bundle}
          {Object.keys(todo.extra).length > 0
            ? ` · extra front matter preserved: ${Object.entries(todo.extra).map(([k, v]) => `${k}: ${v}`).join(", ")}`
            : ""}
        </p>
      </div>
    </Sheet>
  );
}

export function Todos() {
  useStoreVersion();
  const a = useAdapter();
  const { project } = useNav();
  const plans = a.plans(project);
  const [bundle, setBundle] = useState<string>(
    plans.find((p) => p.state === "in-progress")?.bundle ?? plans[0]?.bundle ?? "",
  );
  const [scope, setScope] = useState<"project" | "all">("project");
  const [showDone, setShowDone] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [prevStatus, setPrevStatus] = useState<Record<string, TodoStatus>>({});

  const plan = a.plan(bundle);
  const scoped = useMemo(() => {
    if (scope === "all") {
      return a.projects().flatMap((p) => a.todos(p.slug));
    }
    return a.todos(project).filter((t) => t.bundle === bundle);
  }, [a, scope, project, bundle]);
  const active = scoped.filter((t) => t.status !== "done");
  const completed = scoped.filter((t) => t.status === "done");
  const open = openId ? a.todo(openId) : undefined;

  const armedHere = a
    .classification(project)
    .filter((c) => c.armed && c.derivation);

  const toggle = (t: FileTodo) => {
    if (t.status === "done") {
      void a.writeTodo(t.id, { status: prevStatus[t.id] ?? "todo" });
    } else {
      setPrevStatus((m) => ({ ...m, [t.id]: t.status }));
      void a.writeTodo(t.id, { status: "done" });
    }
  };

  const rowFor = (t: FileTodo, last: boolean) => {
    const tPlan = a.plan(t.bundle);
    const lastCp = t.checkpoints[t.checkpoints.length - 1];
    return (
      <Row key={t.id} last={last} onClick={() => setOpenId(t.id)}>
        <TodoCheckbox todo={t} onToggle={() => toggle(t)} />
        <span className="min-w-0">
          <span className="block truncate text-[14.5px] font-medium">{t.title}</span>
          <Sub>
            Plan: {tPlan?.title ?? t.bundle}
            {lastCp ? ` · checkpoint ${relTime(lastCp.at)}` : ""}
            {scope === "all" ? ` · ${t.project}` : ""}
          </Sub>
        </span>
        <span className="ml-auto">
          <TodoPill status={t.status} />
        </span>
      </Row>
    );
  };

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>Todos</LargeTitle>
      <Subtitle>Bundle: {plan?.title ?? bundle}</Subtitle>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegmentedControl
          ariaLabel="Todo scope"
          options={[
            { value: "project", label: "This project" },
            { value: "all", label: "All projects" },
          ]}
          value={scope}
          onChange={(v) => setScope(v as "project" | "all")}
        />
        {scope === "project" ? (
          <Select
            ariaLabel="Bundle"
            options={plans.map((p) => ({ value: p.bundle, label: p.title }))}
            value={bundle}
            onChange={(e) => setBundle(e.target.value)}
            className="min-w-[180px]"
          />
        ) : null}
      </div>

      {armedHere.length > 0 ? (
        <div className="mb-5">
          <GroupLabel>Armed — progress supervision (classification feed)</GroupLabel>
          <Group>
            {armedHere.map((c, i) => (
              <Row key={c.todo.id} last={i === armedHere.length - 1} onClick={() => setOpenId(c.todo.id)}>
                <span className="min-w-0">
                  <span className="block text-[14px] font-medium">{c.todo.title}</span>
                  <Sub>
                    cadence {c.derivation!.cadenceMinutes} min · last activity{" "}
                    {relTime(c.derivation!.lastActivity)} · {c.derivation!.missedChecks} missed checks
                  </Sub>
                </span>
                <span
                  className="ml-auto inline-flex rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                  style={{
                    backgroundColor:
                      c.derivation!.verdict === "stalled"
                        ? "color-mix(in srgb, var(--wb-okabe-vermilion) 12%, transparent)"
                        : "color-mix(in srgb, var(--wb-okabe-bluish-green) 14%, transparent)",
                    color:
                      c.derivation!.verdict === "stalled"
                        ? "var(--wb-status-hard-gate-text)"
                        : "var(--wb-status-implemented-text)",
                  }}
                >
                  {c.derivation!.verdict === "stalled" ? "Stalled" : "On track"}
                </span>
              </Row>
            ))}
          </Group>
        </div>
      ) : null}

      <Group>
        <Row>
          <span className="flex w-full items-center gap-2">
            <Plus size={15} style={{ color: "var(--wb-content-muted)" }} />
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  if (newTitle.trim().length === 0) {
                    setAddError("A todo needs a title.");
                    return;
                  }
                  setAddError(null);
                  a.addTodo(project, bundle, newTitle.trim())
                    .then(() => setNewTitle(""))
                    .catch((err) =>
                      setAddError(err instanceof Error ? err.message : String(err)),
                    );
                }
              }}
              placeholder="Add a todo…"
              aria-label="Add a todo"
              className="min-w-0 flex-1 bg-transparent text-[14.5px] outline-none"
              style={{ color: "var(--wb-content-primary)" }}
            />
            <Button
              variant="secondary"
              onClick={() => {
                if (newTitle.trim().length === 0) {
                  setAddError("A todo needs a title.");
                  return;
                }
                setAddError(null);
                a.addTodo(project, bundle, newTitle.trim())
                  .then(() => setNewTitle(""))
                  .catch((err) =>
                    setAddError(err instanceof Error ? err.message : String(err)),
                  );
              }}
            >
              Add
            </Button>
          </span>
        </Row>
        {active.map((t, i) => rowFor(t, i === active.length - 1 && completed.length === 0))}
      </Group>
      {addError ? (
        <p className="mt-2 text-[13px]" style={{ color: "var(--wb-danger)" }}>
          {addError}
        </p>
      ) : null}

      <GroupLabel>Completed · {completed.length}</GroupLabel>
      <Group>
        <Row onClick={() => setShowDone((v) => !v)} last={!showDone}>
          <Lab>{showDone ? "Hide completed todos" : "Show completed todos"}</Lab>
          <span className="ml-auto">
            <ChevronRight
              size={15}
              style={{
                color: "var(--wb-content-muted)",
                transform: showDone ? "rotate(90deg)" : undefined,
              }}
            />
          </span>
        </Row>
        {showDone ? completed.map((t, i) => rowFor(t, i === completed.length - 1)) : null}
      </Group>

      {open ? <TodoDetail todo={open} onClose={() => setOpenId(null)} /> : null}
    </div>
  );
}
