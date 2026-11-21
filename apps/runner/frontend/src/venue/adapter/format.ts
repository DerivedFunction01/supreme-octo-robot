// Formatting (served display-ready): the venue timezone's
// time/date/duration forms and the served kind labels.
// Split from adapter.ts along the formatting seam;
// adapter.ts re-exports the public names.

import type { EventKind } from "../types";

export const TZ = "America/New_York";
export function fmtTime(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: TZ,
  }).format(new Date(iso));
}

/** Served kind labels (labels are backend work; the frontend
 *  never maps a kind to its display word). */
export const KIND_LABEL: Record<EventKind, string> = {
  lease: "Lease",
  run: "Run",
  grant: "Grant",
  error: "Error",
  budget: "Budget",
};

/** Compact served date token ("Nov 13") for the LogRow column. */
export function fmtDateToken(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

/** Time with seconds, for the event drawer's Time fact. */
export function fmtTimeLong(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(iso));
}
export function fmtDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${String(m % 60).padStart(2, "0")}m`;
  }
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}
export function fmtRemaining(ms: number): string {
  const mins = Math.max(0, Math.round(ms / 60000));
  const h = Math.floor(mins / 60);
  return `${h} h ${String(mins % 60).padStart(2, "0")} min left`;
}
