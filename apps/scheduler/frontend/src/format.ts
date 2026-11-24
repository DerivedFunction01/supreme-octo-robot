// Presentation formatting over served instants and values —
// the only derivation the client does (contract 06/09:
// arithmetic and presentation over served data).

import type { JobFamily, OpenInTarget } from "./types";

export const DISPLAY_TZ = "America/New_York";

/** Parse a served instant. An absent or unparseable value is
 *  an honest absence (null), never an Invalid Date handed to
 *  Intl — Intl.DateTimeFormat.format() throws RangeError:
 *  Invalid time value on one. The live adapter's empty
 *  snapshot (the pre-live states) carries "" for its
 *  instants, so every formatter below must survive them. */
function parseInstant(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function fmtTimeOfDay(iso: string, tz: string = DISPLAY_TZ): string {
  const date = parseInstant(iso);
  if (date === null) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

/** The LogRow date token ("Nov 13") — the compact day form
 *  the kit timeline row's fixed column carries. */
export function fmtDateToken(iso: string, tz: string = DISPLAY_TZ): string {
  const date = parseInstant(iso);
  if (date === null) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    month: "short",
    day: "numeric",
  }).format(date);
}

export function fmtDayTime(iso: string, tz: string = DISPLAY_TZ): string {
  const date = parseInstant(iso);
  if (date === null) return "—";
  const day = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    month: "short",
    day: "numeric",
  }).format(date);
  return `${day} · ${fmtTimeOfDay(iso, tz)}`;
}

export function isToday(iso: string, tz: string = DISPLAY_TZ): boolean {
  const date = parseInstant(iso);
  if (date === null) return false;
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return fmt.format(date) === fmt.format(new Date());
}

export function fmtAge(ageSecs: number): string {
  if (ageSecs < 60) return `${ageSecs} sec old`;
  if (ageSecs < 3600) return `${Math.floor(ageSecs / 60)} min old`;
  if (ageSecs < 86400) {
    const h = Math.floor(ageSecs / 3600);
    const m = Math.floor((ageSecs % 3600) / 60);
    return m > 0 ? `${h} h ${m} min old` : `${h} h old`;
  }
  return `${Math.floor(ageSecs / 86400)} d old`;
}

export function fmtCountdown(secs: number | null): string {
  if (secs === null) return "—";
  if (secs < 60) return `in ${secs} s`;
  if (secs < 3600) return `in ${Math.floor(secs / 60)} min`;
  if (secs < 86400) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    return m > 0 ? `in ${h} h ${m} min` : `in ${h} h`;
  }
  return `in ${Math.floor(secs / 86400)} d`;
}

export function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(0)}G`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)}M`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)}K`;
  return `${n}B`;
}

export function fmtUptime(secs: number): string {
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  if (d > 0) return `${d}d ${h}h`;
  const m = Math.floor((secs % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/** The jobs-list cadence family word (storyboard form:
 *  "Interval · …" for interval cadences, "Cron · …" for the
 *  daily/weekly forms) — presentation over the served cadence. */
export function cadenceKindWord(cadence: { type: string }): string {
  return cadence.type === "interval" ? "Interval" : "Cron";
}

// Display labels for the served classification (contract 09,
// amendment) — capitalization of the served enum
// keys, the capitalize() pattern applied to a fixed axis.
export const FAMILY_LABELS: Record<JobFamily, string> = {
  venue: "Venue",
  arming: "Arming",
  attention: "Attention",
  workbench: "Workbench",
  dispatch: "Dispatch",
};

export const OPEN_IN_LABELS: Record<OpenInTarget, string> = {
  runner: "Runner",
  workbench: "Workbench",
  attention: "Attention",
  dispatch: "Dispatch",
};

export function capitalize(text: string): string {
  return text.length === 0 ? text : text.charAt(0).toUpperCase() + text.slice(1);
}
