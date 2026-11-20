// Phone-form render harness for scripts/render-smoke.mjs —
// same idea as render-harness.tsx, but the matchMedia stub
// (./phone-stub, imported first) makes the kit's useIsPhone
// seam report a phone viewport, so the shell's phone
// presentation — the kit PhoneShell (contract 09) — and the
// explorer/peek phone forms render. Asserts the PhoneShell
// forms are present AND the desktop two-pane sidebar is
// absent.
//
// The PhoneShell is index-first: at a root section it
// renders its grouped-list index (the section's content
// opens pushed, on tap — a state server rendering cannot
// reach), so root-section phone forms are asserted by
// rendering the section directly, as the desktop harness
// does; pushed detail screens and the full-bleed sections
// are asserted through the Shell itself. Not part of the
// app bundle.

import "./phone-stub";
import { renderToString } from "react-dom/server";
import { createElement } from "react";
import { AdapterContext } from "../src/lib/store";
import { MockWorkbenchAdapter } from "../src/lib/mockAdapter";
import { NavContext, type NavApi, type NavTarget } from "../src/lib/nav";
import { Shell } from "../src/components/Shell";
import { Home } from "../src/sections/Home";
import { Editor } from "../src/sections/Editor";
import { Browse, PeekPage } from "../src/sections/Explorer";
import { GoalDetail, Goals } from "../src/sections/Goals";

const adapter = new MockWorkbenchAdapter(() => new Date("2026-11-13T14:36:00.000Z"));

function navFor(project: string, nav: NavTarget = { section: "home" }): NavApi {
  return {
    nav,
    navigate: () => {},
    project,
    setProject: () => {},
    setEditorGuard: () => {},
  };
}

function wrap(project: string, el: React.ReactNode, nav?: NavTarget) {
  return createElement(
    AdapterContext.Provider,
    { value: adapter },
    createElement(NavContext.Provider, { value: navFor(project, nav) }, el),
  );
}

const CASES: { name: string; el: React.ReactNode; marker: string; absent?: string }[] = [
  {
    name: "Phone shell · PhoneShell index (grouped nav + live counts, no desktop sidebar)",
    el: wrap("fennelwick", createElement(Shell, null, createElement(Home))),
    marker: "Goals",
    absent: "flex-[0_0_224px]",
  },
  {
    name: "Phone shell · PhoneShell pushed detail — Goals frame 5 (blocked basis notice + pair, no sidebar)",
    el: wrap(
      "aldercrest",
      createElement(Shell, null, createElement(GoalDetail, { slug: "document-parsing-successor" })),
      { section: "goal", slug: "document-parsing-successor" },
    ),
    marker: "Blocked basis",
    absent: "flex-[0_0_224px]",
  },
  {
    name: "Phone shell · Goals frame 4 — list phone form (owner-waiting line)",
    el: wrap("workbench-viewer", createElement(Goals)),
    marker: "Owner waiting · Genre ruling-line cure",
  },
  {
    name: "Phone shell · Home phone form renders",
    el: wrap("fennelwick", createElement(Home)),
    marker: "Awaiting review",
  },
  {
    name: "Phone shell · Frame 15 explorer (Browse engages PhoneExplorer)",
    el: wrap("fennelwick", createElement(Shell, { hideTopbar: true }, createElement(Browse, { repoSlug: "aldercrest", trail: [] }))),
    marker: "Show hidden",
  },
  {
    name: "Phone shell · Frame 17 peek (PeekPage engages PhonePeek)",
    el: wrap("fennelwick", createElement(Shell, { hideTopbar: true }, createElement(PeekPage, { repoSlug: "aldercrest", path: "docs/scanners.md" }))),
    marker: "Guarded save",
  },
  {
    name: "Phone shell · Editor with degraded banner (editing off)",
    el: wrap("fennelwick", createElement(Shell, { hideTopbar: true }, createElement(Editor, { repoSlug: "aldercrest", path: "AGENTS.md" }))),
    marker: "Editing is off for this viewer.",
  },
];

export const results = CASES.map((c) => {
  try {
    const html = renderToString(c.el);
    const ok = html.includes(c.marker) && (c.absent === undefined || !html.includes(c.absent));
    return { name: c.name, ok, length: html.length, marker: c.marker, absent: c.absent };
  } catch (err) {
    return {
      name: c.name,
      ok: false,
      length: 0,
      marker: c.marker,
      absent: c.absent,
      error: err instanceof Error ? err.message : String(err),
    };
  }
});
