// Served shapes for the workbench app, as pinned by the S0
// contracts and the pinned workbench review
// (the pinned workbench review in docs/review/, §2–§3).
//
// The app renders served shapes only; every derivation below is
// a shape the backend serves ready (progress derivation,
// classification feed, home rollups) — in this build the mock
// adapter computes them, at S8 the pipeline serves them.

/** Ruled entry statuses — SPEC §5.1, one contract in two files
 *  (contract 06 / kit status table). */
export type RuledStatus =
  | "canonical"
  | "implemented"
  | "deferred"
  | "unexplored"
  | "hard-gate"
  | "abandoned";

/** Derived / review states — rendered as Badges, never Chips. */
export type ReviewState =
  | "in-triage"
  | "needs-changes"
  | "stale"
  | "approved"
  | "not-covered";

export type TodoStatus = "todo" | "doing" | "blocked" | "done";

/** File todo — contract 11 (WR1) front matter + body lines. */
export interface FileTodo {
  id: string; // the todo's name: ^[a-z0-9]+(-[a-z0-9]+)*$
  project: string;
  bundle: string; // bundle dir name, e.g. "<date>-superapp-storyboards"
  title: string;
  status: TodoStatus;
  created: string; // ISO date
  updated: string; // ISO date
  /** Raw progress_check as declared: "30m" | "2h" | "off" | undefined
   *  (absent = writer arms at the 15-minute default on the doing move). */
  progressCheck?: string;
  /** Arming stamp (progress_armed), ISO-8601, when armed. */
  progressArmed?: string;
  /** Body checkpoint lines, parsed: `progress-checkpoint: <ISO> — <text>`. */
  checkpoints: { at: string; text: string }[];
  /** Free body text under the checkpoints (the todo's notes). */
  notes: string;
  /** Unknown front-matter fields, preserved losslessly (WR1). */
  extra: Record<string, string>;
}

/** The armed row — contract 03 (ARM2), schema
 *  contracts/schemas/armed-row.schema.json. */
export interface ArmedRow {
  handle: string;
  programme: string;
  project: string;
  todo: string;
  title: string;
  bundle: string | null;
  cadence: string | null;
  cadence_minutes: number | null;
  armed_at: string | null;
  status: TodoStatus;
  source: {
    writer: "workbench-harness";
    project: string;
    todo: string;
    source_class: "project" | "fixture";
  };
}

/** Progress derivation for one armed todo — computed at read
 *  time, never stored (review §3; contract 03 stall rule:
 *  2 missed intervals = stalled). */
export interface ProgressDerivation {
  todoId: string;
  cadenceMinutes: number;
  lastActivity: string; // ISO
  missedChecks: number;
  verdict: "on-track" | "stalled";
}

/** One row of the classification feed (contract 03 annex):
 *  every todo across a project's active bundles, served ready. */
export interface ClassificationRow {
  todo: FileTodo;
  optOut: boolean; // derived explicitly from progress_check === "off"
  armed: boolean;
  derivation: ProgressDerivation | null;
}

export interface PlanStep {
  n: number;
  title: string;
  detail: string;
  /** File todo this step is executed as, when it has one. */
  todoId?: string;
}

/** A question the plan file itself poses (SPEC §5.1: the
 *  plan carries its open questions; the resolve act writes
 *  the answers back into the plan — POST …/plan/resolve,
 *  backend `apply_answers`). */
export interface PlanQuestion {
  id: string;
  text: string;
  /** Choice set when the question is a pick, not free text. */
  options?: string[];
  answer?: string;
  answeredBy?: string;
  answeredLabel?: string;
}

export type PlanState = "draft" | "in-progress" | "done";

/** A plan bundle — `.plans/<date>-<slug>/` with plan.md + todos/. */
export interface Plan {
  bundle: string;
  project: string;
  title: string;
  state: PlanState;
  executor: string;
  createdLabel: string;
  steps: PlanStep[];
  /** The plan.md source, for the Raw view. */
  raw: string;
  archived: boolean; // lives under finished/
  /** Open + answered questions the plan file carries. */
  questions?: PlanQuestion[];
}

/** One anchored annotation thread over a plan's text: the
 *  anchor quote, its relocation status against the current
 *  text (anchored = found in place, relocated = found
 *  moved, orphaned = no longer found), and the replies. */
export interface AnnotationThread {
  id: string;
  bundle: string;
  project: string;
  anchorQuote: string;
  /** The full line the quote was anchored in when the
   *  thread opened — relocation is derived against it:
   *  line intact → anchored, quote found in a changed
   *  line → relocated, quote gone → orphaned. */
  anchorContext?: string;
  status: "anchored" | "relocated" | "orphaned";
  resolved: boolean;
  messages: { id: string; author: string; body: string; when: string }[];
}

export type EntryKind = "mockup" | "plan" | "doc";

export interface ReviewLogEntry {
  label: string;
  when: string; // display label, served
  actor: string;
}

/** One file of a registry entry, as the entry detail
 *  serves it (path + main flag + size). */
export interface EntryFileInfo {
  path: string;
  isMain: boolean;
  sizeLabel: string;
}

/** A registry entry (registry-DB store; export shape per WR2). */
export interface Entry {
  id: string;
  project: string;
  kind: EntryKind;
  title: string;
  status: RuledStatus;
  review: ReviewState | null;
  /** Magnitude for badges, e.g. needs-changes open count. */
  reviewCount?: number;
  version: number;
  registeredLabel: string;
  stateHash?: string;
  approvedBy?: string;
  /** Mockup specimens only: how the preview well renders. */
  viewport?: "Phone" | "Desktop";
  mode?: "Light" | "Dark";
  staleNote?: string;
  reviewLog: ReviewLogEntry[];
  /** Where Open leads: a plan bundle or a repo file. */
  planBundle?: string;
  repoPath?: { repo: string; path: string };
  /** The entry's files, when the detail serves them. */
  files?: EntryFileInfo[];
  /** Archived entries live in the archive list, not the
   *  active registry (archive/unarchive lifecycle verbs). */
  archived?: boolean;
  /** The entry's free state document (set-state verb), as
   *  JSON text — the state editor round-trips it verbatim. */
  stateJson?: string;
}

export interface Project {
  slug: string;
  name: string;
  /** Manifest (WR3) — null when the sweep found no manifest. */
  manifest: {
    registry: string;
    plans: string;
    mockups: string;
    archive: string;
    catalogOrigin: string;
    catalogGenerality: string;
    catalogUseCase: string;
  } | null;
  health: "ok" | "degraded" | "manifest-only";
  healthNote: string;
  lastActivityLabel: string;
}

/** Goal record — contract 11: a record plus its ping. */
export interface GoalRecord {
  slug: string;
  project: string;
  title: string;
  /** Served one-clause form of the objective, for condensed
   *  rows (the phone list) where the full line cannot ride. */
  shortObjective?: string;
  contract: {
    objective: string;
    completeWhen: string;
    blockedOnlyWhen: string;
    continuation: string;
  };
  /** The ping: a pipeline scheduling entry armed by the record. */
  ping: {
    entryId: string; // owner: goal:<slug>
    cadenceMinutes: number;
    armed: boolean;
  };
  /** Latest status post (contract 03 status-post form). */
  lastPost: StatusPost | null;
}

/** Status post — contract 03 (ATT10), schema
 *  contracts/schemas/status-post.schema.json. Groups the state
 *  does not call for are absent, never empty-filled. */
export interface StatusPost {
  handle: string;
  status_code:
    | "WORKING"
    | "CONTINUE"
    | "REVIEW"
    | "DONE"
    | "CLOSED"
    | "PARKED"
    | "BLOCKED-OWNER"
    | "BLOCKED-HARD";
  summary: string;
  refs?: {
    project: string;
    plan: string | null;
    todo_ids: string[];
    steps_open?: number;
    steps_independent?: number;
  };
  done?: string[];
  ongoing?: string[];
  owner_waiting?: { label: string; commissioned_at: string } | null;
  /** Blocked-state pair (contract 11 amendment):
   *  a post asserting BLOCKED-OWNER / BLOCKED-HARD carries
   *  the cited basis — the owner's message reference, thread
   *  + time — and the verification stamp, applied by the
   *  verifying party. A blocked post without the pair is
   *  invalid at the writer, not a renderable state. */
  basis_citation?: { thread: string; at: string };
  verification?: { by: string; at: string };
  postedAt: string; // mock-store bookkeeping, not part of the wire shape
}

/** One row of the task-mode status vocabulary — contract 06:
 *  `{code, label, need, short, terminal}` as served registry
 *  data (pinned defaults: contracts/fixtures/
 *  attention-status-codes.json). Labels, needs, and terminal
 *  flags are read from these rows, never re-derived. */
export interface StatusVocabularyRow {
  code: StatusPost["status_code"];
  label: string;
  need: "agent_clearable" | "owner_actionable";
  short: string;
  terminal: boolean;
}

export interface InboxMessage {
  id: string;
  kind: "mockup" | "doctor" | "plan";
  title: string;
  project: string;
  arrivedLabel: string;
  /** null = awaiting a first disposition. */
  disposition: "filed" | "opened" | "dismissed" | null;
  /** Navigation target for Open. */
  target:
    | { section: "mockups"; entryId: string }
    | { section: "plans"; bundle: string }
    | { section: "overview" };
}

/** One table of a dataset file, as the dataset feeds
 *  serve it (schema + rows are separate served parts). */
export interface DatasetTable {
  name: string;
  columns: string[];
  rows: string[][];
}

export interface RepoFile {
  name: string;
  kind: "folder" | "file";
  children?: RepoFile[];
  /** Served classification where not the default (tracked). */
  classification?: "untracked" | "pruned" | "withheld";
  hidden?: boolean;
  sizeLabel?: string;
  lines?: number;
  sha?: string;
  content?: string;
  /** Working-tree content at HEAD, when it differs (diff source). */
  headContent?: string;
  /** Staged (index) content, when it differs from both —
   *  the staged half of the uncommitted split. */
  stagedContent?: string;
  dataset?: { tables: DatasetTable[] };
  editable?: "guarded" | "no";
  editableNote?: string;
}

export interface Repo {
  slug: string;
  name: string;
  path: string;
  sweep: "swept" | "degraded" | "manifest-only";
  branch: string;
  syncLabel: string;
  modifiedCount: number;
  worktrees: { label: string; path: string; branch: string; dirty: number | null }[];
  history: { sha: string; title: string; when: string }[];
  files: RepoFile[];
  /** The repo-registry tracking record (ReposTrackingPanel:
   *  name/expected/pinned/ignored/notes → POST
   *  /api/projects/registry). */
  tracking?: {
    expected: string;
    pinned: boolean;
    ignored: boolean;
    notes: string;
  };
}

/** One file's lines in a project diff (the /diff feed's
 *  per-file form, normalized over the served hunks). */
export interface DiffFile {
  path: string;
  adds: number;
  dels: number;
  lines: { kind: "ctx" | "add" | "del"; text: string }[];
}

/** A project diff in one mode. The uncommitted mode splits
 *  into staged / unstaged halves. */
export interface ProjectDiff {
  mode: string;
  label: string;
  files: DiffFile[];
  staged?: DiffFile[];
  unstaged?: DiffFile[];
  /** Honest absence: why a requested mode serves nothing. */
  note?: string;
}

export type DiffMode = "working" | "uncommitted" | "committed" | "range";

/** A worktree drill-in: the worktree's own facts plus the
 *  files it has dirty, as the /worktrees feed serves them. */
export interface WorktreeDetail {
  label: string;
  path: string;
  branch: string;
  dirty: number | null;
  activePlan?: string;
  changedFiles: string[];
}

/** A message thread — the message store's own shape
 *  (POST /api/messages + /{id}/{verb}): a state, an
 *  optional anchor, and its messages in order. */
export interface MessageThread {
  id: string;
  project: string;
  title: string;
  state: "draft" | "sent" | "acknowledged" | "done" | "archived";
  anchorText?: string;
  messages: { id: string; author: string; body: string; when: string }[];
}

/** The server-care surface (W3's UI half): link state,
 *  the supervised classification, and the repair log the
 *  ladder leaves behind (state/{link,repair,health}). */
export interface ServerCare {
  linkState: "ok" | "down";
  classification: string;
  doctorLabel: string;
  lastRepairLabel: string;
  strayCount: number;
  log: string[];
}

export interface AppSettings {
  boardLaneWidth: number; // px
  guardedSaves: boolean; // config-gated, default OFF (review §2)
  serverLabel: string;
  projectsSwept: number;
  doctorLabel: string;
}

/** Home feed rollups (lib/derived/home.py shapes, served ready). */
export interface ProjectRollup {
  project: Project;
  dot: "ok" | "warn" | "muted";
  sub: string;
  chip:
    | { type: "ruled"; status: RuledStatus }
    | { type: "badge"; kind: ReviewState; text: string }
    | { type: "plain"; text: string };
}
