// Mock seed — invented programme/todo content in the pinned
// served shapes (review §2–§3, contracts 02/03/11). Project
// slugs and the manifest census are the S1 overlay's
// (docs/overlay/workbench.md: 11 canonical projects); all
// content below is invented for the mock store — no live
// workbench state was read. Specimen titles/labels follow the
// approved storyboard, which is the design record.

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
import { slugifyTodoTitle } from "./arming";

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

const MANIFEST = {
  registry: "workbench/registry.db",
  plans: ".plans",
  mockups: "workbench/entries",
  archive: "workbench/archive",
  catalogOrigin: "hand",
  catalogGenerality: "parameterized",
  catalogUseCase: "work-tracking",
};

function project(
  slug: string,
  name: string,
  health: Project["health"],
  healthNote: string,
  lastActivityLabel: string,
  manifestOnly = false,
): Project {
  return {
    slug,
    name,
    manifest: manifestOnly ? null : { ...MANIFEST },
    health,
    healthNote,
    lastActivityLabel,
  };
}

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

export function buildSeed(now: Date): SeedDb {
  const minsAgo = (m: number) => new Date(now.getTime() - m * 60_000).toISOString();
  const hoursAgo = (h: number) => minsAgo(h * 60);

  const projects: Project[] = [
    project("fennelwick", "fennelwick", "ok", "4 in triage · board updated 12 min ago", "12 min ago"),
    project("aldercrest", "aldercrest", "ok", "2 plans in progress", "26 min ago"),
    project("copperleaf", "copperleaf", "degraded", "Degraded · feed stale 23 d", "23 d ago"),
    project("sablebrook", "sablebrook", "ok", "1 mockup awaiting review", "1 h ago"),
    project("colab-runner", "colab-runner", "ok", "Manifest + registry declared", "3 h ago"),
    project("scheduler", "scheduler", "ok", "Registry current", "44 min ago"),
    project("owner-attention", "owner-attention", "ok", "Today + Digest build in progress", "18 min ago"),
    project("workbench-viewer", "workbench-viewer", "ok", "Viewer build programme", "2 h ago"),
    project("sorrelfield", "sorrelfield", "ok", "Quiet", "4 d ago"),
    project("wintermere", "wintermere", "ok", "Quiet", "6 d ago"),
    project("staging", "staging", "ok", "Staging project · pre-home for unhomed work", "1 d ago"),
  ];

  const entries: Entry[] = [
    {
      id: "e-launcher",
      project: "fennelwick",
      kind: "mockup",
      title: "Superapp storyboard — launcher",
      status: "unexplored",
      review: "in-triage",
      version: 3,
      registeredLabel: "Registered today",
      stateHash: "a3f9c1",
      viewport: "Phone",
      mode: "Dark",
      reviewLog: [
        { label: "Entered triage", when: "Today · 12:04 AM", actor: "spec-starter" },
        { label: "State changed · viewport", when: "Yesterday", actor: "spec-starter" },
      ],
    },
    {
      id: "e-board-lanes",
      project: "fennelwick",
      kind: "mockup",
      title: "Board — lanes at card width",
      status: "implemented",
      review: "approved",
      version: 2,
      registeredLabel: "Registered Nov 10",
      stateHash: "9f31c2",
      approvedBy: "owner",
      viewport: "Desktop",
      mode: "Dark",
      reviewLog: [{ label: "Approved · state 9f31c2", when: "Nov 11", actor: "owner" }],
    },
    {
      id: "e-scheduler-frames",
      project: "fennelwick",
      kind: "mockup",
      title: "Superapp storyboard — scheduler frames",
      status: "unexplored",
      review: "in-triage",
      version: 1,
      registeredLabel: "Registered today",
      stateHash: "c41d07",
      viewport: "Desktop",
      mode: "Light",
      reviewLog: [{ label: "Entered triage", when: "Today · 12:31 AM", actor: "spec-starter" }],
    },
    {
      id: "e-workbench-frames",
      project: "fennelwick",
      kind: "mockup",
      title: "Superapp storyboard — workbench frames",
      status: "unexplored",
      review: "in-triage",
      version: 1,
      registeredLabel: "Registered today",
      stateHash: "77ab9e",
      viewport: "Desktop",
      mode: "Dark",
      reviewLog: [{ label: "Entered triage", when: "Today · 1:02 AM", actor: "spec-starter" }],
    },
    {
      id: "e-fundamentals",
      project: "fennelwick",
      kind: "doc",
      title: "Fundamentals — backend/frontend contract",
      status: "implemented",
      review: null,
      version: 1,
      registeredLabel: "Registered Oct 25",
      reviewLog: [],
      repoPath: { repo: "fennelwick", path: "docs/fundamentals.md" },
    },
    {
      id: "e-viewer-master",
      project: "fennelwick",
      kind: "plan",
      title: "Viewer build program — master plan",
      status: "implemented",
      review: null,
      version: 2,
      registeredLabel: "Registered Oct 25",
      reviewLog: [],
    },
    {
      id: "e-supervision-rules",
      project: "fennelwick",
      kind: "doc",
      title: "Supervision rules — generic text",
      status: "canonical",
      review: null,
      version: 4,
      registeredLabel: "Registered Nov 11",
      reviewLog: [],
      repoPath: { repo: "fennelwick", path: "docs/supervision-rules.md" },
    },
    {
      id: "e-operator-chat",
      project: "sablebrook",
      kind: "mockup",
      title: "Operator chat view",
      status: "unexplored",
      review: "needs-changes",
      reviewCount: 2,
      version: 5,
      registeredLabel: "Registered Nov 9",
      stateHash: "b81e04",
      viewport: "Desktop",
      mode: "Light",
      reviewLog: [
        { label: "Needs changes · 2 open", when: "Yesterday", actor: "owner" },
        { label: "Entered triage", when: "Nov 10", actor: "sablebrook-cust" },
      ],
    },
    {
      id: "e-lease-lifecycle",
      project: "colab-runner",
      kind: "mockup",
      title: "Lease lifecycle — grant flow",
      status: "unexplored",
      review: null,
      version: 1,
      registeredLabel: "Registered Nov 3",
      stateHash: "51c9aa",
      viewport: "Desktop",
      mode: "Light",
      staleNote: "Stale · drift",
      reviewLog: [{ label: "Registered", when: "Nov 3", actor: "colab-panel" }],
    },
    {
      id: "e-field-note",
      project: "aldercrest",
      kind: "doc",
      title: "Field note — residual diagnostics",
      status: "implemented",
      review: null,
      version: 1,
      registeredLabel: "Registered Nov 13",
      reviewLog: [],
    },
    {
      id: "e-scanners-doc",
      project: "aldercrest",
      kind: "doc",
      title: "Scanners — policy catalog",
      status: "canonical",
      review: null,
      version: 3,
      registeredLabel: "Registered Oct 30",
      reviewLog: [],
      repoPath: { repo: "aldercrest", path: "docs/scanners.md" },
    },
    {
      id: "e-agents-doc",
      project: "aldercrest",
      kind: "doc",
      title: "AGENTS.md — repo rules",
      status: "implemented",
      review: null,
      version: 7,
      registeredLabel: "Registered Oct 27",
      reviewLog: [],
      repoPath: { repo: "aldercrest", path: "AGENTS.md" },
    },
  ];

  const plans: Plan[] = [
    {
      bundle: "2026-11-12-superapp-storyboards",
      project: "fennelwick",
      title: "Superapp per-app storyboards",
      state: "in-progress",
      executor: "spec-starter thread",
      createdLabel: "Created Nov 12",
      archived: false,
      raw: [
        "# Superapp per-app storyboards",
        "",
        "Status: in progress · Executor: spec-starter thread",
        "",
        "> Ruling (2026-11-12): an approved mockup is an exact spec — what the owner sees in the storyboard is what gets implemented, with no explanatory prose in the mock itself.",
        "",
        "## Steps",
        "",
        "1. Scheduler storyboard — files/2026-11-12-storyboard-scheduler.html",
        "2. Runner storyboard — files/2026-11-12-storyboard-runner.html",
        "3. Attention storyboard — files/2026-11-12-storyboard-attention.html",
        "4. Workbench storyboard — files/2026-11-12-storyboard-workbench.html",
        "",
        "## Checklist",
        "",
        "- [x] Frames rendered at phone width",
        "- [x] Frames rendered at desktop width",
        "- [ ] Critic pass over all four storyboards",
        "- [ ] Close report to main",
        "",
        "## Frame inventory",
        "",
        "| App | Frames | State |",
        "| --- | --- | --- |",
        "| Scheduler | 20 | rendered |",
        "| Workbench | 20 | in progress |",
        "",
        "## Build note",
        "",
        "```ts",
        "// each app builds over the frozen S0 contracts",
        "const adapter = feeds ? createLiveAdapter(feeds) : createMockAdapter();",
        "```",
        "",
        "## Flow",
        "",
        "```mermaid",
        "graph TD",
        "  A[Storyboard] --> B[Critic pass]",
        "  B --> C[Owner pick]",
        "  C --> D[Build]",
        "```",
        "",
        "## Questions",
        "",
        "- [ ] q1: Does the launcher frame carry the goals strip, or does it stay a later frame?",
        "- [x] q2: One shell for all four apps? — Yes: one AppShell, four mounts (owner, 2026-11-12).",
        "",
      ].join("\n"),
      questions: [
        {
          id: "q1",
          text: "Does the launcher frame carry the goals strip, or does it stay a later frame?",
          options: ["Carry the goals strip", "Later frame"],
        },
        {
          id: "q2",
          text: "One shell for all four apps?",
          answer: "Yes: one AppShell, four mounts",
          answeredBy: "owner",
          answeredLabel: "Nov 12",
        },
      ],
      steps: [
        { n: 1, title: "Scheduler storyboard", detail: "Files: files/2026-11-12-storyboard-scheduler.html · Verify: frames rendered + inspected", todoId: "step-1-scheduler-storyboard" },
        { n: 2, title: "Runner storyboard", detail: "Files: files/2026-11-12-storyboard-runner.html · Verify: frames rendered + inspected", todoId: "step-2-runner-storyboard" },
        { n: 3, title: "Attention storyboard", detail: "Files: files/2026-11-12-storyboard-attention.html · Verify: frames rendered + inspected", todoId: "step-3-attention-storyboard" },
        { n: 4, title: "Workbench storyboard", detail: "Files: files/2026-11-12-storyboard-workbench.html · Done when: nine frames rendered + inspected", todoId: "step-4-workbench-storyboard" },
      ],
    },
    {
      bundle: "2026-11-10-ops-kit-serve",
      project: "fennelwick",
      title: "Ops-kit serve.sh genericization",
      state: "draft",
      executor: "—",
      createdLabel: "Created Nov 10",
      archived: false,
      raw: "# Ops-kit serve.sh genericization\n\nStatus: draft\n\n## Steps\n\n1. Inventory serve.sh copies\n2. Parameterize the workspace root\n3. Adopt in the four workhorses\n",
      steps: [
        { n: 1, title: "Inventory serve.sh copies", detail: "Find every serve.sh in the workspace and diff them", todoId: "inventory-serve-sh-copies" },
        { n: 2, title: "Parameterize the workspace root", detail: "One script, root passed in, no machine literals", todoId: "parameterize-the-workspace-root" },
        { n: 3, title: "Adopt in the four workhorses", detail: "Each workhorse points at the generic script", todoId: "adopt-in-the-four-workhorses" },
      ],
    },
    {
      bundle: "2026-11-08-agents-rule-layers",
      project: "fennelwick",
      title: "AGENTS.md rule layers",
      state: "done",
      executor: "spec-starter thread",
      createdLabel: "Created Nov 8",
      archived: true,
      raw: "# AGENTS.md rule layers\n\nStatus: done · 6 of 6 steps\n",
      steps: [1, 2, 3, 4, 5, 6].map((n) => ({
        n,
        title: `Rule layer ${n}`,
        detail: "Landed",
        todoId: `rule-layer-${n}`,
      })),
    },
    {
      bundle: "2026-11-05-backlog-62-65",
      project: "fennelwick",
      title: "Backlog items 62–65",
      state: "done",
      executor: "spec-starter thread",
      createdLabel: "Created Nov 5",
      archived: true,
      raw: "# Backlog items 62–65\n\nStatus: done · 4 of 4 items\n",
      steps: [62, 63, 64, 65].map((n, i) => ({
        n: i + 1,
        title: `Backlog item ${n}`,
        detail: "Landed",
        todoId: `backlog-item-${n}`,
      })),
    },
    {
      bundle: "2026-11-11-document-parsing-successor",
      project: "aldercrest",
      title: "Document-parsing successor — coverage re-drive",
      state: "in-progress",
      executor: "aldercrest-data thread",
      createdLabel: "Created Nov 11",
      archived: false,
      raw: "# Document-parsing successor — coverage re-drive\n\nStatus: in progress · Executor: aldercrest-data thread\n\n## Steps\n\n1. Freeze the labelled denominator\n2. Re-drive coverage over the corpus\n3. Genre defect — ruling-line cure\n4. Segment + substrate lanes\n5. Population audit\n6. Adopt / refresh / retire call\n",
      steps: [
        { n: 1, title: "Freeze the labelled denominator", detail: "Owner ruling 2026-11-12: labelled-only, bar unchanged", todoId: "freeze-the-labelled-denominator" },
        { n: 2, title: "Re-drive coverage over the corpus", detail: "Both denominators reported", todoId: "re-drive-coverage-over-the-corpus" },
        { n: 3, title: "Genre defect — ruling-line cure", detail: "Impostor classifications; cure is a ruling line, not a build", todoId: "genre-defect-ruling-line-cure" },
        { n: 4, title: "Segment + substrate lanes", detail: "Recovery, library/graph, segmentation lanes", todoId: "segment-substrate-lanes" },
        { n: 5, title: "Population audit", detail: "Specimen standing does not transfer; audit on population evidence", todoId: "population-audit" },
        { n: 6, title: "Adopt / refresh / retire call", detail: "Owner call at the end, on the audit", todoId: "adopt-refresh-retire-call" },
      ],
    },
    {
      bundle: "2026-11-09-venue-core-extraction",
      project: "colab-runner",
      title: "Venue core extraction — adapter contract",
      state: "draft",
      executor: "—",
      createdLabel: "Created Nov 9",
      archived: false,
      raw: "# Venue core extraction — adapter contract\n\nStatus: draft\n\n## Steps\n\n1. Name the venue seam\n2. Extract the generic core\n3. Colab adapter over the core\n4. Venue-key the records\n5. Second-adapter proof (deferred)\n",
      steps: [1, 2, 3, 4, 5].map((n) => ({
        n,
        title: ["Name the venue seam", "Extract the generic core", "Colab adapter over the core", "Venue-key the records", "Second-adapter proof"][n - 1],
        detail: "Not started",
        todoId: ["name-the-venue-seam", "extract-the-generic-core", "colab-adapter-over-the-core", "venue-key-the-records", "second-adapter-proof"][n - 1],
      })),
    },
    {
      bundle: "2026-11-11-today-digest-build",
      project: "owner-attention",
      title: "Today + Digest surfaces build",
      state: "in-progress",
      executor: "attention thread",
      createdLabel: "Created Nov 11",
      archived: false,
      raw: "# Today + Digest surfaces build\n\nStatus: in progress · Executor: attention thread\n\n## Steps\n\n1. P1 — defect fixes\n2. P2 — Today actions + reply\n3. P3 — Digest programme cards\n4. P4 — render-time re-verification\n5. In-service dispatch consumption\n6. Push-state source\n7. Handle registry as scoping source\n",
      steps: [1, 2, 3, 4, 5, 6, 7].map((n) => ({
        n,
        title: ["P1 — defect fixes", "P2 — Today actions + reply", "P3 — Digest programme cards", "P4 — render-time re-verification", "In-service dispatch consumption", "Push-state source", "Handle registry as scoping source"][n - 1],
        detail: n <= 4 ? "Landed" : n === 5 ? "In progress" : "Not started",
        todoId: ["p1-defect-fixes", "p2-today-actions-reply", "p3-digest-programme-cards", "p4-render-time-re-verification", "in-service-dispatch-consumption", "push-state-source", "handle-registry-as-scoping-source"][n - 1],
      })),
    },
    {
      bundle: "2026-11-10-step6-reparse-cadence",
      project: "copperleaf",
      title: "Step 6 — reparse cadence",
      state: "in-progress",
      executor: "copperleaf thread",
      createdLabel: "Created Nov 10",
      archived: false,
      raw: "# Step 6 — reparse cadence\n\nStatus: in progress · the cadence itself is the owner's tap (hard gate)\n",
      steps: [
        { n: 1, title: "Reparse cadence ruling", detail: "The cadence is the owner's tap alone", todoId: "reparse-cadence-ruling" },
      ],
    },
    {
      bundle: "2026-11-12-consolidation-plan",
      project: "workbench-viewer",
      title: "Consolidation plan — one pipeline, four apps",
      state: "in-progress",
      executor: "workbench viewer thread",
      createdLabel: "Created Nov 12",
      archived: false,
      raw: "# Consolidation plan — one pipeline, four apps\n\nStatus: in progress · Executor: workbench viewer thread\n\n## Steps\n\n1. S0 — contracts frozen\n2. S1 — overlay capture\n3. S2 — Workhorse Kit extraction\n4. S3–S7 — pipeline build\n5. S8 — live adapters\n6. S9–S11 — cutover + archive\n",
      steps: [
        { n: 1, title: "S0 — contracts frozen", detail: "Fourteen contracts + schemas + fixtures; traceability 36 of 36", todoId: "s0-contracts-frozen" },
        { n: 2, title: "S1 — overlay capture", detail: "The untracked fleet held under docs/overlay; source repos untouched", todoId: "s1-overlay-capture" },
        { n: 3, title: "S2 — Workhorse Kit extraction", detail: "Kit homed in the starter; byte-identity + contrast proofs", todoId: "s2-workhorse-kit-extraction" },
        { n: 4, title: "S3–S7 — pipeline build", detail: "Scheduling, dispatch, venue, workrecord, evaluation, platform", todoId: "s3-s7-pipeline-build" },
        { n: 5, title: "S8 — live adapters", detail: "Live feeds replace the mock adapters behind the same seams", todoId: "s8-live-adapters" },
        { n: 6, title: "S9–S11 — cutover + archive", detail: "Cutover, then the four source repos archived as they are", todoId: "s9-s11-cutover-archive" },
      ],
    },
    {
      bundle: "2026-11-08-greenfield-tagger-successor",
      project: "aldercrest",
      title: "Aldercrest greenfield tagger successor",
      state: "done",
      executor: "aldercrest-data thread",
      createdLabel: "Created Nov 8",
      archived: true,
      raw: "# Aldercrest greenfield tagger successor\n\nStatus: done · 11 of 11 steps landed · union tree gated 271/271\n",
      steps: [
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
      ].map((title, i) => ({
        n: i + 1,
        title,
        detail: "Landed",
        todoId: slugifyTodoTitle(title),
      })),
    },
  ];

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

  const goals: GoalRecord[] = [
    {
      slug: "workhorse-superapp-build",
      project: "workbench-viewer",
      title: "Workhorse superapp build — supreme-octo-robot",
      shortObjective: "one unified app over one pipeline, on Workhorse Kit v1",
      contract: {
        objective: "Scheduler, workbench, runner, and attention in one unified app over one pipeline, on Workhorse Kit v1.",
        completeWhen: "S0–S11 landed; the four apps live over pipeline feeds; the four source repos archived as they are.",
        blockedOnlyWhen: "A hard stop fires (push, external send, purchase, permission card) or a §10 decision is genuinely unruled.",
        continuation: "Agent-clearable work continues without a tap; the ping measures the record every 15 minutes.",
      },
      ping: { entryId: "goal-ping-workhorse-superapp-build", cadenceMinutes: 15, armed: true },
      lastPost: {
        handle: "@workbench-viewer",
        status_code: "WORKING",
        summary: "S2 kit extraction in flight; four frontend lanes staffed on the frozen contracts",
        refs: { project: "workbench-viewer", plan: "2026-11-12-consolidation-plan", todo_ids: [] },
        ongoing: ["S2 — kit extraction + consumer switch"],
        postedAt: minsAgo(20),
      },
    },
    {
      slug: "document-parsing-successor",
      project: "aldercrest",
      title: "Document-parsing successor",
      contract: {
        objective: "A rules-only successor to the retired taxonomy classifier, with coverage parity as a build step.",
        completeWhen: "Population audit clears the .90/.90 floor per family, or the owner rules adopt / refresh / retire on the audit.",
        blockedOnlyWhen: "A ruling line only the owner can write is missing (the genre cure).",
        continuation: "Lanes continue in parallel; only the ruling-line cure waits.",
      },
      ping: { entryId: "goal-ping-document-parsing-successor", cadenceMinutes: 15, armed: true },
      lastPost: {
        handle: "@aldercrest-data",
        status_code: "BLOCKED-OWNER",
        summary: "Genre defect cure is a ruling line; segment lanes wait on it",
        refs: { project: "aldercrest", plan: "2026-11-11-document-parsing-successor", todo_ids: ["genre-defect-ruling-line-cure"] },
        owner_waiting: { label: "Genre ruling-line cure", commissioned_at: hoursAgo(6) },
        // Contract 11 amendment (2026-11-13): a blocked post
        // carries its cited basis + verification stamp. The
        // citation is the owner's escalation the genre cure
        // rides on; main verified it against the owner's
        // traffic and stamped the post.
        basis_citation: { thread: "aldercrest greenfield design thread", at: hoursAgo(6.5) },
        verification: { by: "main", at: hoursAgo(6) },
        postedAt: hoursAgo(2),
      },
    },
    {
      slug: "copperleaf-dag",
      project: "copperleaf",
      title: "Copperleaf v2 — serving DAG",
      contract: {
        objective: "Store-sourced serving for the copperleaf: the DAG complete except Step 6.",
        completeWhen: "Step 6's reparse cadence is ruled and the reparse runs on it.",
        blockedOnlyWhen: "The Step 6 cadence tap — the owner's alone.",
        continuation: "Daily runs continue on the current cadence meanwhile.",
      },
      ping: { entryId: "goal-ping-copperleaf-dag", cadenceMinutes: 60, armed: false },
      lastPost: null,
    },
    {
      // The deployment's real closed goal, seeded at record
      // level from its record (programme closed 2026-11-13,
      // 11 of 11 steps landed): the Completed group's specimen.
      slug: "aldercrest-greenfield-tagger",
      project: "aldercrest",
      title: "Aldercrest greenfield tagger successor programme",
      contract: {
        objective: "The rules-only successor to the retired taxonomy classifier, built under the owner's 2026-11-08 retire-and-rebuild approval.",
        completeWhen: "All 11 steps landed, the union tree gated, and the verdict record filed.",
        blockedOnlyWhen: "A family or statement line closing below the .90 audited floor without an owner ruling on named evidence.",
        continuation: "Successors staff immediately on verified completion; milestones, blockers, and the completion verdict only.",
      },
      // A closed record retires its ping: disarmed for good,
      // never re-armed by the toggle.
      ping: { entryId: "goal-ping-aldercrest-greenfield-tagger", cadenceMinutes: 15, armed: false },
      lastPost: {
        handle: "@aldercrest-data",
        status_code: "CLOSED",
        summary: "Programme closed — all 11 steps landed; the verdict record is filed",
        refs: { project: "aldercrest", plan: "2026-11-08-greenfield-tagger-successor", todo_ids: [] },
        postedAt: hoursAgo(3),
      },
    },
  ];

  const messages: InboxMessage[] = [
    {
      id: "m-1", kind: "mockup", title: "Superapp storyboard — launcher",
      project: "fennelwick", arrivedLabel: "arrived 12 min ago",
      disposition: null, target: { section: "mockups", entryId: "e-launcher" },
    },
    {
      id: "m-2", kind: "mockup", title: "Operator chat view — storyboard rebuild",
      project: "sablebrook", arrivedLabel: "arrived 1 h ago",
      disposition: null, target: { section: "mockups", entryId: "e-operator-chat" },
    },
    {
      id: "m-3", kind: "doctor", title: "Doctor digest — 2 findings changed",
      project: "workbench doctor", arrivedLabel: "arrived 2 h ago",
      disposition: null, target: { section: "overview" },
    },
    {
      id: "m-4", kind: "plan", title: "AGENTS.md rule layers — plan adopted",
      project: "fennelwick", arrivedLabel: "yesterday",
      disposition: "filed", target: { section: "plans", bundle: "2026-11-08-agents-rule-layers" },
    },
  ];

  const agentsMd = [
    "# AGENTS.md",
    "",
    "## Read order",
    "",
    "1. `SPEC.md` — what this repo is",
    "2. `docs/supervision-rules.md` (starter) — the generic",
    "   supervision statements this repo binds",
    "3. This file — the repo's own residue",
    "",
    "## Rules",
    "",
    "- Formation and gating live in the sessions, not",
    "  locally, while High-RAM sessions are up.",
    "- Gates run on Colab High-RAM while a",
    "  session is up, never locally.",
    "- check.py is the uniform validation gate: ruff",
    "  format + lint, the policy scanners, and pytest.",
    "- Scope the gate to the session's own work when",
    "  parallel changes are in the tree.",
  ].join("\n");
  const agentsMdHead = agentsMd.replace(
    "- Gates run on Colab High-RAM while a\n  session is up, never locally.",
    "- Gates run locally when convenient.",
  );
  // The staged (index) snapshot: the Colab line is already
  // corrected there, the scope line is not yet — the two
  // halves of the uncommitted split the diff panel shows.
  const agentsMdStaged = agentsMdHead.replace(
    "- Gates run locally when convenient.",
    "- Gates run on Colab High-RAM while a\n  session is up, never locally.",
  ).replace(
    "- Scope the gate to the session's own work when\n  parallel changes are in the tree.",
    "- Scope the gate loosely; parallel changes are fine.",
  );

  const scannersMd = [
    "# Scanners",
    "",
    "The policy scanners read the tree at the gate:",
    "ruff format + lint, then the scanners below,",
    "then pytest over the affected modules.",
    "",
    "## Catalog",
    "",
    "- length — file-length fails the gate at 800",
    "- portability — no outside paths in tracked files",
    "- denylist — untracked enforcement list",
  ].join("\n");

  const aldercrestFiles: Repo["files"] = [
    {
      name: "data", kind: "folder",
      children: [
        {
          name: "records.csv", kind: "file", sizeLabel: "2.1 MB · dataset", sha: "c81d22",
          editable: "no", editableNote: "No — binary dataset (metadata and table only)",
          dataset: {
            tables: [
              {
                name: "records",
                columns: ["Accession", "Company", "Form", "Filed"],
                rows: [
                  ["0000320193-25-000108", "Apple Inc", "10-K", "2025-10-31"],
                  ["0000789019-25-000014", "Microsoft Corp", "10-K", "2025-07-30"],
                  ["0001045810-25-000312", "NVIDIA Corp", "10-Q", "2025-11-19"],
                  ["0000050863-25-000201", "Intel Corp", "10-Q", "2025-10-24"],
                  ["0000320193-25-000121", "Apple Inc", "10-Q", "2026-01-30"],
                  ["0000789019-25-000021", "Microsoft Corp", "10-Q", "2025-10-24"],
                ],
              },
              {
                name: "forms",
                columns: ["Form", "Filings"],
                rows: [
                  ["10-K", "2"],
                  ["10-Q", "4"],
                ],
              },
            ],
          },
        },
        { name: "filers.csv", kind: "file", sizeLabel: "840 KB · dataset", sha: "9aa014", editable: "no", editableNote: "No — binary dataset (metadata and table only)", dataset: { tables: [{ name: "filers", columns: ["CIK", "Name"], rows: [["320193", "Apple Inc"], ["789019", "Microsoft Corp"]] }] } },
      ],
    },
    {
      name: "docs", kind: "folder",
      children: [
        { name: "archive", kind: "folder", children: [{ name: "old-rulings.md", kind: "file", sizeLabel: "3,102 bytes · 41 lines", lines: 41, sha: "77c1e0", editable: "guarded", content: "# Old rulings\n\nArchived rulings, kept for provenance.\n" }] },
        { name: "scanners.md", kind: "file", sizeLabel: "5,260 bytes · 96 lines", lines: 96, sha: "9c41be02", editable: "guarded", content: scannersMd },
        { name: "supervision-rules.md", kind: "file", sizeLabel: "8,940 bytes · 132 lines", lines: 132, sha: "41d8c2", editable: "guarded", content: "# Supervision rules\n\nThe generic statements this repo binds.\n" },
        { name: "scanner-notes.md", kind: "file", classification: "untracked", sizeLabel: "640 bytes · 18 lines", lines: 18, sha: "0f77aa", editable: "guarded", content: "# Scanner notes (untracked)\n\nWorking notes, not yet adopted.\n" },
      ],
    },
    { name: "lib", kind: "folder", children: [{ name: "engine.py", kind: "file", sizeLabel: "12,204 bytes · 310 lines", lines: 310, sha: "b2c901", editable: "guarded", content: "# engine\n" }] },
    { name: "viewer", kind: "folder", children: [{ name: "client", kind: "folder", children: [] }] },
    { name: "node_modules", kind: "folder", classification: "pruned", children: [] },
    { name: "SPEC.md", kind: "file", sizeLabel: "21,480 bytes · 402 lines", lines: 402, sha: "d9012b", editable: "guarded", content: "# SPEC\n\nWhat this repo is.\n" },
    { name: "AGENTS.md", kind: "file", sizeLabel: "1,940 bytes · 19 lines", lines: 19, sha: "a3f9c1", editable: "guarded", content: agentsMd, headContent: agentsMdHead, stagedContent: agentsMdStaged },
    { name: "check.py", kind: "file", sizeLabel: "4,412 bytes · 118 lines", lines: 118, sha: "e55a10", editable: "guarded", content: "#!/usr/bin/env python3\n# check.py — the uniform validation gate\n" },
    { name: "notes-draft.md", kind: "file", classification: "untracked", sizeLabel: "380 bytes · 9 lines", lines: 9, sha: "3b90cd", editable: "guarded", content: "# Draft notes\n\nUntracked working draft.\n" },
    {
      name: "secrets.env", kind: "file", classification: "withheld", hidden: true,
      sizeLabel: "212 bytes · 6 lines", lines: 6, sha: "f00d42", editable: "no",
      editableNote: "No — secret-shaped files are never edited in the viewer",
      content: "# FICTITIOUS mock content — no real values\nEXAMPLE_TOKEN=not-a-real-secret\nEXAMPLE_ENDPOINT=https://example.invalid/\n",
    },
  ];

  const smallTree = (names: string[]): Repo["files"] =>
    names.map((n) => ({ name: n, kind: "file" as const, sizeLabel: "1,024 bytes · 24 lines", lines: 24, sha: "aa1100", editable: "guarded" as const, content: `# ${n}\n` }));

  function repo(
    slug: string,
    path: string,
    sweep: Repo["sweep"],
    partial: Partial<Repo> = {},
  ): Repo {
    return {
      slug, name: slug, path, sweep,
      branch: "main",
      syncLabel: "Even with origin",
      modifiedCount: 0,
      worktrees: [{ label: "Main checkout", path, branch: "main", dirty: 0 }],
      history: [{ sha: "0a1b2c3", title: "Latest work", when: "Today" }],
      files: smallTree(["README.md"]),
      tracking: { expected: "On the daily sweep", pinned: false, ignored: false, notes: "" },
      ...partial,
    };
  }

  const repos: Repo[] = [
    repo("aldercrest", "${WS}/aldercrest", "swept", {
      syncLabel: "Even with origin · pushed 1:39 PM",
      modifiedCount: 3,
      tracking: { expected: "On the daily sweep", pinned: true, ignored: false, notes: "The XBRL engine repo; the successor programme's home." },
      worktrees: [
        { label: "Main checkout", path: "${WS}/aldercrest · main", branch: "main", dirty: 3 },
        { label: "Lane — doc-parsing", path: "aldercrest-wt-lane3 · lane/doc-parsing", branch: "lane/doc-parsing", dirty: 0 },
        { label: "Lane — fetch-operator", path: "aldercrest-wt-lane1 · lane/fetch-operator", branch: "lane/fetch-operator", dirty: 1 },
      ],
      history: [
        { sha: "8c9c710d", title: "Extraction-consolidation formation lands", when: "Today · 1:39 PM" },
        { sha: "1f9a1578", title: "Strip iteration 3 — closeout", when: "Nov 11" },
        { sha: "5e02ab91", title: "Classifier reset — corrected gate", when: "Nov 11" },
      ],
      files: aldercrestFiles,
    }),
    repo("fennelwick", "${WS}/fennelwick", "swept", {
      files: [
        { name: "docs", kind: "folder", children: [
          { name: "fundamentals.md", kind: "file", sizeLabel: "6,120 bytes · 88 lines", lines: 88, sha: "c201aa", editable: "guarded", content: "# Fundamentals\n\nThe backend does the work; the frontend is a consumer.\n" },
          { name: "supervision-rules.md", kind: "file", sizeLabel: "9,300 bytes · 140 lines", lines: 140, sha: "c202bb", editable: "guarded", content: "# Supervision rules\n\nGeneric statements; repos bind them locally.\n" },
        ] },
        { name: "SPEC.md", kind: "file", sizeLabel: "3,340 bytes · 60 lines", lines: 60, sha: "c203cc", editable: "guarded", content: "# SPEC\n" },
      ],
    }),
    repo("copperleaf", "${WS}/copperleaf", "degraded"),
    repo("sablebrook", "${WS}/sablebrook", "swept"),
    repo("colab-runner", "${WS}/colab-runner", "swept"),
    repo("scheduler", "${WS}/scheduler", "swept"),
    repo("owner-attention", "${WS}/owner-attention", "swept"),
    repo("workbench-viewer", "${WS}/workbench-viewer", "swept"),
  ];

  const annotations: AnnotationThread[] = [
    {
      id: "ann-1",
      bundle: "2026-11-12-superapp-storyboards",
      project: "fennelwick",
      anchorQuote: "an approved mockup is an exact spec",
      anchorContext:
        "> Ruling (2026-11-12): an approved mockup is an exact spec — what the owner sees in the storyboard is what gets implemented, with no explanatory prose in the mock itself.",
      status: "anchored",
      resolved: false,
      messages: [
        {
          id: "ann-1-m1",
          author: "critic",
          body: "This is the line the whole storyboard programme hangs on — the frames either are the spec or they are decoration.",
          when: "Nov 12",
        },
        {
          id: "ann-1-m2",
          author: "spec-starter",
          body: "Agreed; the critic pass checks every frame against it before the owner pick.",
          when: "Nov 12",
        },
      ],
    },
    {
      id: "ann-2",
      bundle: "2026-11-12-superapp-storyboards",
      project: "fennelwick",
      anchorQuote: "the storyboard is inspiration, not a spec",
      status: "orphaned",
      resolved: false,
      messages: [
        {
          id: "ann-2-m1",
          author: "critic",
          body: "This phrasing was struck from the plan when the ruling landed — the anchor no longer exists in the text.",
          when: "Nov 12",
        },
      ],
    },
    {
      id: "ann-3",
      bundle: "2026-11-11-document-parsing-successor",
      project: "aldercrest",
      anchorQuote: "Genre defect — ruling-line cure",
      anchorContext: "3. Genre defect — ruling-line cure",
      status: "anchored",
      resolved: true,
      messages: [
        {
          id: "ann-3-m1",
          author: "aldercrest-data",
          body: "The cure is a ruling line, not a build — noted here so the segment lanes do not start against the impostor classes.",
          when: "Nov 11",
        },
      ],
    },
    {
      id: "ann-4",
      bundle: "2026-11-11-document-parsing-successor",
      project: "aldercrest",
      anchorQuote: "Population audit",
      anchorContext: "5. Population audit — specimen standing transfers to the draw",
      status: "relocated",
      resolved: false,
      messages: [
        {
          id: "ann-4-m1",
          author: "aldercrest-data",
          body: "The step line was edited after this annotation was anchored — the quote survives, its line does not.",
          when: "Nov 12",
        },
      ],
    },
  ];

  const threads: MessageThread[] = [
    {
      id: "th-1",
      project: "fennelwick",
      title: "Superapp storyboard — launcher",
      state: "sent",
      messages: [
        {
          id: "th-1-m1",
          author: "spec-starter",
          body: "The launcher storyboard is in triage. It renders the programme's entries as frames; the owner pick makes it the exact spec for the launcher build.",
          when: "12 min ago",
        },
      ],
    },
    {
      id: "th-2",
      project: "sablebrook",
      title: "Operator chat view — storyboard rebuild",
      state: "acknowledged",
      messages: [
        {
          id: "th-2-m1",
          author: "sablebrook-cust",
          body: "Rebuilt storyboard for the operator chat view; two change requests are open on the entry itself.",
          when: "1 h ago",
        },
        {
          id: "th-2-m2",
          author: "owner",
          body: "Seen — the changes ride the entry's review, not this thread.",
          when: "44 min ago",
        },
      ],
    },
    {
      id: "th-3",
      project: "workbench doctor",
      title: "Doctor digest — 2 findings changed",
      state: "sent",
      messages: [
        {
          id: "th-3-m1",
          author: "workbench doctor",
          body: "Two findings changed since the last digest: the missing doctor runner (now ported) and a stale link probe state.",
          when: "2 h ago",
        },
      ],
    },
    {
      id: "th-4",
      project: "fennelwick",
      title: "Draft — storyboard close-out note",
      state: "draft",
      messages: [
        {
          id: "th-4-m1",
          author: "owner",
          body: "Draft: when the critic pass clears, the close report goes to main with the frame inventory attached.",
          when: "draft",
        },
      ],
    },
  ];

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
