// State routing — the ONE router of the one client.
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
// shell parses only the app segment. Unknown routes land
// on the Launcher, never a blank.
//
// The route VALUES keep the hash grammar above — every
// href builder in the client produces them and parseHash
// reads them — but the route itself is shell STATE, not
// the document URL: no navigation path mutates
// window.location. The desktop viewer serves the app
// document as a blob: URL and blocks fragment navigation
// on it as a resource load, so under a hash router the
// clicks landed, the handlers ran, and the view never
// swapped (desktop click probe, Step 4); in-page state
// routing is the form that survives both viewers. The
// store below is the one instance: navigate() writes it
// and useRoute() subscribes the shell's render to it.

import {
  useSyncExternalStore,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from "react";
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

/* The route store: the current route VALUE (a string in
 * the grammar above), held as state. It is seeded once,
 * at module load, from the document's hash where one is
 * present — a deep link or bookmark still lands on its
 * surface, exactly as the hash router's first parse did —
 * and "#/" (the Launcher) where it is not. That seed is
 * the store's only read of window.location; after it,
 * the value lives only here and nothing writes the URL. */
let currentRouteValue: string =
  typeof window !== "undefined" && window.location.hash
    ? window.location.hash
    : "#/";
const routeListeners = new Set<() => void>();

export function navigate(hash: string): void {
  if (hash === currentRouteValue) return;
  currentRouteValue = hash;
  for (const listener of routeListeners) listener();
}

function subscribeRoute(listener: () => void): () => void {
  routeListeners.add(listener);
  return () => {
    routeListeners.delete(listener);
  };
}

function routeSnapshot(): string {
  return currentRouteValue;
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

/** Reactive route: re-renders the caller when the route
 * state changes. The Route shape is the one the shell
 * has always consumed, now sourced from the store. */
export function useRoute(): Route {
  return parseHash(useSyncExternalStore(subscribeRoute, routeSnapshot, routeSnapshot));
}

/** An in-client link: renders a real anchor carrying its
 * href — the route value stays visible and copyable and
 * the element keeps anchor semantics — but a plain click
 * routes through the store and the default fragment
 * navigation never runs, so the click works in viewers
 * that block fragment navigation. Modified clicks (new
 * tab or window, middle-click) and clicks a caller's own
 * onClick already claimed keep the browser's behaviour. */
export function RouteLink({
  href,
  onClick,
  children,
  ...rest
}: AnchorHTMLAttributes<HTMLAnchorElement> & {
  href?: string;
  children?: ReactNode;
}) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      !href ||
      event.button !== 0 ||
      event.metaKey ||
      event.altKey ||
      event.ctrlKey ||
      event.shiftKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(href);
  };
  return (
    <a href={href} onClick={handleClick} {...rest}>
      {children}
    </a>
  );
}
