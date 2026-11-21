// Todo projection: a served feed todo row in the
// seam's FileTodo shape — checkpoint lines parsed out
// of the body, unknown fields carried as extras.

import type { FeedTodoRow } from "../feeds";
import type { FileTodo } from "../types";

const KNOWN_TODO_FIELDS = new Set([
  "id", "title", "status", "feature", "plan", "plan_step",
  "worktree", "created", "updated", "progress_check",
  "progress_armed",
]);

const CHECKPOINT_RE = /^progress-checkpoint: (\S+) — (.*)$/;


export function projectTodo(row: FeedTodoRow, project: string): FileTodo {
  const checkpoints: { at: string; text: string }[] = [];
  const noteLines: string[] = [];
  for (const line of (row.body ?? "").split("\n")) {
    const m = CHECKPOINT_RE.exec(line);
    if (m) checkpoints.push({ at: m[1], text: m[2] });
    else noteLines.push(line);
  }
  const extra: Record<string, string> = {};
  for (const [k, v] of Object.entries(row.fields ?? {})) {
    if (!KNOWN_TODO_FIELDS.has(k)) extra[k] = v;
  }
  return {
    id: row.id,
    project,
    bundle: row.bundle,
    title: row.title,
    status: row.status,
    created: row.created ?? "",
    updated: row.updated ?? "",
    progressCheck: row.progress_check ?? undefined,
    progressArmed: row.progress_armed ?? undefined,
    checkpoints,
    notes: noteLines.join("\n").trim(),
    extra,
  };
}
