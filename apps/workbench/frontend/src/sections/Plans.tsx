import { useState } from "react";
import { useIsPhone } from "@kit/lib/responsive";
import { SegmentedControl } from "@kit/components/controls/SegmentedControl";
import { Button } from "@kit/components/controls/Button";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { AnnotationThread, Plan } from "../lib/types";
import { PickChip } from "./Mockups";
import { PlanReader } from "../components/PlanReader";
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
} from "../components/ui";

// Frame 4 · Plans — bundle list (In progress / Finished)
// beside the reading pane: steps as served, with the
// Structured / Raw toggle over the same plan record. Step
// state derives from the bundle's file todos — marking a
// todo done in Todos moves the plan's count here.

function PlanRow({
  plan,
  selected,
  doneCount,
  onSelect,
  last,
}: {
  plan: Plan;
  selected: boolean;
  doneCount: number;
  onSelect: () => void;
  last?: boolean;
}) {
  const unit = plan.bundle.includes("backlog") ? "items" : "steps";
  return (
    <Row onClick={onSelect} selected={selected} last={last}>
      <span className="min-w-0">
        <span className="block truncate text-[14.5px] font-medium">{plan.title}</span>
        <Sub>
          {doneCount} of {plan.steps.length} {unit}
          {plan.state === "in-progress" ? " landed" : ""}
        </Sub>
      </span>
      <span className="ml-auto">
        <TodoPill status={plan.state === "done" ? "done" : plan.state === "in-progress" ? "doing" : "todo"} />
      </span>
    </Row>
  );
}

const ANCHOR_STYLE: Record<AnnotationThread["status"], { label: string; bg: string; fg: string }> = {
  anchored: {
    label: "Anchored",
    bg: "color-mix(in srgb, var(--wb-okabe-bluish-green) 14%, transparent)",
    fg: "var(--wb-status-implemented-text)",
  },
  relocated: {
    label: "Relocated",
    bg: "color-mix(in srgb, var(--wb-okabe-orange) 16%, transparent)",
    fg: "var(--wb-status-stale-text)",
  },
  orphaned: {
    label: "Orphaned",
    bg: "color-mix(in srgb, var(--wb-okabe-vermilion) 12%, transparent)",
    fg: "var(--wb-status-hard-gate-text)",
  },
};

const planInputStyle: React.CSSProperties = {
  backgroundColor: "var(--wb-surface-sunken)",
  color: "var(--wb-content-primary)",
  borderRadius: 9,
  padding: "6px 10px",
  fontSize: 13.5,
};

export function Plans({ initialBundle }: { initialBundle?: string }) {
  useStoreVersion();
  const a = useAdapter();
  const isPhone = useIsPhone();
  const { navigate, project } = useNav();
  const plans = a.plans(project);
  const [selected, setSelected] = useState<string>(
    initialBundle ?? plans.find((p) => p.state === "in-progress")?.bundle ?? plans[0]?.bundle ?? "",
  );
  const [view, setView] = useState<"structured" | "raw" | "formatted">("structured");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [annotateQuote, setAnnotateQuote] = useState("");
  const [annotateBody, setAnnotateBody] = useState("");
  const [replyBodies, setReplyBodies] = useState<Record<string, string>>({});
  const plan = a.plan(selected) ?? plans[0];
  if (!plan) {
    return (
      <div className="px-[26px] py-[22px]">
        <LargeTitle>Plans</LargeTitle>
        <Subtitle>No plan bundles in this project.</Subtitle>
      </div>
    );
  }
  const inProgress = plans.filter((p) => !p.archived);
  const finished = plans.filter((p) => p.archived);
  const doneOf = (p: Plan) =>
    p.steps.filter((s) => s.todoId && a.todo(s.todoId)?.status === "done").length;

  return (
    <div className={isPhone ? "px-[18px] py-4" : "px-[26px] py-[22px]"}>
      {/* Phone stacks the bundle list over the reading pane:
          the fixed 272px list column beside a flex-1 pane
          left the pane ~48px wide at 390px
          (mobile critic). */}
      <div className={isPhone ? "flex flex-col gap-[18px]" : "flex gap-[18px]"}>
        <div className={isPhone ? "w-full" : "w-[272px] flex-[0_0_272px]"}>
          <GroupLabel>In progress</GroupLabel>
          <Group>
            {inProgress.map((p, i) => (
              <PlanRow
                key={p.bundle}
                plan={p}
                selected={p.bundle === plan.bundle}
                doneCount={doneOf(p)}
                onSelect={() => setSelected(p.bundle)}
                last={i === inProgress.length - 1}
              />
            ))}
          </Group>
          <GroupLabel>Finished</GroupLabel>
          <Group>
            {finished.map((p, i) => (
              <PlanRow
                key={p.bundle}
                plan={p}
                selected={p.bundle === plan.bundle}
                doneCount={doneOf(p)}
                onSelect={() => setSelected(p.bundle)}
                last={i === finished.length - 1}
              />
            ))}
          </Group>
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="m-0 mb-1 text-[23px] font-bold [overflow-wrap:anywhere]">{plan.title}</h2>
          <Subtitle>
            Status: {plan.state === "in-progress" ? "in progress" : plan.state} · Executor:{" "}
            {plan.executor} · {plan.createdLabel}
          </Subtitle>
          {view === "structured" ? (
            <div>
              {plan.steps.map((s) => {
                const t = s.todoId ? a.todo(s.todoId) : undefined;
                return (
                  <button
                    key={s.n}
                    type="button"
                    onClick={() => t && navigate({ section: "todos" })}
                    className="mb-2.5 block w-full p-[12px_14px] text-left"
                    style={{
                      backgroundColor: "var(--wb-surface-2)",
                      border: "1px solid var(--wb-border-default)",
                      borderRadius: "var(--wb-radius-md)",
                    }}
                  >
                    <span className="flex items-center gap-2">
                      <span className="min-w-0 text-sm font-semibold [overflow-wrap:anywhere]">
                        Step {s.n} — {s.title}
                      </span>
                      {t ? (
                        <span className="ml-auto">
                          <TodoPill status={t.status} />
                        </span>
                      ) : null}
                    </span>
                    <span
                      className="mt-[3px] block text-[12.8px] [overflow-wrap:anywhere]"
                      style={{ color: "var(--wb-content-secondary)" }}
                    >
                      {s.detail}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : view === "formatted" ? (
            <PlanReader raw={plan.raw} onAnnotate={(q) => setAnnotateQuote(q)} />
          ) : (
            <pre
              className="overflow-x-auto p-4 font-mono text-[12.5px] leading-[1.7] whitespace-pre-wrap"
              style={{
                backgroundColor: "var(--wb-surface-2)",
                border: "1px solid var(--wb-border-default)",
                borderRadius: "var(--wb-radius-md)",
                color: "var(--wb-content-primary)",
              }}
            >
              {plan.raw}
            </pre>
          )}
          <div className="mt-1 flex flex-wrap gap-2">
            <PickChip label="Structured" on={view === "structured"} onPress={() => setView("structured")} />
            <PickChip label="Formatted" on={view === "formatted"} onPress={() => setView("formatted")} />
            <PickChip label="Raw" on={view === "raw"} onPress={() => setView("raw")} />
          </div>

          <QuestionsPanel
            plan={plan}
            answers={answers}
            setAnswers={setAnswers}
          />
          <AnnotationsPanel
            plan={plan}
            annotateQuote={annotateQuote}
            setAnnotateQuote={setAnnotateQuote}
            annotateBody={annotateBody}
            setAnnotateBody={setAnnotateBody}
            replyBodies={replyBodies}
            setReplyBodies={setReplyBodies}
          />
        </div>
      </div>
    </div>
  );
}

/** Plan questions (W8) — the plan file's Questions section
 *  as a resolve surface: pick an offered option or write
 *  the answer, then resolve — the answers write back into
 *  the plan (POST …/plan/resolve at the shell). */
function QuestionsPanel({
  plan,
  answers,
  setAnswers,
}: {
  plan: Plan;
  answers: Record<string, string>;
  setAnswers: (fn: (prev: Record<string, string>) => Record<string, string>) => void;
}) {
  const a = useAdapter();
  const questions = a.planQuestions(plan.bundle);
  if (questions.length === 0) return null;
  const open = questions.filter((q) => !q.answer);
  const draftCount = open.filter((q) => answers[q.id]?.trim()).length;
  return (
    <div>
      <GroupLabel>Questions · {open.length} open</GroupLabel>
      <div className="flex flex-col gap-2.5">
        {questions.map((q) => (
          <div
            key={q.id}
            className="p-[12px_14px]"
            style={{
              backgroundColor: "var(--wb-surface-2)",
              border: "1px solid var(--wb-border-default)",
              borderRadius: "var(--wb-radius-md)",
            }}
          >
            <div className="text-sm font-semibold [overflow-wrap:anywhere]">{q.text}</div>
            {q.answer ? (
              <div className="mt-1.5 text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
                Answered: {q.answer}
                {q.answeredBy ? ` · ${q.answeredBy}` : ""}
                {q.answeredLabel ? ` · ${q.answeredLabel}` : ""}
              </div>
            ) : (
              <div className="mt-2">
                {q.options && q.options.length > 0 ? (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {q.options.map((opt) => (
                      <PickChip
                        key={opt}
                        label={opt}
                        on={answers[q.id] === opt}
                        onPress={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                      />
                    ))}
                  </div>
                ) : null}
                <input
                  aria-label={`Answer for: ${q.text}`}
                  value={answers[q.id] ?? ""}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                  placeholder="Write the answer…"
                  className="w-full"
                  style={planInputStyle}
                />
              </div>
            )}
          </div>
        ))}
      </div>
      {open.length > 0 ? (
        <div className="mt-3">
          <Button
            disabled={draftCount === 0}
            onClick={() => {
              void a.resolvePlanQuestions(plan.bundle, answers);
              setAnswers(() => ({}));
            }}
          >
            Resolve {draftCount > 0 ? `${draftCount} answer${draftCount === 1 ? "" : "s"}` : ""}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** Anchored annotations (W5) — threads on quoted passages
 *  of the plan. Select text in the Formatted view and hit
 *  Annotate, or type the passage here. Each thread shows
 *  its live anchor state (anchored / relocated /
 *  orphaned), replies, and resolve. */
function AnnotationsPanel({
  plan,
  annotateQuote,
  setAnnotateQuote,
  annotateBody,
  setAnnotateBody,
  replyBodies,
  setReplyBodies,
}: {
  plan: Plan;
  annotateQuote: string;
  setAnnotateQuote: (q: string) => void;
  annotateBody: string;
  setAnnotateBody: (b: string) => void;
  replyBodies: Record<string, string>;
  setReplyBodies: (fn: (prev: Record<string, string>) => Record<string, string>) => void;
}) {
  const a = useAdapter();
  const threads = a.annotationsForPlan(plan.bundle);
  return (
    <div>
      <GroupLabel>Annotations · {threads.filter((t) => !t.resolved).length} open</GroupLabel>
      <div
        className="mb-3 p-[12px_14px]"
        style={{
          backgroundColor: "var(--wb-surface-2)",
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-md)",
        }}
      >
        <input
          aria-label="Passage to annotate"
          value={annotateQuote}
          onChange={(e) => setAnnotateQuote(e.target.value)}
          placeholder="Passage — select it in the Formatted view, or type it"
          className="mb-2 w-full"
          style={planInputStyle}
        />
        <textarea
          aria-label="Annotation"
          value={annotateBody}
          onChange={(e) => setAnnotateBody(e.target.value)}
          placeholder="Annotation…"
          rows={2}
          className="w-full"
          style={{ ...planInputStyle, resize: "vertical" }}
        />
        <div className="mt-2">
          <Button
            disabled={!annotateQuote.trim() || !annotateBody.trim()}
            onClick={() => {
              // Server-first: the composer clears only
              // on acceptance; a refusal keeps the text.
              void a
                .addAnnotation(plan.bundle, annotateQuote.trim(), annotateBody.trim())
                .then(() => {
                  setAnnotateQuote("");
                  setAnnotateBody("");
                })
                .catch(() => {});
            }}
          >
            Add annotation
          </Button>
        </div>
      </div>
      <div className="flex flex-col gap-2.5">
        {threads.map((t) => {
          const chip = ANCHOR_STYLE[t.status];
          return (
            <div
              key={t.id}
              className="p-[12px_14px]"
              style={{
                backgroundColor: "var(--wb-surface-2)",
                border: "1px solid var(--wb-border-default)",
                borderRadius: "var(--wb-radius-md)",
                opacity: t.resolved ? 0.72 : 1,
              }}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="inline-flex rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                  style={{ backgroundColor: chip.bg, color: chip.fg }}
                >
                  {chip.label}
                </span>
                {t.resolved ? (
                  <span className="text-xs font-semibold" style={{ color: "var(--wb-content-secondary)" }}>
                    Resolved
                  </span>
                ) : null}
                <span className="min-w-0 flex-1 truncate text-[13px] italic" style={{ color: "var(--wb-content-secondary)" }}>
                  "{t.anchorQuote}"
                </span>
              </div>
              <div className="mt-2 flex flex-col gap-1.5">
                {t.messages.map((m) => (
                  <div key={m.id} className="text-[13.5px] leading-[1.5]">
                    <span className="font-bold">{m.author}</span>{" "}
                    <span style={{ color: "var(--wb-content-muted)" }}>{m.when}</span>
                    <span className="block [overflow-wrap:anywhere]">{m.body}</span>
                  </div>
                ))}
              </div>
              <div className="mt-2.5 flex items-start gap-2">
                <input
                  aria-label="Reply to annotation"
                  value={replyBodies[t.id] ?? ""}
                  onChange={(e) => setReplyBodies((prev) => ({ ...prev, [t.id]: e.target.value }))}
                  placeholder="Reply…"
                  className="min-w-0 flex-1"
                  style={planInputStyle}
                />
                <Button
                  variant="secondary"
                  disabled={!(replyBodies[t.id] ?? "").trim()}
                  onClick={() => {
                    // Server-first: the reply box clears
                    // only on acceptance.
                    void a
                      .replyAnnotation(t.id, (replyBodies[t.id] ?? "").trim())
                      .then(() =>
                        setReplyBodies((prev) => ({ ...prev, [t.id]: "" })),
                      )
                      .catch(() => {});
                  }}
                >
                  Reply
                </Button>
                {a.mode === "mock" ? (
                  <Button
                    variant="secondary"
                    onClick={() => a.setAnnotationResolved(t.id, !t.resolved)}
                  >
                    {t.resolved ? "Reopen" : "Resolve"}
                  </Button>
                ) : null}
                {/* Live mode renders no toggle: resolved-ness
                    is derived from the thread's message
                    lifecycle states (W-C5 disposition), so
                    the state above is read-only here — a
                    local toggle would fabricate a state the
                    server contradicts on reload. The mock
                    keeps the toggle functional against the
                    fake, per demo rules. */}
              </div>
            </div>
          );
        })}
        {threads.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
            No annotations on this plan yet.
          </p>
        ) : null}
      </div>
    </div>
  );
}
