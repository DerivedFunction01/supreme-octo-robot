// Live adapter settings panels + server care +
// refresh: the local-only settings write (W-C5),
// workspace config rows, message counts and cleanup,
// repair actions, and refresh / rescan.

import type { AppSettings, ServerCare } from "../types";
import type { LiveHost } from "./host";


export function updateSettings(h: LiveHost, patch: Partial<AppSettings>): AppSettings {
  // W-C5 disposition (ruled local-only, 2026-11-15):
  // the writable fields are a
  // client preference (boardLaneWidth) and a local
  // override of a config-served default (guardedSaves
  // seeds from the server's file_editing_enabled at
  // load). The server's settings surface is the
  // read-only effective-config payload (spec §3); no
  // preferences store exists to write to, and inventing
  // one is a ruling, not a cure. Flagged in the W-C5
  // hand-back.
  h.s.settingsState = { ...h.s.settingsState, ...patch };
  h.emit();
  return h.s.settingsState;
}

export function workspaceConfig(h: LiveHost): { label: string; value: string }[] {
  const cfg = h.doc.config.config;
  const rows: { label: string; value: string }[] = [
    { label: "Config file", value: h.doc.config.config_file },
    { label: "Server", value: h.s.settingsState.serverLabel },
    { label: "Projects swept", value: String(h.s.projectList.length) },
    { label: "Registry entries", value: String(h.s.entryList.length) },
  ];
  for (const [key, value] of Object.entries(cfg)) {
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      rows.push({ label: key, value: String(value) });
    }
  }
  return rows;
}

export function messageCounts(h: LiveHost): { label: string; count: number }[] {
  const served = h.doc.settings.messages.counts;
  const rows = Object.entries(served).map(([label, count]) => ({ label, count }));
  if (rows.length > 0) return rows;
  const by = (d: string | null) => h.s.messageList.filter((m) => m.disposition === d).length;
  return [
    { label: "Awaiting disposition", count: by(null) },
    { label: "Filed", count: by("filed") },
    { label: "Opened", count: by("opened") },
    { label: "Dismissed", count: by("dismissed") },
  ];
}

export function cleanupMessages(h: LiveHost): { removed: number } {
  const before = h.s.messageList.length;
  h.s.messageList = h.s.messageList.filter((m) => m.disposition !== "dismissed");
  h.emit();
  return { removed: before - h.s.messageList.length };
}

export function purgeMessages(h: LiveHost): { removed: number } {
  const before = h.s.messageList.length;
  h.s.messageList = h.s.messageList.filter((m) => m.disposition === null);
  h.emit();
  return { removed: before - h.s.messageList.length };
}

export function repairAction(h: LiveHost, kind: "clear-strays" | "fallback-restart"): ServerCare {
  if (kind === "clear-strays") {
    const n = h.s.care.strayCount;
    h.s.care = {
      ...h.s.care,
      strayCount: 0,
      lastRepairLabel: "Stray-process clear · Just now",
      log: [`Cleared ${n} stray processes · Just now`, ...h.s.care.log],
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
  return h.serverCare();
}

export async function refresh(h: LiveHost): Promise<{ label: string }> {
  // POST /api/refresh at the serving shell; the snapshot
  // itself is re-injected on the next page load — the
  // adapter cannot re-fetch its own document. In the
  // frame form the forceRefresh action carries the
  // same bust over the relay.
  try {
    if (h.channel) {
      await h.channel("forceRefresh");
    } else {
      await fetch(h.url("/api/refresh"), { method: "POST" });
    }
  } catch {
    // offline snapshot — the label still moves
  }
  h.s.lastRefresh = h.clock();
  h.emit();
  return { label: h.freshnessLabel() };
}

export async function rescan(h: LiveHost): Promise<{ label: string }> {
  try {
    if (h.channel) {
      await h.channel("rescanProjects");
    } else {
      await fetch(h.url("/api/projects/rescan"), { method: "POST" });
    }
  } catch {
    // offline snapshot — the label still moves
  }
  h.s.lastRefresh = h.clock();
  h.emit();
  return { label: h.freshnessLabel() };
}
