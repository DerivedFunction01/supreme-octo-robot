// Plan projection: a served plan bundle (+ its plan
// document and the project's todo rows) in the seam's
// Plan shape; a bundle with no plan projects to null.

import type { FeedPlanDoc, FeedTodoRow } from "../feeds";
import type { Plan } from "../types";
import { dateLabel } from "./shared";


export function projectPlan(
  bundle: { id: string; archived: boolean; plan: { title: string; status_bucket: "todo" | "doing" | "done" } | null },
  doc: FeedPlanDoc | undefined,
  rows: FeedTodoRow[],
  project: string,
): Plan | null {
  if (!bundle.plan) return null;
  const state =
    bundle.plan.status_bucket === "doing"
      ? "in-progress"
      : bundle.plan.status_bucket === "done"
        ? "done"
        : "draft";
  // A step's todo is the bundle todo whose served
  // plan_step names it (WR1 front matter).
  const byStep = new Map<number, string>();
  for (const row of rows) {
    if (row.bundle === bundle.id && row.plan_step != null) {
      byStep.set(Number(row.plan_step), row.id);
    }
  }
  const steps = (doc?.steps ?? []).map((s) => {
    const heading = /^###\s+Step\s+\d+\s+—\s+(.*)$/m.exec(s.raw ?? s.body ?? "");
    return {
      n: s.n,
      title: heading ? heading[1].trim() : `Step ${s.n}`,
      detail: s.body ?? "",
      todoId: byStep.get(s.n),
    };
  });
  const datePrefix = /^\d{4}-\d{2}-\d{2}/.exec(bundle.id)?.[0];
  return {
    bundle: bundle.id,
    project,
    title: bundle.plan.title,
    state,
    executor: doc?.fields?.["Executor"] ?? "",
    createdLabel: datePrefix ? dateLabel(`${datePrefix}T00:00:00+00:00`) : "",
    steps,
    raw: doc?.markdown ?? "",
    archived: bundle.archived,
  };
}
