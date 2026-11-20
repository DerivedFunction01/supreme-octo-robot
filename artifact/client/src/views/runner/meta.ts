// Runner view meta — the shell-facing half of the
// Runner mount (INTEGRATION.md §2): the nav, the active
// key, and the breadcrumb. Pure data and pure functions
// of the subroute, with no component imports, so the
// shell can import this module statically and render
// the full chrome (sidebar, breadcrumb, the route's H1,
// document.title) from the first paint, while the view's
// component tree loads as its own bundle chunk on first
// navigation (the per-view split: ./index assembles the
// full AppViewModule from this meta and its Component;
// src/App.tsx holds the seam).

import type { AppViewModule } from "../../lib/view-contract";

export const runnerMeta: Omit<AppViewModule, "Component"> = {
  appId: "runner",
  nav: [
    { key: "leases", label: "Leases", href: "#/runner" },
    { key: "new", label: "New lease", href: "#/runner/new" },
    { key: "access", label: "Access", href: "#/runner/access" },
    { key: "budget", label: "Budget", href: "#/runner/budget" },
    { key: "events", label: "Events", href: "#/runner/events" },
    { key: "orphans", label: "Orphans", href: "#/runner/orphans" },
  ],
  activeKey(subroute) {
    if (subroute === "/" || subroute === "/leases" || subroute.startsWith("/leases/")) {
      return "leases";
    }
    if (subroute === "/new") return "new";
    if (subroute === "/access") return "access";
    if (subroute === "/budget") return "budget";
    if (subroute === "/events") return "events";
    if (subroute === "/orphans") return "orphans";
    return "";
  },
  crumb(subroute) {
    if (subroute === "/" || subroute === "/leases") return ["Runner", "Leases"];
    if (subroute.startsWith("/leases/")) {
      return ["Runner", "Leases", decodeURIComponent(subroute.slice("/leases/".length))];
    }
    if (subroute === "/new") return ["Runner", "New lease"];
    if (subroute === "/access") return ["Runner", "Access"];
    if (subroute === "/budget") return ["Runner", "Budget"];
    if (subroute === "/events") return ["Runner", "Events"];
    if (subroute === "/orphans") return ["Runner", "Orphans"];
    return ["Runner"];
  },
};
