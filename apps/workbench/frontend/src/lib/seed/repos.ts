// Seed repos: the swept repo records with their file
// trees (the aldercrest tree carries the dataset and
// diff specimens), worktrees, and history.

import type { Repo } from "../types";

export function buildRepos(): Repo[] {
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
    repo("venue-runner", "${WS}/venue-runner", "swept"),
    repo("scheduler", "${WS}/scheduler", "swept"),
    repo("owner-attention", "${WS}/owner-attention", "swept"),
    repo("workbench-viewer", "${WS}/workbench-viewer", "swept"),
  ];
  return repos;
}
