// Workbench view mount — the shell's contract surface for
// the Workbench app (INTEGRATION.md §2). The subroute
// grammar is the restored original's route table
// (client/pages/workbench/src/lib/routing.ts), read
// against the remainder after "#/workbench":
//
//   /                            workspace home
//   /projects                    the project chooser
//   /board                       the cross-project board
//   /repos[/<id>]                LEGACY (SPEC §21): the
//                                retired Repos destination —
//                                resolves through the project
//                                index to the owning
//                                project's Code section
//   /p/<slug>/<section>[/<item>] per-project sections:
//                                overview | entries | plans |
//                                todos | board (the retired
//                                mockups/artifacts segments
//                                map to entries at parse time)
//   /p/<slug>/preview/<id>       one entry's page as a full
//                                page of the client (FU-1) —
//                                rendered full-bleed below,
//                                outside the centred column
//   /settings                    the app's own settings view
//                                (workbench storyboard frame 9)
//
// The component behind the mount is the port of the
// restored viewer client (pages/workbench is the source
// of record): its sections under ./sections, its lib
// under ./lib with the three seams INTEGRATION.md names
// — transport is the one client's action layer
// (lib/api.ts re-exports src/lib/actions), appearance is
// the shell's unified state (lib/preferences.ts
// delegates to src/lib/appearance), and the href
// builders produce full client hashes (lib/routing.ts).
// The original's own shell (rail, headers, phone bars)
// is NOT ported — the one client's shell owns the
// chrome; the project section nav survives in-view as
// ./SectionNav (the original's PhoneSectionNav form).

import { useEffect, useMemo } from "react";
import { SectionBoundary } from "@workhorse/kit/components/SectionBoundary";
import { useAppearance as useShellAppearance } from "../../lib/appearance";
import type { AppViewModule, NavBadges, ViewProps } from "../../lib/view-contract";
import { type Appearance } from "./lib/preferences";
import { parseRoute } from "./lib/routing";
import { resetContentScroll } from "./lib/scroll";
import { WorkbenchRoutes } from "./routes";
import { SectionNav } from "./SectionNav";
import { useShellStatus } from "./status";
import { workbenchMeta } from "./meta";
// KaTeX's stylesheet, consumed from the kit's home: the
// plans math renderer (sections/plans/math.ts) renders
// through the katex package directly, so the kit
// component that normally carries this import (Math) is
// not in this view's graph. The stylesheet is the kit's
// own asset — never a copy (INTEGRATION.md §8).
import "@workhorse/kit/assets/katex.css";

function Component({ subroute, onBadges }: ViewProps) {
  const route = useMemo(() => parseRoute(`#${subroute}`), [subroute]);

  // The appearance state is the shell's unified state —
  // the ONE shared store in src/lib/appearance (this
  // view's lib/preferences delegates to it). This mount
  // subscribes to the same store the shell and the
  // unified Settings view use, so a change made in either
  // Settings surface is live in the other with no remount
  // or re-read; writes go through the store, which applies
  // at the root and persists. The palette conversion is
  // the delegation's boundary rule (anything but teal
  // resolves to olive, the kit default).
  const [shellAppearance, updateShellAppearance] = useShellAppearance();
  const appearance: Appearance = {
    mode: shellAppearance.mode,
    palette: shellAppearance.palette,
    density: shellAppearance.density,
  };
  const changeAppearance = (next: Appearance) => {
    updateShellAppearance({
      mode: next.mode,
      density: next.density,
      palette: next.palette === "teal" ? "teal" : "olive",
    });
  };

  const status = useShellStatus(route);

  // The shell's nav badges: the original rail's live
  // counts, keyed by this mount's nav keys — Board
  // (doing across projects). Reported only when > 0,
  // as the rail rendered them.
  const { doingCount } = status;
  useEffect(() => {
    const badges: NavBadges = {};
    if (doingCount != null && doingCount > 0) badges.board = { count: doingCount };
    onBadges(badges);
  }, [doingCount, onBadges]);

  // Route changes reset the content scroll (the original
  // App's effect, same trigger): a new route entered at
  // the previous page's scroll depth is the defect the
  // reset exists to mask. lib/scroll resolves the host
  // scroller from this container's anchor — the AppShell
  // content column in the one client.
  useEffect(() => {
    resetContentScroll();
  }, [route]);

  // The full-page entry preview (FU-1) fills the content
  // column edge to edge and full-height — its own top bar
  // and the page itself, no centred measure — where every
  // other route takes the centred 1600px column. The
  // height half of that is a chain: this mount flexes as
  // the flexible child of the shell's full-height main
  // (the shell grants that form only where the view
  // module declares it — meta.ts fillsContent), and the
  // EntryPage root's own height:100% flex column
  // completes the chain down to the page iframe. A bare
  // height:100% here was inert: the shell main sized to
  // content, so the percentage resolved to auto and the
  // page collapsed to the iframe's intrinsic height.
  const isEntryPage = route.view === "entry-page";
  return (
    <div
      data-anchor="shell/content"
      style={
        isEntryPage
          ? { width: "100%", flex: "1 1 auto", minHeight: 0, minWidth: 0 }
          : { width: "100%", maxWidth: "1600px", margin: "0 auto", minWidth: 0 }
      }
    >
      {route.view === "section" ? (
        <SectionNav slug={route.slug} current={route.section} />
      ) : null}
      <SectionBoundary key={JSON.stringify(route)}>
        <WorkbenchRoutes
          route={route}
          selected={status.selected}
          projectsPending={status.projectsQuery.isPending}
          appearance={appearance}
          onAppearanceChange={changeAppearance}
        />
      </SectionBoundary>
    </div>
  );
}

// The mount assembles from ./meta (the shell-facing
// half — nav, active key, crumb — which the shell
// imports statically for its chrome) and this module's
// Component. The shell loads this module lazily, as the
// workbench chunk of the one bundle (per-view split;
// src/App.tsx holds the seam).
export const workbenchView: AppViewModule = {
  ...workbenchMeta,
  Component,
};
