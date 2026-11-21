// The standalone preview entry: the whole attention app on
// the mock adapter, inside the kit's one shell (AppShell —
// SidebarNav on desktop, PhoneShell at the kit's phone
// seam). The strip at the top is preview furniture (not app
// UI): the frame switcher for the storyboard's frames,
// the launcher badge mirror (the same store's decision
// count — it moves with every decision, like every other
// surface), and the kit's appearance controls. The glance
// and night frames are ambient full-stage surfaces and
// render outside the shell, as they did before the re-point;
// every other route renders inside AppShell. At S8 the live
// adapter replaces the mock behind the same seam.
import { useEffect, useMemo, useState } from "react";
import { Bell, ChevronLeft, Settings } from "lucide-react";
import { AppShell } from "@workhorse/kit/components/shell/AppShell";
import { ModeControl, type ModeValue } from "@workhorse/kit/components/controls/ModeControl";
import { PaletteSelect } from "@workhorse/kit/components/controls/PaletteSelect";
import { createMockAttentionStore } from "./attention/store";
import { DataContext, useDataSource, useStoreVersion } from "./attention/useStore";
import { NavContext, type Route } from "./nav";
import { PresenceChipView } from "./components/chips";
import { WriteNotice } from "./components/SurfaceNotice";
import { TodayView } from "./views/TodayView";
import { HandlersView } from "./views/HandlersView";
import { HandlerDetailView } from "./views/HandlerDetailView";
import { PresenceView } from "./views/PresenceView";
import { DigestView } from "./views/DigestView";
import { RulesView } from "./views/RulesView";
import { RegistriesView } from "./views/RegistriesView";
import { GlanceView } from "./views/GlanceView";

const FRAMES: { route: Route; label: string }[] = [
  { route: { name: "glance" }, label: "1 · Glance" },
  { route: { name: "today" }, label: "2 · Today" },
  { route: { name: "handler", handle: "main" }, label: "3 · Handler" },
  { route: { name: "presence" }, label: "4 · Presence" },
  { route: { name: "digest" }, label: "5 · Digest" },
  { route: { name: "night" }, label: "6 · Night" },
  { route: { name: "handlers" }, label: "7 · Handlers" },
  { route: { name: "rules" }, label: "8 · Rules" },
  { route: { name: "registries" }, label: "9 · Registries" },
];

/** Preview furniture: ?frame=<name> opens the preview on a
 * frame (used by the stage gate's screenshot pass). */
function initialRoute(): Route {
  const frame = new URLSearchParams(window.location.search).get("frame");
  switch (frame) {
    case "glance":
      return { name: "glance" };
    case "night":
      return { name: "night" };
    case "handlers":
      return { name: "handlers" };
    case "handler":
      return { name: "handler", handle: "main" };
    case "presence":
      return { name: "presence" };
    case "digest":
      return { name: "digest" };
    case "rules":
      return { name: "rules" };
    case "registries":
      return { name: "registries" };
    default:
      return { name: "today" };
  }
}

type NavKey = "today" | "handlers" | "digest" | "rules" | "registries" | "settings";

const NAVKEY_FOR_ROUTE: Record<Exclude<Route["name"], "glance" | "night">, NavKey> = {
  today: "today",
  handlers: "handlers",
  handler: "handlers",
  digest: "digest",
  rules: "rules",
  registries: "registries",
  presence: "settings",
};

const ROUTE_FOR_NAVKEY: Record<NavKey, Route> = {
  today: { name: "today" },
  handlers: { name: "handlers" },
  digest: { name: "digest" },
  rules: { name: "rules" },
  registries: { name: "registries" },
  settings: { name: "presence" },
};

export default function App() {
  const ds = useMemo(() => createMockAttentionStore(), []);
  return (
    <DataContext.Provider value={ds}>
      <AppMain />
    </DataContext.Provider>
  );
}

export function AppMain({
  embedded = false,
  palette: extPalette,
  mode: extMode,
  density: extDensity,
}: {
  /** Integration form: no preview harness; palette/mode/
   * density are driven by the embedding shell's unified
   * Settings (see src/integration.tsx). */
  embedded?: boolean;
  palette?: string;
  mode?: ModeValue;
  density?: string;
} = {}) {
  useStoreVersion();
  const ds = useDataSource();
  const [route, setRoute] = useState<Route>(initialRoute);
  const [paletteState, setPalette] = useState("olive");
  const [modeState, setMode] = useState<ModeValue>("system");
  const palette = embedded && extPalette ? extPalette : paletteState;
  const mode = embedded && extMode ? extMode : modeState;
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );

  // The simulated dispatch consumer: one pass per interval
  // (claim -> settle -> deliver/fail), so a decision visibly
  // walks the band queued -> sent -> fulfilled/returned.
  useEffect(() => {
    const t = setInterval(() => ds.tick(), 700);
    return () => clearInterval(t);
  }, [ds]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const fn = () => setSystemDark(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  const effectiveMode = mode === "system" ? (systemDark ? "dark" : "light") : mode;
  const nav = useMemo(() => ({ route, go: setRoute }), [route]);

  const today = ds.getToday();
  const presence = ds.getPresence();
  const handlerLabel =
    route.name === "handler"
      ? (ds.getHandlerDetail(route.handle)?.handler.label ?? "Handler")
      : undefined;

  const crumb =
    route.name === "handler" ? (
      <>
        <button
          type="button"
          className="crumb-back"
          onClick={() => setRoute({ name: "handlers" })}
        >
          <ChevronLeft size={14} aria-hidden /> Handlers
        </button>
        <span className="crumb">
          / <b>{handlerLabel}</b>
        </span>
      </>
    ) : (
      <span className="crumb">
        Attention /{" "}
        <b>
          {route.name === "today"
            ? "Today"
            : route.name === "handlers"
              ? "Handlers"
              : route.name === "digest"
                ? "Digest"
                : route.name === "rules"
                  ? "Rules"
                  : route.name === "registries"
                    ? "Registries"
                    : route.name === "presence"
                    ? "Settings"
                    : ""}
        </b>
      </span>
    );

  // The top bar's right slot: the presence chip, linking to
  // the presence (Settings) destination, as in the retired
  // local shell.
  const chips = (
    <span style={{ marginLeft: "auto", display: "flex" }}>
      <button
        type="button"
        className="presence-link"
        onClick={() => setRoute({ name: "presence" })}
        aria-label="Presence settings"
      >
        <PresenceChipView presence={presence} />
      </button>
    </span>
  );

  return (
    <NavContext.Provider value={nav}>
      <div
        data-palette={palette}
        data-mode={effectiveMode}
        data-density={embedded && extDensity ? extDensity : "comfortable"}
        className="app-root"
      >
        {embedded ? null : (
          <PreviewStrip
            route={route}
            go={setRoute}
            palette={paletteState}
            setPalette={setPalette}
            mode={modeState}
            setMode={setMode}
          />
        )}
        <div className="stage">
          {route.name === "glance" ? (
            <GlanceView />
          ) : route.name === "night" ? (
            <GlanceView night />
          ) : (
            <AppShell
              appName="Attention"
              appIcon={<Bell size={19} color="#fff" strokeWidth={2} />}
              appTileStyle={{
                background: "linear-gradient(160deg, #f0854c, #d55e00)",
              }}
              navItems={[
                {
                  key: "today",
                  label: "Today",
                  count: today.decision_count > 0 ? today.decision_count : undefined,
                  hot: true,
                },
                { key: "handlers", label: "Handlers" },
                { key: "digest", label: "Digest" },
                { key: "rules", label: "Rules" },
                { key: "registries", label: "Registries" },
              ]}
              footerNavItems={[
                {
                  key: "settings",
                  label: "Settings",
                  icon: <Settings size={17} aria-hidden />,
                },
              ]}
              active={NAVKEY_FOR_ROUTE[route.name]}
              onNavigate={(k) => setRoute(ROUTE_FOR_NAVKEY[k as NavKey])}
              onApps={() => setRoute({ name: "glance" })}
              crumb={crumb}
              chips={chips}
              phoneTitle={route.name === "handler" ? handlerLabel : undefined}
              phoneBack={
                route.name === "handler"
                  ? {
                      label: "Handlers",
                      onClick: () => setRoute({ name: "handlers" }),
                    }
                  : undefined
              }
              style={{ flex: 1, minHeight: 0, height: "auto" }}
            >
              <WriteNotice text={ds.getWriteNotice()} />
              {route.name === "today" ? <TodayView /> : null}
              {route.name === "handlers" ? <HandlersView /> : null}
              {route.name === "handler" ? (
                <HandlerDetailView handle={route.handle} />
              ) : null}
              {route.name === "presence" ? <PresenceView /> : null}
              {route.name === "digest" ? <DigestView /> : null}
              {route.name === "rules" ? <RulesView /> : null}
              {route.name === "registries" ? <RegistriesView /> : null}
            </AppShell>
          )}
        </div>
      </div>
    </NavContext.Provider>
  );
}

function PreviewStrip({
  route,
  go,
  palette,
  setPalette,
  mode,
  setMode,
}: {
  route: Route;
  go: (r: Route) => void;
  palette: string;
  setPalette: (p: string) => void;
  mode: ModeValue;
  setMode: (m: ModeValue) => void;
}) {
  useStoreVersion();
  const ds = useDataSource();
  const count = ds.getToday().decision_count;
  return (
    <div className="harness">
      <span className="harness-title">Attention — mock preview</span>
      <div className="harness-frames">
        {FRAMES.map((f) => {
          const active =
            route.name === f.route.name &&
            (f.route.name !== "handler" || (route.name === "handler" && route.handle === "main"));
          return (
            <button
              key={f.label}
              type="button"
              className={`harness-btn ${active ? "on" : ""}`}
              onClick={() => go(f.route)}
            >
              {f.label}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className="harness-badge"
        onClick={() => go({ name: "today" })}
        aria-label={`Launcher badge: ${count} decisions waiting — open Today`}
        title="Launcher badge (same store)"
      >
        <Bell size={17} color="#fff" />
        {count > 0 ? <span className="harness-badge-count">{count}</span> : null}
      </button>
      <div className="harness-appearance">
        <PaletteSelect
          value={palette}
          options={[
            { id: "olive", label: "Olive" },
            { id: "teal", label: "Teal" },
          ]}
          onChange={setPalette}
        />
        <ModeControl value={mode} onChange={setMode} />
      </div>
    </div>
  );
}
