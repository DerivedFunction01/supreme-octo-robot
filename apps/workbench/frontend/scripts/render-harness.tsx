// Render harness for scripts/render-smoke.mjs — mounts every
// section server-side against a fresh mock adapter and
// reports, per section, whether it rendered and whether its
// marker content is present. Not part of the app bundle.

import { renderToString } from "react-dom/server";
import { createElement } from "react";
import { AdapterContext } from "../src/lib/store";
import { MockWorkbenchAdapter } from "../src/lib/mockAdapter";
import { NavContext, type NavApi } from "../src/lib/nav";
import { Home } from "../src/sections/Home";
import { Overview } from "../src/sections/Overview";
import { GoalDetail, Goals } from "../src/sections/Goals";
import { MockupDetail, Mockups } from "../src/sections/Mockups";
import { Entries } from "../src/sections/Entries";
import { Plans } from "../src/sections/Plans";
import { TodoDetail, Todos } from "../src/sections/Todos";
import { Board } from "../src/sections/Board";
import { Inbox } from "../src/sections/Inbox";
import { RepoDetail, Repos } from "../src/sections/Repos";
import { PeekPane, PhoneExplorer, PhonePeek, SplitView } from "../src/sections/Explorer";
import { Editor } from "../src/sections/Editor";
import { Settings } from "../src/sections/Settings";

const adapter = new MockWorkbenchAdapter(() => new Date("2026-11-13T14:36:00.000Z"));

function navFor(project: string): NavApi {
  return {
    nav: { section: "home" },
    navigate: () => {},
    project,
    setProject: () => {},
    setEditorGuard: () => {},
  };
}

function wrap(project: string, el: React.ReactNode) {
  return createElement(
    AdapterContext.Provider,
    { value: adapter },
    createElement(NavContext.Provider, { value: navFor(project) }, el),
  );
}

const step4 = adapter.todo("step-4-workbench-storyboard")!;

const CASES: { name: string; el: React.ReactNode; marker: string }[] = [
  { name: "Frame 1 · Home", el: wrap("fennelwick", createElement(Home)), marker: "Awaiting review" },
  { name: "Frame 10 · Overview (fennelwick)", el: wrap("fennelwick", createElement(Overview)), marker: "Active plan" },
  { name: "Frame 10 · Overview + goal record (aldercrest)", el: wrap("aldercrest", createElement(Overview)), marker: "Genre ruling-line cure" },
  { name: "Frame 10 · Overview + goal record (workbench-viewer)", el: wrap("workbench-viewer", createElement(Overview)), marker: "Ping armed" },
  { name: "Frame 2 · Mockups", el: wrap("fennelwick", createElement(Mockups)), marker: "Superapp storyboard — launcher" },
  { name: "Frame 3 · Mockup drill-in", el: wrap("fennelwick", createElement(MockupDetail, { entryId: "e-launcher" })), marker: "Disposition" },
  { name: "Frame 11 · Entries", el: wrap("fennelwick", createElement(Entries)), marker: "Fundamentals — backend/frontend contract" },
  { name: "Frame 4 · Plans", el: wrap("fennelwick", createElement(Plans, {})), marker: "Superapp per-app storyboards" },
  { name: "Frame 5 · Todos", el: wrap("fennelwick", createElement(Todos)), marker: "classification feed" },
  { name: "Frame 5 · Todo detail sheet (armed)", el: wrap("fennelwick", createElement(TodoDetail, { todo: step4, onClose: () => {} })), marker: "wb-armed-fennelwick" },
  { name: "Frame 6 · Board", el: wrap("fennelwick", createElement(Board)), marker: "Review queue" },
  { name: "Frame 7 · Inbox", el: wrap("fennelwick", createElement(Inbox)), marker: "awaiting a first disposition" },
  { name: "Frame 8 · Repos", el: wrap("fennelwick", createElement(Repos)), marker: "owner-attention" },
  { name: "Frame 14 · Repo status & worktrees", el: wrap("fennelwick", createElement(RepoDetail, { repoSlug: "aldercrest" })), marker: "Lane — doc-parsing" },
  { name: "Frame 20 · Split view (dataset peek)", el: wrap("fennelwick", createElement(SplitView, { repoSlug: "aldercrest" })), marker: "Edit unavailable" },
  { name: "Frame 15 · Phone explorer — repo root", el: wrap("fennelwick", createElement(PhoneExplorer, { repoSlug: "aldercrest", trail: [] })), marker: "Show hidden" },
  { name: "Frame 16 · Phone explorer — folder", el: wrap("fennelwick", createElement(PhoneExplorer, { repoSlug: "aldercrest", trail: ["docs"] })), marker: "scanners.md" },
  { name: "Frame 17 · Phone peek — content", el: wrap("fennelwick", createElement(PhonePeek, { repoSlug: "aldercrest", path: "docs/scanners.md" })), marker: "Guarded save" },
  { name: "Frame 18 · Peek — diff vs HEAD", el: wrap("fennelwick", createElement(PeekPane, { repoSlug: "aldercrest", path: "AGENTS.md", initialTab: "diff" })), marker: "Gates run on Colab High-RAM" },
  { name: "Frame 19 · Peek — withheld file", el: wrap("fennelwick", createElement(PeekPane, { repoSlug: "aldercrest", path: "secrets.env" })), marker: "Content withheld" },
  { name: "Frame 12 · File editor", el: wrap("fennelwick", createElement(Editor, { repoSlug: "aldercrest", path: "AGENTS.md" })), marker: "Compare-and-swap" },
  { name: "Frame 9 · Settings", el: wrap("fennelwick", createElement(Settings)), marker: "Board lane width" },
  { name: "Goals frame 1 · List (desktop)", el: wrap("workbench-viewer", createElement(Goals)), marker: "Aldercrest greenfield tagger successor programme" },
  { name: "Goals frame 1 · List subtitle derives the census", el: wrap("workbench-viewer", createElement(Goals)), marker: "3 active · 1 waiting on owner · 1 closed" },
  { name: "Goals frame 2 · Detail — the record (blocked pair served)", el: wrap("aldercrest", createElement(GoalDetail, { slug: "document-parsing-successor" })), marker: "Verified · main" },
  { name: "Goals frame 3 · Detail — the work (arms specimen)", el: wrap("aldercrest", createElement(GoalDetail, { slug: "document-parsing-successor" })), marker: "wb-armed-aldercrest-genre-defect-ruling-line-cure.json" },
  { name: "Goals frame 3 · Detail — the work (stall verdict)", el: wrap("aldercrest", createElement(GoalDetail, { slug: "document-parsing-successor" })), marker: "Stalled · 2 missed intervals" },
  { name: "Goals · Detail — completed goal (retired ping)", el: wrap("aldercrest", createElement(GoalDetail, { slug: "aldercrest-greenfield-tagger" })), marker: "Retired" },
];

export const results = CASES.map((c) => {
  try {
    const html = renderToString(c.el);
    return { name: c.name, ok: html.includes(c.marker), length: html.length, marker: c.marker };
  } catch (err) {
    return { name: c.name, ok: false, length: 0, marker: c.marker, error: err instanceof Error ? err.message : String(err) };
  }
});
