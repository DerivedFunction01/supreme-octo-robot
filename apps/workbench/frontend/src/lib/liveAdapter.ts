// The LIVE adapter — the WorkbenchAdapter seam over the
// work-record pipeline's served shapes (the feeds document,
// feeds.ts). Every feed below projects a payload the
// pipeline served; derivations the pipeline serves
// (classification progress blocks, board portions, home
// rollups) are consumed as served, never recomputed in the
// client, except where a local mutation has moved state
// past the snapshot — then the shared contract-03 pure
// functions (arming.ts, the same ones the mock drives)
// re-derive that item until the next document lands.
//
// Mutations mirror the mock adapter's writer semantics
// over the projected state (contract 03 arming, guarded-
// save CAS, contract 11's goal writer rules) and persist
// through the pipeline's own writers: each write lands on
// the serving shell's POST routes first (the same lib
// writers `wb` calls), and the projected state moves only
// on the server's acceptance — so a mutation survives a
// reload and shows in `wb` (D-4, cured). The
// writes are therefore async at the seam. Goal ping/posts
// and annotation creates/replies joined the cured set
// under W-C5: POST /api/goals/{slug}/… and
// the messages route. Two verbs stay local by ruling
// (the W-C5 dispositions, named at their methods): app
// settings are local-only, and annotation resolved-ness
// is derived-only — live surfaces render it read-only.
//
// Every fetch the adapter makes (the byte route, the
// segment feed, the dataset engine, refresh/rescan)
// rides the surface base: "" — same-origin — in the
// serving shell's topology, or the integration entry's
// ?api= base in the published form, where the app and
// the surface do not share an origin by construction.
//
// In the rebuilt superapp's frame form (REBUILD STEP 3)
// the adapter instead carries a relay channel
// (transport.ts): every route below maps onto its
// wbApi/wbRaw action and rides the workhorse:*
// postMessage relay to the shell, which executes the
// action over the privileged bridge. The channel swaps
// the transport beneath the seam — the server-first
// semantics above are unchanged: a call still lands on
// the server first, and a refusal still surfaces the
// server's own error text (the envelope's, in the frame
// form).
//
// Layout: the class below is the seam's surface. The
// feeds document is projected by liveAdapter/state.ts
// over the per-kind projections (liveAdapter/
// todoProjection.ts, entryProjection.ts,
// planProjection.ts, messageProjection.ts); the method
// groups live in
// the remaining liveAdapter/ modules as plain functions
// over the shared context (liveAdapter/host.ts), and
// the class delegates to them.

import type { WorkbenchFeeds } from "./feeds";
import { actionForPost, type WbChannel } from "./transport";
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
  InboxMessage,
  MessageThread,
  Plan,
  ProjectDiff,
  ProjectRollup,
  Repo,
  RuledStatus,
  ServerCare,
  StatusPost,
} from "./types";
import * as datasets from "./liveAdapter/datasets";
import * as documents from "./liveAdapter/documents";
import * as entryMutations from "./liveAdapter/entryMutations";
import * as goalsModule from "./liveAdapter/goals";
import type { LiveHost, LiveState } from "./liveAdapter/host";
import * as panels from "./liveAdapter/panels";
import * as plansModule from "./liveAdapter/plans";
import * as reads from "./liveAdapter/reads";
import * as repoFiles from "./liveAdapter/repoFiles";
import { buildLiveState } from "./liveAdapter/state";
import * as threadsModule from "./liveAdapter/threads";
import * as todoMutations from "./liveAdapter/todoMutations";

export class LiveWorkbenchAdapter implements WorkbenchAdapter {
  readonly mode = "live" as const;
  private doc: WorkbenchFeeds;
  private listeners = new Set<() => void>();
  private ver = 0;
  private s: LiveState;
  private host: LiveHost;

  constructor(
    doc: WorkbenchFeeds,
    private apiBase: string = "",
    private clock: () => Date = () => new Date(),
    private channel: WbChannel | null = null,
  ) {
    this.doc = doc;
    this.s = buildLiveState(doc);
    this.host = {
      doc: this.doc,
      s: this.s,
      channel: this.channel,
      clock: this.clock,
      emit: () => this.emit(),
      url: (path) => this.url(path),
      postJson: (path, body) => this.postJson(path, body),
      entryAction: (e, body) => this.entryAction(e, body),
      entry: (id) => this.entry(id),
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

  /** A surface path on this adapter's base (see the
   *  header note): the base carries no trailing slash,
   *  so the join is a plain prefix. */
  private url(path: string): string {
    return `${this.apiBase}${path}`;
  }

  /** One write to the serving shell's POST routes — the
   *  one mutation path (D-4): the live adapter's writes
   *  land on the server first, through the same lib
   *  writers `wb` calls, and local state moves only on
   *  the server's acceptance. A refusal throws with the
   *  server's own error text, so the caller's guard
   *  surfaces it and the snapshot stays untouched. */
  private async postJson<T>(path: string, body: unknown): Promise<T> {
    if (this.channel) return this.postViaChannel<T>(path, body);
    let res: Response;
    try {
      res = await fetch(this.url(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (err) {
      throw new Error(
        `The write could not reach the workbench server — nothing was saved. (${err instanceof Error ? err.message : String(err)})`,
      );
    }
    const payload = (await res.json().catch(() => null)) as
      | (Record<string, unknown> & { error?: string })
      | null;
    if (!res.ok) {
      throw new Error(
        payload?.error ?? `The server refused the write (${res.status}). Nothing was saved.`,
      );
    }
    return payload as T;
  }

  /** postJson over the relay channel (the frame form):
   *  the path translates to its workbench action
   *  (transport.ts), the bridge envelope adapts back to
   *  postJson's contract — a 2xx envelope serves its
   *  payload; any other status throws with the server's
   *  error text (the envelope's error, falling back to
   *  the payload's); a relay-level rejection is the
   *  could-not-reach refusal. A path no action carries
   *  throws unsent — the table covers every postJson
   *  call site, so that throw is a build defect, never
   *  a runtime path. */
  private async postViaChannel<T>(path: string, body: unknown): Promise<T> {
    const channel = this.channel as WbChannel;
    const mapped = actionForPost(path, body);
    if (!mapped) {
      throw new Error(
        `No workbench action carries ${path} — the write was not sent.`,
      );
    }
    let env;
    try {
      env = await channel(mapped.action, mapped.args);
    } catch (err) {
      throw new Error(
        `The write could not reach the workbench server — nothing was saved. (${err instanceof Error ? err.message : String(err)})`,
      );
    }
    const payload = env.payload as
      | (Record<string, unknown> & { error?: string })
      | null;
    if (env.status < 200 || env.status >= 300) {
      throw new Error(
        env.error ??
          payload?.error ??
          `The server refused the write (${env.status}). Nothing was saved.`,
      );
    }
    return payload as T;
  }

  /** An entry mutation through POST …/entries/{id}/action;
   *  the route answers with the entry-detail payload. */
  private async entryAction<T = Record<string, unknown>>(
    e: Entry,
    body: Record<string, unknown>,
  ): Promise<T> {
    return this.postJson<T>(
      `/api/projects/${encodeURIComponent(e.project)}/entries/${encodeURIComponent(e.id)}/action`,
      body,
    );
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  version(): number {
    return this.ver;
  }

  // -- feeds ---------------------------------------------------

  projects() {
    return this.s.projectList;
  }

  projectRollups(): ProjectRollup[] {
    return reads.projectRollups(this.host);
  }

  homeSummary() {
    return reads.homeSummary(this.host);
  }

  entries(project: string) {
    return this.s.entryList.filter((e) => e.project === project && !e.archived);
  }

  entry(id: string) {
    return this.s.entryList.find((e) => e.id === id);
  }

  plans(project: string) {
    return this.s.planList.filter((p) => p.project === project);
  }

  plan(bundle: string) {
    return this.s.planList.find((p) => p.bundle === bundle);
  }

  todos(project: string) {
    return this.s.todoList.filter((t) => t.project === project);
  }

  todo(id: string) {
    return this.s.todoList.find((t) => t.id === id);
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
    return this.s.messageList;
  }

  repos() {
    return this.s.repoList;
  }

  repo(slug: string) {
    return this.s.repoList.find((r) => r.slug === slug);
  }

  goals(project: string) {
    return this.s.goalList.filter((g) => g.project === project);
  }

  allGoals() {
    return this.s.goalList;
  }

  goal(slug: string) {
    return this.s.goalList.find((g) => g.slug === slug);
  }

  goalBundle(goal: GoalRecord) {
    return reads.goalBundle(this.host, goal);
  }

  goalTodos(goal: GoalRecord): FileTodo[] {
    return reads.goalTodos(this.host, goal);
  }

  statusVocabulary() {
    return this.doc.statusVocabulary;
  }

  settings() {
    return this.s.settingsState;
  }

  counts() {
    return reads.counts(this.host);
  }

  // -- served documents ----------------------------------------

  async entryPage(id: string): Promise<EntryPageResult> {
    return documents.entryPage(this.host, id);
  }

  async entrySegments(id: string): Promise<EntrySegmentsResult> {
    return documents.entrySegments(this.host, id);
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
    return repoFiles.guardedSave(this.host, repoSlug, path, content, baseSha);
  }

  async repoFileContent(repoSlug: string, path: string): Promise<EntryFileResult> {
    return repoFiles.repoFileContent(this.host, repoSlug, path);
  }

  async setGoalPing(slug: string, armed: boolean): Promise<GoalRecord> {
    return goalsModule.setGoalPing(this.host, slug, armed);
  }

  async postGoalStatus(slug: string, post: Omit<StatusPost, "postedAt">): Promise<GoalRecord> {
    return goalsModule.postGoalStatus(this.host, slug, post);
  }

  updateSettings(patch: Partial<AppSettings>): AppSettings {
    return panels.updateSettings(this.host, patch);
  }

  // -- entry lifecycle (W4) ----------------------------------
  // The mock adapter's writer semantics over the projected
  // entries, with persistence through the pipeline's
  // writers (POST …/entries/{id}/action, …/file): every
  // method below lands its write on the server first and
  // mirrors it into the snapshot only on acceptance (D-4).

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

  async saveEntryFile(id: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
    return entryMutations.saveEntryFile(this.host, id, path, content, baseSha);
  }

  // -- plan questions + annotations (W8, W5) -----------------

  planQuestions(bundle: string) {
    return plansModule.planQuestions(this.host, bundle);
  }

  async resolvePlanQuestions(bundle: string, answers: Record<string, string>) {
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
    return this.s.threadList;
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

  projectDiff(repoSlug: string, mode: DiffMode) {
    return datasets.projectDiff(this.host, repoSlug, mode);
  }

  worktreeDetail(repoSlug: string, path: string) {
    return datasets.worktreeDetail(this.host, repoSlug, path);
  }

  // -- board done-lane paging (W15) ----------------------------

  boardDone(offset: number, limit: number): { cards: BoardCard[]; total: number } {
    // The served board is a single portion — the done
    // total here is the served done count; deeper history
    // rides the board feed at the serving shell.
    const done = this.board().filter((c) => c.lane === "done");
    return { cards: done.slice(offset, offset + limit), total: done.length };
  }

  // -- repo registry (W12) --------------------------------------

  async updateRepoTracking(
    slug: string,
    patch: Partial<NonNullable<Repo["tracking"]>> & { name?: string },
  ): Promise<Repo> {
    return repoFiles.updateRepoTracking(this.host, slug, patch);
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
    return { ...this.s.care, doctorLabel: this.s.settingsState.doctorLabel };
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

export function createLiveAdapter(
  doc: WorkbenchFeeds,
  apiBase: string = "",
  channel: WbChannel | null = null,
): LiveWorkbenchAdapter {
  return new LiveWorkbenchAdapter(
    doc,
    apiBase,
    () => new Date(),
    channel,
  );
}
