import { useState } from "react";
import { Checkbox } from "@kit/components/controls/Checkbox";
import { Toggle } from "@kit/components/controls/Toggle";
import { useIsPhone } from "@kit/lib/responsive";
import {
  armedRowFilename,
  progressEntryId,
  renderArmedRow,
} from "../lib/arming";
import { useAdapter, useStoreVersion } from "../lib/store";
import type { WorkbenchAdapter } from "../lib/seam";
import { useNav } from "../lib/nav";
import type {
  FileTodo,
  GoalRecord,
  Plan,
  ProgressDerivation,
  StatusPost,
} from "../lib/types";
import {
  ActionRow,
  Chev,
  Group,
  GroupLabel,
  Lab,
  LargeTitle,
  Row,
  Sub,
  Subtitle,
  TodoPill,
  TOGGLE_LABEL_SR_ONLY,
  Val,
  relTime,
} from "../components/ui";
import { StatusChip, StatusPostFormRows } from "../components/StatusPost";

// Goals — the dedicated section for contract 11's records
// (the storyboard-goals storyboard, approved;
// mockup approval = exact reproduction). A goal
// is the top level of the work record — goal → bundle →
// todos → arms — and its ping state rides the same views.
// Every label, count, and derivation is served through the
// seam; this file only composes them.

type Adapter = WorkbenchAdapter;

/** Terminal is read from the served vocabulary, never from a
 *  local copy of the table (contract 06). */
function isTerminal(a: Adapter, post: StatusPost | null): boolean {
  if (!post) return false;
  return a.statusVocabulary().find((r) => r.code === post.status_code)?.terminal ?? false;
}

function isBlocked(post: StatusPost | null): boolean {
  return post?.status_code === "BLOCKED-OWNER" || post?.status_code === "BLOCKED-HARD";
}

function statusLabel(a: Adapter, post: StatusPost): string {
  return a.statusVocabulary().find((r) => r.code === post.status_code)?.label ?? post.status_code;
}

/** ISO when it parses (relative), the served string as-is
 *  when it does not (a citation typed at the form). */
function timeLabel(iso: string): string {
  return Number.isNaN(new Date(iso).getTime()) ? iso : relTime(iso);
}

function closedDateLabel(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function cadenceLabel(minutes: number): string {
  return minutes >= 60 && minutes % 60 === 0 ? `${minutes / 60} h` : `${minutes} min`;
}

interface GoalProgress {
  done: number;
  total: number;
  doing: number;
  blocked: number;
  todo: number;
}

function goalProgress(a: Adapter, goal: GoalRecord): GoalProgress | null {
  const bundle = a.goalBundle(goal);
  if (!bundle) return null;
  const todos = a.goalTodos(goal);
  return {
    done: todos.filter((t) => t.status === "done").length,
    total: todos.length,
    doing: todos.filter((t) => t.status === "doing").length,
    blocked: todos.filter((t) => t.status === "blocked").length,
    todo: todos.filter((t) => t.status === "todo").length,
  };
}

function planStateLabel(plan: Plan): string {
  return plan.state === "in-progress" ? "In progress" : plan.state === "done" ? "Done" : "Draft";
}

function pingSegment(goal: GoalRecord, phone: boolean): string {
  const cad = `every ${goal.ping.cadenceMinutes} min`;
  if (goal.ping.armed) return `Ping armed · ${cad}`;
  return phone ? "Ping disarmed" : `Ping disarmed · ${cad}`;
}

/** "2 of 6 todos done" (+ the blocked count when it is not
 *  already carried by the owner-waiting line). */
function progressSegment(goal: GoalRecord, p: GoalProgress): string {
  const waiting = Boolean(goal.lastPost?.owner_waiting);
  return (
    `${p.done} of ${p.total} todos done` +
    (p.blocked > 0 && !waiting ? ` · ${p.blocked} blocked` : "")
  );
}

function ownerLine(post: StatusPost): string {
  return `Owner waiting · ${post.owner_waiting!.label} · commissioned ${relTime(post.owner_waiting!.commissioned_at)}`;
}

// ----------------------------------------------------------------
// List (storyboard frame 1 desktop, frame 4 phone)

function GoalListRow({
  goal,
  phone,
  last,
}: {
  goal: GoalRecord;
  phone: boolean;
  last?: boolean;
}) {
  const a = useAdapter();
  const { navigate, setProject } = useNav();
  const post = goal.lastPost;
  const terminal = isTerminal(a, post);
  const p = goalProgress(a, goal);

  const open = () => {
    setProject(goal.project);
    navigate({ section: "goal", slug: goal.slug });
  };

  let subs: React.ReactNode[];
  if (terminal && p) {
    const meta = `${p.done} of ${p.total} steps landed · Ping retired · Closed ${closedDateLabel(post!.postedAt)}`;
    subs = phone
      ? [<Sub key="m">{meta}</Sub>]
      : [
          <Sub key="o">{goal.contract.objective}</Sub>,
          <Sub key="m">{`${goal.project} · ${meta}`}</Sub>,
        ];
  } else if (phone) {
    subs = [
      <Sub key="m">
        {p ? `${progressSegment(goal, p)} · ${pingSegment(goal, true)}` : (goal.shortObjective ?? goal.contract.objective)}
      </Sub>,
    ];
    if (post?.owner_waiting) {
      subs.push(
        <Sub key="w">
          <span style={{ color: "var(--ui-status-hard-gate-text)" }}>{ownerLine(post)}</span>
        </Sub>,
      );
    }
  } else {
    const meta = p
      ? `${goal.project} · ${progressSegment(goal, p)} · ${pingSegment(goal, false)}`
      : `${goal.project} · ${pingSegment(goal, false)}`;
    subs = [
      <Sub key="o">{goal.contract.objective}</Sub>,
      <Sub key="m">{meta}</Sub>,
    ];
    if (post?.owner_waiting) {
      subs.push(
        <Sub key="w">
          <span style={{ color: "var(--ui-status-hard-gate-text)" }}>{ownerLine(post)}</span>
        </Sub>,
      );
    }
  }

  return (
    <Row onClick={open} last={last}>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14.5px] font-medium">{goal.title}</span>
        {subs}
      </span>
      <span className="ml-auto shrink-0">
        <StatusChip post={post} />
      </span>
      {phone ? null : <Chev />}
    </Row>
  );
}

export function Goals() {
  useStoreVersion();
  const a = useAdapter();
  const isPhone = useIsPhone();
  const all = a.allGoals();
  const active = all.filter((g) => !isTerminal(a, g.lastPost));
  const completed = all.filter((g) => isTerminal(a, g.lastPost));
  const waiting = active.filter((g) => g.lastPost?.owner_waiting).length;

  return (
    <div className={isPhone ? "px-[18px] py-4" : "px-[26px] py-[22px]"}>
      <LargeTitle>Goals</LargeTitle>
      <Subtitle>
        {`${active.length} active · ${waiting} waiting on owner · ${completed.length} closed`}
      </Subtitle>
      <GroupLabel>Active</GroupLabel>
      <Group>
        {active.map((g, i) => (
          <GoalListRow key={g.slug} goal={g} phone={isPhone} last={i === active.length - 1} />
        ))}
      </Group>
      {completed.length > 0 ? (
        <>
          <GroupLabel>Completed</GroupLabel>
          <Group>
            {completed.map((g, i) => (
              <GoalListRow key={g.slug} goal={g} phone={isPhone} last={i === completed.length - 1} />
            ))}
          </Group>
        </>
      ) : null}
    </div>
  );
}

// ----------------------------------------------------------------
// Detail — shared pieces

function ContractGroup({ goal }: { goal: GoalRecord }) {
  const c = goal.contract;
  const fields: [string, string][] = [
    ["Objective", c.objective],
    ["Complete when", c.completeWhen],
    ["Blocked only when", c.blockedOnlyWhen],
    ["Continuation", c.continuation],
  ];
  return (
    <>
      <GroupLabel>Contract</GroupLabel>
      <Group>
        {fields.map(([label, text], i) => (
          <Row key={label} last={i === fields.length - 1}>
            <span className="min-w-0 flex-1">
              <Lab>{label}</Lab>
              <Sub>{text}</Sub>
            </span>
          </Row>
        ))}
      </Group>
    </>
  );
}

/** The cited basis + verification stamp (contract 11
 *  amendment) as served on the blocked post. */
function CitationLines({ post }: { post: StatusPost }) {
  return (
    <>
      {post.basis_citation ? (
        <Sub>{`Citation · ${post.basis_citation.thread} · ${timeLabel(post.basis_citation.at)}`}</Sub>
      ) : null}
      {post.verification ? (
        <Sub>{`Verified · ${post.verification.by} · ${timeLabel(post.verification.at)}`}</Sub>
      ) : null}
    </>
  );
}

function PingArmedRow({ goal, last }: { goal: GoalRecord; last?: boolean }) {
  const a = useAdapter();
  const terminal = isTerminal(a, goal.lastPost);
  return (
    <Row last={last}>
      <Lab>Armed</Lab>
      {terminal ? (
        <Val>Retired</Val>
      ) : (
        <span className="ml-auto">
          <Toggle
            checked={goal.ping.armed}
            onChange={(v) => {
              // Server-first, as in Overview: a refusal
              // leaves the served state standing.
              void a.setGoalPing(goal.slug, v).catch(() => {});
            }}
            label={`Goal ping for ${goal.title}`}
            className={TOGGLE_LABEL_SR_ONLY}
          />
        </span>
      )}
    </Row>
  );
}

function TodoCheckbox({ todo }: { todo: FileTodo }) {
  const a = useAdapter();
  const done = todo.status === "done";
  return (
    <Checkbox
      checked={done}
      onChange={(checked) =>
        a.writeTodo(todo.id, { status: checked ? "done" : "todo" })
      }
      label={`Mark "${todo.title}" ${done ? "not done" : "done"}`}
    />
  );
}

/** A todo's sub-line in the work view: the checkpoint line
 *  for a doing todo (with its stall state, served by the
 *  classification feed's derivation), the note for a
 *  blocked one. */
function todoSub(todo: FileTodo, derivation: ProgressDerivation | null): React.ReactNode {
  if (todo.status === "doing" && todo.checkpoints.length > 0) {
    const cp = todo.checkpoints[todo.checkpoints.length - 1];
    return (
      <Sub>
        Checkpoint {relTime(cp.at)}
        {derivation ? ` · cadence ${cadenceLabel(derivation.cadenceMinutes)}` : ""}
        {derivation?.verdict === "stalled" ? (
          <>
            {" · "}
            <span style={{ color: "var(--ui-status-hard-gate-text)", fontWeight: 650 }}>
              Stalled
            </span>
          </>
        ) : null}
      </Sub>
    );
  }
  if (todo.status === "blocked" && todo.notes) return <Sub>{todo.notes}</Sub>;
  return null;
}

function verdictPill(derivation: ProgressDerivation) {
  const stalled = derivation.verdict === "stalled";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold whitespace-nowrap"
      style={{
        backgroundColor: stalled
          ? "color-mix(in srgb, var(--ui-okabe-vermilion) 12%, transparent)"
          : "color-mix(in srgb, var(--ui-okabe-bluish-green) 14%, transparent)",
        color: stalled ? "var(--ui-status-hard-gate-text)" : "var(--ui-status-done-text)",
      }}
    >
      <span
        className="block h-[7px] w-[7px] rounded-full"
        style={{
          backgroundColor: stalled ? "var(--ui-okabe-vermilion)" : "var(--ui-okabe-bluish-green)",
        }}
      />
      {stalled ? `Stalled · ${derivation.missedChecks} missed intervals` : "On track"}
    </span>
  );
}

// ----------------------------------------------------------------
// Detail — desktop (storyboard frames 2 + 3)

function GoalDetailDesktop({ goal }: { goal: GoalRecord }) {
  const a = useAdapter();
  const { navigate, setProject } = useNav();
  const post = goal.lastPost;
  const bundle = a.goalBundle(goal);
  const todos = a.goalTodos(goal);
  const p = goalProgress(a, goal);
  const cls = new Map(a.classification(goal.project).map((r) => [r.todo.id, r]));
  const armed = todos.filter((t) => cls.get(t.id)?.armed);
  const derivations = armed
    .map((t) => ({ todo: t, derivation: cls.get(t.id)?.derivation ?? null }))
    .filter((x) => x.derivation !== null) as { todo: FileTodo; derivation: ProgressDerivation }[];

  const workSummary = bundle && p
    ? `Plan ${bundle.bundle} · ${p.done} of ${p.total} todos done` +
      (p.doing > 0 ? ` · ${p.doing} doing` : "") +
      (p.blocked > 0 ? ` · ${p.blocked} blocked` : "") +
      (p.todo > 0 ? ` · ${p.todo} to do` : "")
    : null;

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>{goal.title}</LargeTitle>
      <Subtitle>
        {goal.project} · <span className="font-mono">goal:{goal.slug}</span>
        {post ? ` · ${post.handle} · posted ${relTime(post.postedAt)}` : " · no post yet"}
      </Subtitle>

      <div className="flex gap-[18px]">
        <div className="min-w-0 flex-1">
          {post && isBlocked(post) ? (
            <>
              <GroupLabel>{statusLabel(a, post)}</GroupLabel>
              <Group>
                <Row last={!post.owner_waiting && !post.refs}>
                  <span className="min-w-0 flex-1">
                    <Lab>Basis</Lab>
                    <Sub>{post.summary}</Sub>
                    <CitationLines post={post} />
                  </span>
                </Row>
                {post.owner_waiting ? (
                  <Row last={!post.refs}>
                    <span className="min-w-0 flex-1">
                      <Lab>{post.owner_waiting.label}</Lab>
                      <Sub>
                        Owner waiting · commissioned {relTime(post.owner_waiting.commissioned_at)}
                      </Sub>
                    </span>
                  </Row>
                ) : null}
                {post.refs ? (
                  <Row last>
                    <span className="min-w-0 flex-1">
                      <Lab>Refs</Lab>
                      <Sub>
                        <span className="font-mono">
                          {post.refs.plan ? `plan ${post.refs.plan}` : ""}
                          {post.refs.todo_ids.length > 0
                            ? `${post.refs.plan ? " · " : ""}todo ${post.refs.todo_ids.join(", ")}`
                            : ""}
                        </span>
                      </Sub>
                    </span>
                  </Row>
                ) : null}
              </Group>
            </>
          ) : null}
          <ContractGroup goal={goal} />
        </div>
        <div className="w-[308px] flex-[0_0_308px]">
          <GroupLabel>Ping</GroupLabel>
          <Group>
            <Row>
              <span className="min-w-0 flex-1">
                <Lab>Entry</Lab>
                <Sub>
                  <span className="font-mono">{goal.ping.entryId}</span>
                </Sub>
              </span>
            </Row>
            <Row>
              <Lab>Owner</Lab>
              <Val mono>goal:{goal.slug}</Val>
            </Row>
            <Row>
              <Lab>Cadence</Lab>
              <Val>Every {goal.ping.cadenceMinutes} min</Val>
            </Row>
            <PingArmedRow goal={goal} last />
          </Group>
          <GroupLabel>Post status</GroupLabel>
          <Group>
            <StatusPostFormRows goal={goal} />
          </Group>
        </div>
      </div>

      {bundle && p ? (
        <>
          <p
            className="mt-7 mb-5 text-sm [overflow-wrap:anywhere]"
            style={{ color: "var(--ui-content-secondary)" }}
          >
            {workSummary}
          </p>
          <GroupLabel>Plan</GroupLabel>
          <Group>
            <Row
              last
              onClick={() => {
                setProject(goal.project);
                navigate({ section: "plans", bundle: bundle.bundle });
              }}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14.5px] font-medium">{bundle.title}</span>
                <Sub>
                  Bundle <span className="font-mono">{bundle.bundle}</span> · {planStateLabel(bundle)}
                </Sub>
              </span>
              <Val>
                {p.done} of {p.total} done
              </Val>
              <Chev />
            </Row>
          </Group>

          <GroupLabel>Todos</GroupLabel>
          <Group>
            {todos.map((t, i) => (
              <Row key={t.id} last={i === todos.length - 1}>
                <TodoCheckbox todo={t} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] font-medium">{t.title}</span>
                  {todoSub(t, cls.get(t.id)?.derivation ?? null)}
                </span>
                <span className="ml-auto shrink-0">
                  <TodoPill status={t.status} />
                </span>
              </Row>
            ))}
          </Group>

          {armed.length > 0 ? (
            <>
              <GroupLabel>Arms · contract 03 projections</GroupLabel>
              <Group>
                {armed.flatMap((t, i) => {
                  const row = renderArmedRow(t);
                  const lastTodo = i === armed.length - 1;
                  return [
                    <Row key={`${t.id}-entry`}>
                      <span className="min-w-0 flex-1">
                        <Lab>Scheduler entry</Lab>
                        <Sub>
                          <span className="font-mono">{progressEntryId(t)}.yaml</span>
                        </Sub>
                      </span>
                      <Val>
                        Every {cadenceLabel(row.cadence_minutes ?? goal.ping.cadenceMinutes)}
                      </Val>
                    </Row>,
                    <Row key={`${t.id}-row`} last={lastTodo}>
                      <span className="min-w-0 flex-1">
                        <Lab>Attention armed row</Lab>
                        <Sub>
                          <span className="font-mono">{armedRowFilename(row)}</span>
                        </Sub>
                      </span>
                      <Val>{t.progressArmed ? `Armed ${relTime(t.progressArmed)}` : ""}</Val>
                    </Row>,
                  ];
                })}
              </Group>
            </>
          ) : null}

          {derivations.length > 0 ? (
            <>
              <GroupLabel>Measurement</GroupLabel>
              <Group>
                {derivations.flatMap(({ todo: t, derivation }, i) => {
                  const lastTodo = i === derivations.length - 1;
                  const cp = t.checkpoints[t.checkpoints.length - 1];
                  return [
                    <Row key={`${t.id}-cp`}>
                      <span className="min-w-0 flex-1">
                        <Lab>Last checkpoint</Lab>
                        {cp ? <Sub>{cp.text}</Sub> : null}
                      </span>
                      <Val>{relTime(derivation.lastActivity)}</Val>
                    </Row>,
                    <Row key={`${t.id}-verdict`}>
                      <Lab>Stall verdict</Lab>
                      <span className="ml-auto shrink-0">{verdictPill(derivation)}</span>
                    </Row>,
                    <Row key={`${t.id}-missed`} last={lastTodo}>
                      <Lab>Missed checks</Lab>
                      <Val>
                        {derivation.missedChecks} · cadence {cadenceLabel(derivation.cadenceMinutes)}
                      </Val>
                    </Row>,
                  ];
                })}
              </Group>
            </>
          ) : null}
        </>
      ) : (
        <>
          <GroupLabel>Plan</GroupLabel>
          <Group>
            <Row last>
              <span className="min-w-0 flex-1">
                <Lab>No plan bundle linked</Lab>
                <Sub>
                  The record's posts name no plan, and the project has no single in-progress
                  plan to derive the work from.
                </Sub>
              </span>
            </Row>
          </Group>
        </>
      )}
    </div>
  );
}

// ----------------------------------------------------------------
// Detail — phone (storyboard frame 5)

function GoalDetailPhone({ goal }: { goal: GoalRecord }) {
  const a = useAdapter();
  const post = goal.lastPost;
  const p = goalProgress(a, goal);
  const todos = a.goalTodos(goal);
  const cls = new Map(a.classification(goal.project).map((r) => [r.todo.id, r]));
  const [showDone, setShowDone] = useState(false);
  const [contractOpen, setContractOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const open = todos.filter((t) => t.status !== "done");
  const doneTodos = todos.filter((t) => t.status === "done");
  const shown = showDone ? [...open, ...doneTodos] : open;

  return (
    <div className="px-[18px] py-4">
      <LargeTitle>{goal.title}</LargeTitle>
      <p
        className="m-0 mb-1 text-sm [overflow-wrap:anywhere]"
        style={{ color: "var(--ui-content-secondary)" }}
      >
        {goal.project}
        {post ? ` · ${statusLabel(a, post)} · posted ${relTime(post.postedAt)}` : " · No post yet"}
      </p>
      {post?.owner_waiting ? (
        <p
          className="m-0 mb-3.5 text-sm [overflow-wrap:anywhere]"
          style={{ color: "var(--ui-status-hard-gate-text)" }}
        >
          {ownerLine(post)}
        </p>
      ) : null}

      {post && isBlocked(post) ? (
        <div
          className="mb-1 p-[11px_14px] text-[13.5px] leading-[1.5]"
          style={{
            backgroundColor: "color-mix(in srgb, var(--ui-okabe-orange) 14%, transparent)",
            border: "1px solid var(--ui-okabe-orange)",
            borderRadius: "var(--ui-radius-lg)",
            color: "var(--ui-content-primary)",
          }}
        >
          <b>Blocked basis</b>
          <br />
          {post.summary}
          <CitationLines post={post} />
        </div>
      ) : null}

      <GroupLabel>Ping</GroupLabel>
      <Group>
        <Row>
          <span className="min-w-0 flex-1">
            <Lab>Entry</Lab>
            <Sub>
              <span className="font-mono">{goal.ping.entryId}</span> · every{" "}
              {goal.ping.cadenceMinutes} min
            </Sub>
          </span>
        </Row>
        <PingArmedRow goal={goal} last />
      </Group>

      {p ? (
        <>
          <GroupLabel>
            Plan · {p.done} of {p.total} done
          </GroupLabel>
          <Group>
            {shown.map((t, i) => (
              <Row key={t.id} last={doneTodos.length === 0 && i === shown.length - 1}>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] font-medium">{t.title}</span>
                  {todoSub(t, cls.get(t.id)?.derivation ?? null)}
                </span>
                <span className="ml-auto shrink-0">
                  <TodoPill status={t.status} />
                </span>
              </Row>
            ))}
            {doneTodos.length > 0 ? (
              <ActionRow
                label={
                  showDone ? "Hide completed todos" : `${doneTodos.length} done · Show completed todos`
                }
                onClick={() => setShowDone((v) => !v)}
                last
              />
            ) : null}
          </Group>
        </>
      ) : null}

      <GroupLabel>Record</GroupLabel>
      <Group>
        <Row onClick={() => setContractOpen((v) => !v)}>
          <Lab>Contract</Lab>
          <span className="ml-auto">
            <Chev />
          </span>
        </Row>
        {contractOpen
          ? ([
              ["Objective", goal.contract.objective],
              ["Complete when", goal.contract.completeWhen],
              ["Blocked only when", goal.contract.blockedOnlyWhen],
              ["Continuation", goal.contract.continuation],
            ] as [string, string][]).map(([label, text]) => (
              <Row key={label}>
                <span className="min-w-0 flex-1">
                  <Lab>{label}</Lab>
                  <Sub>{text}</Sub>
                </span>
              </Row>
            ))
          : null}
        <ActionRow label="Post status" onClick={() => setFormOpen((v) => !v)} last />
      </Group>
      {formOpen ? (
        <>
          <GroupLabel>Post status</GroupLabel>
          <Group>
            <StatusPostFormRows goal={goal} />
          </Group>
        </>
      ) : null}
    </div>
  );
}

export function GoalDetail({ slug }: { slug: string }) {
  useStoreVersion();
  const a = useAdapter();
  const isPhone = useIsPhone();
  const goal = a.goal(slug);
  if (!goal) {
    return (
      <div className={isPhone ? "px-[18px] py-4" : "px-[26px] py-[22px]"}>
        <LargeTitle>Goal</LargeTitle>
        <Subtitle>No goal record carries that slug.</Subtitle>
      </div>
    );
  }
  return isPhone ? <GoalDetailPhone goal={goal} /> : <GoalDetailDesktop goal={goal} />;
}
