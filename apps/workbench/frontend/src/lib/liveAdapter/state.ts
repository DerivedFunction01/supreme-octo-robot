// Live adapter state construction: the feeds document
// projected into the adapter's lists and maps — the
// constructor's build, as a pure function of the
// document.

import { anchorStatus } from "../diffModel";
import type {
  FeedEntryDetail,
  FeedPlanDoc,
  WorkbenchFeeds,
} from "../feeds";
import type { AnnotationThread, Project, Repo } from "../types";
import { projectEntry } from "./entryProjection";
import type { LiveState } from "./host";
import { projectMessage } from "./messageProjection";
import { projectPlan } from "./planProjection";
import { dateLabel } from "./shared";
import { projectTodo } from "./todoProjection";

export function buildLiveState(doc: WorkbenchFeeds): LiveState {
  const s = {} as LiveState;
  s.pagePaths = new Map();
  s.mutatedTodos = new Set();
  s.dispositions = new Map();
  s.annotationList = [];
  s.threadList = [];
  s.entryFileCache = new Map();
  s.entryFileShas = new Map();
  s.planWrite = new Map();
  s.lastRefresh = new Date();
  s.care = {
    linkState: "ok",
    classification: "supervised · one unit",
    doctorLabel: "Every 15 min · served",
    lastRepairLabel: "—",
    strayCount: 0,
    log: [],
  };
  const homeBySlug = new Map(doc.home.projects.map((r) => [r.slug, r]));
  s.projectList = doc.projects.projects.map((p) => {
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

  s.todoList = [];
  s.entryList = [];
  s.planList = [];
  for (const summary of doc.projects.projects) {
    const feed = doc.projectFeeds[summary.slug];
    if (!feed) continue;
    const todos = feed.todos.todos.map((row) =>
      projectTodo(row, summary.slug),
    );
    s.todoList.push(...todos);
    const rows = [...feed.entries.entries, ...feed.entriesArchived.entries];
    for (const row of rows) {
      const detailRaw = feed.entryDetails[row.id];
      const detail =
        detailRaw && !("error" in detailRaw) ? (detailRaw as FeedEntryDetail) : undefined;
      const mainFile = detail?.files?.find((f) => f.is_main);
      if (mainFile) s.pagePaths.set(row.id, mainFile.path);
      s.entryList.push(projectEntry(row, detail, summary.slug));
    }
    for (const bundle of feed.plans.bundles) {
      const docRaw = bundle.plan ? feed.planDocs[bundle.plan.path] : undefined;
      const planDoc = docRaw && !("error" in docRaw) ? (docRaw as FeedPlanDoc) : undefined;
      const plan = projectPlan(bundle, planDoc, feed.todos.todos, summary.slug);
      if (plan) s.planList.push(plan);
      if (bundle.plan && planDoc?.file_sha256) {
        s.planWrite.set(bundle.id, {
          path: bundle.plan.path,
          sha256: planDoc.file_sha256,
        });
      }
    }
  }

  s.messageList = doc.messages.messages
    .filter((m) => m.state !== "draft")
    .map((m) => projectMessage(m, undefined));

  // Message threads (W10): every served row is a thread —
  // drafts included (the Inbox feed above hides them).
  s.threadList = doc.messages.messages.map((m) => ({
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
    const plan = s.planList.find((p) => p.bundle === bundle);
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
    s.annotationList.push({
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
  s.goalList = (doc.goals ?? []).map((g) => ({ ...g }));
  s.boards = new Map(
    Object.entries(doc.projectFeeds).map(([slug, feed]) => [
      slug,
      structuredClone(feed.board),
    ]),
  );
  s.servedDerivations = new Map();
  for (const [slug, feed] of Object.entries(doc.projectFeeds)) {
    for (const block of feed.classification.progress.armed) {
      s.servedDerivations.set(`${slug}:${block.id}`, {
        todoId: block.id,
        cadenceMinutes: (block.interval_seconds ?? 0) / 60,
        lastActivity: block.last_activity ?? block.armed_at ?? "",
        missedChecks: block.missed_checks ?? 0,
        verdict: block.stalled ? "stalled" : "on-track",
      });
    }
  }
  s.sourceClass = new Map();
  for (const row of doc.armedRows) {
    s.sourceClass.set(row.project, row.source.source_class);
  }

  s.repoList = doc.projectsIndex.projects.map((row) =>
    projectRepo(row),
  );

  const cfg = doc.config.config;
  s.settingsState = {
    boardLaneWidth: 264,
    guardedSaves: cfg.file_editing_enabled === true,
    serverLabel: `${cfg.host ?? "127.0.0.1"}:${cfg.port ?? ""} · live`,
    projectsSwept: s.projectList.length,
    doctorLabel: `Message store · ${Object.values(doc.settings.messages.counts).reduce((a, b) => a + b, 0)} messages`,
  };
  return s;
}

function projectRepo(
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
