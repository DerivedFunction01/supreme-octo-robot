import { useState } from "react";
import { adapter, useSnapshot, EMBEDDED } from "./venue";
import { AppShell } from "@workhorse/kit/components/shell/AppShell";
import { LeasesView } from "./views/LeasesView";
import { LeaseDetailView } from "./views/LeaseDetailView";
import { NewLeaseView } from "./views/NewLeaseView";
import { OrphansView } from "./views/OrphansView";
import { EventsView } from "./views/EventsView";
import { BudgetView } from "./views/BudgetView";
import { AccessView } from "./views/AccessView";
import { Input } from "@workhorse/kit/components/controls/Fields";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";
import { Toggle } from "@workhorse/kit/components/controls/Toggle";
import { ChevronLeft, Play } from "lucide-react";

// No Settings destination: the appearance axes (palette ×
// mode × density) are shared and live in the superapp shell's
// unified Settings (consolidation ruling, 2026-11-13). The app
// carries no app-specific settings, so there is no in-app
// settings surface; appearance arrives as the shell-provided
// root attributes the kit themes key off.
type NavKey = "leases" | "new" | "orphans" | "events" | "budget" | "access";

type Route =
  | { name: "leases" }
  | { name: "lease-detail"; session: string }
  | { name: "new" }
  | { name: "orphans" }
  | { name: "events" }
  | { name: "budget" }
  | { name: "access" };

const SECTION: Record<Route["name"], string> = {
  leases: "Leases",
  "lease-detail": "Leases",
  new: "New lease",
  orphans: "Orphans",
  events: "Events",
  budget: "Budget",
  access: "Access",
};

export default function App() {
  const snap = useSnapshot();
  const [route, setRoute] = useState<Route>({ name: "leases" });
  const [query, setQuery] = useState("");
  const [appsOpen, setAppsOpen] = useState(false);
  const [serverUp, setServerUp] = useState(true);
  const [probeNote, setProbeNote] = useState<string | null>(null);

  const navKey: NavKey =
    route.name === "lease-detail" ? "leases" : (route.name as NavKey);
  const ROUTES: Record<NavKey, Route> = {
    leases: { name: "leases" },
    new: { name: "new" },
    orphans: { name: "orphans" },
    events: { name: "events" },
    budget: { name: "budget" },
    access: { name: "access" },
  };
  const navigate = (k: NavKey) => setRoute(ROUTES[k]);

  const setServer = (up: boolean) => {
    setServerUp(up);
    adapter.setReachable(up);
    setProbeNote(
      up ? "Lease server reachable — live state resumed." : "Lease server simulated down — the app serves its last known state (frame 8).",
    );
  };
  const tryAgain = async () => {
    const res = await adapter.probe();
    setProbeNote(
      res.reachable
        ? "Probe answered — live state resumed."
        : "Probe: still unreachable. The state stays frozen at the last served snapshot.",
    );
    if (res.reachable) setServerUp(true);
  };

  const search =
    route.name === "leases" || route.name === "events" ? (
      <span className="rn-search">
        <Input
          type="search"
          ariaLabel={route.name === "leases" ? "Search sessions" : "Filter events"}
          placeholder={route.name === "leases" ? "Search sessions" : "Filter events"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </span>
    ) : undefined;

  const crumb =
    route.name === "lease-detail" ? (
      <>
        <button type="button" className="rn-back" onClick={() => setRoute({ name: "leases" })}>
          <ChevronLeft size={14} aria-hidden /> Leases
        </button>
        <span className="rn-crumb">
          / <b>{snap.leases.find((l) => l.session === route.session)?.displayName ?? "Lease"}</b>
        </span>
      </>
    ) : (
      <span className="rn-crumb">
        Runner / <b>{SECTION[route.name]}</b>
      </span>
    );

  return (
    <>
      {/* Preview harness — NOT part of the app. It carries the
          standalone preview's controls: the mock clock and the
          lease-server reachability switch that drives frame 8.
          The integration (published) build renders no harness:
          EMBEDDED is set by src/integration.tsx. */}
      {!EMBEDDED ? (
      <div className="rn-harness">
        <span>
          <b>Runner preview</b> · mock adapter over contract 12 shapes · venue: Colab
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Toggle checked={serverUp} onChange={setServer} label="Lease server" />
          {serverUp ? "up" : "down"}
        </span>
        {probeNote ? <span role="status">{probeNote}</span> : null}
      </div>
      ) : null}
      <AppShell
        appName="Runner"
        appIcon={<Play size={19} aria-hidden />}
        appTileStyle={{
          background:
            "linear-gradient(160deg, var(--wb-okabe-sky-blue), var(--wb-okabe-blue))",
        }}
        navItems={[
          { key: "leases", label: "Leases", count: snap.leases.length },
          { key: "new", label: "New lease" },
          {
            key: "orphans",
            label: "Orphans",
            count: snap.orphans.length > 0 ? snap.orphans.length : undefined,
          },
          { key: "events", label: "Events" },
          { key: "budget", label: "Budget" },
          { key: "access", label: "Access" },
        ]}
        active={navKey}
        onNavigate={(k) => navigate(k as NavKey)}
        onApps={() => setAppsOpen(true)}
        crumb={crumb}
        search={search}
        phoneTitle={
          route.name === "lease-detail"
            ? (snap.leases.find((l) => l.session === route.session)
                ?.displayName ?? "Lease")
            : undefined
        }
        phoneBack={
          route.name === "lease-detail"
            ? {
                label: "Leases",
                onClick: () => setRoute({ name: "leases" }),
              }
            : undefined
        }
        style={{
          height: EMBEDDED ? "100vh" : "calc(100vh - 41px)",
          minHeight: 560,
        }}
      >
        {route.name === "leases" ? (
          <LeasesView
            snap={snap}
            query={query}
            onOpenLease={(session) => setRoute({ name: "lease-detail", session })}
            onTryAgain={tryAgain}
            onRestart={async () => {
              await adapter.restartServer();
              setServerUp(true);
              setProbeNote("Lease server restarted — live state resumed.");
            }}
            busy={false}
          />
        ) : null}
        {route.name === "lease-detail" ? (
          <LeaseDetailView
            snap={snap}
            session={route.session}
            onBack={() => setRoute({ name: "leases" })}
          />
        ) : null}
        {route.name === "new" ? (
          <NewLeaseView
            snap={snap}
            onAcquired={(session) => setRoute({ name: "lease-detail", session })}
          />
        ) : null}
        {route.name === "orphans" ? <OrphansView snap={snap} /> : null}
        {route.name === "events" ? (
          <EventsView
            snap={snap}
            query={query}
            onOpenSession={(session) => {
              if (snap.leases.some((l) => l.session === session)) {
                setRoute({ name: "lease-detail", session });
              } else {
                setRoute({ name: "orphans" });
              }
            }}
          />
        ) : null}
        {route.name === "budget" ? <BudgetView snap={snap} /> : null}
        {route.name === "access" ? <AccessView snap={snap} /> : null}
      </AppShell>
      {appsOpen ? (
        <Sheet open title="Apps" onClose={() => setAppsOpen(false)}>
          <p>
            The Apps back-row returns to the superapp launcher in the full Workhorse
            Superapp shell. This standalone preview runs the Runner app on its own, so
            there is no launcher to return to here.
          </p>
          <Button variant="primary" onClick={() => setAppsOpen(false)}>
            Stay in Runner
          </Button>
        </Sheet>
      ) : null}
    </>
  );
}
