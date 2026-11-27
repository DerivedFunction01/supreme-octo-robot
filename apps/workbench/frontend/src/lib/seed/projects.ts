// Seed projects: the S1 overlay's canonical project
// census (docs/overlay/workbench.md) in the served
// Project shape.

import type { Project } from "../types";


const MANIFEST = {
  registry: "workbench/registry.db",
  plans: ".plans",
  mockups: "workbench/entries",
  archive: "workbench/archive",
  catalogOrigin: "hand",
  catalogGenerality: "parameterized",
  catalogUseCase: "work-tracking",
};

function project(
  slug: string,
  name: string,
  health: Project["health"],
  healthNote: string,
  lastActivityLabel: string,
  manifestOnly = false,
): Project {
  return {
    slug,
    name,
    manifest: manifestOnly ? null : { ...MANIFEST },
    health,
    healthNote,
    lastActivityLabel,
  };
}

export function buildProjects(): Project[] {
  const projects: Project[] = [
    project("fennelwick", "fennelwick", "ok", "4 in triage · board updated 12 min ago", "12 min ago"),
    project("aldercrest", "aldercrest", "ok", "2 plans in progress", "26 min ago"),
    project("copperleaf", "copperleaf", "degraded", "Degraded · feed stale 23 d", "23 d ago"),
    project("sablebrook", "sablebrook", "ok", "1 mockup awaiting review", "1 h ago"),
    project("venue-runner", "venue-runner", "ok", "Manifest + registry declared", "3 h ago"),
    project("scheduler", "scheduler", "ok", "Registry current", "44 min ago"),
    project("owner-attention", "owner-attention", "ok", "Today + Digest build in progress", "18 min ago"),
    project("workbench-viewer", "workbench-viewer", "ok", "Viewer build programme", "2 h ago"),
    project("sorrelfield", "sorrelfield", "ok", "Quiet", "4 d ago"),
    project("wintermere", "wintermere", "ok", "Quiet", "6 d ago"),
    project("staging", "staging", "ok", "Staging project · pre-home for unhomed work", "1 d ago"),
  ];
  return projects;
}
