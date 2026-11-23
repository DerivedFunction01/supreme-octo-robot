// Runner view mount — the shell's contract surface for
// the Runner app (INTEGRATION.md §2). Subroutes, from the
// panel of record's screens (the restored original panel
// statics, client/pages/runner — the same panel that runs
// on port 8793 as pipeline/venue/ui) and the runner
// storyboard's 8 frames:
//
//   /                Leases (the panel's home)
//   /leases          Leases
//   /leases/<id>     Lease detail
//   /new             New lease
//   /access          Access (grants)
//   /budget          Budget
//   /events          Events (the log stream — the kit
//                    LogRow's first consumer)
//   /orphans         Orphans
//
// Mutations stay (owner ruling): the
// views call the merged registry's runner actions through
// the one client's action layer (src/lib/actions.ts) —
// the restoration lane's mapping is complete, zero open
// seams. The panel's Okabe-Ito theme.css does NOT carry
// (INTEGRATION.md §9): the views compose on kit --wb-*
// tokens. The views are built from the panel of record's
// behaviour, one file per route:
//
//   model.ts    served contracts + the pure form model
//   state.tsx   the portion-poll machinery (poll.js)
//   pickers.tsx portion status, degraded, extend/shorten
//   leases.tsx  Leases + grant card + access list + detail
//   new.tsx     New lease (controls.js)
//   access.tsx  Access
//   budget.tsx  Budget
//   events.tsx  Events (logs.js)
//   orphans.tsx Orphans (orphans.js)

import { useEffect } from "react";
import type {
  AppViewModule,
  NavBadges,
  ViewProps,
} from "../../lib/view-contract";
import { AccessView } from "./access";
import { BudgetView } from "./budget";
import { EventsView } from "./events";
import { LeaseDetailView, LeasesView } from "./leases";
import { NewLeaseView } from "./new";
import { OrphansView } from "./orphans";
import { NoticeBar } from "./pickers";
import { RunnerProvider, useRunner } from "./state";
import { runnerMeta } from "./meta";

/** Live nav counts for the shell's badges: leases running,
 *  orphans waiting (hot — an orphan holds venue capacity
 *  with no caller owning it). Reported only once the
 *  portion has landed; the shell holds the last set. */
function BadgesReporter({ onBadges }: { onBadges: ViewProps["onBadges"] }) {
  const { parts } = useRunner();
  const leases = parts.records.data?.records?.length;
  const orphans = parts.orphans.data?.orphans?.length;
  useEffect(() => {
    const badges: NavBadges = {};
    if (leases != null) badges.leases = { count: leases };
    if (orphans != null) badges.orphans = { count: orphans, hot: orphans > 0 };
    if (Object.keys(badges).length > 0) onBadges(badges);
  }, [leases, orphans, onBadges]);
  return null;
}

function RunnerRoutes({ subroute, navigate }: ViewProps) {
  if (subroute === "/" || subroute === "/leases") {
    return <LeasesView navigate={navigate} />;
  }
  if (subroute.startsWith("/leases/")) {
    const id = subroute
      .slice("/leases/".length)
      .split("/")
      .map((seg) => decodeURIComponent(seg))
      .join("/");
    return <LeaseDetailView session={id} />;
  }
  if (subroute === "/new") return <NewLeaseView navigate={navigate} />;
  if (subroute === "/access") return <AccessView />;
  if (subroute === "/budget") return <BudgetView />;
  if (subroute === "/events") return <EventsView navigate={navigate} />;
  if (subroute === "/orphans") return <OrphansView />;
  return <LeasesView navigate={navigate} />;
}

function Component(props: ViewProps) {
  return (
    <RunnerProvider>
      <BadgesReporter onBadges={props.onBadges} />
      <div className="flex flex-col gap-4">
        <NoticeBar />
        <RunnerRoutes {...props} />
      </div>
    </RunnerProvider>
  );
}

// The mount assembles from ./meta (the shell-facing
// half — nav, active key, crumb — which the shell
// imports statically for its chrome) and this module's
// Component. The shell loads this module lazily, as the
// runner chunk of the one bundle (per-view split;
// src/App.tsx holds the seam).
export const runnerView: AppViewModule = {
  ...runnerMeta,
  Component,
};
