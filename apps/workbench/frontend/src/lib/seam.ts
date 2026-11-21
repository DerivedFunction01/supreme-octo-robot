// THE DATA SEAM.
//
// Every section renders what a WorkbenchAdapter serves and
// mutates only through it. This build ships the stateful mock
// adapter (mockAdapter.ts); at S8 the live adapter implements
// this same interface over the pipeline's work-record feeds
// (plan §8, stage D3) and the sections do not change.
//
// Feeds return served-ready shapes (review §3): derivations —
// progress, classification, rollups, board lanes — are computed
// behind the seam, never in a section.

import type {
  AnnotationThread,
  AppSettings,
  ArmedRow,
  ClassificationRow,
  DatasetTable,
  DiffMode,
  Entry,
  FileTodo,
  GoalRecord,
  InboxMessage,
  MessageThread,
  Plan,
  PlanQuestion,
  Project,
  ProjectDiff,
  ProjectRollup,
  Repo,
  RuledStatus,
  ServerCare,
  StatusPost,
  StatusVocabularyRow,
  TodoStatus,
  WorktreeDetail,
} from "./types";
import type { FeedSegmentBlock } from "./feeds";

export interface BoardCard {
  id: string;
  lane: "review" | "todo" | "doing" | "done";
  projectTag: string;
  title: string;
  meta: string;
  /** Entry review state or a plan's hard gate, when present. */
  badge?: { kind: "review" | "gate"; text: string; count?: number };
  ruled?: "implemented";
  target:
    | { kind: "entry"; id: string }
    | { kind: "plan"; bundle: string }
    | { kind: "todo"; id: string };
}

export type SaveResult =
  | { ok: true; sha: string; savedLabel: string }
  | { ok: false; reason: string };

/** An entry's own page, in the byte route's shape: the
 *  exact served document, or a refusal carrying its reason
 *  (held by reference, byte route down) — never a partial
 *  page and never a client-side reconstruction. */
export type EntryPageResult =
  | { ok: true; body: string; contentType: string }
  | { ok: false; reason: string };

/** An entry's document as served segments (the segment
 *  feed): blocks of text runs plus math nodes, segmented
 *  behind the seam — or a refusal carrying its reason
 *  (held by reference, main file a rendered page), in
 *  which case the caller falls back to the byte route's
 *  page. Never a partial document and never a client-side
 *  reconstruction. */
export type EntrySegmentsResult =
  | { ok: true; mainFile: string; blocks: FeedSegmentBlock[] }
  | { ok: false; reason: string };

/** One entry file's content for the peek: the served bytes
 *  plus the sha a save must present (compare-and-swap). */
export type EntryFileResult =
  | { ok: true; body: string; sha: string }
  | { ok: false; reason: string };

/** A dataset SQL console result (POST …/dataset/sql): the
 *  result table, or the engine's refusal. `source` names
 *  where the answer came from — the live engine, or the
 *  served snapshot when the route did not answer. */
export type DatasetSqlResult =
  | { ok: true; table: DatasetTable; source: "engine" | "snapshot" }
  | { ok: false; reason: string };

export interface WorkbenchAdapter {
  /** Which side of the seam this is: the live adapter
   *  over served data, or the stateful mock (the demo
   *  persona). Surfaces whose live behaviour is
   *  derived-only (annotation resolved-ness, W-C5)
   *  render read-only when this is "live". */
  readonly mode: "live" | "mock";
  // -- feeds -------------------------------------------------
  projects(): Project[];
  projectRollups(): ProjectRollup[];
  homeSummary(): { sweptCount: number; serverHealthy: boolean; editingOn: boolean; awaitingReview: number; doingNow: number };
  entries(project: string): Entry[];
  entry(id: string): Entry | undefined;
  plans(project: string): Plan[];
  plan(bundle: string): Plan | undefined;
  todos(project: string): FileTodo[];
  todo(id: string): FileTodo | undefined;
  /** Contract 03's classification feed for one project. */
  classification(project: string): ClassificationRow[];
  /** The armed set, as rows in contract 03's exact shape. */
  armedRows(): ArmedRow[];
  board(): BoardCard[];
  messages(): InboxMessage[];
  repos(): Repo[];
  repo(slug: string): Repo | undefined;
  goals(project: string): GoalRecord[];
  /** Every goal record, across projects (contract 11: the
   *  record is the top level of the work record). */
  allGoals(): GoalRecord[];
  goal(slug: string): GoalRecord | undefined;
  /** The plan bundle a goal's work hangs off: the bundle its
   *  latest post names in refs, else the project's single
   *  in-progress plan when there is exactly one. */
  goalBundle(goal: GoalRecord): Plan | undefined;
  /** The goal bundle's file todos, in plan-step order. */
  goalTodos(goal: GoalRecord): FileTodo[];
  /** The task-mode status vocabulary, served (contract 06):
   *  labels, needs, and terminal flags ride these rows. */
  statusVocabulary(): StatusVocabularyRow[];
  settings(): AppSettings;
  counts(): { mockupsInTriage: number; boardDoing: number; inboxAwaiting: number; goalsActive: number };

  // -- served documents --------------------------------------
  /** The entry's actual page for the drill-in stage: the
   *  live adapter fetches the main file's exact bytes over
   *  the /raw byte route; the mock serves a stand-in page
   *  in the same shape. Async because the byte route is a
   *  fetch — every other feed is a snapshot projection. */
  entryPage(id: string): Promise<EntryPageResult>;
  /** The entry's document as served segments, for the
   *  drill-in stage's native render: the live adapter
   *  fetches the segment feed; the mock serves fixture
   *  segments in the same shape. Async for the same
   *  reason as entryPage — the feed is a fetch. */
  entrySegments(id: string): Promise<EntrySegmentsResult>;

  // -- mutations ---------------------------------------------
  /** Entry disposition (mockup drill-in): approve / needs
   *  changes / mark stale. Returns the updated entry. */
  setEntryReview(id: string, review: "approved" | "needs-changes" | "stale", note?: string): Promise<Entry>;
  /** Todo write — the one mutation path. Status transitions
   *  arm/retire the contract 03 projections in the same call;
   *  a projection outcome rides the result, never a write
   *  error (contract 03). */
  writeTodo(id: string, patch: Partial<Pick<FileTodo, "title" | "status" | "progressCheck" | "notes">>): Promise<{ todo: FileTodo; armed: boolean }>;
  addTodo(project: string, bundle: string, title: string): Promise<FileTodo>;
  addCheckpoint(id: string, text: string): Promise<FileTodo>;
  moveBoardCard(cardId: string, lane: BoardCard["lane"]): Promise<void>;
  dismissMessage(id: string): Promise<void>;
  openMessage(id: string): InboxMessage;
  /** Guarded file save: sha compare-and-swap; a stale sha
   *  refuses (review §2, SPEC §7.1). */
  guardedSave(repo: string, path: string, content: string, baseSha: string): Promise<SaveResult>;
  // -- entry lifecycle (W4) --------------------------------
  /** The set-status verb: move the entry's ruled status. */
  setEntryStatus(id: string, status: RuledStatus): Promise<Entry>;
  /** The set verb over the entry's editable metadata. */
  setEntryMeta(id: string, patch: Partial<Pick<Entry, "title" | "viewport" | "mode">>): Promise<Entry>;
  /** The verify verb: recompute the entry's state and
   *  record the outcome in its history. */
  verifyEntry(id: string): Promise<Entry>;
  /** The archive / unarchive verbs. */
  archiveEntry(id: string): Promise<Entry>;
  unarchiveEntry(id: string): Promise<Entry>;
  /** The supersede verb: this entry is replaced by another. */
  supersedeEntry(id: string, byId: string): Promise<Entry>;
  /** The set-state verb: replace the entry's free state
   *  document (JSON text, validated at the writer). */
  setEntryState(id: string, json: string): Promise<Entry>;
  /** Peek one of the entry's files (the byte route's shape). */
  entryFileContent(id: string, path: string): Promise<EntryFileResult>;
  /** Open one of the repo's files: the live adapter rides
   *  the on-demand file route for files whose peek the
   *  feeds document deferred; the mock answers from its
   *  tree. The served sha is the guarded save's CAS base. */
  repoFileContent(repo: string, path: string): Promise<EntryFileResult>;
  /** Save one of the entry's files: sha compare-and-swap,
   *  the same guard as the repo editor's saves. */
  saveEntryFile(id: string, path: string, content: string, baseSha: string): Promise<SaveResult>;

  // -- plan questions + annotations (W8, W5) ---------------
  /** The questions the plan file carries, open + answered. */
  planQuestions(bundle: string): PlanQuestion[];
  /** The resolve act (POST …/plan/resolve → apply_answers):
   *  answers write back into the plan record. */
  resolvePlanQuestions(bundle: string, answers: Record<string, string>): Promise<Plan>;
  /** Anchored annotation threads over a plan's text. */
  annotationsForPlan(bundle: string): AnnotationThread[];
  /** Create an annotation (POST /api/messages, anchor_type
   *  text with a §12 selection payload): the thread is a
   *  message thread rooted at the plan's path. */
  addAnnotation(bundle: string, quote: string, body: string): Promise<AnnotationThread>;
  /** Reply on an annotation thread (POST /api/messages
   *  with parent_id — replies carry no selection; the
   *  root holds the anchor). */
  replyAnnotation(id: string, body: string): Promise<AnnotationThread>;
  /** W-C5 disposition (ruled 2026-11-15): DERIVED-ONLY
   *  in live mode — a thread's resolved-ness is derived
   *  from its messages' lifecycle states (done is the
   *  agent's post-back, §7) and no server verb sets it,
   *  so live surfaces render the state read-only and
   *  the live method refuses honestly (throws the
   *  derived-state reason); the mock keeps it
   *  functional against the fake. An owner-resolve
   *  lifecycle verb is a possible future contract
   *  item, not built. */
  setAnnotationResolved(id: string, resolved: boolean): AnnotationThread;

  // -- message threads (W10) -------------------------------
  messageThreads(): MessageThread[];
  /** Compose (POST /api/messages): a draft, or sent now. */
  composeThread(input: {
    project: string;
    body: string;
    anchorText?: string;
    sendNow: boolean;
  }): Promise<MessageThread>;
  replyThread(id: string, body: string): Promise<MessageThread>;
  editThreadMessage(threadId: string, messageId: string, body: string): Promise<MessageThread>;
  /** The thread verbs: send / done / archive. */
  setThreadState(id: string, state: "sent" | "done" | "archived"): Promise<MessageThread>;

  // -- datasets (W11) ---------------------------------------
  /** Run SQL against a dataset file's tables. */
  datasetSql(repo: string, path: string, sql: string): Promise<DatasetSqlResult>;

  // -- project diff + worktrees (W9) ------------------------
  /** The diff modes this repo serves (served, not assumed). */
  diffModes(repo: string): { mode: DiffMode; label: string }[];
  projectDiff(repo: string, mode: DiffMode, range?: { base: string; target: string }): ProjectDiff;
  worktreeDetail(repo: string, path: string): WorktreeDetail | undefined;

  // -- board done-lane paging (W15) --------------------------
  /** One page of the board's Done lane (done_offset /
   *  done_limit over the served portion) + its total. */
  boardDone(offset: number, limit: number): { cards: BoardCard[]; total: number };

  // -- repo registry (W12) -----------------------------------
  /** Save the project's tracking record (POST /api/projects/registry). */
  updateRepoTracking(
    slug: string,
    patch: Partial<NonNullable<Repo["tracking"]>> & { name?: string },
  ): Promise<Repo>;

  // -- settings panels (W13) + server care (W3) --------------
  /** The effective workspace config, read-only rows. */
  workspaceConfig(): { label: string; value: string }[];
  /** Message-store counts by state, as served. */
  messageCounts(): { label: string; count: number }[];
  /** Guarded cleanup: dispositioned-and-done messages go. */
  cleanupMessages(): { removed: number };
  /** Guarded purge: every dispositioned message goes. */
  purgeMessages(): { removed: number };
  serverCare(): ServerCare;
  /** One rung of the repair ladder, run on demand. */
  repairAction(kind: "clear-strays" | "fallback-restart"): ServerCare;

  // -- refresh / rescan (W14) --------------------------------
  /** POST /api/refresh — re-serve the feeds; the freshness
   *  stamp moves either way. */
  refresh(): Promise<{ label: string }>;
  /** POST /api/projects/rescan — re-sweep the projects. */
  rescan(): Promise<{ label: string }>;
  /** "just now" / "3 min ago" against the last refresh. */
  freshnessLabel(): string;

  /** Goal ping arm/disarm (POST /api/goals/{slug}/ping —
   *  contract 11: the record arms its own scheduling
   *  entry; the store's writer refuses to re-arm a closed
   *  goal's retired ping). */
  setGoalPing(slug: string, armed: boolean): Promise<GoalRecord>;
  /** Record a status post against a goal's programme
   *  (POST /api/goals/{slug}/status — contract 03
   *  status-post form, writer rules at the store). */
  postGoalStatus(slug: string, post: Omit<StatusPost, "postedAt">): Promise<GoalRecord>;
  /** W-C5 disposition (ruled 2026-11-15): LOCAL-ONLY —
   *  no server home exists and none is commissioned:
   *  the writable fields are client preferences (lane
   *  width) and a local override of a config-served
   *  default (guarded saves); the server's settings
   *  surface is read-only by spec §3. The adapter keeps
   *  them local and does not claim server persistence. */
  updateSettings(patch: Partial<AppSettings>): AppSettings;

  // -- change notification -----------------------------------
  subscribe(fn: () => void): () => void;
  version(): number;
}
