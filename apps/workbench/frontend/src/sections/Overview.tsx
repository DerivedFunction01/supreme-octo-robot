import { Toggle } from "@kit/components/Toggle";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import {
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
} from "../components/ui";
import { StatusChip, StatusPostFormRows } from "../components/StatusPost";

// Frame 10 · Overview — project: active plan, section rows
// with live counts, recent activity — plus the goal record
// (contract 11) for projects that carry one: the contract
// block as record fields, and the ping state (the record's
// own armed scheduling entry + its latest status post). The
// full record lives in the Goals section; this panel is the
// project's at-a-glance form of the same record, and its
// status form is the shared one (served labels as picker
// chips — contract 06).

function GoalRecordPanel({ slug }: { slug: string }) {
  useStoreVersion();
  const a = useAdapter();
  const goals = a.goals(slug);
  if (goals.length === 0) return null;
  const g = goals[0];
  const post = g.lastPost;

  return (
    <>
      <GroupLabel>Goal record</GroupLabel>
      <Group>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">{g.title}</span>
            <Sub>
              Ping entry <span className="font-mono">{g.ping.entryId}</span> · owner goal:{g.slug} ·
              every {g.ping.cadenceMinutes} min
            </Sub>
          </span>
          <span className="ml-auto flex items-center gap-2">
            <span className="text-xs" style={{ color: "var(--wb-content-secondary)" }}>
              {g.ping.armed ? "Ping armed" : "Ping disarmed"}
            </span>
            <Toggle
              checked={g.ping.armed}
              onChange={(v) => {
                // Server-first: a refusal (a retired
                // ping's re-arm) leaves the served state
                // standing and the toggle where it was.
                void a.setGoalPing(g.slug, v).catch(() => {});
              }}
              label={`Goal ping for ${g.title}`}
              className={TOGGLE_LABEL_SR_ONLY}
            />
          </span>
        </Row>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Objective</span>
            <Sub>{g.contract.objective}</Sub>
          </span>
        </Row>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Complete when</span>
            <Sub>{g.contract.completeWhen}</Sub>
          </span>
        </Row>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Blocked only when</span>
            <Sub>{g.contract.blockedOnlyWhen}</Sub>
          </span>
        </Row>
        <Row last>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Continuation</span>
            <Sub>{g.contract.continuation}</Sub>
          </span>
        </Row>
      </Group>

      <GroupLabel>Latest status post</GroupLabel>
      <Group>
        {post ? (
          <>
            <Row>
              <Lab>{post.handle}</Lab>
              <span className="ml-auto flex shrink-0 items-center gap-2.5">
                <StatusChip post={post} />
                <Val>{new Date(post.postedAt).toLocaleString()}</Val>
              </span>
            </Row>
            <Row>
              <span className="min-w-0 flex-1">
                <span className="block text-[14.5px] [overflow-wrap:anywhere]">{post.summary}</span>
                {post.owner_waiting ? (
                  <Sub>
                    Owner waiting: {post.owner_waiting.label} · commissioned{" "}
                    {new Date(post.owner_waiting.commissioned_at).toLocaleString()}
                  </Sub>
                ) : null}
              </span>
            </Row>
          </>
        ) : (
          <Row>
            <Lab>No status post yet</Lab>
            <Val>the record + its ping stand; nothing posted</Val>
          </Row>
        )}
        <StatusPostFormRows goal={g} />
      </Group>
    </>
  );
}

export function Overview() {
  useStoreVersion();
  const a = useAdapter();
  const { navigate, project } = useNav();
  const p = a.projects().find((x) => x.slug === project);
  const plans = a.plans(project);
  const active = plans.find((pl) => pl.state === "in-progress");
  const activeTodos = active
    ? active.steps
        .map((s) => (s.todoId ? a.todo(s.todoId) : undefined))
        .filter((t) => t && t.status !== "done")
    : [];
  const currentStep = activeTodos[0];
  const entries = a.entries(project);
  const todos = a.todos(project);
  const doing = todos.filter((t) => t.status === "doing").length;
  const done = todos.filter((t) => t.status === "done").length;
  const awaiting = a.messages().filter((m) => m.disposition === null).length;
  const triage = entries.filter((e) => e.review === "in-triage").length;

  if (!p) return null;
  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>{p.name}</LargeTitle>
      <Subtitle>
        Last activity {p.lastActivityLabel} · swept just now
      </Subtitle>

      {active ? (
        <>
          <GroupLabel>Active plan</GroupLabel>
          <Group>
            <Row onClick={() => navigate({ section: "plans", bundle: active.bundle })} last>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14.5px] font-medium">{active.title}</span>
                <Sub>
                  {currentStep
                    ? `Step ${active.steps.findIndex((s) => s.todoId === currentStep.id) + 1} of ${active.steps.length} · ${currentStep.title.toLowerCase()} in progress`
                    : "All steps landed"}
                </Sub>
              </span>
              <span className="ml-auto">{currentStep ? <TodoPill status={currentStep.status} /> : <TodoPill status="done" />}</span>
              <Chev />
            </Row>
          </Group>
        </>
      ) : null}

      <GroupLabel>Sections</GroupLabel>
      <Group>
        <Row onClick={() => navigate({ section: "mockups" })}>
          <Lab>Mockups</Lab>
          <Val>{triage} in triage</Val>
          <Chev />
        </Row>
        <Row onClick={() => navigate({ section: "entries" })}>
          <Lab>Entries</Lab>
          <Val>{entries.length} registered</Val>
          <Chev />
        </Row>
        <Row onClick={() => navigate({ section: "todos" })}>
          <Lab>Todos</Lab>
          <Val>
            {doing} doing · {done} done
          </Val>
          <Chev />
        </Row>
        <Row onClick={() => navigate({ section: "inbox" })} last>
          <Lab>Inbox</Lab>
          <Val>{awaiting} awaiting disposition</Val>
          <Chev />
        </Row>
      </Group>

      <GoalRecordPanel slug={project} />

      <GroupLabel>Recent activity</GroupLabel>
      <Group>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Storyboard reported to main</span>
            <Sub>Attention · 18 min ago</Sub>
          </span>
        </Row>
        <Row last>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Plan adopted · per-app storyboards</span>
            <Sub>Today · 12:11 AM</Sub>
          </span>
        </Row>
      </Group>
    </div>
  );
}
