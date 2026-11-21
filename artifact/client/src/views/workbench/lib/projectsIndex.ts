// The unified project index (SPEC §21): the one query
// every surface that needs canonical project identity
// shares — Home's repository-only rows, the Overview
// Code card, the Code section itself, and the legacy
// Repos redirect. The join is the backend's
// (lib/derived/projects.py); this module only fetches
// and finds.

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { ProjectIndexRow, ProjectsIndexPayload } from "./api-types-code";

export function useProjectIndex() {
  return useQuery({
    queryKey: ["projects-index"],
    queryFn: () => api.getProjectsIndex({}),
  });
}

export function indexPayloadOf(
  data: { payload?: unknown } | undefined,
): ProjectsIndexPayload | null {
  return (data?.payload as unknown as ProjectsIndexPayload | null) ?? null;
}

export function indexRow(
  payload: ProjectsIndexPayload | null,
  id: string,
): ProjectIndexRow | null {
  return payload?.projects.find((row) => row.id === id) ?? null;
}
