// The live feeds document — the assembly the work-record
// pipeline's server half produces in one pass
// (pipeline/workrecord/server/assemble.py): every route
// payload the pinned workbench served, keyed for the
// adapter, plus the merged registry's status vocabulary,
// the armed set, and the goal records.
//
// The serving shell injects this document as
// globalThis.__WORKBENCH_FEEDS__ (its original topology);
// the surface also serves it at GET /api/feeds, and the
// published integration entry fetches it there and
// injects the same global before the app loads.
// store.tsx selects the live adapter when the document
// is present and the mock adapter (the demo persona)
// when it is not. Shapes below are the served shapes as
// the pipeline produces them — wide payloads keep their
// extra keys (index signatures); the adapter reads the
// fields it projects.

import type { ArmedRow, GoalRecord, StatusVocabularyRow } from "./types";

export interface FeedManifest {
  registry: string | null;
  plans: string | null;
  mockups: string | null;
  archive: string | null;
  catalog: {
    origin: string | null;
    generality: string | null;
    use_case: string | null;
  } | null;
}

export interface FeedProjectSummary {
  slug: string;
  name: string;
  root: string;
  sections: Record<string, boolean>;
  also_at: string[];
  manifest: FeedManifest | null;
}

export interface FeedHomeRow {
  slug: string;
  name: string;
  root: string;
  degraded: boolean;
  reasons: string[];
  git: { branch: string | null; head_short: string | null } | null;
  plans: { available: boolean; counts: Record<string, number>; in_progress: unknown; total: number };
  todos: { available: boolean; counts: Record<string, number>; total: number; source: string };
  review: { available: boolean; triage_count: number; stale_count: number };
  last_activity: string | null;
  [key: string]: unknown;
}

export interface FeedEntryRow {
  id: string;
  kind: string;
  title: string;
  status: string;
  version: number;
  created_at: string;
  archived: boolean;
  approval: {
    approved: boolean;
    approved_at: string | null;
    approved_state_sha256: string | null;
    covers_current: boolean;
    current_state_sha256: string | null;
  };
  derived: {
    stale: boolean;
    drift: boolean;
    never_verified: boolean;
    reasons: string[];
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface FeedHistoryRow {
  id: number;
  entry_id: string;
  ts: string;
  actor: string;
  verb: string;
  field: string | null;
  old: string | null;
  new: string | null;
  note: string | null;
}

export interface FeedEntryDetail {
  entry: FeedEntryRow & { entry_dir?: string };
  derived: FeedEntryRow["derived"];
  approval: FeedEntryRow["approval"];
  latest_review: FeedHistoryRow | null;
  history: FeedHistoryRow[];
  files: { path: string; is_main: boolean; size_bytes: number }[];
}

/** One run inside a segment block: prose text, an inline
 *  code span, or a math node. A math node is the served
 *  shape the kit's Math component renders — {source,
 *  display, valid} — validity a served state, decided by
 *  the backend at serve time. */
export type FeedSegmentRun =
  | { type: "text"; text: string }
  | { type: "code"; text: string }
  | { type: "math"; source: string; display: boolean; valid: boolean };

/** A block of an entry's segmented document (the segment
 *  feed: GET /api/projects/{slug}/entries/{id}/segments).
 *  A standalone display equation is a math block; its
 *  equation number, when the document serves one, rides
 *  as `number` — document content, never a counter. */
export type FeedSegmentBlock =
  | { kind: "heading"; level: number; runs: FeedSegmentRun[] }
  | { kind: "paragraph"; runs: FeedSegmentRun[] }
  | { kind: "code"; text: string; language: string | null }
  | { kind: "math"; source: string; display: true; valid: boolean; number?: string }
  | { kind: "list"; ordered: boolean; items: FeedSegmentRun[][] };

export interface FeedEntrySegments {
  entry_id: string;
  main_file: string;
  blocks: FeedSegmentBlock[];
}

export interface FeedPlanSummary {
  path: string;
  title: string;
  status_raw: string | null;
  status_bucket: "todo" | "doing" | "done";
  [key: string]: unknown;
}

export interface FeedBundle {
  kind: string;
  id: string;
  slug: string;
  path: string;
  archived: boolean;
  feature: string | null;
  plan: FeedPlanSummary | null;
  todos?: FeedTodoRow[];
  [key: string]: unknown;
}

export interface FeedPlanDoc {
  path: string;
  title: string;
  status_bucket: "todo" | "doing" | "done";
  status_raw: string | null;
  fields: Record<string, string>;
  steps: {
    n: number;
    body: string;
    raw: string;
    files?: string;
    done_when?: string;
    [key: string]: unknown;
  }[];
  step_count: number;
  markdown: string;
  file_sha256?: string;
  archived: boolean;
  [key: string]: unknown;
}

export interface FeedTodoRow {
  id: string;
  title: string;
  status: "todo" | "doing" | "blocked" | "done";
  bundle: string;
  path: string;
  created: string | null;
  updated: string | null;
  progress_check?: string | null;
  progress_armed?: string | null;
  plan_step?: number | string | null;
  body: string;
  fields: Record<string, string>;
  archived: boolean;
  [key: string]: unknown;
}

export interface FeedProgressBlock {
  id: string;
  title: string;
  status: string;
  bundle: string;
  cadence: string;
  interval_seconds: number;
  armed_at: string | null;
  last_checkpoint: string | null;
  last_activity: string | null;
  missed_checks: number | null;
  stalled: boolean;
}

export interface FeedBoardCard {
  id?: string;
  title: string;
  bundle?: string;
  path?: string;
  step_count?: number;
  project: string;
  project_name: string;
  status?: string;
  [key: string]: unknown;
}

export interface FeedBoard {
  slug: string;
  counts: {
    todos: Record<string, number>;
    plans: Record<string, number>;
    review_queue: number;
  };
  todos: Record<"todo" | "doing" | "blocked" | "done", FeedBoardCard[]>;
  plans: Record<"todo" | "doing" | "done", FeedBoardCard[]>;
  review_queue: {
    id: string;
    kind: string;
    title: string;
    project: string;
    project_name: string;
    reasons: string[];
  }[];
  [key: string]: unknown;
}

export interface FeedProject {
  entries: { entries: FeedEntryRow[]; [key: string]: unknown };
  entriesArchived: { entries: FeedEntryRow[]; [key: string]: unknown };
  entryDetails: Record<string, FeedEntryDetail | { error: string }>;
  plans: { plans: FeedPlanSummary[]; bundles: FeedBundle[]; [key: string]: unknown };
  planDocs: Record<string, FeedPlanDoc | { error: string }>;
  todos: { todos: FeedTodoRow[]; source: string; [key: string]: unknown };
  classification: {
    progress: { armed: FeedProgressBlock[]; summary: { armed: number; stalled: number } };
    [key: string]: unknown;
  };
  board: FeedBoard;
  worktrees: { worktrees: unknown[]; [key: string]: unknown };
  diff: unknown;
}

export interface FeedRepoSummary {
  id: string;
  name: string;
  root: string;
  branch: string | null;
  error: string | null;
  // Null whenever error is set: a repo whose git probe
  // failed (the census deadline's "git timed out" is the
  // common case) serves its counts as honest absence,
  // never as fabricated zeros — the original viewer's
  // type declared the same | null.
  dirty_counts: { staged: number; unstaged: number; untracked: number } | null;
  exposure: { level: string; commits: number; files: number } | null;
  head_short: string | null;
  head_subject: string | null;
  [key: string]: unknown;
}

export interface FeedRepoDetail {
  // Null when the repo's detail assembly raised (the
  // server's error document): the adapter falls back
  // to the census summary's branch and dirty counts.
  status: {
    branch: string | null;
    dirty_counts: { staged: number; unstaged: number; untracked: number } | null;
    worktrees?: { path?: string; root?: string; branch?: string | null; dirty_total?: number | null }[];
    [key: string]: unknown;
  } | null;
  files: {
    entries: { path: string; kind: string; hidden: boolean }[];
    tracked: string[];
    untracked: string[];
    [key: string]: unknown;
  };
  history: {
    records: { at: string; head: string; head_subject: string | null; [key: string]: unknown }[];
    [key: string]: unknown;
  };
  peeks: Record<string, {
    content?: string;
    sha256?: string;
    line_count?: number;
    size_bytes?: number;
    editable?: boolean;
    editable_reason?: string | null;
    error?: string;
    [key: string]: unknown;
  }>;
  datasets: Record<string, {
    schema: { tables: { name: string; columns: { name: string; type: string }[] }[]; [key: string]: unknown };
    rows: { columns: string[]; rows: unknown[]; [key: string]: unknown };
    stats: unknown;
  }>;
}

export interface FeedMessageRow {
  id: number;
  author: string;
  body: string;
  state: "draft" | "sent" | "acknowledged" | "done" | "archived";
  project_slug: string | null;
  anchor_type: string;
  anchor_ref: string | null;
  showcase: string | null;
  created_at: string;
  anchor_context?: {
    status: string;
    kind?: string;
    quote?: string;
    step?: number | null;
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
}

export interface WorkbenchFeeds {
  config: {
    config: Record<string, unknown> & {
      host?: string;
      port?: number;
      file_editing_enabled?: boolean;
    };
    config_hash: string;
    config_file: string;
  };
  home: { projects: FeedHomeRow[]; [key: string]: unknown };
  projects: { projects: FeedProjectSummary[]; errors: unknown[] };
  projectFeeds: Record<string, FeedProject>;
  repos: { repos: FeedRepoSummary[]; [key: string]: unknown };
  repoDetails: Record<string, FeedRepoDetail>;
  messages: { messages: FeedMessageRow[]; [key: string]: unknown };
  outbox: { events: unknown[]; last_id: number };
  settings: {
    config: Record<string, unknown>;
    messages: {
      counts: Record<string, number>;
      db: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  armedRows: ArmedRow[];
  armedSkipped: number;
  statusVocabulary: StatusVocabularyRow[];
  /** Goal records in the seam's shape. Empty today: no
   *  pipeline goal-record store exists yet — goalsSource
   *  names the gap on the document's face. */
  goals: GoalRecord[];
  goalsSource: string;
}
