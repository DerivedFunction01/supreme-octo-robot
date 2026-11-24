// The view's status model — ported from the original
// viewer's sections/shell/ShellStatus (contracts audit
// B1): the queries the workbench views live
// on — projects, health, home, config,
// the board portions behind the doing badge, and the
// per-project triage counts — with their derivations.
// The original file's two header renderings (the phone
// top bar and the desktop header) were chrome and are
// NOT ported: the one client's shell owns the chrome
// (INTEGRATION.md §1). The mount (index.tsx) consumes
// this model for route resolution and the shell's nav
// badges; the sections run their own queries against
// the same keys, so the cache is shared.

import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "./lib/api";
import type {
  BoardProjectPayload,
  EntriesFeed,
  HomePayload,
  ProjectSummary,
} from "./lib/api-types";
import { groupProjects } from "./lib/grouping";
import {
  boardKey,
  configKey,
  entriesKey,
  healthKey,
  homeKey,
  projectsKey,
} from "./lib/keys";
import type { Route } from "./lib/routing";

export function projectStatus(project: ProjectSummary): { word: string; degraded: boolean } {
  const anySection = project.sections.entries || project.sections.todos || project.sections.plans;
  if (anySection) return { word: "ok", degraded: false };
  if (project.sections.registry_declared || project.sections.plans_declared) {
    return { word: "manifest only", degraded: false };
  }
  return { word: "manifest only", degraded: false };
}

export function useShellStatus(route: Route) {
  const projectsQuery = useQuery({
    queryKey: projectsKey,
    queryFn: () => api.listProjects({}),
    refetchInterval: 30000,
  });
  const healthQuery = useQuery({
    queryKey: healthKey,
    queryFn: () => api.getHealth({}),
    refetchInterval: 30000,
  });
  const homeQuery = useQuery({
    queryKey: homeKey,
    queryFn: () => api.getHome({}),
    refetchInterval: 30000,
  });
  const homeRows = useMemo(
    () => (homeQuery.data?.payload as unknown as HomePayload | null)?.projects ?? null,
    [homeQuery.data],
  );
  const configQuery = useQuery({
    queryKey: configKey,
    queryFn: () => api.getConfig({}),
  });
  const editingOn = configQuery.data?.payload?.config.file_editing_enabled === true;

  const projects = useMemo<ProjectSummary[]>(
    () => projectsQuery.data?.payload?.projects ?? [],
    [projectsQuery.data],
  );
  const health = healthQuery.data?.payload ?? null;
  const projectGroups = useMemo(() => groupProjects(projects, homeRows), [projects, homeRows]);
  const serverOk = healthQuery.data?.status === 200 && health?.ok === true;
  // The doing badge assembles the same per-project board
  // portions the Board section renders — same query keys,
  // so the cache is shared and nothing fetches twice.
  const portionQueries = useQueries({
    queries: projects.map((p) => ({
      queryKey: boardKey(p.slug),
      queryFn: () => api.getBoardProject({ slug: p.slug }),
    })),
  });
  const portions: BoardProjectPayload[] = [];
  let portionsPending = projects.length === 0;
  portionQueries.forEach((q) => {
    const payload = q.data?.payload as BoardProjectPayload | undefined;
    if (q.isPending || !payload) {
      portionsPending = true;
      return;
    }
    portions.push(payload);
  });

  const routeSlugValue = route.view === "section" ? route.slug : null;
  const selected = routeSlugValue
    ? (projects.find((project) => project.slug === routeSlugValue) ?? null)
    : null;

  const triageQuery = useQuery({
    queryKey: entriesKey(selected?.slug),
    queryFn: () => api.getEntries({ slug: selected?.slug ?? "" }),
    // biome-ignore lint/complexity/useOptionalChain: the boolean form is load-bearing — `selected?.sections.entries` evaluates to undefined with no project selected, and React Query treats enabled: undefined as enabled (the query would fire with an empty slug and 422)
    enabled: selected != null && selected.sections.entries,
  });
  const triageCount =
    (triageQuery.data?.payload as unknown as EntriesFeed | null)?.triage.length ?? null;
  const doingCount = portionsPending
    ? null
    : portions.reduce(
        (sum, portion) =>
          sum +
          (portion.counts.todos.doing ?? 0) +
          (portion.counts.plans.doing ?? 0) +
          portion.counts.review_queue,
        0,
      );

  return {
    projectsQuery,
    projects,
    health,
    serverOk,
    editingOn,
    homeRows,
    projectGroups,
    portions,
    portionsPending,
    doingCount,
    triageCount,
    routeSlugValue,
    selected,
  };
}

export type ShellStatus = ReturnType<typeof useShellStatus>;
