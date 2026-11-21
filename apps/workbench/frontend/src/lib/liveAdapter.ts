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
// reload and shows in `wb` (D-4, cured 2026-11-15). The
// writes are therefore async at the seam. Goal ping/posts
// and annotation creates/replies joined the cured set
// under W-C5 (2026-11-15): POST /api/goals/{slug}/… and
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

import {
  cadenceMinutes,
  deriveProgress,
  isArmed,
  isOptOut,
  renderArmedRow,
} from "./arming";
import type {
  FeedBoard,
  FeedBoardCard,
  FeedEntryDetail,
  FeedEntryRow,
  FeedEntrySegments,
  FeedMessageRow,
  FeedPlanDoc,
  FeedTodoRow,
  WorkbenchFeeds,
} from "./feeds";
import { runDatasetSql } from "./datasetSql";
import { actionForPost, type WbChannel } from "./transport";
import {
  anchorStatus,
  applyAnswersToRaw,
  computeDiff,
  flattenRepoFiles,
  normalizeServedDiff,
  parsePlanQuestions,
} from "./diffModel";
import type { BoardCard, DatasetSqlResult, EntryFileResult, EntryPageResult, EntrySegmentsResult, SaveResult, WorkbenchAdapter } from "./seam";
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
  Project,
  ProjectDiff,
  ProjectRollup,
  ProgressDerivation,
  Repo,
  RepoFile,
  ReviewState,
  RuledStatus,
  ServerCare,
  StatusPost,
  WorktreeDetail,
} from "./types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-25T11:30:00+00:00" -> "Oct 25, 2026". Display
 *  labels are projections of served stamps. */
function dateLabel(iso: string | null | undefined): string {
  if (!iso) return "No activity";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

/** The local content hash is gone (D-4): every sha the
 *  adapter carries is a sha256 the server served — the
 *  peeks' in the feeds document, the file routes', or a
 *  save's response. Nothing here computes one. */

function findFileInTree(files: RepoFile[], path: string): RepoFile | undefined {
  const parts = path.split("/").filter(Boolean);
  let level = files;
  let found: RepoFile | undefined;
  for (const part of parts) {
    found = level.find((f) => f.name === part);
    if (!found) return undefined;
    level = found.children ?? [];
  }
  return found;
}

const KNOWN_TODO_FIELDS = new Set([
  "id", "title", "status", "feature", "plan", "plan_step",
  "worktree", "created", "updated", "progress_check",
  "progress_armed",
]);

const CHECKPOINT_RE = /^progress-checkpoint: (\S+) — (.*)$/;

function projectTodo(row: FeedTodoRow, project: string): FileTodo {
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

/** Registry kinds are exhibit kinds; the seam's EntryKind
 *  is the storyboard's grouping — storyboards read as
 *  docs, every other exhibit kind as a mockup. */
function entryKind(kind: string): Entry["kind"] {
  if (kind === "storyboard") return "doc";
  if (kind === "plan" || kind === "doc") return kind;
  return "mockup";
}

function reviewOf(
  row: FeedEntryRow,
  detail: FeedEntryDetail | undefined,
): { review: ReviewState | null; reviewCount?: number } {
  const latest = detail?.latest_review;
  if (latest?.verb === "review" && latest.new) {
    try {
      const parsed = JSON.parse(latest.new) as { disposition?: string };
      if (parsed.disposition === "approve") return { review: "approved" };
      if (parsed.disposition === "stale") return { review: "stale" };
      if (parsed.disposition === "needs-changes") {
        const count = (detail?.history ?? []).filter((h) => {
          if (h.verb !== "review" || !h.new) return false;
          try {
            return (JSON.parse(h.new) as { disposition?: string }).disposition === "needs-changes";
          } catch {
            return false;
          }
        }).length;
        return { review: "needs-changes", reviewCount: Math.max(1, count) };
      }
    } catch {
      // a review payload that does not parse carries no state
    }
  }
  // The served review queue's own rule: an unexplored
  // entry awaits a ruling; a ruled status (canonical and
  // its kin) has been dispositioned, verified or not.
  if (row.status === "unexplored") {
    return { review: "in-triage" };
  }
  return { review: null };
}

function projectEntry(
  row: FeedEntryRow,
  detail: FeedEntryDetail | undefined,
  project: string,
): Entry {
  const { review, reviewCount } = reviewOf(row, detail);
  const history = detail?.history ?? [];
  const reviewLog = [...history].reverse().map((h) => {
    let label = h.verb;
    if (h.verb === "review" && h.new) {
      try {
        const parsed = JSON.parse(h.new) as { disposition?: string; comment?: string };
        label = parsed.disposition ?? h.verb;
        if (parsed.comment) label += ` · ${parsed.comment}`;
      } catch {
        label = h.verb;
      }
    } else if (h.note) {
      label += ` · ${h.note}`;
    }
    return { label, when: dateLabel(h.ts), actor: h.actor };
  });
  const approvedBy =
    row.approval?.approved && detail?.latest_review?.verb === "review"
      ? detail.latest_review.actor
      : undefined;
  return {
    id: row.id,
    project,
    kind: entryKind(row.kind),
    title: row.title,
    status: row.status as RuledStatus,
    review,
    reviewCount,
    version: row.version,
    registeredLabel: dateLabel(row.created_at),
    stateHash: row.approval?.current_state_sha256 ?? undefined,
    approvedBy,
    staleNote: row.derived?.stale ? "Stale · served derivation" : undefined,
    reviewLog,
    archived: row.archived,
    files: (detail?.files ?? []).map((f) => ({
      path: f.path,
      isMain: f.is_main,
      sizeLabel: `${f.size_bytes.toLocaleString()} bytes`,
    })),
  };
}

function projectPlan(
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

function projectMessage(
  row: FeedMessageRow,
  disposition: InboxMessage["disposition"] | undefined,
): InboxMessage {
  const ref = row.anchor_ref ?? "";
  const bundle = ref.split("/")[0];
  let kind: InboxMessage["kind"] = "doctor";
  let target: InboxMessage["target"] = { section: "overview" };
  if (row.anchor_type === "text" || row.anchor_type === "component") {
    if (ref.endsWith("plan.md") || row.anchor_context?.step != null) {
      kind = "plan";
      target = { section: "plans", bundle };
    } else if (row.showcase || row.anchor_type === "component") {
      kind = "mockup";
      target = { section: "mockups", entryId: ref };
    }
  }
  const served =
    row.state === "sent"
      ? null
      : row.state === "acknowledged"
        ? "opened"
        : "filed";
  return {
    id: String(row.id),
    kind,
    title: row.body.split("\n")[0].slice(0, 90) || row.anchor_context?.quote || "(no body)",
    project: row.project_slug ?? "",
    arrivedLabel: dateLabel(row.created_at),
    disposition: disposition !== undefined ? disposition : (served as InboxMessage["disposition"]),
    target,
  };
}

export class LiveWorkbenchAdapter implements WorkbenchAdapter {
  readonly mode = "live" as const;
  private doc: WorkbenchFeeds;
  private listeners = new Set<() => void>();
  private ver = 0;

  private projectList: Project[];
  private entryList: Entry[];
  private planList: Plan[];
  private todoList: FileTodo[];
  private messageList: InboxMessage[];
  private repoList: Repo[];
  private goalList: GoalRecord[];
  private boards: Map<string, FeedBoard>;
  /** Each entry's main file, as served in its detail's
   *  file list — the byte route's path for the page. */
  private pagePaths = new Map<string, string>();
  /** Served classification blocks per project+todo. */
  private servedDerivations: Map<string, ProgressDerivation>;
  /** Todos mutated locally since the snapshot: their
   *  derivations re-derive until the next document. */
  private mutatedTodos = new Set<string>();
  /** Armed rows' source class per project, as served. */
  private sourceClass: Map<string, ArmedRow["source"]["source_class"]>;
  private dispositions = new Map<string, InboxMessage["disposition"]>();
  private settingsState: AppSettings;
  private annotationList: AnnotationThread[] = [];
  private threadList: MessageThread[] = [];
  private entryFileCache = new Map<string, string>();
  /** Entry files' served sha256, keyed like the content
   *  cache — the guarded save's compare-and-swap base,
   *  served by the file route, never computed locally. */
  private entryFileShas = new Map<string, string>();
  /** Each plan's write coordinates for the resolve route:
   *  its plans-dir path and the file sha256 the document
   *  served for it, keyed by bundle. */
  private planWrite = new Map<string, { path: string; sha256: string }>();
  private lastRefresh = new Date();

  constructor(
    doc: WorkbenchFeeds,
    private apiBase: string = "",
    private clock: () => Date = () => new Date(),
    private channel: WbChannel | null = null,
  ) {
    this.doc = doc;

    const homeBySlug = new Map(doc.home.projects.map((r) => [r.slug, r]));
    this.projectList = doc.projects.projects.map((p) => {
      const home = homeBySlug.get(p.slug);
      const manifest = p.manifest
        ? {
            registry: p.manifest.registry ?? "",
            plans: p.manifest.plans ?? "",
            mockups: p.manifest.mockups ?? "",
            archive: p.manifest.archive ?? "",
            catalogOrigin: p.manifest.catalog?.origin ?? "",
            catalogGenerality: p.manifest.catalog?.generality ?? "",
            catalogUseCase: p.manifest.catalog?.use_case ?? "",
          }
        : null;
      const health: Project["health"] = home?.degraded
        ? "degraded"
        : !p.manifest
          ? "manifest-only"
          : "ok";
      return {
        slug: p.slug,
        name: p.name,
        manifest,
        health,
        healthNote: home?.degraded
          ? home.reasons.join("; ")
          : !p.manifest
            ? "No manifest found in the sweep"
            : home && !home.todos.available
              ? "Manifest only — declared stores not found"
              : "All stores swept",
        lastActivityLabel: dateLabel(home?.last_activity),
      };
    });

    this.todoList = [];
    this.entryList = [];
    this.planList = [];
    for (const summary of doc.projects.projects) {
      const feed = doc.projectFeeds[summary.slug];
      if (!feed) continue;
      const todos = feed.todos.todos.map((row) =>
        projectTodo(row, summary.slug),
      );
      this.todoList.push(...todos);
      const rows = [...feed.entries.entries, ...feed.entriesArchived.entries];
      for (const row of rows) {
        const detailRaw = feed.entryDetails[row.id];
        const detail =
          detailRaw && !("error" in detailRaw) ? (detailRaw as FeedEntryDetail) : undefined;
        const mainFile = detail?.files?.find((f) => f.is_main);
        if (mainFile) this.pagePaths.set(row.id, mainFile.path);
        this.entryList.push(projectEntry(row, detail, summary.slug));
      }
      for (const bundle of feed.plans.bundles) {
        const docRaw = bundle.plan ? feed.planDocs[bundle.plan.path] : undefined;
        const planDoc = docRaw && !("error" in docRaw) ? (docRaw as FeedPlanDoc) : undefined;
        const plan = projectPlan(bundle, planDoc, feed.todos.todos, summary.slug);
        if (plan) this.planList.push(plan);
        if (bundle.plan && planDoc?.file_sha256) {
          this.planWrite.set(bundle.id, {
            path: bundle.plan.path,
            sha256: planDoc.file_sha256,
          });
        }
      }
    }

    this.messageList = doc.messages.messages
      .filter((m) => m.state !== "draft")
      .map((m) => projectMessage(m, undefined));

    // Message threads (W10): every served row is a thread —
    // drafts included (the Inbox feed above hides them).
    this.threadList = doc.messages.messages.map((m) => ({
      id: String(m.id),
      project: m.project_slug ?? "",
      title: m.body.split("\n")[0].slice(0, 90),
      state: m.state,
      anchorText: m.anchor_context?.quote,
      messages: [
        {
          id: String(m.id),
          author: m.author,
          body: m.body,
          when: dateLabel(m.created_at),
        },
      ],
    }));

    // Anchored annotations (W5): rows carrying an
    // anchor_ref group into threads on their plan; the
    // anchor status rides the served anchor_context when
    // it names one, else derives from the plan text.
    const byRef = new Map<string, typeof doc.messages.messages>();
    for (const m of doc.messages.messages) {
      if (!m.anchor_ref) continue;
      const rows = byRef.get(m.anchor_ref) ?? [];
      rows.push(m);
      byRef.set(m.anchor_ref, rows);
    }
    for (const [ref, rows] of byRef) {
      const first = rows[0];
      const bundle = ref.split("/")[0];
      const plan = this.planList.find((p) => p.bundle === bundle);
      const quote =
        first.anchor_context?.quote ?? first.body.split("\n")[0].slice(0, 90);
      const served = first.anchor_context?.status ?? "";
      const status: AnnotationThread["status"] = /lost|orphan/i.test(served)
        ? "orphaned"
        : /mov|reloc/i.test(served)
          ? "relocated"
          : plan
            ? anchorStatus(plan.raw, quote, undefined)
            : "anchored";
      this.annotationList.push({
        id: `ann-${first.id}`,
        bundle,
        project: first.project_slug ?? plan?.project ?? "",
        anchorQuote: quote,
        status,
        resolved: rows.every((r) => r.state === "done" || r.state === "archived"),
        messages: rows.map((r) => ({
          id: String(r.id),
          author: r.author,
          body: r.body,
          when: dateLabel(r.created_at),
        })),
      });
    }
    this.goalList = (doc.goals ?? []).map((g) => ({ ...g }));
    this.boards = new Map(
      Object.entries(doc.projectFeeds).map(([slug, feed]) => [
        slug,
        structuredClone(feed.board),
      ]),
    );
    this.servedDerivations = new Map();
    for (const [slug, feed] of Object.entries(doc.projectFeeds)) {
      for (const block of feed.classification.progress.armed) {
        this.servedDerivations.set(`${slug}:${block.id}`, {
          todoId: block.id,
          cadenceMinutes: (block.interval_seconds ?? 0) / 60,
          lastActivity: block.last_activity ?? block.armed_at ?? "",
          missedChecks: block.missed_checks ?? 0,
          verdict: block.stalled ? "stalled" : "on-track",
        });
      }
    }
    this.sourceClass = new Map();
    for (const row of doc.armedRows) {
      this.sourceClass.set(row.project, row.source.source_class);
    }

    this.repoList = doc.projectsIndex.projects.map((row) =>
      this.projectRepo(row),
    );

    const cfg = doc.config.config;
    this.settingsState = {
      boardLaneWidth: 264,
      guardedSaves: cfg.file_editing_enabled === true,
      serverLabel: `${cfg.host ?? "127.0.0.1"}:${cfg.port ?? ""} · live`,
      projectsSwept: this.projectList.length,
      doctorLabel: `Message store · ${Object.values(doc.settings.messages.counts).reduce((a, b) => a + b, 0)} messages`,
    };
  }

  private projectRepo(
    row: WorkbenchFeeds["projectsIndex"]["projects"][number],
  ): Repo {
    // The index row IS the repo record now (SPEC §21):
    // its code summary carries the census derivations.
    // Code detail (files, peeks, datasets, history) is
    // no longer in the document — it serves on demand
    // through the Code routes, which this synchronous
    // seam cannot ride — so the live projection carries
    // the summary honestly: no files, no history, and
    // null dirty counts stay the backend's honest
    // absence (no dirty claim is fabricated from them;
    // the sweep chip carries "Degraded").
    const summary = row.code;
    const dirty = summary?.dirty_counts ?? null;
    const modifiedCount = dirty
      ? dirty.staged + dirty.unstaged + dirty.untracked
      : 0;
    return {
      slug: row.id,
      name: row.name,
      path: row.root ?? "",
      sweep: summary?.error ? "degraded" : "swept",
      branch: summary?.branch ?? "",
      syncLabel: !dirty
        ? "Status unavailable"
        : summary?.exposure?.level === "local_only"
          ? "Local only"
          : modifiedCount > 0
            ? `${modifiedCount} modified`
            : "Synced",
      modifiedCount,
      worktrees: row.checkouts
        .filter((c) => c.is_worktree)
        .map((w) => ({
          label: w.branch ?? w.root,
          path: w.root,
          branch: w.branch ?? "",
          dirty: null,
        })),
      history: [],
      files: [],
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
    return this.projectList;
  }

  projectRollups(): ProjectRollup[] {
    return this.projectList.slice(0, 5).map((p) => {
      const home = this.doc.home.projects.find((r) => r.slug === p.slug);
      const board = this.boards.get(p.slug);
      const needsChanges = (board?.review_queue ?? []).filter((item) =>
        item.reasons.some((r) => r.startsWith("needs-changes")),
      ).length;
      const triage = home?.review.triage_count ?? 0;
      if (p.health === "degraded") {
        return { project: p, dot: "warn" as const, sub: p.healthNote, chip: { type: "plain" as const, text: "Degraded" } };
      }
      if (p.health === "manifest-only") {
        return { project: p, dot: "muted" as const, sub: p.healthNote, chip: { type: "plain" as const, text: "Manifest only" } };
      }
      if (needsChanges > 0) {
        return {
          project: p,
          dot: "ok" as const,
          sub: `${needsChanges} mockup awaiting review`,
          chip: { type: "badge" as const, kind: "needs-changes" as const, text: `Needs changes · ${needsChanges}` },
        };
      }
      if (triage > 0) {
        return {
          project: p,
          dot: "ok" as const,
          sub: `${triage} in triage · board updated ${p.lastActivityLabel}`,
          chip: { type: "plain" as const, text: `${triage} in triage` },
        };
      }
      if ((home?.todos.counts.doing ?? 0) > 0) {
        return {
          project: p,
          dot: "ok" as const,
          sub: `${home!.todos.counts.doing} todo${home!.todos.counts.doing > 1 ? "s" : ""} in progress`,
          chip: { type: "ruled" as const, status: "implemented" as const },
        };
      }
      return { project: p, dot: "muted" as const, sub: "Quiet", chip: { type: "plain" as const, text: "Quiet" } };
    });
  }

  homeSummary() {
    let awaitingReview = 0;
    for (const board of this.boards.values()) awaitingReview += board.review_queue.length;
    let doingNow = 0;
    for (const row of this.doc.home.projects) doingNow += row.todos.counts.doing ?? 0;
    return {
      sweptCount: this.projectList.length,
      serverHealthy: true,
      editingOn: this.settingsState.guardedSaves,
      awaitingReview,
      doingNow,
    };
  }

  entries(project: string) {
    return this.entryList.filter((e) => e.project === project && !e.archived);
  }

  entry(id: string) {
    return this.entryList.find((e) => e.id === id);
  }

  plans(project: string) {
    return this.planList.filter((p) => p.project === project);
  }

  plan(bundle: string) {
    return this.planList.find((p) => p.bundle === bundle);
  }

  todos(project: string) {
    return this.todoList.filter((t) => t.project === project);
  }

  todo(id: string) {
    return this.todoList.find((t) => t.id === id);
  }

  classification(project: string): ClassificationRow[] {
    return this.todoList
      .filter((t) => t.project === project)
      .map((t) => {
        const plan = this.plan(t.bundle);
        const armed = isArmed(t, plan?.archived ?? false);
        let derivation: ProgressDerivation | null = null;
        if (armed) {
          derivation = this.mutatedTodos.has(t.id)
            ? deriveProgress(t, this.clock())
            : (this.servedDerivations.get(`${project}:${t.id}`) ??
              deriveProgress(t, this.clock()));
        }
        return { todo: t, optOut: isOptOut(t), armed, derivation };
      });
  }

  armedRows(): ArmedRow[] {
    return this.todoList
      .filter((t) => isArmed(t, this.plan(t.bundle)?.archived ?? false))
      .map((t) => {
        const row = renderArmedRow(t);
        const cls = this.sourceClass.get(t.project);
        if (cls && cls !== row.source.source_class) {
          return { ...row, source: { ...row.source, source_class: cls } };
        }
        return row;
      })
      .sort((a, b) => (a.armed_at ?? "").localeCompare(b.armed_at ?? ""));
  }

  board(): BoardCard[] {
    const cards: BoardCard[] = [];
    for (const summary of this.doc.projects.projects) {
      const board = this.boards.get(summary.slug);
      if (!board) continue;
      const tag = summary.slug.toUpperCase();
      for (const item of board.review_queue) {
        const needs = item.reasons.some((r) => r.startsWith("needs-changes"));
        cards.push({
          id: `card-entry-${item.id}`,
          lane: "review",
          projectTag: tag,
          title: item.title,
          meta: "",
          badge: { kind: "review", text: needs ? "needs-changes" : "in-triage" },
          target: { kind: "entry", id: item.id },
        });
      }
      for (const lane of ["todo", "doing", "done"] as const) {
        for (const card of board.plans[lane] ?? []) {
          cards.push({
            id: `card-plan-${card.bundle}`,
            lane,
            projectTag: tag,
            title: card.title,
            meta: `Plan · ${card.step_count ?? 0} steps`,
            target: { kind: "plan", bundle: card.bundle! },
          });
        }
      }
      for (const lane of ["todo", "doing", "blocked", "done"] as const) {
        for (const card of board.todos[lane] ?? []) {
          const plan = card.bundle ? this.plan(card.bundle) : undefined;
          cards.push({
            id: `card-todo-${card.id}`,
            lane: lane === "blocked" ? "doing" : lane,
            projectTag: tag,
            title: card.title,
            meta: `Todo · ${plan?.title ?? card.bundle ?? ""}`,
            target: { kind: "todo", id: card.id! },
          });
        }
      }
    }
    return cards;
  }

  messages() {
    return this.messageList;
  }

  repos() {
    return this.repoList;
  }

  repo(slug: string) {
    return this.repoList.find((r) => r.slug === slug);
  }

  goals(project: string) {
    return this.goalList.filter((g) => g.project === project);
  }

  allGoals() {
    return this.goalList;
  }

  goal(slug: string) {
    return this.goalList.find((g) => g.slug === slug);
  }

  goalBundle(goal: GoalRecord): Plan | undefined {
    const named = goal.lastPost?.refs?.plan;
    if (named) {
      const plan = this.plan(named);
      if (plan) return plan;
    }
    const inProgress = this.planList.filter(
      (p) => p.project === goal.project && p.state === "in-progress" && !p.archived,
    );
    return inProgress.length === 1 ? inProgress[0] : undefined;
  }

  goalTodos(goal: GoalRecord): FileTodo[] {
    const bundle = this.goalBundle(goal);
    if (!bundle) return [];
    const byId = new Map(
      this.todoList
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
    return this.doc.statusVocabulary;
  }

  settings() {
    return this.settingsState;
  }

  counts() {
    const terminal = new Set(
      this.doc.statusVocabulary.filter((r) => r.terminal).map((r) => r.code),
    );
    let triage = 0;
    for (const board of this.boards.values()) triage += board.review_queue.length;
    return {
      mockupsInTriage: triage,
      boardDoing: this.board().filter((c) => c.lane === "doing").length,
      inboxAwaiting: this.messageList.filter((m) => m.disposition === null).length,
      goalsActive: this.goalList.filter(
        (g) => !g.lastPost || !terminal.has(g.lastPost.status_code),
      ).length,
    };
  }

  // -- served documents ----------------------------------------

  /** The entry's page over the byte route (SPEC §7): the
   *  main file's exact bytes, fetched from /raw — the same
   *  construction the viewer's getEntryPage action used.
   *  The route answers refusals as plain text; the reason
   *  rides the result, never a partial page. */
  async entryPage(id: string): Promise<EntryPageResult> {
    const e = this.entry(id);
    if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
    const main = this.pagePaths.get(id);
    if (!main) {
      return {
        ok: false,
        reason:
          "Page unavailable — this entry is held by reference; its files live outside the harness.",
      };
    }
    if (this.channel) return this.entryPageViaChannel(e, id);
    const enc = encodeURIComponent;
    const url =
      `/raw/${enc(e.project)}/entries/${enc(id)}/` +
      main.split("/").map(enc).join("/");
    let res: Response;
    try {
      res = await fetch(this.url(url));
    } catch {
      return {
        ok: false,
        reason:
          "The page could not be fetched — the byte route did not answer. Nothing was rendered.",
      };
    }
    const body = await res.text();
    if (!res.ok) {
      return {
        ok: false,
        reason: body.trim() || `The byte route refused this page (status ${res.status}).`,
      };
    }
    return {
      ok: true,
      body,
      contentType: res.headers.get("content-type") ?? "text/html; charset=utf-8",
    };
  }

  /** entryPage over the relay channel (the frame form):
   *  the getEntryPage action reads the detail over wbApi
   *  and the main file's exact bytes over wbRaw server-
   *  side, and hands them back base64-encoded in the
   *  envelope — the client decodes and renders, exactly
   *  as with the byte route's bytes. A refusal rides the
   *  envelope's error text; a status-0 envelope is the
   *  bridge's unreachable diagnosis. */
  private async entryPageViaChannel(
    e: Entry,
    id: string,
  ): Promise<EntryPageResult> {
    const channel = this.channel as WbChannel;
    let env;
    try {
      env = await channel("getEntryPage", {
        slug: e.project,
        entryId: id,
      });
    } catch {
      return {
        ok: false,
        reason:
          "The page could not be fetched — the byte route did not answer. Nothing was rendered.",
      };
    }
    const payload = env.payload as {
      contentType?: string | null;
      bodyBase64?: string;
      bytes?: number;
    } | null;
    if (env.status !== 200 || !payload?.bodyBase64) {
      return {
        ok: false,
        reason:
          env.error ||
          `The byte route refused this page (status ${env.status}).`,
      };
    }
    const binary = atob(payload.bodyBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return {
      ok: true,
      body: new TextDecoder().decode(bytes),
      contentType: payload.contentType ?? "text/html; charset=utf-8",
    };
  }

  /** The entry's document as served segments (the
   *  segment feed): blocks of text runs plus math nodes,
   *  segmented by the pipeline — the client renders the
   *  served shape and never parses the document itself.
   *  Refusals (held by reference, main file a rendered
   *  page) ride the result with the route's own reason;
   *  the stage falls back to the byte route on a refusal. */
  async entrySegments(id: string): Promise<EntrySegmentsResult> {
    const e = this.entry(id);
    if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
    if (this.channel) {
      let env;
      try {
        env = await this.channel("getEntrySegments", {
          slug: e.project,
          entryId: id,
        });
      } catch {
        return {
          ok: false,
          reason:
            "The document could not be fetched — the segment feed did not answer. Nothing was rendered.",
        };
      }
      if (env.status !== 200) {
        const payload = env.payload as { error?: string } | null;
        return {
          ok: false,
          reason:
            env.error ||
            payload?.error ||
            `The segment feed refused this document (status ${env.status}).`,
        };
      }
      const payload = env.payload as FeedEntrySegments;
      return { ok: true, mainFile: payload.main_file, blocks: payload.blocks };
    }
    const enc = encodeURIComponent;
    const url = `/api/projects/${enc(e.project)}/entries/${enc(id)}/segments`;
    let res: Response;
    try {
      res = await fetch(this.url(url));
    } catch {
      return {
        ok: false,
        reason:
          "The document could not be fetched — the segment feed did not answer. Nothing was rendered.",
      };
    }
    if (!res.ok) {
      let reason = "";
      try {
        const payload = (await res.json()) as { error?: string };
        reason = payload.error ?? "";
      } catch {
        reason = "";
      }
      return {
        ok: false,
        reason: reason || `The segment feed refused this document (status ${res.status}).`,
      };
    }
    const payload = (await res.json()) as FeedEntrySegments;
    return { ok: true, mainFile: payload.main_file, blocks: payload.blocks };
  }

  // -- mutations -------------------------------------------------

  private moveTodoCard(id: string, to: FileTodo["status"]) {
    const todo = this.todo(id);
    if (!todo) return;
    const board = this.boards.get(todo.project);
    if (!board) return;
    const lanes = board.todos as Record<string, FeedBoardCard[]>;
    for (const lane of Object.values(lanes)) {
      const idx = lane.findIndex((c) => c.id === id);
      if (idx >= 0) lane.splice(idx, 1);
    }
    const target = lanes[to];
    if (target && !target.some((c) => c.id === id)) {
      target.push({
        id,
        title: todo.title,
        bundle: todo.bundle,
        project: todo.project,
        project_name: todo.project,
      });
    }
  }

  async setEntryReview(id: string, review: "approved" | "needs-changes" | "stale", note?: string): Promise<Entry> {
    const e = this.entryList.find((x) => x.id === id);
    if (!e) throw new Error(`unknown entry ${id}`);
    await this.entryAction(e, {
      verb: "review",
      disposition: review === "approved" ? "approve" : review,
      comment: note,
    });
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
    // The board's review queue is served state: a verdict
    // moves the entry out of it (needs-changes keeps it,
    // with the reason updated).
    const board = this.boards.get(e.project);
    if (board) {
      const idx = board.review_queue.findIndex((item) => item.id === id);
      if (review === "needs-changes") {
        if (idx < 0) {
          board.review_queue.push({
            id: e.id,
            kind: e.kind,
            title: e.title,
            project: e.project,
            project_name: e.project,
            reasons: ["needs-changes — unaddressed"],
          });
        }
      } else if (idx >= 0) {
        board.review_queue.splice(idx, 1);
      }
    }
    this.emit();
    return e;
  }

  async writeTodo(
    id: string,
    patch: Partial<Pick<FileTodo, "title" | "status" | "progressCheck" | "notes">>,
  ): Promise<{ todo: FileTodo; armed: boolean }> {
    const t = this.todoList.find((x) => x.id === id);
    if (!t) throw new Error(`unknown todo ${id}`);
    if (patch.title !== undefined && patch.title.trim().length === 0) {
      throw new Error("title must not be empty");
    }
    // Server first (the one mutation path): title/notes
    // ride set-fields; a status or cadence change rides
    // set-status, whose writer arms/retires the progress
    // schedule in the same write. Local state below moves
    // only on the server's acceptance.
    const todosPath = `/api/projects/${encodeURIComponent(t.project)}/todos`;
    if (patch.title !== undefined || patch.notes !== undefined) {
      await this.postJson(todosPath, {
        verb: "set-fields",
        id,
        title: patch.title,
        notes: patch.notes,
      });
    }
    if (patch.status !== undefined || patch.progressCheck !== undefined) {
      const body: Record<string, unknown> = {
        verb: "set-status",
        id,
        status: patch.status ?? t.status,
      };
      if (patch.progressCheck !== undefined) {
        if (patch.progressCheck === "off") body.no_progress = true;
        else if (patch.progressCheck) body.progress = patch.progressCheck;
      }
      await this.postJson(todosPath, body);
    }
    if (patch.title !== undefined) {
      if (patch.title.trim().length === 0) throw new Error("title must not be empty");
      t.title = patch.title.trim();
    }
    if (patch.notes !== undefined) t.notes = patch.notes;
    if (patch.progressCheck !== undefined) t.progressCheck = patch.progressCheck;
    if (patch.status !== undefined && patch.status !== t.status) {
      t.status = patch.status;
      if (patch.status === "doing") {
        if (cadenceMinutes(t.progressCheck) !== null) {
          t.progressArmed = this.clock().toISOString();
        }
      } else {
        t.progressArmed = undefined;
      }
      this.moveTodoCard(id, patch.status);
    }
    if (patch.progressCheck !== undefined && t.status === "doing") {
      if (cadenceMinutes(t.progressCheck) === null) t.progressArmed = undefined;
      else if (!t.progressArmed) t.progressArmed = this.clock().toISOString();
    }
    t.updated = this.clock().toISOString().slice(0, 10);
    this.mutatedTodos.add(id);
    this.emit();
    return { todo: t, armed: isArmed(t, this.plan(t.bundle)?.archived ?? false) };
  }

  async addTodo(project: string, bundle: string, title: string): Promise<FileTodo> {
    // The server's writer assigns the id (project-wide
    // slug rule); the local projection adopts it verbatim.
    const created = await this.postJson<{ todo: { id: string } }>(
      `/api/projects/${encodeURIComponent(project)}/todos`,
      { verb: "create", bundle, title },
    );
    const t: FileTodo = {
      id: created.todo.id,
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
    this.todoList.push(t);
    const board = this.boards.get(project);
    if (board) {
      board.todos.todo.push({
        id: t.id,
        title,
        bundle,
        project,
        project_name: project,
      });
    }
    this.emit();
    return t;
  }

  async addCheckpoint(id: string, text: string): Promise<FileTodo> {
    const t = this.todoList.find((x) => x.id === id);
    if (!t) throw new Error(`unknown todo ${id}`);
    // A checkpoint is a note in the record's own format,
    // appended by the status writer at the todo's current
    // status (the conforming progress-checkpoint line).
    const at = this.clock().toISOString();
    await this.postJson(
      `/api/projects/${encodeURIComponent(t.project)}/todos`,
      {
        verb: "set-status",
        id,
        status: t.status,
        note: `progress-checkpoint: ${at} — ${text}`,
      },
    );
    t.checkpoints = [...t.checkpoints, { at, text }];
    t.updated = this.clock().toISOString().slice(0, 10);
    this.mutatedTodos.add(id);
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
      const state = lane === "done" ? "done" : lane === "doing" ? "in-progress" : lane === "todo" ? "draft" : null;
      if (!state) return;
      p.state = state;
      const board = this.boards.get(p.project);
      if (board) {
        for (const l of ["todo", "doing", "done"] as const) {
          const idx = board.plans[l].findIndex((c) => c.bundle === p.bundle);
          if (idx >= 0) {
            const [moved] = board.plans[l].splice(idx, 1);
            board.plans[lane === "done" ? "done" : lane === "doing" ? "doing" : "todo"].push(moved);
            break;
          }
        }
      }
      this.emit();
      return;
    }
    if (card.target.kind === "entry" && lane === "done") {
      await this.setEntryReview(card.target.id, "approved");
    }
    // Review cards dropped elsewhere stay in the review
    // queue: a disposition is a verdict, not a drag.
  }

  async dismissMessage(id: string): Promise<void> {
    const m = this.messageList.find((x) => x.id === id);
    if (!m) return;
    // Dismissal is the store's done verb; the local
    // disposition moves only on its acceptance.
    await this.postJson(`/api/messages/${encodeURIComponent(id)}/done`, {});
    m.disposition = "dismissed";
    this.dispositions.set(id, "dismissed");
    this.emit();
  }

  openMessage(id: string) {
    const m = this.messageList.find((x) => x.id === id);
    if (!m) throw new Error(`unknown message ${id}`);
    if (m.disposition === null) {
      m.disposition = "opened";
      this.dispositions.set(id, "opened");
    }
    this.emit();
    return m;
  }

  async guardedSave(repoSlug: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
    if (!this.settingsState.guardedSaves) {
      return { ok: false, reason: "Guarded file saves are off — enable them in Settings → Workbench." };
    }
    const repo = this.repo(repoSlug);
    const find = (files: RepoFile[], parts: string[]): RepoFile | undefined => {
      const [head, ...rest] = parts;
      const node = files.find((f) => f.name === head);
      if (!node) return undefined;
      return rest.length === 0 ? node : find(node.children ?? [], rest);
    };
    const file = repo ? find(repo.files, path.split("/")) : undefined;
    if (!repo || !file) return { ok: false, reason: `No such file: ${path}` };
    if (file.editable !== "guarded") {
      return { ok: false, reason: file.editableNote ?? "This file is not editable in the viewer." };
    }
    // The guarded save itself: the server's writer holds
    // the compare-and-swap (base_sha256 against the file's
    // real sha256 — the sha the peek served, never a
    // locally computed one) and returns the saved sha256.
    // In the frame form the saveRepoFile action carries
    // the same write over the relay; the envelope adapts
    // to the same status/payload pair below.
    let status: number;
    let payload: {
      sha256?: string;
      error?: string;
      current_sha256?: string;
    } | null;
    let envError: string | null = null;
    if (this.channel) {
      let env;
      try {
        env = await this.channel("saveRepoFile", {
          repoId: repoSlug,
          path,
          content,
          baseSha256: baseSha,
        });
      } catch (err) {
        return {
          ok: false,
          reason: `The save could not reach the workbench server — the file was not touched. (${err instanceof Error ? err.message : String(err)})`,
        };
      }
      status = env.status;
      payload = env.payload as typeof payload;
      envError = env.error;
    } else {
      let res: Response;
      try {
        res = await fetch(this.url(`/api/projects/code/${repoSlug}/file`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path, content, base_sha256: baseSha }),
        });
      } catch (err) {
        return {
          ok: false,
          reason: `The save could not reach the workbench server — the file was not touched. (${err instanceof Error ? err.message : String(err)})`,
        };
      }
      status = res.status;
      payload = (await res.json().catch(() => null)) as typeof payload;
    }
    if (status < 200 || status >= 300) {
      if (payload?.current_sha256) {
        return {
          ok: false,
          reason: `Save refused — stale sha: the file is at ${payload.current_sha256}, you opened ${baseSha}. The saved file was not touched.`,
        };
      }
      return { ok: false, reason: payload?.error ?? envError ?? `Save refused (${status}). The file was not touched.` };
    }
    file.content = content;
    file.headContent = content;
    file.sha = payload?.sha256 ?? file.sha;
    file.lines = content.split("\n").length;
    file.sizeLabel = `${content.length.toLocaleString()} bytes · ${file.lines} lines`;
    repo.modifiedCount = Math.max(0, repo.modifiedCount - 1);
    this.emit();
    return { ok: true, sha: file.sha ?? "", savedLabel: "Just now" };
  }

  /** Open one of the repo's files on demand: files whose
   *  peek the document deferred carry no content, so the
   *  open rides GET …/file (the repo peek route) and the
   *  served sha256 becomes the file's sha — the guarded
   *  save's CAS base. A file the document already serves
   *  content for answers from the snapshot. */
  async repoFileContent(repoSlug: string, path: string): Promise<EntryFileResult> {
    const repo = this.repo(repoSlug);
    const file = repo ? findFileInTree(repo.files, path) : undefined;
    if (!repo || !file) return { ok: false, reason: `No such file: ${path}` };
    if (file.content !== undefined && file.sha) {
      return { ok: true, body: file.content, sha: file.sha };
    }
    // The peek: over HTTP, GET …/file; in the frame form,
    // the getRepoFile action over the relay. Both adapt
    // to the same status/peek pair below.
    let status: number;
    let statusText = "";
    let peek: {
      content?: string | null;
      sha256?: string | null;
      editable?: boolean;
      editable_reason?: string | null;
      line_count?: number;
      size_bytes?: number;
    };
    if (this.channel) {
      let env;
      try {
        env = await this.channel("getRepoFile", {
          repoId: repoSlug,
          path,
        });
      } catch (err) {
        return {
          ok: false,
          reason: `The file could not be fetched — the file route did not answer. (${err instanceof Error ? err.message : String(err)})`,
        };
      }
      status = env.status;
      statusText = env.error ?? "";
      peek = (env.payload ?? {}) as typeof peek;
    } else {
      let res: Response;
      try {
        res = await fetch(
          this.url(`/api/projects/code/${repoSlug}/file?path=${encodeURIComponent(path)}`),
        );
      } catch (err) {
        return {
          ok: false,
          reason: `The file could not be fetched — the file route did not answer. (${err instanceof Error ? err.message : String(err)})`,
        };
      }
      status = res.status;
      statusText = res.statusText;
      if (status >= 200 && status < 300) {
        peek = (await res.json()) as typeof peek;
      } else {
        peek = {};
      }
    }
    if (status < 200 || status >= 300) {
      return { ok: false, reason: `File read failed: ${status} ${statusText}` };
    }
    if (peek.content == null || !peek.sha256) {
      return {
        ok: false,
        reason: peek.editable_reason ?? "The server does not serve this file's content.",
      };
    }
    file.content = peek.content;
    file.sha = peek.sha256;
    if (peek.line_count != null) file.lines = peek.line_count;
    if (peek.size_bytes != null) {
      file.sizeLabel = `${peek.size_bytes.toLocaleString()} bytes · ${peek.line_count ?? file.lines ?? 0} lines`;
    }
    file.editable = peek.editable ? "guarded" : "no";
    this.emit();
    return { ok: true, body: peek.content, sha: peek.sha256 };
  }

  async setGoalPing(slug: string, armed: boolean): Promise<GoalRecord> {
    // Server first (POST /api/goals/{slug}/ping): the
    // store's writer owns the rule this adapter used to
    // project locally — a closed goal's retired ping
    // refuses re-arm there — and the response carries the
    // record in its served form, which is adopted whole.
    const res = await this.postJson<{ goal: GoalRecord }>(
      `/api/goals/${encodeURIComponent(slug)}/ping`,
      { armed },
    );
    const i = this.goalList.findIndex((x) => x.slug === slug);
    if (i >= 0) this.goalList[i] = res.goal;
    this.emit();
    return res.goal;
  }

  async postGoalStatus(slug: string, post: Omit<StatusPost, "postedAt">): Promise<GoalRecord> {
    // Server first (POST /api/goals/{slug}/status): the
    // writer rules live at the store — contract 06's
    // closed code set, the blocked post's basis citation,
    // the verification stamp, posted_at, and the terminal
    // post's ping retirement + owner-waiting clear all
    // land there; the served record is adopted whole.
    const res = await this.postJson<{ goal: GoalRecord }>(
      `/api/goals/${encodeURIComponent(slug)}/status`,
      { post },
    );
    const i = this.goalList.findIndex((x) => x.slug === slug);
    if (i >= 0) this.goalList[i] = res.goal;
    this.emit();
    return res.goal;
  }

  updateSettings(patch: Partial<AppSettings>): AppSettings {
    // W-C5 disposition (ruled local-only, 2026-11-15):
    // the writable fields are a
    // client preference (boardLaneWidth) and a local
    // override of a config-served default (guardedSaves
    // seeds from the server's file_editing_enabled at
    // load). The server's settings surface is the
    // read-only effective-config payload (spec §3); no
    // preferences store exists to write to, and inventing
    // one is a ruling, not a cure. Flagged in the W-C5
    // hand-back.
    this.settingsState = { ...this.settingsState, ...patch };
    this.emit();
    return this.settingsState;
  }

  // -- entry lifecycle (W4) ----------------------------------
  // The mock adapter's writer semantics over the projected
  // entries, with persistence through the pipeline's
  // writers (POST …/entries/{id}/action, …/file): every
  // method below lands its write on the server first and
  // mirrors it into the snapshot only on acceptance (D-4).

  private entryOrThrow(id: string): Entry {
    const e = this.entryList.find((x) => x.id === id);
    if (!e) throw new Error(`unknown entry ${id}`);
    return e;
  }

  private logEntry(e: Entry, label: string) {
    e.reviewLog = [{ label, when: "Just now", actor: "owner" }, ...e.reviewLog];
  }

  async setEntryStatus(id: string, status: RuledStatus): Promise<Entry> {
    const e = this.entryOrThrow(id);
    await this.entryAction(e, { verb: "set-status", status });
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
    }
    // Title is a registry field (the set verb); viewport
    // and mode are not registry columns — they live in
    // the entry's state document, so they ride set-state
    // merged into the state the detail route serves.
    if (patch.title !== undefined) {
      await this.entryAction(e, {
        verb: "set",
        fields: { title: patch.title.trim() },
      });
    }
    if (patch.viewport !== undefined || patch.mode !== undefined) {
      // The detail read: over HTTP, GET …/entries/{id};
      // in the frame form, the getEntry action over the
      // relay. Both adapt to the same status/detail pair.
      let detail: {
        entry?: { state_json?: Record<string, unknown> | null };
      };
      if (this.channel) {
        const env = await this.channel("getEntry", {
          slug: e.project,
          entryId: e.id,
        });
        if (env.status < 200 || env.status >= 300) {
          throw new Error(
            env.error ??
              `The entry's current state could not be read (${env.status}) — the metadata was not saved.`,
          );
        }
        detail = (env.payload ?? {}) as typeof detail;
      } else {
        const res = await fetch(
          this.url(
            `/api/projects/${encodeURIComponent(e.project)}/entries/${encodeURIComponent(e.id)}`,
          ),
        );
        if (!res.ok) {
          throw new Error(
            `The entry's current state could not be read (${res.status}) — the metadata was not saved.`,
          );
        }
        detail = (await res.json()) as typeof detail;
      }
      const state: Record<string, unknown> = { ...(detail.entry?.state_json ?? {}) };
      if (patch.viewport !== undefined) state.viewport = patch.viewport;
      if (patch.mode !== undefined) state.mode = patch.mode;
      await this.entryAction(e, { verb: "set-state", state });
    }
    if (patch.title !== undefined) {
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
    // The server's verify recomputes the entry's state;
    // the detail it answers with carries the real state
    // sha256 — no locally computed hash.
    const detail = await this.entryAction<{
      entry?: { current_state_sha256?: string | null };
      current_state_sha256?: string | null;
    }>(e, { verb: "verify" });
    const served = detail.entry?.current_state_sha256 ?? detail.current_state_sha256;
    if (served) e.stateHash = served;
    this.logEntry(e, `Verified · state ${e.stateHash ?? "—"}`);
    this.emit();
    return e;
  }

  async archiveEntry(id: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    await this.entryAction(e, { verb: "archive" });
    e.archived = true;
    this.logEntry(e, "Archived");
    this.emit();
    return e;
  }

  async unarchiveEntry(id: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    await this.entryAction(e, { verb: "unarchive" });
    e.archived = false;
    this.logEntry(e, "Unarchived");
    this.emit();
    return e;
  }

  async supersedeEntry(id: string, byId: string): Promise<Entry> {
    const e = this.entryOrThrow(id);
    const by = this.entryOrThrow(byId);
    await this.entryAction(e, { verb: "supersede", new_id: byId });
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
    await this.entryAction(e, { verb: "set-state", state: parsed });
    e.stateJson = JSON.stringify(parsed, null, 2);
    this.logEntry(e, "State saved");
    this.emit();
    return e;
  }

  async entryFileContent(id: string, path: string): Promise<EntryFileResult> {
    const key = `${id}|${path}`;
    const cached = this.entryFileCache.get(key);
    const cachedSha = this.entryFileShas.get(key);
    if (cached !== undefined && cachedSha) {
      return { ok: true, body: cached, sha: cachedSha };
    }
    const e = this.entryList.find((x) => x.id === id);
    if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
    if (!(e.files ?? []).some((f) => f.path === path)) {
      return { ok: false, reason: `The entry serves no file at ${path}.` };
    }
    // The file route's peek: content plus the sha256 the
    // guarded save compares against — served, not computed.
    // In the frame form the getEntryFile action carries
    // the peek over the relay, adapted to the same shape.
    try {
      let peek: {
        content?: string | null;
        sha256?: string | null;
        editable_reason?: string | null;
      };
      if (this.channel) {
        const env = await this.channel("getEntryFile", {
          slug: e.project,
          entryId: id,
          path,
        });
        if (env.status < 200 || env.status >= 300) {
          return {
            ok: false,
            reason: `File read failed: ${env.status} ${env.error ?? ""}`.trim(),
          };
        }
        peek = (env.payload ?? {}) as typeof peek;
      } else {
        const url = `/api/projects/${encodeURIComponent(e.project)}/entries/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`;
        const res = await fetch(this.url(url));
        if (!res.ok) return { ok: false, reason: `File read failed: ${res.status} ${res.statusText}` };
        peek = (await res.json()) as typeof peek;
      }
      if (peek.content == null || !peek.sha256) {
        return {
          ok: false,
          reason: peek.editable_reason ?? "The server does not serve this file's content.",
        };
      }
      this.entryFileCache.set(key, peek.content);
      this.entryFileShas.set(key, peek.sha256);
      return { ok: true, body: peek.content, sha: peek.sha256 };
    } catch (err) {
      return { ok: false, reason: `File read failed: ${err instanceof Error ? err.message : String(err)}` };
    }
  }

  async saveEntryFile(id: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
    const key = `${id}|${path}`;
    if (!this.entryFileShas.has(key)) {
      return { ok: false, reason: "Open the file first — the guarded save needs the sha you opened." };
    }
    const e = this.entryOrThrow(id);
    // The server's writer holds the compare-and-swap and
    // answers with the saved sha256 (its stale-sha refusal
    // carries the current sha256, surfaced verbatim). In
    // the frame form the saveEntryFile action carries the
    // same write over the relay, adapted to the same
    // status/payload pair.
    let status: number;
    let payload: {
      sha256?: string;
      error?: string;
      current_sha256?: string;
    } | null;
    let envError: string | null = null;
    if (this.channel) {
      let env;
      try {
        env = await this.channel("saveEntryFile", {
          slug: e.project,
          entryId: id,
          path,
          content,
          baseSha256: baseSha,
        });
      } catch (err) {
        return {
          ok: false,
          reason: `The save could not reach the workbench server — the file was not touched. (${err instanceof Error ? err.message : String(err)})`,
        };
      }
      status = env.status;
      payload = env.payload as typeof payload;
      envError = env.error;
    } else {
      let res: Response;
      try {
        res = await fetch(
          this.url(
            `/api/projects/${encodeURIComponent(e.project)}/entries/${encodeURIComponent(id)}/file`,
          ),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path, content, base_sha256: baseSha }),
          },
        );
      } catch (err) {
        return {
          ok: false,
          reason: `The save could not reach the workbench server — the file was not touched. (${err instanceof Error ? err.message : String(err)})`,
        };
      }
      status = res.status;
      payload = (await res.json().catch(() => null)) as typeof payload;
    }
    if (status < 200 || status >= 300) {
      if (payload?.current_sha256) {
        return {
          ok: false,
          reason: `Save refused — stale sha: the file is at ${payload.current_sha256}, you opened ${baseSha}. The saved file was not touched.`,
        };
      }
      return { ok: false, reason: payload?.error ?? envError ?? `Save refused (${status}). The file was not touched.` };
    }
    const sha = payload?.sha256 ?? baseSha;
    this.entryFileCache.set(key, content);
    this.entryFileShas.set(key, sha);
    this.logEntry(e, `File saved · ${path}`);
    this.emit();
    return { ok: true, sha, savedLabel: "Just now" };
  }

  // -- plan questions + annotations (W8, W5) -----------------

  planQuestions(bundle: string) {
    const p = this.planList.find((x) => x.bundle === bundle);
    if (!p) return [];
    return p.questions ?? parsePlanQuestions(p.raw);
  }

  async resolvePlanQuestions(bundle: string, answers: Record<string, string>): Promise<Plan> {
    const p = this.planList.find((x) => x.bundle === bundle);
    if (!p) throw new Error(`unknown plan ${bundle}`);
    // The resolve route writes the answers into the plan
    // file itself, guarded by the sha256 the document
    // served for it; a stale sha refuses server-side.
    const write = this.planWrite.get(bundle);
    if (!write) {
      throw new Error(
        "This plan's file coordinates were not served, so its questions cannot be resolved from here.",
      );
    }
    const result = await this.postJson<{ sha256: string }>(
      `/api/projects/${encodeURIComponent(p.project)}/plan/resolve`,
      { path: write.path, base_sha256: write.sha256, answers },
    );
    this.planWrite.set(bundle, { path: write.path, sha256: result.sha256 });
    const questions = p.questions ?? parsePlanQuestions(p.raw);
    for (const q of questions) {
      const answer = answers[q.id]?.trim();
      if (answer) {
        q.answer = answer;
        q.answeredBy = "owner";
        q.answeredLabel = "Just now";
      }
    }
    p.questions = questions;
    p.raw = applyAnswersToRaw(p.raw, answers);
    this.emit();
    return p;
  }

  annotationsForPlan(bundle: string): AnnotationThread[] {
    const plan = this.planList.find((p) => p.bundle === bundle);
    return this.annotationList
      .filter((t) => t.bundle === bundle)
      .map((t) => ({
        ...t,
        status:
          plan && !t.anchorContext
            ? anchorStatus(plan.raw, t.anchorQuote, undefined)
            : t.status,
      }));
  }

  async addAnnotation(bundle: string, quote: string, body: string): Promise<AnnotationThread> {
    const plan = this.planList.find((p) => p.bundle === bundle);
    if (!plan) throw new Error(`unknown plan ${bundle}`);
    // The annotation is a message (POST /api/messages)
    // anchored to the plan's served path with a §12
    // selection payload — quote + line context is the
    // anchor; the component is the plan document itself
    // (plans/plan-reader), since the composer selects a
    // quote, not a component, and no finer component is
    // honestly claimable from it. Born sent, like a reply:
    // the seam's single act is the finished annotation.
    const write = this.planWrite.get(bundle);
    if (!write) {
      throw new Error(
        "This plan's file coordinates were not served, so an annotation cannot be anchored to it from here.",
      );
    }
    const line = plan.raw.split("\n").find((l) => l.includes(quote));
    let prefix = "";
    let suffix = "";
    if (line) {
      const at = line.indexOf(quote);
      prefix = line.slice(Math.max(0, at - 120), at);
      suffix = line.slice(at + quote.length, at + quote.length + 120);
    }
    const res = await this.postJson<{
      message: { id: number; author: string; body: string; created_at: string };
    }>("/api/messages", {
      author: "owner",
      body,
      project_slug: plan.project,
      anchor_type: "text",
      anchor_ref: write.path,
      selection: {
        kind: "text",
        component_id: "plans/plan-reader",
        quote,
        prefix,
        suffix,
      },
      send: true,
    });
    const m = res.message;
    const thread: AnnotationThread = {
      id: `ann-${m.id}`,
      bundle,
      project: plan.project,
      anchorQuote: quote,
      anchorContext: line,
      status: line ? "anchored" : "orphaned",
      resolved: false,
      messages: [
        { id: String(m.id), author: m.author, body: m.body, when: dateLabel(m.created_at) },
      ],
    };
    this.annotationList.push(thread);
    this.emit();
    return thread;
  }

  async replyAnnotation(id: string, body: string): Promise<AnnotationThread> {
    const t = this.annotationList.find((x) => x.id === id);
    if (!t) throw new Error(`unknown annotation ${id}`);
    // A reply is a create with parent_id (POST
    // /api/messages, sent immediately per §7); replies
    // carry no selection — the thread root holds the
    // anchor. The thread id is `ann-<root message id>`,
    // the loader's own form.
    const res = await this.postJson<{
      message: { id: number; author: string; body: string; created_at: string };
    }>("/api/messages", {
      author: "owner",
      body,
      project_slug: t.project,
      parent_id: Number(id.replace(/^ann-/, "")),
      send: true,
    });
    const m = res.message;
    t.messages = [
      ...t.messages,
      { id: String(m.id), author: m.author, body: m.body, when: dateLabel(m.created_at) },
    ];
    this.emit();
    return t;
  }

  setAnnotationResolved(id: string, resolved: boolean): AnnotationThread {
    // W-C5 disposition (ruled derived-only in live
    // mode, 2026-11-15): a thread's resolved-ness is
    // DERIVED at load from its messages' lifecycle
    // states (every row done or archived), and the
    // lifecycle offers no verb for it — done is the
    // agent's explicit post-back (§7, acknowledged →
    // done), sent rows cannot reach done without the
    // pickup acknowledgement, and archiving a root
    // files the thread away rather than resolving it.
    // A local projection would be contradicted by the
    // next reload, so the live method refuses honestly
    // and the Plans UI renders the state read-only;
    // the mock keeps the working toggle against the
    // fake. (id/resolved are the seam's shape; the
    // refusal does not depend on them.)
    void id;
    void resolved;
    throw new Error(
      "Annotation resolved-ness is derived from the thread's message lifecycle states — the server has no verb to set it, so it cannot be toggled here.",
    );
  }

  // -- message threads (W10) ---------------------------------

  messageThreads(): MessageThread[] {
    return this.threadList;
  }

  async composeThread(input: {
    project: string;
    body: string;
    anchorText?: string;
    sendNow: boolean;
  }): Promise<MessageThread> {
    const body = input.body.trim();
    if (!body) throw new Error("A message needs a body.");
    // POST /api/messages — the store assigns the id; the
    // local thread adopts it, so the thread the UI opens
    // is the record the server holds.
    const anchor = input.anchorText?.trim();
    const created = await this.postJson<{
      message: { id: number | string; state: string };
    }>("/api/messages", {
      author: "owner",
      body,
      project_slug: input.project || undefined,
      anchor_type: anchor ? "text" : "none",
      selection: anchor ? { quote: anchor } : undefined,
      send: input.sendNow,
    });
    const thread: MessageThread = {
      id: String(created.message.id),
      project: input.project,
      title: body.split("\n")[0].slice(0, 90),
      state: input.sendNow ? "sent" : "draft",
      anchorText: input.anchorText?.trim() || undefined,
      messages: [
        { id: String(created.message.id), author: "owner", body, when: "Just now" },
      ],
    };
    this.threadList.push(thread);
    this.emit();
    return thread;
  }

  async replyThread(id: string, body: string): Promise<MessageThread> {
    const t = this.threadList.find((x) => x.id === id);
    if (!t) throw new Error(`unknown thread ${id}`);
    const created = await this.postJson<{
      message: { id: number | string };
    }>("/api/messages", {
      author: "owner",
      body,
      project_slug: t.project || undefined,
      parent_id: Number(id),
      send: t.state !== "draft",
    });
    t.messages = [
      ...t.messages,
      { id: String(created.message.id), author: "owner", body, when: "Just now" },
    ];
    if (t.state === "draft") t.state = "sent";
    this.emit();
    return t;
  }

  async editThreadMessage(threadId: string, messageId: string, body: string): Promise<MessageThread> {
    const t = this.threadList.find((x) => x.id === threadId);
    if (!t) throw new Error(`unknown thread ${threadId}`);
    const m = t.messages.find((x) => x.id === messageId);
    if (!m) throw new Error(`unknown message ${messageId}`);
    // The draft-body route: the store's one draft path
    // (it refuses non-draft messages, surfaced as-is).
    await this.postJson(`/api/messages/${encodeURIComponent(messageId)}/body`, { body });
    m.body = body;
    this.emit();
    return t;
  }

  async setThreadState(id: string, state: "sent" | "done" | "archived"): Promise<MessageThread> {
    const t = this.threadList.find((x) => x.id === id);
    if (!t) throw new Error(`unknown thread ${id}`);
    const verb = state === "sent" ? "send" : state === "done" ? "done" : "archive";
    await this.postJson(`/api/messages/${encodeURIComponent(id)}/${verb}`, {});
    t.state = state;
    this.emit();
    return t;
  }

  // -- datasets (W11) -----------------------------------------

  async datasetSql(repoSlug: string, path: string, sql: string): Promise<DatasetSqlResult> {
    // The engine route first (POST /api/projects/code/{slug}/
    // dataset/sql — the repos POST dispatch runs
    // run_dataset_sql server-side); a refused or
    // unreachable route falls back to the same engine
    // over the served snapshot, labelled as such. In the
    // frame form the postRepoDatasetSql action carries
    // the same call over the relay, with the same
    // fallback on refusal or unreachability.
    type SqlPayload = {
      columns?: string[];
      rows?: unknown[][];
      error?: string;
    };
    try {
      let payload: SqlPayload | null = null;
      if (this.channel) {
        const env = await this.channel("postRepoDatasetSql", {
          repoId: repoSlug,
          path,
          sql,
        });
        if (env.status >= 200 && env.status < 300) {
          payload = env.payload as SqlPayload;
        }
      } else {
        const res = await fetch(this.url(`/api/projects/code/${encodeURIComponent(repoSlug)}/dataset/sql`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path, sql }),
        });
        if (res.ok) {
          payload = (await res.json()) as SqlPayload;
        }
      }
      if (payload) {
        if (payload.error) return { ok: false, reason: payload.error };
        if (Array.isArray(payload.columns) && Array.isArray(payload.rows)) {
          return {
            ok: true,
            table: {
              name: "sql",
              columns: payload.columns,
              rows: payload.rows.map((r) => r.map((c) => String(c ?? ""))),
            },
            source: "engine",
          };
        }
      }
    } catch {
      // fall through to the snapshot engine
    }
    const repo = this.repoList.find((r) => r.slug === repoSlug);
    const file = repo ? findFileInTree(repo.files, path) : undefined;
    if (!file?.dataset) return { ok: false, reason: `No dataset is served for ${path}.` };
    const out = runDatasetSql(file.dataset.tables, sql);
    if (!out.ok) return out;
    return { ok: true, table: out.table, source: "snapshot" };
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
    const feed = this.doc.projectFeeds[repoSlug];
    const served = feed ? normalizeServedDiff(feed.diff, mode) : null;
    const repo = this.repoList.find((r) => r.slug === repoSlug);
    if (!repo) {
      return served ?? { mode, label: mode, files: [], note: `Unknown repo: ${repoSlug}` };
    }
    if (mode === "working" && served) return served;
    const computed = computeDiff(repo.files, mode);
    if (mode === "uncommitted" && served && !computed.staged?.length && !computed.unstaged?.length) {
      return {
        ...served,
        note: "The snapshot carries the working diff; the staged / unstaged split rides the /diff route at the serving shell.",
      };
    }
    return computed;
  }

  worktreeDetail(repoSlug: string, path: string): WorktreeDetail | undefined {
    const repo = this.repoList.find((r) => r.slug === repoSlug);
    const w = repo?.worktrees.find((x) => x.path === path);
    if (!repo || !w) return undefined;
    const changedFiles = flattenRepoFiles(repo.files)
      .filter(({ file }) => file.classification === "untracked" || file.headContent !== undefined)
      .map(({ path: p }) => p);
    const feed = this.doc.projectFeeds[repoSlug];
    const served = (feed?.worktrees?.worktrees ?? []).find(
      (x) => (x as { path?: string }).path === path,
    ) as { active?: { title?: string } | string } | undefined;
    const activePlan =
      typeof served?.active === "string"
        ? served.active
        : served?.active?.title;
    return {
      label: w.label,
      path: w.path,
      branch: w.branch,
      dirty: w.dirty,
      activePlan,
      changedFiles: w.branch === repo.branch ? changedFiles : [],
    };
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
    const r = this.repoList.find((x) => x.slug === slug);
    if (!r) throw new Error(`unknown repo ${slug}`);
    // POST /api/projects/registry {id, patch} — the registry
    // record is the server's store; local state follows.
    await this.postJson("/api/projects/registry", { id: slug, patch });
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
    const cfg = this.doc.config.config;
    const rows: { label: string; value: string }[] = [
      { label: "Config file", value: this.doc.config.config_file },
      { label: "Server", value: this.settingsState.serverLabel },
      { label: "Projects swept", value: String(this.projectList.length) },
      { label: "Registry entries", value: String(this.entryList.length) },
    ];
    for (const [key, value] of Object.entries(cfg)) {
      if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        rows.push({ label: key, value: String(value) });
      }
    }
    return rows;
  }

  messageCounts(): { label: string; count: number }[] {
    const served = this.doc.settings.messages.counts;
    const rows = Object.entries(served).map(([label, count]) => ({ label, count }));
    if (rows.length > 0) return rows;
    const by = (d: string | null) => this.messageList.filter((m) => m.disposition === d).length;
    return [
      { label: "Awaiting disposition", count: by(null) },
      { label: "Filed", count: by("filed") },
      { label: "Opened", count: by("opened") },
      { label: "Dismissed", count: by("dismissed") },
    ];
  }

  cleanupMessages(): { removed: number } {
    const before = this.messageList.length;
    this.messageList = this.messageList.filter((m) => m.disposition !== "dismissed");
    this.emit();
    return { removed: before - this.messageList.length };
  }

  purgeMessages(): { removed: number } {
    const before = this.messageList.length;
    this.messageList = this.messageList.filter((m) => m.disposition === null);
    this.emit();
    return { removed: before - this.messageList.length };
  }

  private care: ServerCare = {
    linkState: "ok",
    classification: "supervised · one unit",
    doctorLabel: "Every 15 min · served",
    lastRepairLabel: "—",
    strayCount: 0,
    log: [],
  };

  serverCare(): ServerCare {
    return { ...this.care, doctorLabel: this.settingsState.doctorLabel };
  }

  repairAction(kind: "clear-strays" | "fallback-restart"): ServerCare {
    if (kind === "clear-strays") {
      const n = this.care.strayCount;
      this.care = {
        ...this.care,
        strayCount: 0,
        lastRepairLabel: "Stray-process clear · Just now",
        log: [`Cleared ${n} stray processes · Just now`, ...this.care.log],
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
    return this.serverCare();
  }

  // -- refresh / rescan (W14) -----------------------------------

  async refresh(): Promise<{ label: string }> {
    // POST /api/refresh at the serving shell; the snapshot
    // itself is re-injected on the next page load — the
    // adapter cannot re-fetch its own document. In the
    // frame form the forceRefresh action carries the
    // same bust over the relay.
    try {
      if (this.channel) {
        await this.channel("forceRefresh");
      } else {
        await fetch(this.url("/api/refresh"), { method: "POST" });
      }
    } catch {
      // offline snapshot — the label still moves
    }
    this.lastRefresh = this.clock();
    this.emit();
    return { label: this.freshnessLabel() };
  }

  async rescan(): Promise<{ label: string }> {
    try {
      if (this.channel) {
        await this.channel("rescanProjects");
      } else {
        await fetch(this.url("/api/projects/rescan"), { method: "POST" });
      }
    } catch {
      // offline snapshot — the label still moves
    }
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
