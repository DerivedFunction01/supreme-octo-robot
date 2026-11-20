// Scheduler view meta — the shell-facing half of the
// Scheduler mount (INTEGRATION.md §2): the nav, the
// active key, the search declaration, and the
// breadcrumb. Pure data and pure functions of the
// subroute, with no component imports, so the shell can
// import this module statically and render the full
// chrome (sidebar, breadcrumb, the route's H1,
// document.title) from the first paint, while the view's
// component tree loads as its own bundle chunk on first
// navigation (the per-view split: ./index assembles the
// full AppViewModule from this meta and its Component;
// src/App.tsx holds the seam).

import type { AppViewModule } from "../../lib/view-contract";

export const schedulerMeta: Omit<AppViewModule, "Component"> = {
  appId: "scheduler",
  nav: [
    { key: "overview", label: "Overview", href: "#/scheduler" },
    { key: "jobs", label: "Jobs", href: "#/scheduler/jobs" },
    { key: "pings", label: "Pings", href: "#/scheduler/pings" },
    { key: "ledger", label: "Ledger", href: "#/scheduler/ledger" },
  ],
  activeKey(subroute) {
    if (subroute === "/") return "overview";
    if (subroute === "/jobs" || subroute.startsWith("/jobs/")) return "jobs";
    if (subroute === "/pings") return "pings";
    if (subroute === "/ledger") return "ledger";
    return "";
  },
  // The TopBar search slot exists only where a surface
  // filters on it: the Jobs list (its client-side filter
  // over the served list). The original scheduler has no
  // search on Overview, Pings, Ledger, or the job detail
  // — and neither does this client — so the slot is not
  // rendered there (critic m-1, honest absence).
  searchPlaceholder(subroute) {
    return subroute === "/jobs" ? "Search jobs" : undefined;
  },
  crumb(subroute) {
    if (subroute === "/") return ["Scheduler", "Overview"];
    if (subroute === "/jobs") return ["Scheduler", "Jobs"];
    if (subroute.startsWith("/jobs/")) {
      return ["Scheduler", "Jobs", decodeURIComponent(subroute.slice("/jobs/".length))];
    }
    if (subroute === "/pings") return ["Scheduler", "Pings"];
    if (subroute === "/ledger") return ["Scheduler", "Ledger"];
    return ["Scheduler"];
  },
};
