// Hash routing — the route table (repo-home spec §2, as
// amended for this build).
//
// ONE-CLIENT SEAM (INTEGRATION.md §2): this table is the
// workbench app's subroute grammar inside the one client.
// parseRoute consumes the subroute the shell hands the
// mount, re-prefixed with "#" by the caller (the subroute
// "/p/<slug>/entries" parses exactly as the standalone
// hash "#/p/<slug>/entries" did). The href builders
// produce FULL client hashes — the original's "#/…"
// forms prefixed with "/workbench" — so every link and
// navigate() call in the ported sections routes within
// the one client. The grammar
// below is stated in the app's own segment terms:
//
//   #/                          workspace home (repo-home §4)
//   #/settings                  Settings (app-level)
//   #/projects                  the project chooser (the
//                               Project tab's target when no
//                               project is in scope)
//   #/p/<slug>/overview         per-project Overview (repo-home
//                               §4) — the FIRST per-project tab,
//                               ahead of the viewer's sections
//   #/p/<slug>/entries          per-project sections…
//   #/p/<slug>/entries/<id>     …with an optional item segment
//                               (the retired mockups/artifacts
//                               segments map here at parse time)
//   #/p/<slug>/preview/<id>     one entry's page as a full
//                               page of the client (FU-1,
//                               owner ruling) —
//                               the drill-in's door navigates
//                               here; the page's own top bar
//                               backs out to the drill-in
//   #/p/<slug>/plans[/<path>]   (the plans item is a file path
//   #/p/<slug>/todos             and may itself contain slashes)
//   #/p/<slug>/board
//   #/board                     the cross-project board
//   #/p/<slug>/code             the project's Code facet
//                               (SPEC §21): git status,
//                               files, and history inside
//                               the project's own grammar
//   #/repos[/<id>]               LEGACY (SPEC §21): the
//                               retired Repos destination;
//                               parses so the routes layer
//                               can resolve the id through
//                               the project index and land
//                               on the owning project's
//                               Code section
//
// Unknown routes land on the default view, never a blank
// (ui-context). Parsing is pure so App stays declarative.

export type SectionId = "overview" | "entries" | "plans" | "todos" | "board" | "code";

export const SECTION_IDS: SectionId[] = ["overview", "entries", "plans", "todos", "board", "code"];

// The retired collection segments (the
// unification): old hashes in messages and bookmarks
// land on the unified section, item segment preserved.
const RETIRED_SECTION_SEGMENTS: Record<string, SectionId> = {
  mockups: "entries",
  artifacts: "entries",
};

export type Route =
  | { view: "home" }
  | { view: "settings" }
  | { view: "picker" }
  | { view: "section"; slug: string; section: SectionId; item: string | null }
  | { view: "entry-page"; slug: string; entryId: string }
  | { view: "board-all" }
  | { view: "repos"; repoId: string | null };

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, "");
  const parts = raw.split("/").filter((part) => part.length > 0);
  if (parts.length === 0) return { view: "home" };
  if (parts[0] === "settings" && parts.length === 1) return { view: "settings" };
  if (parts[0] === "projects" && parts.length === 1) return { view: "picker" };
  if (parts[0] === "board" && parts.length === 1) return { view: "board-all" };
  if (parts[0] === "repos") {
    const repoId = parts.length > 1 ? parts.slice(1).map(decodeURIComponent).join("/") : null;
    return { view: "repos", repoId };
  }
  if (parts[0] === "p" && parts.length >= 3) {
    const slug = decodeURIComponent(parts[1] ?? "");
    if (slug && parts[2] === "preview" && parts.length >= 4) {
      const entryId = parts.slice(3).map(decodeURIComponent).join("/");
      if (entryId) return { view: "entry-page", slug, entryId };
    }
    const section = (RETIRED_SECTION_SEGMENTS[parts[2] ?? ""] ?? parts[2]) as SectionId;
    if (slug && SECTION_IDS.includes(section)) {
      const item = parts.length > 3 ? parts.slice(3).map(decodeURIComponent).join("/") : null;
      return { view: "section", slug, section, item };
    }
  }
  return { view: "home" };
}

export function homeHref(): string {
  return "#/workbench/";
}

export function settingsHref(): string {
  return "#/workbench/settings";
}

export function boardAllHref(): string {
  return "#/workbench/board";
}

/** The project chooser (the Project tab's destination
 * when no project is in scope): a list, never a jump
 * into whichever project an ordering happens to put
 * first. */
export function pickerHref(): string {
  return "#/workbench/projects";
}

export function sectionHref(slug: string, section: SectionId, item?: string | null): string {
  const base = `#/workbench/p/${encodeURIComponent(slug)}/${section}`;
  return item ? `${base}/${item.split("/").map(encodeURIComponent).join("/")}` : base;
}

/** One entry's full-page preview (FU-1): the drill-in's
 * door navigates here, and the page's back control
 * returns to the drill-in (sectionHref with the entry
 * as the item). */
export function entryPageHref(slug: string, entryId: string): string {
  const base = `#/workbench/p/${encodeURIComponent(slug)}/preview`;
  return `${base}/${entryId.split("/").map(encodeURIComponent).join("/")}`;
}

/** A legacy Repos address (SPEC §21): kept so old
 * links and the tracking panel's row links still land —
 * the routes layer resolves the id through the project
 * index and redirects to the project's Code section.
 * The id's segments are encoded individually, like a
 * plans item. */
export function reposHref(repoId?: string | null): string {
  if (!repoId) return "#/workbench/repos";
  return `#/workbench/repos/${repoId.split("/").map(encodeURIComponent).join("/")}`;
}

/** The project a route is scoped to, when it has one. */
export function routeSlug(route: Route): string | null {
  return route.view === "section" ? route.slug : null;
}
