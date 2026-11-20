// The route table — ported from the original viewer's
// sections/shell/ShellRoutes (contracts audit B1,
// 2026-11-05): which section a route renders. The
// content is identical for both presentations — only
// the chrome around it differs — so the switch lives
// here once and the mount (index.tsx) composes it
// behind the error boundary.

import type { ProjectSummary } from "./lib/api-types";
import type { Appearance } from "./lib/preferences";
import { homeHref, type Route } from "./lib/routing";
import { BoardSection } from "./sections/board/Board";
import { EntriesSection } from "./sections/entries/Entries";
import { EntryPage } from "./sections/entries/EntryPage";
import { HomeSection, ProjectPickerSection } from "./sections/homepage/Home";
import { OverviewSection } from "./sections/overview/Overview";
import { PlansSection } from "./sections/plans/Plans";
import { ReposSection } from "./sections/repos/Repos";
import { SettingsSection } from "./sections/settings/Settings";
import { TodosSection } from "./sections/todos/Todos";

export function WorkbenchRoutes({
  route,
  selected,
  projectsPending,
  appearance,
  onAppearanceChange,
}: {
  route: Route;
  selected: ProjectSummary | null;
  projectsPending: boolean;
  appearance: Appearance;
  onAppearanceChange: (next: Appearance) => void;
}) {
  if (route.view === "settings") {
    return <SettingsSection appearance={appearance} onChange={onAppearanceChange} />;
  }
  if (route.view === "picker") {
    return <ProjectPickerSection />;
  }
  if (route.view === "board-all") {
    return <BoardSection slug={null} projectName={null} />;
  }
  if (route.view === "repos") {
    return <ReposSection repoId={route.repoId} />;
  }
  if (route.view === "entry-page") {
    return <EntryPage slug={route.slug} entryId={route.entryId} />;
  }
  if (route.view === "section") {
    if (selected == null && !projectsPending) {
      return (
        <p style={{ color: "var(--wb-content-secondary)" }}>
          Project <span className="mono">{route.slug}</span> is not in the current sweep.{" "}
          <a
            href={homeHref()}
            style={{
              color: "var(--wb-accent)",
              textDecoration: "underline",
              textUnderlineOffset: "0.14em",
            }}
          >
            Back to projects
          </a>
        </p>
      );
    }
    if (route.section === "overview") {
      return <OverviewSection slug={route.slug} projectName={selected?.name ?? route.slug} />;
    }
    if (route.section === "entries") {
      return (
        <EntriesSection
          slug={route.slug}
          projectName={selected?.name ?? route.slug}
          item={route.item}
        />
      );
    }
    if (route.section === "plans") {
      return (
        <PlansSection
          slug={route.slug}
          projectName={selected?.name ?? route.slug}
          item={route.item}
        />
      );
    }
    if (route.section === "todos") {
      return <TodosSection slug={route.slug} projectName={selected?.name ?? route.slug} />;
    }
    return <BoardSection slug={route.slug} projectName={selected?.name ?? route.slug} />;
  }
  return <HomeSection />;
}
