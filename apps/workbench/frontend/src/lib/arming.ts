// Arming — contract 03's projections, as pure functions.
//
// A todo's doing transition arms two projections (a scheduler
// entry, an attention armed row); its terminal transition
// retires both. Armed predicate: a cadence in progress_check
// (not the opt-out value), not at a stop status
// (done|blocked), not in an archived bundle. A doing todo
// that declares no cadence arms at the 15-minute default.

import type { ArmedRow, FileTodo, ProgressDerivation } from "./types";

export const DEFAULT_CADENCE_MINUTES = 15;

/** Parse a cadence declaration ("30m", "2h") to minutes.
 *  Returns null for the opt-out and for unparseable values. */
export function cadenceMinutes(declared: string | undefined): number | null {
  if (declared === undefined) return DEFAULT_CADENCE_MINUTES;
  if (declared === "off") return null;
  const m = /^(\d+)\s*(m|h)$/.exec(declared.trim());
  if (!m) return null;
  const n = Number(m[1]);
  return m[2] === "h" ? n * 60 : n;
}

export function isOptOut(todo: FileTodo): boolean {
  return todo.progressCheck === "off";
}

/** Stop statuses retire the projections (contract 03). */
export function isStopStatus(todo: FileTodo): boolean {
  return todo.status === "done" || todo.status === "blocked";
}

export function isArmed(todo: FileTodo, bundleArchived: boolean): boolean {
  if (bundleArchived || isStopStatus(todo)) return false;
  if (todo.status !== "doing") return false;
  return cadenceMinutes(todo.progressCheck) !== null;
}

/** Render the armed row in contract 03's exact shape
 *  (schemas/armed-row.schema.json; keys sorted, as written). */
export function renderArmedRow(todo: FileTodo): ArmedRow {
  const minutes = cadenceMinutes(todo.progressCheck);
  return {
    armed_at: todo.progressArmed ?? null,
    bundle: todo.bundle,
    cadence: todo.progressCheck ?? null,
    cadence_minutes: minutes,
    handle: todo.id,
    programme: todo.project,
    project: todo.project,
    source: {
      project: todo.project,
      source_class: "project",
      todo: todo.id,
      writer: "workbench-harness",
    },
    status: todo.status,
    title: todo.title,
    todo: todo.id,
  };
}

/** The armed row's filename (contract 03, ARM2). */
export function armedRowFilename(row: ArmedRow): string {
  return `wb-armed-${row.project}-${row.todo.toLowerCase()}.json`;
}

/** The scheduler entry's id + filename (contract 03, ARM1;
 *  entry form is contract 14's). */
export function progressEntryId(todo: FileTodo): string {
  return `wb-progress-${todo.project}-${todo.id.toLowerCase()}`;
}

/** Render the scheduler-entry projection in the target form.
 *  Amendment 3 (2026-11-13): the `migrated` field family does
 *  not exist in the target format — presence in the registry
 *  store through the writer path IS admission. The pinned
 *  fixture (fixtures/scheduler-entry-wb-progress.yaml) still
 *  carries the stamp; the target render drops it. */
export function renderProgressEntry(todo: FileTodo): Record<string, unknown> {
  const cadence = todo.progressCheck ?? `${DEFAULT_CADENCE_MINUTES}m`;
  return {
    id: progressEntryId(todo),
    title: `Progress check - ${todo.project}: ${todo.title} (${todo.id})`,
    kind: "scripted",
    status: "active",
    cadence: { type: "interval", every: cadence },
    owner: "none",
    owner_reason:
      "Machine-written by the workbench harness for one armed todo; the todo file is the record of truth and this entry is its derived schedule.",
    run: {
      argv: [
        "${WS}/workbench-viewer/wb",
        "--root",
        `\${WS}/${todo.project}`,
        "progress-check",
        todo.id,
      ],
    },
    timeout_secs: 120,
    report: { when: "on_failure", ok_exit_codes: [0] },
    classification:
      "fixed command (wb progress-check <todo-id>); exit 0 on track, disarmed, or gone, exit 3 stalled with the stall line as output",
    lifetime: "until_complete",
    self_removal:
      "the harness deletes this entry in the same writer call that disarms the todo",
    catalog: {
      origin: "machine",
      generality: "deployment-specific",
      use_case: "work-tracking",
    },
    source: {
      writer: "workbench-harness",
      project: todo.project,
      todo: todo.id,
      source_class: "project",
    },
  };
}

/** The progress derivation (review §3: computed at read time,
 *  never stored). Stall verdict at 2 missed intervals. */
export function deriveProgress(
  todo: FileTodo,
  now: Date,
): ProgressDerivation | null {
  const minutes = cadenceMinutes(todo.progressCheck);
  if (minutes === null || !todo.progressArmed) return null;
  const last =
    todo.checkpoints.length > 0
      ? todo.checkpoints[todo.checkpoints.length - 1].at
      : todo.progressArmed;
  const elapsedMs = now.getTime() - new Date(last).getTime();
  const missed = Math.max(0, Math.floor(elapsedMs / (minutes * 60_000)));
  return {
    todoId: todo.id,
    cadenceMinutes: minutes,
    lastActivity: last,
    missedChecks: missed,
    verdict: missed >= 2 ? "stalled" : "on-track",
  };
}

/** A checkpoint body line, in the preserved format (WR1):
 *  `progress-checkpoint: <ISO-8601> — <text>`. */
export function checkpointLine(at: Date, text: string): string {
  return `progress-checkpoint: ${at.toISOString()} — ${text}`;
}

/** A todo's name is its id: a GitHub-like slug (contract
 *  11 WR1, the 2026-11-14 naming ruling). */
export const TODO_ID_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** Slugify a title the backend writer's way: lowercase,
 *  non-alphanumeric runs collapse to single hyphens, cut
 *  at the 50-char slug cap, "todo" when nothing survives. */
export function slugifyTodoTitle(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50)
    .replace(/-+$/g, "");
  return slug || "todo";
}

/** Derive a todo's name from its title, suffixing -2,
 *  -3, … until free in `taken` (the project's name set) —
 *  the mirror of the backend writer's derivation. */
export function deriveTodoName(
  title: string,
  taken: Iterable<string>,
): string {
  const used = new Set(taken);
  const base = slugifyTodoTitle(title);
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}-${n}`)) n++;
  return `${base}-${n}`;
}
