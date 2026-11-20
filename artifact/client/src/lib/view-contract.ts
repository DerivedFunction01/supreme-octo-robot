// The composition contract between the shell and the four
// apps' view mounts (INTEGRATION.md §2–§3 states it in
// prose; this module is its code form). Each app owns one
// module under `src/views/<app>/` exporting an
// `AppViewModule`; the shell (App.tsx) renders the matched
// module inside the kit AppShell and knows nothing else
// about the app.

import type { ComponentType } from "react";

export type AppId = "workbench" | "scheduler" | "attention" | "runner";

/** Live nav counts reported by a view mount, keyed by its
 *  nav items' keys. `hot` renders the vermilion badge (the
 *  kit AppShell's CountBadge form — e.g. pings waiting). */
export type NavBadges = Record<string, { count: number; hot?: boolean }>;

export interface ViewProps {
  /** The route remainder inside the app's space, always
   *  beginning with "/"; "/" is the app's home route.
   *  Segments arrive URL-encoded, as the hash carried
   *  them — decode per segment, as the originals did. */
  subroute: string;
  /** Navigate anywhere in the one client by full hash
   *  (e.g. "#/scheduler/jobs/<id>", "#/settings", "#/"). */
  navigate: (hash: string) => void;
  /** Report live nav counts for the shell's badges.
   *  Call when the counts change; the shell holds the
   *  last reported set for the app. */
  onBadges: (badges: NavBadges) => void;
  /** The TopBar search text (shell-owned state). A view
   *  with a served-list surface filters client-side over
   *  the text — the faithful form, as no served search
   *  exists; a view without one ignores it. "" until the
   *  user types. */
  searchText: string;
}

export interface AppNavItem {
  /** Stable key: the badge key and the active-key space. */
  key: string;
  label: string;
  /** Full hash the shell navigates to for this item. */
  href: string;
}

export interface AppViewModule {
  appId: AppId;
  /** Sidebar destinations, in order (kit sheet: SidebarNav
   *  — destination rows with live count badges). */
  nav: AppNavItem[];
  /** The nav key active for a subroute; "" when none is
   *  (e.g. a detail route the lane keeps off the nav). */
  activeKey: (subroute: string) => string;
  /** Breadcrumb segments for the TopBar, app name first
   *  (e.g. ["Scheduler", "Jobs", "<id>"]). */
  crumb: (subroute: string) => string[];
  /** The TopBar search slot, declared PER SURFACE: the
   *  placeholder for a subroute whose view actually
   *  filters on ViewProps.searchText, or undefined where
   *  the surface has no search behaviour — the slot must
   *  not render there (honest absence: a chrome control
   *  that promises a search that does not exist is a
   *  defect, critic m-1). A module that declares this
   *  owns its app's whole search surface; the shell
   *  renders the slot exactly where this returns a
   *  placeholder. Modules without it keep the shell's
   *  per-app default. */
  searchPlaceholder?: (subroute: string) => string | undefined;
  /** Whether a subroute's view fills the content region's
   *  full height instead of sizing to its content —
   *  declared PER SURFACE, like the search slot. Where
   *  this returns true, the shell's <main> becomes a
   *  full-height flex column and the mount renders as its
   *  flexible child, so the AppShell scroller's definite
   *  height reaches the view: a surface built as a page
   *  (the workbench entry preview, FU-1) fills the page
   *  under the chrome. Where the member is absent or
   *  returns false, the main region sizes to content —
   *  the form every other surface renders in. */
  fillsContent?: (subroute: string) => boolean;
  Component: ComponentType<ViewProps>;
}
