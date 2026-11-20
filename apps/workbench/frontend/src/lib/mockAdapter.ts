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

import {
  cadenceMinutes,
  deriveProgress,
  isArmed,
  isOptOut,
  deriveTodoName,
  renderArmedRow,
} from "./arming";
import { buildSeed, STATUS_VOCABULARY, type SeedDb } from "./seed";
import { runDatasetSql } from "./datasetSql";
import {
  anchorStatus,
  applyAnswersToRaw,
  computeDiff,
  flattenRepoFiles,
} from "./diffModel";
import type {
  BoardCard,
  DatasetSqlResult,
  EntryFileResult,
  EntryPageResult,
  EntrySegmentsResult,
  SaveResult,
  WorkbenchAdapter,
} from "./seam";
import { FIXTURE_SEGMENT_BLOCKS } from "./segmentFixture";
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
  RepoFile,
  RuledStatus,
  ServerCare,
  StatusPost,
  WorktreeDetail,
} from "./types";

function shaOf(content: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < content.length; i++) {
    h ^= content.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0").slice(0, 6);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** The mock's stand-in for an entry's own page: a complete
 *  document authored in the entry's recorded mode, served
 *  through entryPage in the byte route's shape. The demo's
 *  specimens have no files on disk; in the live store this
 *  is the entry's own file, served byte-for-byte. The
 *  page's script runs in the stage's sandboxed frame, as
 *  a served page's would. */
function standinEntryPage(e: Entry): string {
  const dark = e.mode === "Dark";
  const bg = dark ? "#22251a" : "#f7f6ef";
  const ink = dark ? "#e8e6da" : "#2c2f22";
  const sub = dark ? "#a9ad97" : "#6a6e58";
  const bar = dark ? "#3a3f2c" : "#59652c";
  const line = dark ? "#565b45" : "#d8d5c2";
  const title = escapeHtml(e.title);
  return [
    "<!doctype html>",
    '<html lang="en"><head><meta charset="utf-8">',
    `<title>${title}</title>`,
    `<style>body{font-family:system-ui,sans-serif;background:${bg};color:${ink};margin:0;padding:30px}` +
      `h1{font-size:22px;margin:0 0 6px}.sub{color:${sub};font-size:13px;margin:0 0 22px}` +
      `.bar{height:14px;border-radius:4px;background:${bar};width:38%;margin-bottom:12px}` +
      `.ln{height:10px;border-radius:4px;background:${line};margin-bottom:9px}` +
      `.row{display:flex;gap:8px;margin:16px 0}.blk{height:38px;width:58px;border-radius:5px}</style>`,
    "</head><body>",
    `<div class="bar"></div><h1>${title}</h1>`,
    `<p class="sub">${escapeHtml(e.project)} · ${escapeHtml(e.viewport ?? "Desktop")} · ${escapeHtml(e.mode ?? "Light")} — the specimen's own page, as authored.</p>`,
    '<div class="ln" style="width:86%"></div><div class="ln" style="width:68%"></div>',
    '<div class="row"><div class="blk" style="background:#67742f"></div><div class="blk" style="background:#0f766e"></div><div class="blk" style="background:#0072B2"></div><div class="blk" style="background:#D55E00"></div></div>',
    '<div class="ln" style="width:56%"></div>',
    '<p class="sub" id="stamp"></p>',
    '<script>document.getElementById("stamp").textContent = "Page script running · rendered " + new Date().toLocaleTimeString();</script>',
    "</body></html>",
  ].join("\n");
}

function findFile(files: RepoFile[], path: string): RepoFile | undefined {
  const parts = path.split("/");
  let level: RepoFile[] | undefined = files;
  let found: RepoFile | undefined;
  for (const part of parts) {
    found = level?.find((f) => f.name === part);
    if (!found) return undefined;
    level = found.children;
  }
  return found;
}

export class MockWorkbenchAdapter implements WorkbenchAdapter {
  readonly mode = "mock" as const;
  private db: SeedDb;
  private settingsState: AppSettings;
  private listeners = new Set<() => void>();
  private ver = 0;
  private clock: () => Date;

  constructor(clock: () => Date = () => new Date()) {
    this.clock = clock;
    const now = clock();
    this.db = buildSeed(now);
    this.settingsState = {
      boardLaneWidth: 264,
      guardedSaves: false,
      serverLabel: "127.0.0.1:8792 · healthy",
      projectsSwept: this.db.projects.length,
      doctorLabel: "Every 15 min · last run 1:58 PM",
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
    return this.db;
  }

  // -- feeds ---------------------------------------------------

  projects() {
    return this.db.projects;
  }

  projectRollups(): ProjectRollup[] {
    return this.db.projects.slice(0, 5).map((p) => {
      const triage = this.db.entries.filter(
        (e) => e.project === p.slug && e.review === "in-triage",
      ).length;
      const needs = this.db.entries.filter(
        (e) => e.project === p.slug && e.review === "needs-changes",
      );
      const doingPlans = this.db.plans.filter(
        (pl) => pl.project === p.slug && pl.state === "in-progress",
      ).length;
      if (p.health === "degraded") {
        return { project: p, dot: "warn" as const, sub: p.healthNote, chip: { type: "badge" as const, kind: "stale" as const, text: "Stale · 23 d" } };
      }
      if (p.health === "manifest-only" || !p.manifest) {
        return { project: p, dot: "muted" as const, sub: p.healthNote, chip: { type: "plain" as const, text: "Manifest only" } };
      }
      if (needs.length > 0) {
        return { project: p, dot: "ok" as const, sub: `${needs.length} mockup awaiting review`, chip: { type: "badge" as const, kind: "needs-changes" as const, text: `Needs changes · ${needs[0].reviewCount ?? 1}` } };
      }
      if (triage > 0) {
        return { project: p, dot: "ok" as const, sub: `${triage} in triage · board updated ${p.lastActivityLabel}`, chip: { type: "ruled" as const, status: "canonical" as const } };
      }
      if (doingPlans > 0) {
        return { project: p, dot: "ok" as const, sub: `${doingPlans} plan${doingPlans > 1 ? "s" : ""} in progress`, chip: { type: "ruled" as const, status: "implemented" as const } };
      }
      return { project: p, dot: "muted" as const, sub: p.healthNote, chip: { type: "plain" as const, text: "Quiet" } };
    });
  }

  homeSummary() {
    return {
      sweptCount: this.db.projects.length,
      serverHealthy: true,
      editingOn: this.settingsState.guardedSaves,
      awaitingReview: this.db.entries.filter(
        (e) => e.review === "in-triage" || e.review === "needs-changes",
      ).length,
      doingNow: this.db.todos.filter((t) => t.status === "doing").length,
    };
  }

  entries(project: string) {
    return this.db.entries.filter((e) => e.project === project && !e.archived);
  }

  entry(id: string) {
    return this.db.entries.find((e) => e.id === id);
  }

  /** The byte route's shape, served from the store: a
   *  specimen entry gets its stand-in page; an entry held
   *  by reference (a doc or plan living elsewhere in the
   *  seed) refuses with the live store's own reason. */
  async entryPage(id: string): Promise<EntryPageResult> {
    const e = this.db.entries.find((x) => x.id === id);
    if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
    if (e.kind !== "mockup") {
      return {
        ok: false,
        reason:
          "Page unavailable — this entry is held by reference; its files live outside the harness.",
      };
    }
    return {
      ok: true,
      body: standinEntryPage(e),
      contentType: "text/html; charset=utf-8",
    };
  }

  /** The segment feed's shape, served from the store:
   *  the field-note specimen's document rides as fixture
   *  segments generated by the pipeline's own segmenter
   *  (segmentFixture.ts) — the same blocks the live feed
   *  serves for the same document. Every other specimen
   *  refuses as the live store's classes do: a mockup's
   *  main file is a rendered page, and a held doc has no
   *  document of its own here. */
  async entrySegments(id: string): Promise<EntrySegmentsResult> {
    const e = this.db.entries.find((x) => x.id === id);
    if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
    if (e.id === "e-field-note") {
      return { ok: true, mainFile: "note.md", blocks: FIXTURE_SEGMENT_BLOCKS };
    }
    if (e.kind === "mockup") {
      return {
        ok: false,
        reason:
          "The entry's main file is a rendered page, not a text document — the segment feed does not apply.",
      };
    }
    return {
      ok: false,
      reason:
        "Segments unavailable — this entry is held by reference; its files live outside the harness.",
    };
  }

  plans(project: string) {
    return this.db.plans.filter((p) => p.project === project);
  }

  plan(bundle: string) {
    return this.db.plans.find((p) => p.bundle === bundle);
  }

  todos(project: string) {
    return this.db.todos.filter((t) => t.project === project);
  }

  todo(id: string) {
    return this.db.todos.find((t) => t.id === id);
  }

  classification(project: string): ClassificationRow[] {
    const now = this.clock();
    return this.db.todos
      .filter((t) => t.project === project)
      .map((t) => {
        const plan = this.plan(t.bundle);
        const armed = isArmed(t, plan?.archived ?? false);
        return {
          todo: t,
          optOut: isOptOut(t),
          armed,
          derivation: armed ? deriveProgress(t, now) : null,
        };
      });
  }

  armedRows(): ArmedRow[] {
    return this.db.todos
      .filter((t) => isArmed(t, this.plan(t.bundle)?.archived ?? false))
      .map(renderArmedRow)
      .sort((a, b) => a.armed_at!.localeCompare(b.armed_at!));
  }

  board(): BoardCard[] {
    const cards: BoardCard[] = [];
    for (const e of this.db.entries) {
      if (e.archived) continue;
      if (e.review === "in-triage" || e.review === "needs-changes") {
        cards.push({
          id: `card-entry-${e.id}`,
          lane: "review",
          projectTag: e.project.toUpperCase(),
          title: e.title + (e.kind === "mockup" ? "" : ""),
          meta: "",
          badge: { kind: "review", text: e.review, count: e.reviewCount },
          target: { kind: "entry", id: e.id },
        });
      } else if (e.review === "approved") {
        cards.push({
          id: `card-entry-${e.id}`,
          lane: "done",
          projectTag: e.project.toUpperCase(),
          title: e.title,
          meta: "",
          ruled: "implemented",
          target: { kind: "entry", id: e.id },
        });
      }
    }
    for (const p of this.db.plans) {
      if (p.archived) continue;
      const stepsDone = p.steps.filter(
        (s) => s.todoId && this.todo(s.todoId)?.status === "done",
      ).length;
      const anyDoing = p.steps.some(
        (s) => s.todoId && this.todo(s.todoId)?.status === "doing",
      );
      const gated = p.bundle === "2026-11-10-step6-reparse-cadence";
      cards.push({
        id: `card-plan-${p.bundle}`,
        lane: p.state === "done" ? "done" : anyDoing || gated ? "doing" : "todo",
        projectTag: p.project.toUpperCase(),
        title: p.title,
        meta: `Plan · ${stepsDone}/${p.steps.length} steps`,
        badge: gated ? { kind: "gate", text: "hard-gate" } : undefined,
        target: { kind: "plan", bundle: p.bundle },
      });
    }
    for (const t of this.db.todos) {
      const plan = this.plan(t.bundle);
      if (!plan || plan.archived) continue;
      if (plan.steps.some((s) => s.todoId === t.id)) continue; // rides its plan card
      cards.push({
        id: `card-todo-${t.id}`,
        lane: t.status === "done" ? "done" : t.status === "todo" ? "todo" : "doing",
        projectTag: t.project.toUpperCase(),
        title: t.title,
        meta: `Todo · ${plan.title}`,
        target: { kind: "todo", id: t.id },
      });
    }
    return cards;
  }

  messages() {
    return this.db.messages;
  }

  repos() {
    return this.db.repos;
  }

  repo(slug: string) {
    return this.db.repos.find((r) => r.slug === slug);
  }

  goals(project: string) {
    return this.db.goals.filter((g) => g.project === project);
  }

  allGoals() {
    return this.db.goals;
  }

  goal(slug: string) {
    return this.db.goals.find((g) => g.slug === slug);
  }

  goalBundle(goal: GoalRecord): Plan | undefined {
    const named = goal.lastPost?.refs?.plan;
    if (named) {
      const plan = this.plan(named);
      if (plan) return plan;
    }
    const inProgress = this.db.plans.filter(
      (p) => p.project === goal.project && p.state === "in-progress" && !p.archived,
    );
    return inProgress.length === 1 ? inProgress[0] : undefined;
  }

  goalTodos(goal: GoalRecord): FileTodo[] {
    const bundle = this.goalBundle(goal);
    if (!bundle) return [];
    const byId = new Map(
      this.db.todos
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

  statusVocabulary() {
    return STATUS_VOCABULARY;
  }

  settings() {
    return this.settingsState;
  }

  counts() {
    const terminal = new Set(
      STATUS_VOCABULARY.filter((r) => r.terminal).map((r) => r.code),
    );
    return {
      mockupsInTriage: this.db.entries.filter(
        (e) => e.project === "spec-driven-starter" && e.kind === "mockup" && e.review === "in-triage" && !e.archived,
      ).length,
      boardDoing: this.board().filter((c) => c.lane === "doing").length,
      inboxAwaiting: this.db.messages.filter((m) => m.disposition === null).length,
      goalsActive: this.db.goals.filter(
        (g) => !g.lastPost || !terminal.has(g.lastPost.status_code),
      ).length,
    };
  }

  // -- mutations -------------------------------------------------

  async setEntryReview(id: string, review: "approved" | "needs-changes" | "stale", note?: string): Promise<Entry> {
    const e = this.db.entries.find((x) => x.id === id);
    if (!e) throw new Error(`unknown entry ${id}`);
    if (review === "approved") {
      e.review = "approved";
      e.approvedBy = "owner";
      e.reviewLog = [
        { label: `Approved · state ${e.stateHash ?? "—"}`, when: "Just now", actor: "owner" },
        ...e.reviewLog,
      ];
    } else if (review === "needs-changes") {
      e.review = "needs-changes";
      e.reviewCount = (e.reviewCount ?? 0) + 1;
      e.reviewLog = [
        { label: `Needs changes · ${e.reviewCount} open`, when: "Just now", actor: "owner" },
        ...e.reviewLog,
      ];
    } else {
      e.review = null;
      e.staleNote = "Stale · marked by owner";
      e.reviewLog = [
        { label: note ?? "Marked stale", when: "Just now", actor: "owner" },
        ...e.reviewLog,
      ];
    }
    this.emit();
    return e;
  }

  async writeTodo(
    id: string,
    patch: Partial<Pick<FileTodo, "title" | "status" | "progressCheck" | "notes">>,
  ): Promise<{ todo: FileTodo; armed: boolean }> {
    const t = this.db.todos.find((x) => x.id === id);
    if (!t) throw new Error(`unknown todo ${id}`);
    if (patch.title !== undefined) {
      if (patch.title.trim().length === 0) throw new Error("title must not be empty");
      t.title = patch.title.trim();
    }
    if (patch.notes !== undefined) t.notes = patch.notes;
    if (patch.progressCheck !== undefined) t.progressCheck = patch.progressCheck;
    if (patch.status !== undefined && patch.status !== t.status) {
      t.status = patch.status;
      if (patch.status === "doing") {
        // The doing transition arms: stamp + both projections,
        // in the same writer call (contract 03).
        if (cadenceMinutes(t.progressCheck) !== null) {
          t.progressArmed = this.clock().toISOString();
        }
      } else {
        // Stop status retires the projections.
        t.progressArmed = undefined;
      }
    }
    // Cadence edited while doing: re-render the projections;
    // opting out disarms.
    if (patch.progressCheck !== undefined && t.status === "doing") {
      if (cadenceMinutes(t.progressCheck) === null) t.progressArmed = undefined;
      else if (!t.progressArmed) t.progressArmed = this.clock().toISOString();
    }
    t.updated = this.clock().toISOString().slice(0, 10);
    this.emit();
    return { todo: t, armed: isArmed(t, this.plan(t.bundle)?.archived ?? false) };
  }

  async addTodo(project: string, bundle: string, title: string): Promise<FileTodo> {
    const t: FileTodo = {
      id: deriveTodoName(
        title,
        this.db.todos.filter((x) => x.project === project).map((x) => x.id),
      ),
      project,
      bundle,
      title,
      status: "todo",
      created: this.clock().toISOString().slice(0, 10),
      updated: this.clock().toISOString().slice(0, 10),
      checkpoints: [],
      notes: "",
      extra: {},
    };
    this.db.todos.push(t);
    this.emit();
    return t;
  }

  async addCheckpoint(id: string, text: string): Promise<FileTodo> {
    const t = this.db.todos.find((x) => x.id === id);
    if (!t) throw new Error(`unknown todo ${id}`);
    t.checkpoints = [...t.checkpoints, { at: this.clock().toISOString(), text }];
    t.updated = this.clock().toISOString().slice(0, 10);
    this.emit();
    return t;
  }

  async moveBoardCard(cardId: string, lane: BoardCard["lane"]): Promise<void> {
    const card = this.board().find((c) => c.id === cardId);
    if (!card) return;
    if (card.target.kind === "todo") {
      const status = lane === "done" ? "done" : lane === "todo" ? "todo" : lane === "doing" ? "doing" : null;
      if (status) await this.writeTodo(card.target.id, { status });
      return;
    }
    if (card.target.kind === "plan") {
      const p = this.plan(card.target.bundle);
      if (!p) return;
      if (lane === "done") p.state = "done";
      else if (lane === "doing") p.state = "in-progress";
      else if (lane === "todo") p.state = "draft";
      this.emit();
      return;
    }
    if (card.target.kind === "entry" && lane === "done") {
      await this.setEntryReview(card.target.id, "approved");
    }
    // Review cards dropped elsewhere stay in the review queue:
    // a disposition is a verdict, not a drag (storyboard frame 3).
  }

  async dismissMessage(id: string): Promise<void> {
    const m = this.db.messages.find((x) => x.id === id);
    if (m) m.disposition = "dismissed";
    this.emit();
  }

  openMessage(id: string) {
    const m = this.db.messages.find((x) => x.id === id);
    if (!m) throw new Error(`unknown message ${id}`);
    if (m.disposition === null) m.disposition = "opened";
    this.emit();
    return m;
  }

  async guardedSave(repoSlug: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
    if (!this.settingsState.guardedSaves) {
      return { ok: false, reason: "Guarded file saves are off — enable them in Settings → Workbench." };
    }
    const repo = this.repo(repoSlug);
    const file = repo ? findFile(repo.files, path) : undefined;
    if (!repo || !file) return { ok: false, reason: `No such file: ${path}` };
    if (file.editable !== "guarded") {
      return { ok: false, reason: file.editableNote ?? "This file is not editable in the viewer." };
    }
    if (file.sha !== baseSha) {
      return {
        ok: false,
        reason: `Save refused — stale sha: the file is at ${file.sha ?? "—"}, you opened ${baseSha}. The saved file was not touched.`,
      };
    }
    file.content = content;
    file.headContent = content;
    file.sha = shaOf(content);
    file.lines = content.split("\n").length;
    file.sizeLabel = `${content.length.toLocaleString()} bytes · ${file.lines} lines`;
    repo.modifiedCount = Math.max(0, repo.modifiedCount - 1);
    this.emit();
    return { ok: true, sha: file.sha, savedLabel: "Just now" };
  }

  async setGoalPing(slug: string, armed: boolean) {
    const g = this.db.goals.find((x) => x.slug === slug);
    if (!g) throw new Error(`unknown goal ${slug}`);
    if (armed) {
      // A terminal post retires the record's ping for good:
      // a closed goal's entry is never re-armed.
      const row = STATUS_VOCABULARY.find((r) => r.code === g.lastPost?.status_code);
      if (row?.terminal) {
        throw new Error("This goal is closed — its ping is retired and cannot be re-armed.");
      }
    }
    g.ping.armed = armed;
    this.emit();
    return g;
  }

  async postGoalStatus(slug: string, post: Omit<StatusPost, "postedAt">) {
    const g = this.db.goals.find((x) => x.slug === slug);
    if (!g) throw new Error(`unknown goal ${slug}`);
    if (post.status_code === "BLOCKED-OWNER" || post.status_code === "BLOCKED-HARD") {
      // Contract 11 amendment (2026-11-13): a blocked post
      // without its cited basis is invalid at the writer.
      // The citation is the poster's; the verification stamp
      // is applied here, by the verifying party (main), as
      // the post is recorded.
      if (!post.basis_citation || post.basis_citation.thread.trim().length === 0) {
        throw new Error(
          "A blocked post must carry its basis citation — the owner's message reference (thread + time). Uncited blocked posts are refused at the writer.",
        );
      }
      post = {
        ...post,
        verification: post.verification ?? { by: "main", at: this.clock().toISOString() },
      };
    }
    g.lastPost = { ...post, postedAt: this.clock().toISOString() };
    if (post.status_code === "DONE" || post.status_code === "CLOSED") {
      // A terminal post clears the sticky owner-waiting
      // declaration (contract 03, ATT10).
      if (g.lastPost.owner_waiting) g.lastPost = { ...g.lastPost, owner_waiting: null };
    }
    this.emit();
    return g;
  }

  updateSettings(patch: Partial<AppSettings>): AppSettings {
    this.settingsState = { ...this.settingsState, ...patch };
    this.emit();
    return this.settingsState;
  }

  // -- entry lifecycle (W4) ----------------------------------

  private entryOrThrow(id: string): Entry {
    const e = this.db.entries.find((x) => x.id === id);
    if (!e) throw new Error(`unknown entry ${id}`);
    return e;
  }

  private logEntry(e: Entry, label: string) {
    e.reviewLog = [{ label, when: "Just now", actor: "owner" }, ...e.reviewLog];
  }

  async setEntryStatus(id: string, status: RuledStatus): Promise<Entry> {
    const e = this.entryOrThrow(id);
    e.status = status;
    if (status !== "unexplored" && e.review === "in-triage") e.review = null;
    this.logEntry(e, `Status set · ${status}`);
    this.emit();
    return e;
  }

  async setEntryMeta(
    id: string,
    patch: Partial<Pick<Entry, "title" | "viewport" | "mode">>,
  ): Promise<Entry> {
    const e = this.entryOrThrow(id);
    if (patch.title !== undefined) {
      if (patch.title.trim().length === 0) throw new Error("title must not be empty");
      e.title = patch.title.trim();
    }
    if (patch.viewport !== undefined) e.viewport = patch.viewport;
    if (patch.mode !== undefined) e.mode = patch.mode;
    this.logEntry(e, "Metadata edited");
    this.emit();
    return e;
  }

  async verifyEntry(id: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    e.stateHash = shaOf(
      JSON.stringify({ t: e.title, s: e.status, v: e.version, f: e.files?.map((f) => f.path) }),
    );
    this.logEntry(e, `Verified · state ${e.stateHash}`);
    this.emit();
    return e;
  }

  async archiveEntry(id: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    e.archived = true;
    this.logEntry(e, "Archived");
    this.emit();
    return e;
  }

  async unarchiveEntry(id: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    e.archived = false;
    this.logEntry(e, "Unarchived");
    this.emit();
    return e;
  }

  async supersedeEntry(id: string, byId: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    const by = this.entryOrThrow(byId);
    e.staleNote = `Superseded by ${by.title}`;
    e.review = null;
    this.logEntry(e, `Superseded by ${by.id}`);
    this.logEntry(by, `Supersedes ${e.id}`);
    this.emit();
    return e;
  }

  async setEntryState(id: string, json: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      throw new Error("State must be valid JSON — the entry's state was not touched.");
    }
    e.stateJson = JSON.stringify(parsed, null, 2);
    this.logEntry(e, "State saved");
    this.emit();
    return e;
  }

  /** Entry-file bodies in the mock store: the main file of
   *  a mockup is its stand-in page; a doc's file is the repo
   *  file it points at; anything else is a small authored
   *  stand-in, overridable by a save. */
  private entryFileOverrides = new Map<string, string>();

  private entryFileBody(id: string, path: string): { body: string } | { reason: string } {
    const e = this.db.entries.find((x) => x.id === id);
    if (!e) return { reason: `Unknown entry: ${id}` };
    const override = this.entryFileOverrides.get(`${id}|${path}`);
    if (override !== undefined) return { body: override };
    const info = e.files?.find((f) => f.path === path);
    if (!info) return { reason: `The entry serves no file at ${path}.` };
    if (e.repoPath && path === e.repoPath.path) {
      const repo = this.db.repos.find((r) => r.slug === e.repoPath!.repo);
      const file = repo ? findFile(repo.files, path.split("/").slice(1).join("/")) ?? findFile(repo.files, path) : undefined;
      if (file?.content) return { body: file.content };
    }
    if (info.isMain && e.kind === "mockup") return { body: standinEntryPage(e) };
    if (info.isMain && e.kind === "plan") {
      const plan = this.db.plans.find((p) => p.project === e.project);
      if (plan) return { body: plan.raw };
    }
    return {
      body: `/* ${path} — a file of "${e.title}".\n   The demo store authors no body for this file;\n   a save here replaces this stand-in. */\n`,
    };
  }

  async entryFileContent(id: string, path: string): Promise<EntryFileResult> {
    const found = this.entryFileBody(id, path);
    if ("reason" in found) return { ok: false, reason: found.reason };
    return { ok: true, body: found.body, sha: shaOf(found.body) };
  }

  async repoFileContent(repoSlug: string, path: string): Promise<EntryFileResult> {
    const repo = this.repo(repoSlug);
    const file = repo ? findFile(repo.files, path) : undefined;
    if (!repo || !file) return { ok: false, reason: `No such file: ${path}` };
    if (file.content === undefined) {
      return { ok: false, reason: file.editableNote ?? "The mock does not serve this file's content." };
    }
    return { ok: true, body: file.content, sha: file.sha ?? shaOf(file.content) };
  }

  async saveEntryFile(id: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
    const found = this.entryFileBody(id, path);
    if ("reason" in found) return { ok: false, reason: found.reason };
    const currentSha = shaOf(found.body);
    if (currentSha !== baseSha) {
      return {
        ok: false,
        reason: `Save refused — stale sha: the file is at ${currentSha}, you opened ${baseSha}. The saved file was not touched.`,
      };
    }
    this.entryFileOverrides.set(`${id}|${path}`, content);
    const e = this.entryOrThrow(id);
    this.logEntry(e, `File saved · ${path}`);
    this.emit();
    return { ok: true, sha: shaOf(content), savedLabel: "Just now" };
  }

  // -- plan questions + annotations (W8, W5) -----------------

  planQuestions(bundle: string) {
    return this.plan(bundle)?.questions ?? [];
  }

  async resolvePlanQuestions(bundle: string, answers: Record<string, string>): Promise<Plan> {
    const p = this.plan(bundle);
    if (!p) throw new Error(`unknown plan ${bundle}`);
    for (const q of p.questions ?? []) {
      const answer = answers[q.id]?.trim();
      if (answer) {
        q.answer = answer;
        q.answeredBy = "owner";
        q.answeredLabel = "Just now";
      }
    }
    p.raw = applyAnswersToRaw(p.raw, answers);
    this.emit();
    return p;
  }

  annotationsForPlan(bundle: string): AnnotationThread[] {
    const plan = this.plan(bundle);
    return this.db.annotations
      .filter((t) => t.bundle === bundle)
      .map((t) => ({
        ...t,
        status: plan ? anchorStatus(plan.raw, t.anchorQuote, t.anchorContext) : t.status,
      }));
  }

  async addAnnotation(bundle: string, quote: string, body: string): Promise<AnnotationThread> {
    const plan = this.plan(bundle);
    if (!plan) throw new Error(`unknown plan ${bundle}`);
    const line = plan.raw.split("\n").find((l) => l.includes(quote));
    const thread: AnnotationThread = {
      id: `ann-${this.db.annotations.length + 1}`,
      bundle,
      project: plan.project,
      anchorQuote: quote,
      anchorContext: line,
      status: line ? "anchored" : "orphaned",
      resolved: false,
      messages: [
        { id: `ann-m-${Date.now()}`, author: "owner", body, when: "Just now" },
      ],
    };
    this.db.annotations.push(thread);
    this.emit();
    return thread;
  }

  async replyAnnotation(id: string, body: string): Promise<AnnotationThread> {
    const t = this.db.annotations.find((x) => x.id === id);
    if (!t) throw new Error(`unknown annotation ${id}`);
    t.messages = [
      ...t.messages,
      { id: `${id}-m${t.messages.length + 1}`, author: "owner", body, when: "Just now" },
    ];
    this.emit();
    return t;
  }

  setAnnotationResolved(id: string, resolved: boolean): AnnotationThread {
    const t = this.db.annotations.find((x) => x.id === id);
    if (!t) throw new Error(`unknown annotation ${id}`);
    t.resolved = resolved;
    this.emit();
    return t;
  }

  // -- message threads (W10) ---------------------------------

  messageThreads(): MessageThread[] {
    return this.db.threads;
  }

  async composeThread(input: {
    project: string;
    body: string;
    anchorText?: string;
    sendNow: boolean;
  }): Promise<MessageThread> {
    const body = input.body.trim();
    if (!body) throw new Error("A message needs a body.");
    const thread: MessageThread = {
      id: `th-${this.db.threads.length + 1}`,
      project: input.project,
      title: body.split("\n")[0].slice(0, 90),
      state: input.sendNow ? "sent" : "draft",
      anchorText: input.anchorText?.trim() || undefined,
      messages: [
        { id: `th-m-${Date.now()}`, author: "owner", body, when: "Just now" },
      ],
    };
    this.db.threads.push(thread);
    this.emit();
    return thread;
  }

  async replyThread(id: string, body: string): Promise<MessageThread> {
    const t = this.db.threads.find((x) => x.id === id);
    if (!t) throw new Error(`unknown thread ${id}`);
    t.messages = [
      ...t.messages,
      { id: `${id}-m${t.messages.length + 1}`, author: "owner", body, when: "Just now" },
    ];
    if (t.state === "draft") t.state = "sent";
    this.emit();
    return t;
  }

  async editThreadMessage(threadId: string, messageId: string, body: string): Promise<MessageThread> {
    const t = this.db.threads.find((x) => x.id === threadId);
    if (!t) throw new Error(`unknown thread ${threadId}`);
    const m = t.messages.find((x) => x.id === messageId);
    if (!m) throw new Error(`unknown message ${messageId}`);
    m.body = body;
    this.emit();
    return t;
  }

  async setThreadState(id: string, state: "sent" | "done" | "archived"): Promise<MessageThread> {
    const t = this.db.threads.find((x) => x.id === id);
    if (!t) throw new Error(`unknown thread ${id}`);
    t.state = state;
    this.emit();
    return t;
  }

  // -- datasets (W11) -----------------------------------------

  async datasetSql(repoSlug: string, path: string, sql: string): Promise<DatasetSqlResult> {
    const repo = this.repo(repoSlug);
    const file = repo ? findFile(repo.files, path) : undefined;
    if (!repo || !file?.dataset) {
      return { ok: false, reason: `No dataset is served for ${path}.` };
    }
    const out = runDatasetSql(file.dataset.tables, sql);
    if (!out.ok) return out;
    return { ok: true, table: out.table, source: "engine" };
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
    const repo = this.repo(repoSlug);
    if (!repo) return { mode, label: mode, files: [], note: `Unknown repo: ${repoSlug}` };
    return computeDiff(repo.files, mode);
  }

  worktreeDetail(repoSlug: string, path: string): WorktreeDetail | undefined {
    const repo = this.repo(repoSlug);
    const w = repo?.worktrees.find((x) => x.path === path);
    if (!repo || !w) return undefined;
    const changedFiles = flattenRepoFiles(repo.files)
      .filter(
        ({ file }) =>
          (file.headContent !== undefined && file.headContent !== (file.content ?? "")) ||
          file.classification === "untracked",
      )
      .map(({ path: p }) => p);
    const active = this.db.plans.find(
      (p) => p.project === repoSlug && p.state === "in-progress" && !p.archived,
    );
    return {
      label: w.label,
      path: w.path,
      branch: w.branch,
      dirty: w.dirty,
      activePlan: w.branch === repo.branch ? active?.title : undefined,
      changedFiles: w.branch === repo.branch ? changedFiles : [],
    };
  }

  // -- board done-lane paging (W15) ----------------------------

  boardDone(offset: number, limit: number): { cards: BoardCard[]; total: number } {
    const done = this.board().filter((c) => c.lane === "done");
    return { cards: done.slice(offset, offset + limit), total: done.length };
  }

  // -- repo registry (W12) --------------------------------------

  async updateRepoTracking(
    slug: string,
    patch: Partial<NonNullable<Repo["tracking"]>> & { name?: string },
  ): Promise<Repo> {
    const r = this.repo(slug);
    if (!r) throw new Error(`unknown repo ${slug}`);
    if (patch.name !== undefined && patch.name.trim()) r.name = patch.name.trim();
    const { name: _name, ...tracking } = patch;
    r.tracking = {
      expected: r.tracking?.expected ?? "",
      pinned: r.tracking?.pinned ?? false,
      ignored: r.tracking?.ignored ?? false,
      notes: r.tracking?.notes ?? "",
      ...tracking,
    };
    this.emit();
    return r;
  }

  // -- settings panels (W13) + server care (W3) -----------------

  workspaceConfig(): { label: string; value: string }[] {
    return [
      { label: "Server", value: this.settingsState.serverLabel },
      { label: "Projects swept", value: String(this.db.projects.length) },
      { label: "Registry entries", value: String(this.db.entries.length) },
      { label: "Guarded file saves", value: this.settingsState.guardedSaves ? "On" : "Off" },
      { label: "Board lane width", value: `${this.settingsState.boardLaneWidth} px` },
      { label: "Doctor", value: this.settingsState.doctorLabel },
    ];
  }

  messageCounts(): { label: string; count: number }[] {
    const by = (d: string | null) => this.db.messages.filter((m) => m.disposition === d).length;
    return [
      { label: "Awaiting disposition", count: by(null) },
      { label: "Filed", count: by("filed") },
      { label: "Opened", count: by("opened") },
      { label: "Dismissed", count: by("dismissed") },
      { label: "Draft threads", count: this.db.threads.filter((t) => t.state === "draft").length },
      { label: "Sent threads", count: this.db.threads.filter((t) => t.state === "sent").length },
    ];
  }

  cleanupMessages(): { removed: number } {
    const before = this.db.messages.length;
    this.db.messages = this.db.messages.filter((m) => m.disposition !== "dismissed");
    const removed = before - this.db.messages.length;
    this.emit();
    return { removed };
  }

  purgeMessages(): { removed: number } {
    const before = this.db.messages.length;
    this.db.messages = this.db.messages.filter((m) => m.disposition === null);
    const removed = before - this.db.messages.length;
    this.emit();
    return { removed };
  }

  private care: ServerCare = {
    linkState: "ok",
    classification: "supervised · one unit",
    doctorLabel: "Every 15 min · last run 1:58 PM",
    lastRepairLabel: "—",
    strayCount: 1,
    log: ["Link probe ok · 2 min ago", "Health state written · 2 min ago"],
  };

  serverCare(): ServerCare {
    return this.care;
  }

  repairAction(kind: "clear-strays" | "fallback-restart"): ServerCare {
    if (kind === "clear-strays") {
      const n = this.care.strayCount;
      this.care = {
        ...this.care,
        strayCount: 0,
        lastRepairLabel: "Stray-process clear · Just now",
        log: [`Cleared ${n} stray process${n === 1 ? "" : "es"} · Just now`, ...this.care.log],
      };
    } else {
      this.care = {
        ...this.care,
        linkState: "ok",
        lastRepairLabel: "Fallback start · Just now",
        log: ["Fallback start ran · server healthy · Just now", ...this.care.log],
      };
    }
    this.emit();
    return this.care;
  }

  // -- refresh / rescan (W14) -----------------------------------

  private lastRefresh = new Date();

  async refresh(): Promise<{ label: string }> {
    this.lastRefresh = this.clock();
    this.emit();
    return { label: this.freshnessLabel() };
  }

  async rescan(): Promise<{ label: string }> {
    this.settingsState = { ...this.settingsState, projectsSwept: this.db.projects.length };
    this.lastRefresh = this.clock();
    this.emit();
    return { label: this.freshnessLabel() };
  }

  freshnessLabel(): string {
    const secs = Math.max(0, Math.floor((this.clock().getTime() - this.lastRefresh.getTime()) / 1000));
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
