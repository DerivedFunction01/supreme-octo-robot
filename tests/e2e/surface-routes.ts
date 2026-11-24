/**
 * The surface census: every user-facing route the rendered
 * legs (qa-axe, qa-geometry, qa-truncation, qa-dead-click,
 * qa-parity) measure, enrolled here — the legs iterate this
 * file and nothing else, so a route no leg can see is a
 * route no leg pretends to cover.
 *
 * Enrollment discipline (docs/checks.md, rendered legs): a
 * route joins the census when it is built, not after it
 * breaks. A route that cannot yet pass a leg is enrolled
 * with the measured failure recorded beside it and named in
 * the leg's report — the record carries the defect; it does
 * not excuse it, and the route's bars apply in full when the
 * defect is fixed. A route with an approved design reference
 * also joins the parity manifest (parity-views.ts); a route
 * in neither file is unenrolled, and the project keeps the
 * two files complete against its router by its own census
 * check (the starter's route_coverage scanner enrolls the
 * backend's routes; the rendered census is this file).
 *
 * `pattern` is the router's route (dynamic segments as
 * [param]); `path` is the concrete seeded path the legs
 * drive. `landmarks` names the navigation-chrome landmark
 * selectors the dead-click sweep works over on this route.
 * `rendered: false` marks a transport route (a JSON or
 * download endpoint): enrolled so the census is complete,
 * skipped by every rendered leg by name.
 *
 * THIS PROJECT's router is the one client's hash router
 * (artifact/client/src/lib/router.ts; grammar of record in
 * artifact/client/INTEGRATION.md §2): the first hash segment
 * names the app, the remainder is the app's subroute. The
 * census below enrolls every route that grammar carries.
 * The client is a single document, so every concrete path
 * is the document root plus its hash.
 *
 * Landmarks: an app route's chrome is the kit AppShell —
 * the sidebar (the Apps button, the app's nav, and the
 * settings footer nav, all inside the one container div
 * whose direct child is `nav[aria-label="<App>"]`) and the
 * TopBar breadcrumb (`nav[aria-label="Breadcrumb"]`). The
 * Launcher and the unified Settings are shell routes
 * outside AppShell; each renders its own <main>, and the
 * main is the landmark the sweep works over.
 *
 * Breadcrumb record (measured against the client of
 * record): the breadcrumb renders its crumbs
 * as plain <span>s (App.tsx's Crumb component) — it
 * carries no a[href] and no button, so the sweep collects
 * ZERO candidates on every app route's Breadcrumb
 * landmark and that pass is vacuous: it proves the
 * landmark renders, nothing about controls. The landmark
 * stays enrolled — a crumb that grows controls is priced
 * the day it does — but no report may count it as control
 * coverage.
 *
 * Seeded-state record (the beside-the-entry record the
 * discipline above requires): the suite's serve route
 * (tests/e2e/serve.mjs) answers the two reads the shell's
 * own unboundary'd Settings sections consume (getGlance,
 * getDigest) with the real backend's empty-state shapes,
 * held in the serve's in-memory seeded state; the two
 * writes those sections post (postPresence,
 * postDigestPrefs) land in that state and are served
 * back, so a control's effect is measured against the
 * state the real path would paint; every other action
 * answers a canned success envelope carrying an empty
 * payload — guarded writes, per the leg's own rule
 * (docs/checks.md). Project, repo, job, handler, and
 * lease detail routes therefore render the surface the
 * seeded state serves (an empty state, or the
 * workbench's not-in-the-current-sweep notice for the
 * census project slug `e2e-census`), inside intact
 * chrome. The legs measure the chrome on those routes
 * exactly as served; populated-state measurement of a
 * detail route joins when the suite's seeded state grows
 * the fixture for it.
 */

export interface SurfaceRoute {
  pattern: string;
  path: string;
  rendered: boolean;
  landmarks?: string[];
}

const appLandmarks = (appName: string): string[] => [
  `div:has(> nav[aria-label="${appName}"])`,
  `nav[aria-label="Breadcrumb"]`,
];

export const SURFACE_ROUTES: SurfaceRoute[] = [
  // The shell routes (artifact/client/src/lib/router.ts).
  { pattern: "/", path: "/#/", rendered: true, landmarks: ["main"] },
  // The annotations landing (mega repo a3333569) deleted the
  // standalone Inbox view: #/inbox is an unknown hash and
  // lands on the Launcher (the DOM verdict of record is
  // inbox_lands_on_home). Enrolled so the census prices the
  // landing, not a memory of the deleted view.
  { pattern: "/inbox", path: "/#/inbox", rendered: true, landmarks: ["main"] },
  // Measured failure of record, since cured: in gate
  // run workhorse-s4-gate-20261119T091942Z the sweep priced
  // every control in this landmark except the two
  // unselected expiry presets ("At 5:00 PM", "Tomorrow,
  // 8:00 AM"), which read not-actionable / "control
  // vanished" — unmeasured, not dead. Root cause, verified
  // from the client source: PresenceSection's delegated
  // readiness requires the shell prop expiry to agree with
  // the section's own glance expiry — fetched once per
  // mount, so frozen at the mount-time value — or with
  // lastPostedIso, the bridge recording the expiry the
  // section just posted. The bridge-clearing effect spent
  // the bridge on prop–glance agreement alone, which is
  // already true of the pre-post values in the very commit
  // that sets the bridge; when the postPresence response
  // then moved the prop to the new expiry (the backend
  // returns presence_view over the posted body — the
  // contract side is sound), the prop disagreed with the
  // frozen glance for the life of the mount and the
  // section sat in "still syncing" with both radio groups
  // unmounted (probe workhorse-s4-probe2-20261119T073107Z,
  // phase C). Mode posts, which never diverge prop from
  // glance, converged — the asymmetry that identified the
  // mechanism. The cure (settings-sections.tsx): the
  // bridge is spent only once the prop has converged to
  // the posted value AND the read corroborates it. Proof:
  // probe workhorse-s4-probe4-20261119T101346Z — a
  // DOM-level scenario (expiry posts "In 1 hour" →
  // evening → morning → "No expiry" → a mode post, the
  // section ready throughout) plus the full census at
  // 66/66 — and the re-gate of record on this snapshot.
  // The route's bar applies in full; no control in this
  // landmark is excused.
  { pattern: "/settings", path: "/#/settings", rendered: true, landmarks: ["main"] },

  // Workbench (subroute grammar: INTEGRATION.md §2).
  { pattern: "/workbench", path: "/#/workbench", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/projects", path: "/#/workbench/projects", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/board", path: "/#/workbench/board", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/repos", path: "/#/workbench/repos", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/repos/[id]", path: "/#/workbench/repos/e2e-census", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/settings", path: "/#/workbench/settings", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/p/[slug]/overview", path: "/#/workbench/p/e2e-census/overview", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/p/[slug]/entries", path: "/#/workbench/p/e2e-census/entries", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/p/[slug]/entries/[item]", path: "/#/workbench/p/e2e-census/entries/e2e-census", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/p/[slug]/plans", path: "/#/workbench/p/e2e-census/plans", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/p/[slug]/todos", path: "/#/workbench/p/e2e-census/todos", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/p/[slug]/board", path: "/#/workbench/p/e2e-census/board", rendered: true, landmarks: appLandmarks("Workbench") },
  { pattern: "/workbench/p/[slug]/preview/[entryId]", path: "/#/workbench/p/e2e-census/preview/e2e-census", rendered: true, landmarks: appLandmarks("Workbench") },

  // Scheduler (subroute grammar: INTEGRATION.md §2).
  { pattern: "/scheduler", path: "/#/scheduler", rendered: true, landmarks: appLandmarks("Scheduler") },
  { pattern: "/scheduler/jobs", path: "/#/scheduler/jobs", rendered: true, landmarks: appLandmarks("Scheduler") },
  { pattern: "/scheduler/jobs/[id]", path: "/#/scheduler/jobs/e2e-census", rendered: true, landmarks: appLandmarks("Scheduler") },
  { pattern: "/scheduler/pings", path: "/#/scheduler/pings", rendered: true, landmarks: appLandmarks("Scheduler") },
  { pattern: "/scheduler/ledger", path: "/#/scheduler/ledger", rendered: true, landmarks: appLandmarks("Scheduler") },

  // Attention (subroute grammar: INTEGRATION.md §2;
  // Presence and Digest settings are not routes — §6).
  { pattern: "/attention", path: "/#/attention", rendered: true, landmarks: appLandmarks("Attention") },
  { pattern: "/attention/digest", path: "/#/attention/digest", rendered: true, landmarks: appLandmarks("Attention") },
  { pattern: "/attention/handlers", path: "/#/attention/handlers", rendered: true, landmarks: appLandmarks("Attention") },
  { pattern: "/attention/handlers/[handle]", path: "/#/attention/handlers/e2e-census", rendered: true, landmarks: appLandmarks("Attention") },
  { pattern: "/attention/rules", path: "/#/attention/rules", rendered: true, landmarks: appLandmarks("Attention") },
  { pattern: "/attention/registries", path: "/#/attention/registries", rendered: true, landmarks: appLandmarks("Attention") },

  // Runner (subroute grammar: INTEGRATION.md §2).
  { pattern: "/runner", path: "/#/runner", rendered: true, landmarks: appLandmarks("Runner") },
  { pattern: "/runner/leases/[id]", path: "/#/runner/leases/e2e-census", rendered: true, landmarks: appLandmarks("Runner") },
  { pattern: "/runner/new", path: "/#/runner/new", rendered: true, landmarks: appLandmarks("Runner") },
  { pattern: "/runner/access", path: "/#/runner/access", rendered: true, landmarks: appLandmarks("Runner") },
  { pattern: "/runner/budget", path: "/#/runner/budget", rendered: true, landmarks: appLandmarks("Runner") },
  { pattern: "/runner/events", path: "/#/runner/events", rendered: true, landmarks: appLandmarks("Runner") },
  { pattern: "/runner/orphans", path: "/#/runner/orphans", rendered: true, landmarks: appLandmarks("Runner") },
];

export const RENDERED_ROUTES: SurfaceRoute[] = SURFACE_ROUTES.filter(
  (route) => route.rendered,
);

/**
 * The appearance modes the legs exercise, in order. A
 * product with one appearance carries ["light"]; a product
 * with a second mode adds it here and implements the switch
 * in qa-fixtures.ts (applyMode) — the legs pick the axis up
 * from this list, never from their own constants.
 *
 * This product's mode axis (artifact/client/src/lib/
 * appearance.ts) is light/dark, riding the document root's
 * data-mode attribute; "system" is the absence of the
 * attribute, not a third mode the legs exercise.
 */
export const SURFACE_MODES = ["light", "dark"] as const;
export type SurfaceMode = (typeof SURFACE_MODES)[number];
