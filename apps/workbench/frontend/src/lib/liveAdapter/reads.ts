// Live adapter read derivations over the projected
// state: project rollups, the home summary,
// classification, armed rows, the board, counts, and
// the goal bundle/todo reads.

import {
  deriveProgress,
  isArmed,
  isOptOut,
  renderArmedRow,
} from "../arming";
import type { BoardCard } from "../seam";
import type {
  ArmedRow,
  ClassificationRow,
  FileTodo,
  GoalRecord,
  Plan,
  ProgressDerivation,
  ProjectRollup,
} from "../types";
import type { LiveHost } from "./host";


export function projectRollups(h: LiveHost): ProjectRollup[] {
  return h.s.projectList.slice(0, 5).map((p) => {
    const home = h.doc.home.projects.find((r) => r.slug === p.slug);
    const board = h.s.boards.get(p.slug);
    const needsChanges = (board?.review_queue ?? []).filter((item) =>
      item.reasons.some((r) => r.startsWith("needs-changes")),
    ).length;
    const triage = home?.review.triage_count ?? 0;
    if (p.health === "degraded") {
      return { project: p, dot: "warn" as const, sub: p.healthNote, chip: { type: "plain" as const, text: "Degraded" } };
    }
    if (p.health === "manifest-only") {
      return { project: p, dot: "muted" as const, sub: p.healthNote, chip: { type: "plain" as const, text: "Manifest only" } };
    }
    if (needsChanges > 0) {
      return {
        project: p,
        dot: "ok" as const,
        sub: `${needsChanges} mockup awaiting review`,
        chip: { type: "badge" as const, kind: "needs-changes" as const, text: `Needs changes · ${needsChanges}` },
      };
    }
    if (triage > 0) {
      return {
        project: p,
        dot: "ok" as const,
        sub: `${triage} in triage · board updated ${p.lastActivityLabel}`,
        chip: { type: "plain" as const, text: `${triage} in triage` },
      };
    }
    if ((home?.todos.counts.doing ?? 0) > 0) {
      return {
        project: p,
        dot: "ok" as const,
        sub: `${home!.todos.counts.doing} todo${home!.todos.counts.doing > 1 ? "s" : ""} in progress`,
        chip: { type: "ruled" as const, status: "implemented" as const },
      };
    }
    return { project: p, dot: "muted" as const, sub: "Quiet", chip: { type: "plain" as const, text: "Quiet" } };
  });
}

export function homeSummary(h: LiveHost) {
  let awaitingReview = 0;
  for (const board of h.s.boards.values()) awaitingReview += board.review_queue.length;
  let doingNow = 0;
  for (const row of h.doc.home.projects) doingNow += row.todos.counts.doing ?? 0;
  return {
    sweptCount: h.s.projectList.length,
    serverHealthy: true,
    editingOn: h.s.settingsState.guardedSaves,
    awaitingReview,
    doingNow,
  };
}

export function classification(h: LiveHost, project: string): ClassificationRow[] {
  return h.s.todoList
    .filter((t) => t.project === project)
    .map((t) => {
      const plan = h.plan(t.bundle);
      const armed = isArmed(t, plan?.archived ?? false);
      let derivation: ProgressDerivation | null = null;
      if (armed) {
        derivation = h.s.mutatedTodos.has(t.id)
          ? deriveProgress(t, h.clock())
          : (h.s.servedDerivations.get(`${project}:${t.id}`) ??
            deriveProgress(t, h.clock()));
      }
      return { todo: t, optOut: isOptOut(t), armed, derivation };
    });
}

export function armedRows(h: LiveHost): ArmedRow[] {
  return h.s.todoList
    .filter((t) => isArmed(t, h.plan(t.bundle)?.archived ?? false))
    .map((t) => {
      const row = renderArmedRow(t);
      const cls = h.s.sourceClass.get(t.project);
      if (cls && cls !== row.source.source_class) {
        return { ...row, source: { ...row.source, source_class: cls } };
      }
      return row;
    })
    .sort((a, b) => (a.armed_at ?? "").localeCompare(b.armed_at ?? ""));
}

export function board(h: LiveHost): BoardCard[] {
  const cards: BoardCard[] = [];
  for (const summary of h.doc.projects.projects) {
    const board = h.s.boards.get(summary.slug);
    if (!board) continue;
    const tag = summary.slug.toUpperCase();
    for (const item of board.review_queue) {
      const needs = item.reasons.some((r) => r.startsWith("needs-changes"));
      cards.push({
        id: `card-entry-${item.id}`,
        lane: "review",
        projectTag: tag,
        title: item.title,
        meta: "",
        badge: { kind: "review", text: needs ? "needs-changes" : "in-triage" },
        target: { kind: "entry", id: item.id },
      });
    }
    for (const lane of ["todo", "doing", "done"] as const) {
      for (const card of board.plans[lane] ?? []) {
        cards.push({
          id: `card-plan-${card.bundle}`,
          lane,
          projectTag: tag,
          title: card.title,
          meta: `Plan · ${card.step_count ?? 0} steps`,
          target: { kind: "plan", bundle: card.bundle! },
        });
      }
    }
    for (const lane of ["todo", "doing", "blocked", "done"] as const) {
      for (const card of board.todos[lane] ?? []) {
        const plan = card.bundle ? h.plan(card.bundle) : undefined;
        cards.push({
          id: `card-todo-${card.id}`,
          lane: lane === "blocked" ? "doing" : lane,
          projectTag: tag,
          title: card.title,
          meta: `Todo · ${plan?.title ?? card.bundle ?? ""}`,
          target: { kind: "todo", id: card.id! },
        });
      }
    }
  }
  return cards;
}

export function goalBundle(h: LiveHost, goal: GoalRecord): Plan | undefined {
  const named = goal.lastPost?.refs?.plan;
  if (named) {
    const plan = h.plan(named);
    if (plan) return plan;
  }
  const inProgress = h.s.planList.filter(
    (p) => p.project === goal.project && p.state === "in-progress" && !p.archived,
  );
  return inProgress.length === 1 ? inProgress[0] : undefined;
}

export function goalTodos(h: LiveHost, goal: GoalRecord): FileTodo[] {
  const bundle = goalBundle(h, goal);
  if (!bundle) return [];
  const byId = new Map(
    h.s.todoList
      .filter((t) => t.project === goal.project && t.bundle === bundle.bundle)
      .map((t) => [t.id, t]),
  );
  const ordered: FileTodo[] = [];
  for (const step of bundle.steps) {
    const t = step.todoId ? byId.get(step.todoId) : undefined;
    if (t) {
      ordered.push(t);
      byId.delete(t.id);
    }
  }
  return [...ordered, ...byId.values()];
}

export function counts(h: LiveHost) {
  const terminal = new Set(
    h.doc.statusVocabulary.filter((r) => r.terminal).map((r) => r.code),
  );
  let triage = 0;
  for (const board of h.s.boards.values()) triage += board.review_queue.length;
  return {
    mockupsInTriage: triage,
    boardDoing: h.board().filter((c) => c.lane === "doing").length,
    inboxAwaiting: h.s.messageList.filter((m) => m.disposition === null).length,
    goalsActive: h.s.goalList.filter(
      (g) => !g.lastPost || !terminal.has(g.lastPost.status_code),
    ).length,
  };
}
