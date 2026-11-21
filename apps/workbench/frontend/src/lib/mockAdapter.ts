// The stateful mock adapter — the demo-mode store behind the
// seam. Seeded with contract-shaped data (seed.ts); every
// mutation lands in the store and re-derives the feeds, so
// counts, lanes, armed rows, and rollups move as you act.
//
// Arming semantics are contract 03's, executed here exactly
// as the harness writer executes them: the doing transition
// arms both projections in the same call; a stop status
// (done|blocked), a disarm, or an archive retires both; a
// projection outcome never fails the todo write.
//
// Layout: the class below is the seam's surface. The
// method groups live in the mockAdapter/ modules as plain
// functions over the shared context (mockAdapter/
// host.ts), mirroring the live adapter's split, and the
// class delegates to them.

import { buildSeed, STATUS_VOCABULARY, type SeedDb } from "./seed";
import type {
  BoardCard,
  DatasetSqlResult,
  EntryFileResult,
  EntryPageResult,
  EntrySegmentsResult,
  SaveResult,
  WorkbenchAdapter,
} from "./seam";
import type {
  AnnotationThread,
  AppSettings,
  ArmedRow,
  ClassificationRow,
  DiffMode,
  Entry,
  FileTodo,
  GoalRecord,
  MessageThread,
  Plan,
  ProjectDiff,
  ProjectRollup,
  Repo,
  RuledStatus,
  ServerCare,
  StatusPost,
  WorktreeDetail,
} from "./types";
import * as datasets from "./mockAdapter/datasets";
import * as entryMutations from "./mockAdapter/entryMutations";
import * as goalsModule from "./mockAdapter/goals";
import type { MockHost, MockState } from "./mockAdapter/host";
import * as panels from "./mockAdapter/panels";
import * as plansModule from "./mockAdapter/plans";
import * as reads from "./mockAdapter/reads";
import * as threadsModule from "./mockAdapter/threads";
import * as todoMutations from "./mockAdapter/todoMutations";

export class MockWorkbenchAdapter implements WorkbenchAdapter {
  readonly mode = "mock" as const;
  private s: MockState;
  private host: MockHost;
  private listeners = new Set<() => void>();
  private ver = 0;
  private clock: () => Date;

  constructor(clock: () => Date = () => new Date()) {
    this.clock = clock;
    const now = clock();
    const db = buildSeed(now);
    this.s = {
      db,
      settingsState: {
        boardLaneWidth: 264,
        guardedSaves: false,
        serverLabel: "127.0.0.1:8792 · healthy",
        projectsSwept: db.projects.length,
        doctorLabel: "Every 15 min · last run 1:58 PM",
      },
      entryFileOverrides: new Map(),
      care: {
        linkState: "ok",
        classification: "supervised · one unit",
        doctorLabel: "Every 15 min · last run 1:58 PM",
        lastRepairLabel: "—",
        strayCount: 1,
        log: ["Link probe ok · 2 min ago", "Health state written · 2 min ago"],
      },
      lastRefresh: new Date(),
    };
    this.host = {
      s: this.s,
      clock: this.clock,
      emit: () => this.emit(),
      plan: (bundle) => this.plan(bundle),
      todo: (id) => this.todo(id),
      repo: (slug) => this.repo(slug),
      board: () => this.board(),
      serverCare: () => this.serverCare(),
      freshnessLabel: () => this.freshnessLabel(),
      setEntryReview: (id, review, note) => this.setEntryReview(id, review, note),
    };
  }

  private emit() {
    this.ver++;
    this.listeners.forEach((fn) => fn());
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  version(): number {
    return this.ver;
  }

  /** Test/validation access to the raw store. */
  raw(): SeedDb {
    return this.s.db;
  }

  // -- feeds ---------------------------------------------------

  projects() {
    return this.s.db.projects;
  }

  projectRollups(): ProjectRollup[] {
    return reads.projectRollups(this.host);
  }

  homeSummary() {
    return reads.homeSummary(this.host);
  }

  entries(project: string) {
    return this.s.db.entries.filter((e) => e.project === project && !e.archived);
  }

  entry(id: string) {
    return this.s.db.entries.find((e) => e.id === id);
  }

  async entryPage(id: string): Promise<EntryPageResult> {
    return reads.entryPage(this.host, id);
  }

  async entrySegments(id: string): Promise<EntrySegmentsResult> {
    return reads.entrySegments(this.host, id);
  }

  plans(project: string) {
    return this.s.db.plans.filter((p) => p.project === project);
  }

  plan(bundle: string) {
    return this.s.db.plans.find((p) => p.bundle === bundle);
  }

  todos(project: string) {
    return this.s.db.todos.filter((t) => t.project === project);
  }

  todo(id: string) {
    return this.s.db.todos.find((t) => t.id === id);
  }

  classification(project: string): ClassificationRow[] {
    return reads.classification(this.host, project);
  }

  armedRows(): ArmedRow[] {
    return reads.armedRows(this.host);
  }

  board(): BoardCard[] {
    return reads.board(this.host);
  }

  messages() {
    return this.s.db.messages;
  }

  repos() {
    return this.s.db.repos;
  }

  repo(slug: string) {
    return this.s.db.repos.find((r) => r.slug === slug);
  }

  goals(project: string) {
    return this.s.db.goals.filter((g) => g.project === project);
  }

  allGoals() {
    return this.s.db.goals;
  }

  goal(slug: string) {
    return this.s.db.goals.find((g) => g.slug === slug);
  }

  goalBundle(goal: GoalRecord) {
    return reads.goalBundle(this.host, goal);
  }

  goalTodos(goal: GoalRecord): FileTodo[] {
    return reads.goalTodos(this.host, goal);
  }

  statusVocabulary() {
    return STATUS_VOCABULARY;
  }

  settings() {
    return this.s.settingsState;
  }

  counts() {
    return reads.counts(this.host);
  }

  // -- mutations -------------------------------------------------

  async setEntryReview(id: string, review: "approved" | "needs-changes" | "stale", note?: string): Promise<Entry> {
    return entryMutations.setEntryReview(this.host, id, review, note);
  }

  async writeTodo(
    id: string,
    patch: Partial<Pick<FileTodo, "title" | "status" | "progressCheck" | "notes">>,
  ): Promise<{ todo: FileTodo; armed: boolean }> {
    return todoMutations.writeTodo(this.host, id, patch);
  }

  async addTodo(project: string, bundle: string, title: string): Promise<FileTodo> {
    return todoMutations.addTodo(this.host, project, bundle, title);
  }

  async addCheckpoint(id: string, text: string): Promise<FileTodo> {
    return todoMutations.addCheckpoint(this.host, id, text);
  }

  async moveBoardCard(cardId: string, lane: BoardCard["lane"]): Promise<void> {
    return todoMutations.moveBoardCard(this.host, cardId, lane);
  }

  async dismissMessage(id: string): Promise<void> {
    return todoMutations.dismissMessage(this.host, id);
  }

  openMessage(id: string) {
    return todoMutations.openMessage(this.host, id);
  }

  async guardedSave(repoSlug: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
    return entryMutations.guardedSave(this.host, repoSlug, path, content, baseSha);
  }

  async setGoalPing(slug: string, armed: boolean) {
    return goalsModule.setGoalPing(this.host, slug, armed);
  }

  async postGoalStatus(slug: string, post: Omit<StatusPost, "postedAt">) {
    return goalsModule.postGoalStatus(this.host, slug, post);
  }

  updateSettings(patch: Partial<AppSettings>): AppSettings {
    return goalsModule.updateSettings(this.host, patch);
  }

  // -- entry lifecycle (W4) ----------------------------------

  async setEntryStatus(id: string, status: RuledStatus): Promise<Entry> {
    return entryMutations.setEntryStatus(this.host, id, status);
  }

  async setEntryMeta(
    id: string,
    patch: Partial<Pick<Entry, "title" | "viewport" | "mode">>,
  ): Promise<Entry> {
    return entryMutations.setEntryMeta(this.host, id, patch);
  }

  async verifyEntry(id: string): Promise<Entry> {
    return entryMutations.verifyEntry(this.host, id);
  }

  async archiveEntry(id: string): Promise<Entry> {
    return entryMutations.archiveEntry(this.host, id);
  }

  async unarchiveEntry(id: string): Promise<Entry> {
    return entryMutations.unarchiveEntry(this.host, id);
  }

  async supersedeEntry(id: string, byId: string): Promise<Entry> {
    return entryMutations.supersedeEntry(this.host, id, byId);
  }

  async setEntryState(id: string, json: string): Promise<Entry> {
    return entryMutations.setEntryState(this.host, id, json);
  }

  async entryFileContent(id: string, path: string): Promise<EntryFileResult> {
    return entryMutations.entryFileContent(this.host, id, path);
  }

  async repoFileContent(repoSlug: string, path: string): Promise<EntryFileResult> {
    return entryMutations.repoFileContent(this.host, repoSlug, path);
  }

  async saveEntryFile(id: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
    return entryMutations.saveEntryFile(this.host, id, path, content, baseSha);
  }

  // -- plan questions + annotations (W8, W5) -----------------

  planQuestions(bundle: string) {
    return plansModule.planQuestions(this.host, bundle);
  }

  async resolvePlanQuestions(bundle: string, answers: Record<string, string>): Promise<Plan> {
    return plansModule.resolvePlanQuestions(this.host, bundle, answers);
  }

  annotationsForPlan(bundle: string): AnnotationThread[] {
    return plansModule.annotationsForPlan(this.host, bundle);
  }

  async addAnnotation(bundle: string, quote: string, body: string): Promise<AnnotationThread> {
    return plansModule.addAnnotation(this.host, bundle, quote, body);
  }

  async replyAnnotation(id: string, body: string): Promise<AnnotationThread> {
    return plansModule.replyAnnotation(this.host, id, body);
  }

  setAnnotationResolved(id: string, resolved: boolean): AnnotationThread {
    return plansModule.setAnnotationResolved(this.host, id, resolved);
  }

  // -- message threads (W10) ---------------------------------

  messageThreads(): MessageThread[] {
    return this.s.db.threads;
  }

  async composeThread(input: {
    project: string;
    body: string;
    anchorText?: string;
    sendNow: boolean;
  }): Promise<MessageThread> {
    return threadsModule.composeThread(this.host, input);
  }

  async replyThread(id: string, body: string): Promise<MessageThread> {
    return threadsModule.replyThread(this.host, id, body);
  }

  async editThreadMessage(threadId: string, messageId: string, body: string): Promise<MessageThread> {
    return threadsModule.editThreadMessage(this.host, threadId, messageId, body);
  }

  async setThreadState(id: string, state: "sent" | "done" | "archived"): Promise<MessageThread> {
    return threadsModule.setThreadState(this.host, id, state);
  }

  // -- datasets (W11) -----------------------------------------

  async datasetSql(repoSlug: string, path: string, sql: string): Promise<DatasetSqlResult> {
    return datasets.datasetSql(this.host, repoSlug, path, sql);
  }

  // -- project diff + worktrees (W9) ---------------------------

  diffModes(_repo: string): { mode: DiffMode; label: string }[] {
    return [
      { mode: "working", label: "Working" },
      { mode: "uncommitted", label: "Uncommitted" },
      { mode: "committed", label: "Committed" },
      { mode: "range", label: "Range" },
    ];
  }

  projectDiff(repoSlug: string, mode: DiffMode): ProjectDiff {
    return datasets.projectDiff(this.host, repoSlug, mode);
  }

  worktreeDetail(repoSlug: string, path: string): WorktreeDetail | undefined {
    return datasets.worktreeDetail(this.host, repoSlug, path);
  }

  // -- board done-lane paging (W15) ----------------------------

  boardDone(offset: number, limit: number): { cards: BoardCard[]; total: number } {
    return datasets.boardDone(this.host, offset, limit);
  }

  // -- repo registry (W12) --------------------------------------

  async updateRepoTracking(
    slug: string,
    patch: Partial<NonNullable<Repo["tracking"]>> & { name?: string },
  ): Promise<Repo> {
    return datasets.updateRepoTracking(this.host, slug, patch);
  }

  // -- settings panels (W13) + server care (W3) -----------------

  workspaceConfig(): { label: string; value: string }[] {
    return panels.workspaceConfig(this.host);
  }

  messageCounts(): { label: string; count: number }[] {
    return panels.messageCounts(this.host);
  }

  cleanupMessages(): { removed: number } {
    return panels.cleanupMessages(this.host);
  }

  purgeMessages(): { removed: number } {
    return panels.purgeMessages(this.host);
  }

  serverCare(): ServerCare {
    return this.s.care;
  }

  repairAction(kind: "clear-strays" | "fallback-restart"): ServerCare {
    return panels.repairAction(this.host, kind);
  }

  // -- refresh / rescan (W14) -----------------------------------

  async refresh(): Promise<{ label: string }> {
    return panels.refresh(this.host);
  }

  async rescan(): Promise<{ label: string }> {
    return panels.rescan(this.host);
  }

  freshnessLabel(): string {
    const secs = Math.max(0, Math.floor((this.clock().getTime() - this.s.lastRefresh.getTime()) / 1000));
    if (secs < 5) return "just now";
    if (secs < 60) return `${secs} s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins} min ago`;
    return `${Math.floor(mins / 60)} h ago`;
  }
}

export function createMockAdapter(): MockWorkbenchAdapter {
  return new MockWorkbenchAdapter();
}
