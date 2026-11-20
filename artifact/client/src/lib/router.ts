// Hash routing — the ONE router of the one client.
//
//   #/                              the Launcher
//   #/settings                      the unified Settings view
//   #/workbench[/<subroute>]        the Workbench app's views
//   #/scheduler[/<subroute>]        the Scheduler app's views
//   #/attention[/<subroute>]        the Attention app's views
//   #/runner[/<subroute>]           the Runner app's views
//
// The first segment names the app; the remainder is the
// app's subroute, handed to its view mount verbatim
// (always beginning with "/"; "/" is the app's home).
// Each app's subroute grammar is its own — the workbench
// grammar is its restored `lib/routing.ts` table read
// against the remainder (see INTEGRATION.md §2) — the
// shell parses only the app segment. Unknown hashes land
// on the Launcher, never a blank.

import { useEffect, useState } from "react";
import type { AppId } from "./view-contract";

export type Route =
  | { view: "launcher" }
  | { view: "settings" }
  | { view: "app"; app: AppId; subroute: string };

export const APP_IDS: readonly AppId[] = [
  "workbench",
  "scheduler",
  "attention",
  "runner",
];

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, "");
  const parts = raw.split("/").filter((part) => part.length > 0);
  if (parts.length === 0) return { view: "launcher" };
  const [head, ...rest] = parts as [string, ...string[]];
  if (head === "settings" && rest.length === 0) return { view: "settings" };
  if ((APP_IDS as readonly string[]).includes(head)) {
    return {
      view: "app",
      app: head as AppId,
      subroute: rest.length > 0 ? `/${rest.join("/")}` : "/",
    };
  }
  return { view: "launcher" };
}

export function navigate(hash: string): void {
  if (window.location.hash !== hash) {
    window.location.hash = hash;
  }
}

export function launcherHref(): string {
  return "#/";
}

export function settingsHref(): string {
  return "#/settings";
}

export function appHref(app: AppId): string {
  return `#/${app}`;
}

/** Reactive route: re-renders the caller on hashchange. */
export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    onChange();
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
