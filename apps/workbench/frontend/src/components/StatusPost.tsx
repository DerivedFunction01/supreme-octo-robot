import { useState } from "react";
import { Button } from "@kit/components/controls/Button";
import { useAdapter } from "../lib/store";
import type { GoalRecord, StatusPost } from "../lib/types";
import { PickChip } from "../sections/Mockups";
import { Row, Sub } from "./ui";

// The task-mode status vocabulary (contract 06) as the app
// renders it: the label on every chip and in every picker
// comes from the served vocabulary rows — apps never
// re-derive a label, a need, or a terminal flag, and never
// render a raw code where a label is served. This file is
// the one rendering, shared by the Overview goal panel and
// the Goals section.

type Tone = { dot: string; bg: string; fg: string };

const TONES: Record<StatusPost["status_code"], Tone> = {
  WORKING: {
    dot: "var(--ui-okabe-blue)",
    bg: "color-mix(in srgb, var(--ui-okabe-blue) 12%, transparent)",
    fg: "var(--ui-status-canonical-text)",
  },
  CONTINUE: {
    dot: "var(--ui-okabe-sky-blue)",
    bg: "color-mix(in srgb, var(--ui-okabe-sky-blue) 16%, transparent)",
    fg: "var(--ui-status-canonical-text)",
  },
  REVIEW: {
    dot: "var(--ui-okabe-reddish-purple)",
    bg: "color-mix(in srgb, var(--ui-okabe-reddish-purple) 12%, transparent)",
    fg: "var(--ui-status-needs-changes-text)",
  },
  PARKED: {
    dot: "var(--ui-content-muted)",
    bg: "var(--ui-surface-sunken)",
    fg: "var(--ui-content-secondary)",
  },
  "BLOCKED-OWNER": {
    dot: "var(--ui-okabe-orange)",
    bg: "color-mix(in srgb, var(--ui-okabe-orange) 18%, transparent)",
    fg: "var(--ui-status-deferred-text)",
  },
  "BLOCKED-HARD": {
    dot: "var(--ui-okabe-vermilion)",
    bg: "color-mix(in srgb, var(--ui-okabe-vermilion) 12%, transparent)",
    fg: "var(--ui-status-hard-gate-text)",
  },
  DONE: {
    dot: "var(--ui-okabe-bluish-green)",
    bg: "color-mix(in srgb, var(--ui-okabe-bluish-green) 14%, transparent)",
    fg: "var(--ui-status-done-text)",
  },
  CLOSED: {
    dot: "var(--ui-okabe-bluish-green)",
    bg: "color-mix(in srgb, var(--ui-okabe-bluish-green) 14%, transparent)",
    fg: "var(--ui-status-done-text)",
  },
};

const NO_POST_TONE: Tone = {
  dot: "var(--ui-content-muted)",
  bg: "var(--ui-surface-sunken)",
  fg: "var(--ui-content-secondary)",
};

function chipShell(tone: Tone, label: string) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold whitespace-nowrap"
      style={{ backgroundColor: tone.bg, color: tone.fg }}
    >
      <span className="block h-[7px] w-[7px] rounded-full" style={{ backgroundColor: tone.dot }} />
      {label}
    </span>
  );
}

/** The status chip for a goal's latest post — the served
 *  label in the code's tone; no post renders the idle
 *  "No post yet" chip. */
export function StatusChip({ post }: { post: StatusPost | null }) {
  const a = useAdapter();
  if (!post) return chipShell(NO_POST_TONE, "No post yet");
  const row = a.statusVocabulary().find((r) => r.code === post.status_code);
  return chipShell(TONES[post.status_code], row?.label ?? post.status_code);
}

const BLOCKED = new Set<StatusPost["status_code"]>(["BLOCKED-OWNER", "BLOCKED-HARD"]);

/** The status-post form, as rows inside the caller's Group:
 *  the vocabulary as picker chips (served labels, never raw
 *  codes), the one-line summary, and — when a blocked code
 *  is picked — the basis-citation fields the contract 11
 *  amendment requires (the writer refuses an uncited
 *  blocked post; the refusal shows on the form's face). */
export function StatusPostFormRows({ goal }: { goal: GoalRecord }) {
  const a = useAdapter();
  const vocab = a.statusVocabulary();
  const prev = goal.lastPost;
  const [code, setCode] = useState<StatusPost["status_code"]>("WORKING");
  const [summary, setSummary] = useState("");
  const [citeThread, setCiteThread] = useState("");
  const [citeAt, setCiteAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const blocked = BLOCKED.has(code);
  const terminal = vocab.find((r) => r.code === code)?.terminal ?? false;

  const submit = () => {
    if (summary.trim().length === 0) {
      setError("A status post needs a summary — the grouped form is never empty-filled (contract 03).");
      return;
    }
    if (blocked && citeThread.trim().length === 0) {
      setError(
        "A blocked post must cite its basis — the owner's message reference (thread + time). An uncited blocked claim is not a postable state (contract 11).",
      );
      return;
    }
    // Server-first: the form clears only on the store's
    // acceptance; a writer refusal (the server's own
    // text) surfaces here and the typed post stays.
    a.postGoalStatus(goal.slug, {
      handle: prev?.handle ?? `@${goal.project}`,
      status_code: code,
      summary: summary.trim(),
      refs: prev?.refs ?? {
        project: goal.project,
        plan: a.goalBundle(goal)?.bundle ?? null,
        todo_ids: [],
      },
      ...(terminal ? {} : { ongoing: [summary.trim()] }),
      ...(terminal ? {} : { owner_waiting: prev?.owner_waiting ?? undefined }),
      ...(blocked
        ? { basis_citation: { thread: citeThread.trim(), at: citeAt.trim() } }
        : {}),
    })
      .then(() => {
        setError(null);
        setSummary("");
        setCiteThread("");
        setCiteAt("");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      });
  };

  const inputCls =
    "min-w-0 flex-1 rounded-[var(--ui-radius-sm)] px-2.5 py-2 text-sm";
  const inputStyle = {
    backgroundColor: "var(--ui-surface-1)",
    border: "1px solid var(--ui-border-default)",
    color: "var(--ui-content-primary)",
  } as const;

  return (
    <>
      <Row>
        <span className="flex flex-wrap items-center gap-1.5">
          {vocab.map((r) => (
            <PickChip
              key={r.code}
              label={r.label}
              on={code === r.code}
              onPress={() => setCode(r.code)}
            />
          ))}
        </span>
      </Row>
      {blocked ? (
        <Row>
          <span className="flex w-full flex-wrap items-center gap-2">
            <input
              value={citeThread}
              onChange={(e) => setCiteThread(e.target.value)}
              placeholder="Basis citation — owner message thread"
              aria-label="Basis citation thread"
              className={inputCls}
              style={inputStyle}
            />
            <input
              value={citeAt}
              onChange={(e) => setCiteAt(e.target.value)}
              placeholder="Message time"
              aria-label="Basis citation time"
              className="w-[170px] rounded-[var(--ui-radius-sm)] px-2.5 py-2 text-sm"
              style={inputStyle}
            />
          </span>
        </Row>
      ) : null}
      <Row last>
        <span className="flex w-full flex-wrap items-center gap-2">
          <input
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Summary — one line"
            aria-label="Status post summary"
            className={inputCls}
            style={inputStyle}
          />
          <Button variant="primary" onClick={submit}>
            Post status
          </Button>
        </span>
      </Row>
      {error ? (
        <Row last>
          <Sub>
            <span style={{ color: "var(--ui-danger)" }}>{error}</span>
          </Sub>
        </Row>
      ) : null}
    </>
  );
}
