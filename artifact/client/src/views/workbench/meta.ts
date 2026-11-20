// Workbench view meta — the shell-facing half of the
// Workbench mount (INTEGRATION.md §2): the nav, the
// active key, and the breadcrumb. Pure data and pure
// functions of the subroute, with no component imports,
// so the shell can import this module statically and
// render the full chrome (sidebar, breadcrumb, the
// route's H1, document.title) from the first paint,
// while the view's component tree loads as its own
// bundle chunk on first navigation (the per-view split:
// ./index assembles the full AppViewModule from this
// meta and its Component; src/App.tsx holds the seam).

import type { AppViewModule } from "../../lib/view-contract";

const SECTION_LABELS: Record<string, string> = {
  overview: "Overview",
  entries: "Entries",
  plans: "Plans",
  todos: "Todos",
  board: "Board",
};

export const workbenchMeta: Omit<AppViewModule, "Component"> = {
  appId: "workbench",
  nav: [
    { key: "home", label: "Home", href: "#/workbench" },
    { key: "projects", label: "Projects", href: "#/workbench/projects" },
    { key: "board", label: "Board", href: "#/workbench/board" },
    { key: "repos", label: "Repos", href: "#/workbench/repos" },
  ],
  activeKey(subroute) {
    if (subroute === "/") return "home";
    if (subroute === "/projects" || subroute.startsWith("/p/")) return "projects";
    if (subroute === "/board") return "board";
    if (subroute === "/repos" || subroute.startsWith("/repos/")) return "repos";
    return "";
  },
  crumb(subroute) {
    if (subroute === "/") return ["Workbench", "Home"];
    if (subroute === "/projects") return ["Workbench", "Projects"];
    if (subroute === "/board") return ["Workbench", "Board"];
    if (subroute === "/repos") return ["Workbench", "Repos"];
    if (subroute.startsWith("/repos/")) {
      return ["Workbench", "Repos", decodeURIComponent(subroute.slice("/repos/".length))];
    }
    if (subroute.startsWith("/p/")) {
      const parts = subroute.split("/").filter((p) => p.length > 0);
      const slug = parts[1] ? decodeURIComponent(parts[1]) : "";
      if (parts[2] === "preview") return ["Workbench", slug, "Preview"];
      const section = parts[2] ? (SECTION_LABELS[parts[2]] ?? parts[2]) : "";
      return ["Workbench", slug, section].filter((s) => s.length > 0);
    }
    if (subroute === "/settings") return ["Workbench", "Settings"];
    return ["Workbench"];
  },
  fillsContent(subroute) {
    // The entry preview (FU-1) is a full page of the
    // client: it alone fills the content region's height.
    // The parse mirrors crumb's: /p/<slug>/preview/<id>.
    if (!subroute.startsWith("/p/")) return false;
    const parts = subroute.split("/").filter((p) => p.length > 0);
    return parts[2] === "preview";
  },
};
