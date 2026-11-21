// Mock adapter settings panels + server care +
// refresh over the seeded store: workspace config
// rows, message counts and cleanup/purge, repair
// actions, and refresh / rescan.

import type { ServerCare } from "../types";
import type { MockHost } from "./host";


export function workspaceConfig(h: MockHost): { label: string; value: string }[] {
  return [
    { label: "Server", value: h.s.settingsState.serverLabel },
    { label: "Projects swept", value: String(h.s.db.projects.length) },
    { label: "Registry entries", value: String(h.s.db.entries.length) },
    { label: "Guarded file saves", value: h.s.settingsState.guardedSaves ? "On" : "Off" },
    { label: "Board lane width", value: `${h.s.settingsState.boardLaneWidth} px` },
    { label: "Doctor", value: h.s.settingsState.doctorLabel },
  ];
}

export function messageCounts(h: MockHost): { label: string; count: number }[] {
  const by = (d: string | null) => h.s.db.messages.filter((m) => m.disposition === d).length;
  return [
    { label: "Awaiting disposition", count: by(null) },
    { label: "Filed", count: by("filed") },
    { label: "Opened", count: by("opened") },
    { label: "Dismissed", count: by("dismissed") },
    { label: "Draft threads", count: h.s.db.threads.filter((t) => t.state === "draft").length },
    { label: "Sent threads", count: h.s.db.threads.filter((t) => t.state === "sent").length },
  ];
}

export function cleanupMessages(h: MockHost): { removed: number } {
  const before = h.s.db.messages.length;
  h.s.db.messages = h.s.db.messages.filter((m) => m.disposition !== "dismissed");
  const removed = before - h.s.db.messages.length;
  h.emit();
  return { removed };
}

export function purgeMessages(h: MockHost): { removed: number } {
  const before = h.s.db.messages.length;
  h.s.db.messages = h.s.db.messages.filter((m) => m.disposition === null);
  const removed = before - h.s.db.messages.length;
  h.emit();
  return { removed };
}

export function repairAction(h: MockHost, kind: "clear-strays" | "fallback-restart"): ServerCare {
  if (kind === "clear-strays") {
    const n = h.s.care.strayCount;
    h.s.care = {
      ...h.s.care,
      strayCount: 0,
      lastRepairLabel: "Stray-process clear · Just now",
      log: [`Cleared ${n} stray process${n === 1 ? "" : "es"} · Just now`, ...h.s.care.log],
    };
  } else {
    h.s.care = {
      ...h.s.care,
      linkState: "ok",
      lastRepairLabel: "Fallback start · Just now",
      log: ["Fallback start ran · server healthy · Just now", ...h.s.care.log],
    };
  }
  h.emit();
  return h.s.care;
}

export async function refresh(h: MockHost): Promise<{ label: string }> {
  h.s.lastRefresh = h.clock();
  h.emit();
  return { label: h.freshnessLabel() };
}

export async function rescan(h: MockHost): Promise<{ label: string }> {
  h.s.settingsState = { ...h.s.settingsState, projectsSwept: h.s.db.projects.length };
  h.s.lastRefresh = h.clock();
  h.emit();
  return { label: h.freshnessLabel() };
}
