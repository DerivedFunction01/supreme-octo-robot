// Seed todos: the plans' step todos and the loose
// programme todos, in the served FileTodo shape.

import { slugifyTodoTitle } from "../arming";
import type { FileTodo } from "../types";
import type { SeedTime } from "./time";


function todo(
  partial: Partial<FileTodo> & Pick<FileTodo, "id" | "project" | "bundle" | "title" | "status">,
): FileTodo {
  return {
    created: "2026-11-12",
    updated: "2026-11-13",
    checkpoints: [],
    notes: "",
    extra: {},
    ...partial,
  };
}

export function buildTodos(t: SeedTime): FileTodo[] {
  const { minsAgo, hoursAgo } = t;
  const B = "2026-11-12-superapp-storyboards";
  const todos: FileTodo[] = [
    todo({ id: "step-1-scheduler-storyboard", project: "fennelwick", bundle: B, title: "Step 1 — Scheduler storyboard", status: "done" }),
    todo({ id: "step-2-runner-storyboard", project: "fennelwick", bundle: B, title: "Step 2 — Runner storyboard", status: "done" }),
    todo({ id: "step-3-attention-storyboard", project: "fennelwick", bundle: B, title: "Step 3 — Attention storyboard", status: "done" }),
    todo({
      id: "step-4-workbench-storyboard", project: "fennelwick", bundle: B,
      title: "Step 4 — Workbench storyboard", status: "doing",
      progressCheck: "30m", progressArmed: hoursAgo(1),
      checkpoints: [{ at: minsAgo(12), text: "nine frames rendered; explorer frames in progress" }],
      notes: "The largest app: 20 frames. Explorer + peek frames ride the repo feeds.",
      extra: { lane: "spec-starter" },
    }),
    todo({ id: "step-5-close-report-to-main", project: "fennelwick", bundle: B, title: "Step 5 — Close report to main", status: "todo" }),
    todo({ id: "inventory-serve-sh-copies", project: "fennelwick", bundle: "2026-11-10-ops-kit-serve", title: "Inventory serve.sh copies", status: "todo" }),
    todo({ id: "parameterize-the-workspace-root", project: "fennelwick", bundle: "2026-11-10-ops-kit-serve", title: "Parameterize the workspace root", status: "todo" }),
    todo({ id: "adopt-in-the-four-workhorses", project: "fennelwick", bundle: "2026-11-10-ops-kit-serve", title: "Adopt in the four workhorses", status: "todo" }),
    ...[1, 2, 3, 4, 5, 6].map((n) =>
      todo({ id: `rule-layer-${n}`, project: "fennelwick", bundle: "2026-11-08-agents-rule-layers", title: `Rule layer ${n}`, status: "done" as const }),
    ),
    ...[62, 63, 64, 65].map((n, i) =>
      todo({ id: `backlog-item-${n}`, project: "fennelwick", bundle: "2026-11-05-backlog-62-65", title: `Backlog item ${n}`, status: "done" as const }),
    ),
    todo({ id: "freeze-the-labelled-denominator", project: "aldercrest", bundle: "2026-11-11-document-parsing-successor", title: "Freeze the labelled denominator", status: "done" }),
    todo({ id: "re-drive-coverage-over-the-corpus", project: "aldercrest", bundle: "2026-11-11-document-parsing-successor", title: "Re-drive coverage over the corpus", status: "done" }),
    todo({
      id: "genre-defect-ruling-line-cure", project: "aldercrest", bundle: "2026-11-11-document-parsing-successor",
      title: "Genre defect — ruling-line cure", status: "doing",
      progressCheck: "2h", progressArmed: hoursAgo(5),
      checkpoints: [{ at: hoursAgo(4.5), text: "impostor rate measured; cure drafted as a ruling line" }],
    }),
    todo({
      id: "segment-substrate-lanes", project: "aldercrest", bundle: "2026-11-11-document-parsing-successor",
      title: "Segment + substrate lanes", status: "blocked",
      notes: "Blocked on the genre ruling line — the cure is ruled before the lanes build against it.",
    }),
    todo({ id: "population-audit", project: "aldercrest", bundle: "2026-11-11-document-parsing-successor", title: "Population audit", status: "todo" }),
    todo({ id: "adopt-refresh-retire-call", project: "aldercrest", bundle: "2026-11-11-document-parsing-successor", title: "Adopt / refresh / retire call", status: "todo" }),
    ...[1, 2, 3, 4, 5].map((n) =>
      todo({ id: ["name-the-venue-seam", "extract-the-generic-core", "colab-adapter-over-the-core", "venue-key-the-records", "second-adapter-proof"][n - 1], project: "colab-runner", bundle: "2026-11-09-venue-core-extraction", title: ["Name the venue seam", "Extract the generic core", "Colab adapter over the core", "Venue-key the records", "Second-adapter proof"][n - 1], status: "todo" as const }),
    ),
    ...[1, 2, 3, 4].map((n) =>
      todo({ id: ["p1-defect-fixes", "p2-today-actions-reply", "p3-digest-programme-cards", "p4-render-time-re-verification"][n - 1], project: "owner-attention", bundle: "2026-11-11-today-digest-build", title: ["P1 — defect fixes", "P2 — Today actions + reply", "P3 — Digest programme cards", "P4 — render-time re-verification"][n - 1], status: "done" as const }),
    ),
    todo({
      id: "in-service-dispatch-consumption", project: "owner-attention", bundle: "2026-11-11-today-digest-build",
      title: "In-service dispatch consumption", status: "doing",
      progressArmed: minsAgo(40), // no cadence declared → arms at the 15-minute default
      checkpoints: [{ at: minsAgo(9), text: "consumer claiming sends under the attention-service name" }],
    }),
    todo({ id: "push-state-source", project: "owner-attention", bundle: "2026-11-11-today-digest-build", title: "Push-state source", status: "todo" }),
    todo({ id: "handle-registry-as-scoping-source", project: "owner-attention", bundle: "2026-11-11-today-digest-build", title: "Handle registry as scoping source", status: "todo" }),
    todo({
      id: "reparse-cadence-ruling", project: "copperleaf", bundle: "2026-11-10-step6-reparse-cadence",
      title: "Reparse cadence ruling", status: "blocked",
      notes: "The reparse cadence is the owner's tap alone (hard gate).",
    }),
    todo({
      id: "storage-watch-retune-home-tiers", project: "scheduler", bundle: "2026-11-11-storage-watch-retune",
      title: "Storage-watch retune — home tiers", status: "doing",
      progressCheck: "off", // explicit opt-out: never arms
      notes: "Landed f335939 in the live repo; this record tracks the follow-up verification.",
    }),
    todo({ id: "s0-contracts-frozen", project: "workbench-viewer", bundle: "2026-11-12-consolidation-plan", title: "S0 — contracts frozen", status: "done" }),
    todo({ id: "s1-overlay-capture", project: "workbench-viewer", bundle: "2026-11-12-consolidation-plan", title: "S1 — overlay capture", status: "done" }),
    todo({
      id: "s2-workhorse-kit-extraction", project: "workbench-viewer", bundle: "2026-11-12-consolidation-plan",
      title: "S2 — Workhorse Kit extraction", status: "doing",
      progressCheck: "30m", progressArmed: hoursAgo(1),
      checkpoints: [{ at: minsAgo(12), text: "kit home staged; consumer switch proving in a worktree" }],
    }),
    todo({ id: "s3-s7-pipeline-build", project: "workbench-viewer", bundle: "2026-11-12-consolidation-plan", title: "S3–S7 — pipeline build", status: "todo" }),
    todo({ id: "s8-live-adapters", project: "workbench-viewer", bundle: "2026-11-12-consolidation-plan", title: "S8 — live adapters", status: "todo" }),
    todo({ id: "s9-s11-cutover-archive", project: "workbench-viewer", bundle: "2026-11-12-consolidation-plan", title: "S9–S11 — cutover + archive", status: "todo" }),
    ...[
      "Corpus + labels freeze",
      "Rules engine — reflow",
      "Location features",
      "Prose n-gram features",
      "Coverage parity build step",
      "Diversified held-out validation set",
      "Specimen audit",
      "Population draw",
      "Defect register sweep",
      "Union formation + gate",
      "Verdict record",
    ].map((title, i) =>
      todo({
        id: slugifyTodoTitle(title),
        project: "aldercrest",
        bundle: "2026-11-08-greenfield-tagger-successor",
        title,
        status: "done" as const,
      }),
    ),
  ];
  return todos;
}
