// Mock seed — invented programme/todo content in the pinned
// served shapes (review §2–§3, contracts 02/03/11). Project
// slugs and the manifest census are the S1 overlay's
// (docs/overlay/workbench.md: 11 canonical projects); all
// content below is invented for the mock store — no live
// workbench state was read. Specimen titles/labels follow the
// approved storyboard, which is the design record.
//
// The builders live one domain area per module under
// seed/ (projects, entries, plans, todos, goals,
// messages + annotations + threads, repos); this module
// keeps the vocabulary, the SeedDb shape, and buildSeed.

import type {
  AnnotationThread,
  Entry,
  FileTodo,
  GoalRecord,
  InboxMessage,
  MessageThread,
  Plan,
  Project,
  Repo,
  StatusVocabularyRow,
} from "./types";
import { buildEntries } from "./seed/entries";
import { buildGoals } from "./seed/goals";
import { buildAnnotations, buildMessages, buildThreads } from "./seed/messages";
import { buildPlans } from "./seed/plans";
import { buildProjects } from "./seed/projects";
import { buildRepos } from "./seed/repos";
import { seedTime } from "./seed/time";
import { buildTodos } from "./seed/todos";

/** The task-mode status vocabulary, as served (contract 06).
 *  These are the pinned domain defaults — the same rows as
 *  contracts/fixtures/attention-status-codes.json, which
 *  validate:mocks checks this mirror against. Registry
 *  contents are data: at S8 the pipeline serves the live
 *  registry, owner edits included, through the same feed. */
export const STATUS_VOCABULARY: StatusVocabularyRow[] = [
  { code: "WORKING", label: "Working", need: "agent_clearable", short: "W", terminal: false },
  { code: "CONTINUE", label: "Continue", need: "agent_clearable", short: "C", terminal: false },
  { code: "DONE", label: "Done", need: "agent_clearable", short: "D", terminal: true },
  { code: "CLOSED", label: "Closed", need: "agent_clearable", short: "CL", terminal: true },
  { code: "PARKED", label: "Parked", need: "agent_clearable", short: "P", terminal: false },
  { code: "BLOCKED-OWNER", label: "Blocked — owner", need: "owner_actionable", short: "BO", terminal: false },
  { code: "BLOCKED-HARD", label: "Blocked — hard stop", need: "owner_actionable", short: "BH", terminal: false },
  { code: "REVIEW", label: "Review", need: "owner_actionable", short: "R", terminal: false },
];

export interface SeedDb {
  projects: Project[];
  entries: Entry[];
  plans: Plan[];
  todos: FileTodo[];
  goals: GoalRecord[];
  messages: InboxMessage[];
  repos: Repo[];
  annotations: AnnotationThread[];
  threads: MessageThread[];
}

export function buildSeed(now: Date): SeedDb {
  const t = seedTime(now);

  const projects = buildProjects();
  const entries = buildEntries();
  const plans = buildPlans();
  const todos = buildTodos(t);
  const goals = buildGoals(t);
  const messages = buildMessages();
  const repos = buildRepos();
  const annotations = buildAnnotations();
  const threads = buildThreads();

  // Every entry carries its file list (the detail's served
  // shape): a mockup's page + assets, a doc's own file, a
  // plan's plan.md.
  for (const e of entries) {
    if (e.files) continue;
    if (e.kind === "mockup") {
      e.files = [
        { path: "index.html", isMain: true, sizeLabel: "18 KB" },
        { path: "frame.css", isMain: false, sizeLabel: "4 KB" },
      ];
    } else if (e.repoPath) {
      e.files = [{ path: e.repoPath.path, isMain: true, sizeLabel: "9 KB" }];
    } else {
      e.files = [{ path: "plan.md", isMain: true, sizeLabel: "12 KB" }];
    }
    e.stateJson = JSON.stringify(
      { viewport: e.viewport ?? null, mode: e.mode ?? null, state: e.stateHash ?? null },
      null,
      2,
    );
  }

  return { projects, entries, plans, todos, goals, messages, repos, annotations, threads };
}
