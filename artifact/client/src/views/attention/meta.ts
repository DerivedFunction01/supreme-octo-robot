// Attention view meta — the shell-facing half of the
// Attention mount (INTEGRATION.md §2): the nav, the
// active key, and the breadcrumb. Pure data and pure
// functions of the subroute, with no component imports,
// so the shell can import this module statically and
// render the full chrome (sidebar, breadcrumb, the
// route's H1, document.title) from the first paint,
// while the view's component tree loads as its own
// bundle chunk on first navigation (the per-view split:
// ./index assembles the full AppViewModule from this
// meta and its Component; src/App.tsx holds the seam).
//
// Presence is NOT part of the split: it is the shell's
// own served state (§6), bound in ./presence and
// ./settings-sections, which the shell imports
// statically as before.

import type { AppViewModule } from "../../lib/view-contract";

export const attentionMeta: Omit<AppViewModule, "Component"> = {
  appId: "attention",
  nav: [
    { key: "today", label: "Today", href: "#/attention" },
    { key: "digest", label: "Digest", href: "#/attention/digest" },
    { key: "handlers", label: "Handlers", href: "#/attention/handlers" },
    { key: "rules", label: "Rules", href: "#/attention/rules" },
    { key: "registries", label: "Registries", href: "#/attention/registries" },
  ],
  activeKey(subroute) {
    if (subroute === "/" || subroute === "/today") return "today";
    if (subroute === "/handlers" || subroute.startsWith("/handlers/")) return "handlers";
    if (subroute === "/digest") return "digest";
    if (subroute === "/rules") return "rules";
    if (subroute === "/registries") return "registries";
    return "";
  },
  crumb(subroute) {
    if (subroute === "/" || subroute === "/today") return ["Attention", "Today"];
    if (subroute === "/handlers") return ["Attention", "Handlers"];
    if (subroute.startsWith("/handlers/")) {
      return ["Attention", "Handlers", decodeURIComponent(subroute.slice("/handlers/".length))];
    }
    if (subroute === "/digest") return ["Attention", "Digest"];
    if (subroute === "/rules") return ["Attention", "Rules"];
    if (subroute === "/registries") return ["Attention", "Registries"];
    return ["Attention"];
  },
};
