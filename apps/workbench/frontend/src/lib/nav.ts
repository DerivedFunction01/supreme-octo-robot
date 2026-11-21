import { createContext, useContext } from "react";
import type { SaveResult } from "./seam";

// Navigation state for the one shell (contract 09). Sections
// are the storyboard's sidebar destinations; drill-ins are
// targets within them.

export type NavTarget =
  | { section: "home" }
  | { section: "overview" }
  | { section: "goals" }
  | { section: "goal"; slug: string }
  | { section: "mockups" }
  | { section: "mockup"; entryId: string }
  | { section: "entries" }
  | { section: "plans"; bundle?: string }
  | { section: "todos" }
  | { section: "board" }
  | { section: "inbox" }
  | { section: "code" }
  | { section: "repo"; repo: string }
  | { section: "browse"; repo: string; path: string[] }
  | { section: "peek"; repo: string; path: string; tab?: "content" | "diff" | "table" }
  | { section: "editor"; repo: string; path: string }
  | { section: "settings" };

/** The editor's unsaved-changes guard (storyboard frame 13):
 *  registered by the Editor while it holds a dirty draft. */
export interface EditorGuard {
  fileName: string;
  sha: string;
  save: () => Promise<SaveResult>;
  discard: () => void;
}

export interface NavApi {
  nav: NavTarget;
  navigate: (t: NavTarget) => void;
  /** The project the project-scoped sections operate on. */
  project: string;
  setProject: (slug: string) => void;
  setEditorGuard: (g: EditorGuard | null) => void;
}

export const NavContext = createContext<NavApi>({
  nav: { section: "home" },
  navigate: () => {},
  project: "spec-driven-starter",
  setProject: () => {},
  setEditorGuard: () => {},
});

export function useNav(): NavApi {
  return useContext(NavContext);
}

/** Which sidebar destination a target belongs to. */
export function sidebarKey(nav: NavTarget): string {
  switch (nav.section) {
    case "home":
      return "home";
    case "overview":
      return "overview";
    case "goals":
    case "goal":
      return "goals";
    case "mockups":
    case "mockup":
      return "mockups";
    case "entries":
      return "entries";
    case "plans":
      return "plans";
    case "todos":
      return "todos";
    case "board":
      return "board";
    case "inbox":
      return "inbox";
    case "code":
    case "repo":
    case "browse":
    case "peek":
    case "editor":
      return "code";
    case "settings":
      return "settings";
  }
}
