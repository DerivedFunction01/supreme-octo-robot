// App — the one client's shell composition (owner ruling,
// audit Addendum 3: ONE app — one client, one
// bundle, one router, the four apps as views on the
// unified kit).
//
// The shell owns exactly: the route (lib/router.ts), the
// appearance state (lib/appearance.ts — applied once at
// the document root), the presence state (bound to the
// attention actions by the attention lane, §6 of
// INTEGRATION.md), the per-app nav badges the view mounts
// report, and the chrome — the Launcher and Settings as
// shell views, and the kit AppShell around every app view
// (SidebarNav with the Apps back-row, per-app destinations
// with badge slots, the Settings foot; TopBar with the
// breadcrumb, the search slot, and the presence control).
//
// The shell holds NO app data and NO transport of its own:
// views call the single action layer (lib/actions.ts)
// directly. There are no iframes, no postMessage relay,
// and no per-app documents — the composition this file
// replaced (the frame shell) is deleted, not extended.
//
// The one bundle carries every view (the per-view
// split of perf lane L-D retired — the CVM
// publish stage accepts exactly one JS bundle): the
// dynamic imports below are inlined into the single
// entry chunk by the canonical build, so each app
// view's component tree arrives with the bundle. What the shell
// needs synchronously — each mount's nav, active key,
// search declaration, and crumb — lives in the views'
// meta modules (views/<app>/meta.ts: pure data and pure
// functions, no component imports), which the shell
// imports statically, so the chrome (sidebar, breadcrumb,
// the route's one H1, document.title) is complete from
// the first paint and only the content region waits on
// the chunk. Still one client, one document, one router,
// one action layer — only the bytes move.

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
  type CSSProperties,
  type ReactNode,
} from "react";
import { AppShell } from "@workhorse/kit/components/shell/AppShell";
import { useIsPhone } from "@workhorse/kit/lib/responsive";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { Input } from "@workhorse/kit/components/controls/Fields";
import { SectionBoundary } from "@workhorse/kit/components/shell/SectionBoundary";
import { useAppearance } from "./lib/appearance";
import { launcherHref, navigate, settingsHref, useHashRoute } from "./lib/router";
import type { AppId, AppViewModule, NavBadges, ViewProps } from "./lib/view-contract";
import { APP_META, SettingsGlyph } from "./shell/apps";
import { Launcher } from "./shell/Launcher";
import { PresenceControl, type PresenceState } from "./shell/PresenceControl";
import { Settings } from "./shell/Settings";
import { attentionMeta } from "./views/attention/meta";
import { useServedPresence } from "./views/attention/presence";
import { runnerMeta } from "./views/runner/meta";
import { schedulerMeta } from "./views/scheduler/meta";
import { workbenchMeta } from "./views/workbench/meta";

/** The shell-facing half of each mount (INTEGRATION.md
 *  §2), imported statically: nav, active key, search
 *  declaration, crumb — everything the chrome renders
 *  before any view code has loaded. */
const VIEW_META: Record<AppId, Omit<AppViewModule, "Component">> = {
  workbench: workbenchMeta,
  scheduler: schedulerMeta,
  attention: attentionMeta,
  runner: runnerMeta,
};

/** Each app view's component tree, mounted on first
 *  navigation to the app: the dynamic imports are the
 *  mount seam — under the canonical single-bundle build
 *  the bundler inlines them into the one entry chunk, so
 *  the module is already present and React.lazy resolves
 *  it in place. A module that fails to load throws into
 *  the SectionBoundary at the mount (below) and renders
 *  its fallback — the client's
 *  error form — never a blank. The assembled AppViewModule
 *  each view exports stays the contract of record; the
 *  shell takes only its Component from the lazy module,
 *  and the rest from the meta above. */
const LAZY_COMPONENTS: Record<AppId, ComponentType<ViewProps>> = {
  workbench: lazy(() =>
    import("./views/workbench").then((m) => ({ default: m.workbenchView.Component })),
  ),
  scheduler: lazy(() =>
    import("./views/scheduler").then((m) => ({ default: m.schedulerView.Component })),
  ),
  attention: lazy(() =>
    import("./views/attention").then((m) => ({ default: m.attentionView.Component })),
  ),
  runner: lazy(() =>
    import("./views/runner").then((m) => ({ default: m.runnerView.Component })),
  ),
};

/** The route's section name — the shell H1's text,
 *  document.title's first segment, and the PhoneShell
 *  title (critic M-5): segment 2 of the view module's
 *  own crumb, with one exception. On workbench project
 *  subroutes ("/p/<slug>/…") the crumb is
 *  [Workbench, <slug>, <section>, …]: segment 2 is the
 *  project slug — a detail id, and the H1 names the
 *  section, never the detail id (F4 census follow-up) —
 *  so the shell takes segment 3 there. The breadcrumb
 *  itself is untouched: it keeps the slug as path.
 *  Every other route selects exactly as before. */
function sectionNameFor(app: AppId, subroute: string): string {
  const crumbs = VIEW_META[app].crumb(subroute);
  if (app === "workbench" && subroute.startsWith("/p/")) {
    return crumbs[2] ?? crumbs[1] ?? APP_META[app].name;
  }
  return crumbs[1] ?? APP_META[app].name;
}

/** Apps whose storyboards carry a TopBar search field
 *  (scheduler frame: "Search jobs"; workbench: the
 *  explorer/search surfaces). The slot is the kit Input;
 *  the shell owns the text and hands it to the view mount
 *  through ViewProps.searchText — views filter
 *  client-side over their served lists (no served search
 *  exists; INTEGRATION.md §2). */
const SEARCH_APPS: Partial<Record<AppId, string>> = {
  scheduler: "Search jobs",
  workbench: "Search",
};

/** TopBar reflow seam (critic B-3): the three-slot TopBar
 *  (breadcrumb + presence + search) does not fit the
 *  content column at tablet widths — the presence control
 *  wraps over the breadcrumb. At or below this width the
 *  shell relocates the search slot to a second row at the
 *  head of the content region (the same search-under-the-
 *  header form the kit's PhoneShell uses), leaving the
 *  bar itself two slots that fit. Above it, and on phone
 *  (where the PhoneShell owns the composition), the bar
 *  is unchanged. */
const TOPBAR_REFLOW_QUERY = "(max-width: 1024px)";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

/** The shell's page-title style — the token form the
 *  views' own section titles use (workbench shared
 *  sectionTitleStyle), so the shell H1 and the views'
 *  remaining headings read as one system. */
const SHELL_TITLE_STYLE: CSSProperties = {
  fontSize: "var(--ui-font-size-xl)",
  lineHeight: "var(--ui-line-height-xl)",
  fontWeight: 600,
  letterSpacing: "-0.011em",
  margin: "0 0 var(--ui-space-16)",
};

function Crumb({ segments }: { segments: string[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-[8px] text-[14px]">
      {segments.map((segment, i) => (
        <span key={i} className="flex min-w-0 items-center gap-[8px]">
          {i > 0 ? (
            <span aria-hidden style={{ color: "var(--ui-content-muted)" }}>
              /
            </span>
          ) : null}
          <span
            className="truncate"
            style={{
              color:
                i === segments.length - 1
                  ? "var(--ui-content-primary)"
                  : "var(--ui-content-secondary)",
              fontWeight: i === segments.length - 1 ? 650 : 500,
            }}
          >
            {segment}
          </span>
        </span>
      ))}
    </nav>
  );
}

export default function App() {
  const route = useHashRoute();
  const [appearance, updateAppearance] = useAppearance();
  // Presence is attention's SERVED state (INTEGRATION.md
  // §6, bound by the attention lane): the hook reads it
  // via getGlance and writes via postPresence, so the
  // TopBar control, the Launcher widget, and the Settings
  // PresenceSection all read and write the one state.
  const servedPresence = useServedPresence();
  const presence: PresenceState = servedPresence.mode;
  const [badgesByApp, setBadgesByApp] = useState<Partial<Record<AppId, NavBadges>>>({});
  const [searchText, setSearchText] = useState("");
  const isPhone = useIsPhone();
  const reflowTopbar = useMediaQuery(TOPBAR_REFLOW_QUERY);
  // PhoneShell navigation state (critic M-3): the shell
  // presents every phone route as a pushed screen (content
  // directly under a back row) from the FIRST render —
  // cold loads, deep links, and refreshes land on the
  // requested surface with its data. The back row opens
  // the section menu; the menu is navigation, not a gate,
  // and any route change closes it again.
  const [phoneMenuOpen, setPhoneMenuOpen] = useState(false);
  const routeKey =
    route.view === "app" ? `${route.app}${route.subroute}` : route.view;
  useEffect(() => {
    setPhoneMenuOpen(false);
  }, [routeKey]);

  // Document title follows the route (critic M-5): the
  // section name from the view module's own crumb, then
  // the app name — never the static app title on an app
  // route.
  useEffect(() => {
    if (route.view === "launcher") {
      document.title = "Workhorse Superapp";
    } else if (route.view === "settings") {
      document.title = "Settings · Workhorse Superapp";
    } else {
      const section = sectionNameFor(route.app, route.subroute);
      document.title = `${section} · ${APP_META[route.app].name}`;
    }
  }, [route]);

  const onBadges = useCallback(
    (app: AppId) =>
      (badges: NavBadges): void => {
        setBadgesByApp((prev) => ({ ...prev, [app]: badges }));
      },
    [],
  );

  const attentionCount = useMemo(() => {
    const today = badgesByApp.attention?.today;
    return today ? today.count : null;
  }, [badgesByApp]);

  if (route.view === "launcher") {
    return (
      <Launcher
        presence={presence}
        attentionCount={servedPresence.decisionCount ?? attentionCount}
        presenceExpiresAt={servedPresence.expiresAt}
        nextDigestLabel={servedPresence.nextDigestLabel}
        onOpen={navigate}
      />
    );
  }

  if (route.view === "settings") {
    return (
      <Settings
        appearance={appearance}
        onAppearanceChange={updateAppearance}
        presence={presence}
        onPresenceChange={servedPresence.setMode}
        presenceExpiresAt={servedPresence.expiresAt}
        onSetPresence={servedPresence.setPresence}
        onOpen={navigate}
      />
    );
  }

  const module = VIEW_META[route.app];
  const meta = APP_META[route.app];
  const badges = badgesByApp[route.app] ?? {};
  const navItems = module.nav.map((item) => {
    const badge = badges[item.key];
    return {
      key: item.key,
      label: item.label,
      count: badge?.count,
      hot: badge?.hot,
    };
  });
  // Search-slot adoption (critic m-1): a view module
  // that declares searchPlaceholder owns its app's whole
  // search surface — the slot renders exactly where the
  // member returns a placeholder, and its undefined is
  // honest absence, NOT a fall back to the per-app
  // default (the scheduler declares "Search jobs" for
  // /jobs only). Only modules without the member
  // (workbench) keep the SEARCH_APPS default. The B-3
  // reflow below consumes this same node, so the tablet
  // content-head form follows the same adoption.
  const searchPlaceholder = module.searchPlaceholder
    ? module.searchPlaceholder(route.subroute)
    : SEARCH_APPS[route.app];
  const search: ReactNode = searchPlaceholder ? (
    <Input
      type="search"
      ariaLabel="Search"
      placeholder={searchPlaceholder}
      value={searchText}
      onChange={(e) => setSearchText(e.target.value)}
    />
  ) : undefined;
  const View = LAZY_COMPONENTS[route.app];

  // The route's names, from the view module's own crumb:
  // the breadcrumb is the PATH (App / Section / detail),
  // and the section segment is the surface's one title —
  // the shell H1 below and document.title both take it
  // through sectionNameFor (critic M-5; on workbench
  // project subroutes the crumb's segment 2 is the
  // project slug, so the selection steps one segment
  // deeper — see the helper).
  const crumbs = module.crumb(route.subroute);
  const sectionName = sectionNameFor(route.app, route.subroute);

  // Full-height surfaces (view contract: fillsContent,
  // declared per subroute by the view module — today only
  // the workbench entry preview, FU-1): the AppShell
  // content column is a definite-height scroller, but a
  // plain <main> sizes to its content, so the height
  // never reaches the mount and a page-shaped surface
  // collapses to its content's height. Where a module
  // declares the fill, the main region becomes a
  // full-height flex column: the chrome rows above the
  // mount (the relocated search row, the route H1) keep
  // their natural height and the mount flexes into the
  // rest. Every other route renders the plain main and
  // sizes to content, exactly as before.
  const fillsContent = module.fillsContent?.(route.subroute) ?? false;

  // B-3 reflow: on a non-phone width at or below the
  // reflow seam the search slot leaves the TopBar and
  // renders as a second row at the head of the content
  // region; the bar keeps breadcrumb + presence, which
  // fit. On phone the PhoneShell owns the search row.
  const searchInBar = isPhone || !reflowTopbar;

  // M-3: on phone, present the route as a pushed screen
  // from the first render — PhoneShell's phoneBack pins
  // the pushed form, so content (and its actions) load
  // immediately; the back row opens the section menu.
  const phoneChrome =
    isPhone && !phoneMenuOpen
      ? {
          phoneTitle: sectionName,
          phoneBack: {
            label: meta.name,
            onClick: () => setPhoneMenuOpen(true),
          },
        }
      : {};

  return (
    <AppShell
      appName={meta.name}
      appIcon={meta.glyph}
      appTileStyle={meta.tileStyle}
      navItems={navItems}
      footerNavItems={[
        {
          key: "settings",
          label: "Settings",
          icon: (
            <span style={{ color: "var(--ui-content-secondary)", display: "flex" }}>
              <SettingsGlyph />
            </span>
          ),
        },
      ]}
      active={module.activeKey(route.subroute)}
      onNavigate={(key) => {
        setPhoneMenuOpen(false);
        if (key === "settings") {
          navigate(settingsHref());
          return;
        }
        const item = module.nav.find((n) => n.key === key);
        if (item) navigate(item.href);
      }}
      onApps={() => navigate(launcherHref())}
      crumb={<Crumb segments={crumbs} />}
      search={searchInBar ? search : undefined}
      chips={<PresenceControl value={presence} onChange={servedPresence.setMode} />}
      {...phoneChrome}
    >
      <main
        style={
          fillsContent
            ? { display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }
            : undefined
        }
      >
        {!searchInBar && search ? (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              marginBottom: "var(--ui-space-16)",
            }}
          >
            <div style={{ width: "min(320px, 100%)" }}>{search}</div>
          </div>
        ) : null}
        {/* The route's ONE H1, shell-provided (critic
            M-5/m-2): its text is the route's section name.
            On phone it is visually hidden — the
            PhoneShell's large title presents the same
            name — so the surface is never titled twice,
            while the document still carries exactly one
            H1. Views must not render their own page-level
            H1 (see the F2 contract in the lane report). */}
        <h1
          className={isPhone ? "sr-only" : undefined}
          style={isPhone ? undefined : SHELL_TITLE_STYLE}
        >
          {sectionName}
        </h1>
        {/* The view mount: the kit's
            SectionBoundary is the shell's backstop — a
            module that fails to load, or a render that
            throws, lands in its fallback inside intact
            chrome, never a blank root. It is keyed by app
            so navigating to another app clears a stuck
            fallback, and NOT by subroute, so the mount
            (and the views' own poll state) survives in-app
            navigation exactly as before the split. While
            the app's chunk is in flight, Suspense renders
            the views' own pending form — the kit
            EmptyState the surfaces themselves use while
            their data portions load. */}
        <SectionBoundary key={route.app}>
          <Suspense fallback={<EmptyState message="Loading…" />}>
            <View
              subroute={route.subroute}
              navigate={navigate}
              onBadges={onBadges(route.app)}
              searchText={searchText}
            />
          </Suspense>
        </SectionBoundary>
      </main>
    </AppShell>
  );
}
