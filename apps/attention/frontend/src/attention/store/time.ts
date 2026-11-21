// Scenario-zone time helpers for the mock store
// (EST, UTC-5, fixed): wall-clock parts, scenario
// instants, and the served label formatters.

// ---- scenario-zone time helpers (EST, UTC-5, fixed) ----

export function wallParts(d: Date): { y: number; mo: number; da: number; h: number; mi: number } {
  const shifted = new Date(d.getTime() - 5 * 3_600_000);
  return {
    y: shifted.getUTCFullYear(),
    mo: shifted.getUTCMonth() + 1,
    da: shifted.getUTCDate(),
    h: shifted.getUTCHours(),
    mi: shifted.getUTCMinutes(),
  };
}

export function scenarioInstant(y: number, mo: number, da: number, h: number, mi: number): number {
  return Date.UTC(y, mo - 1, da, h + 5, mi, 0);
}

export const timeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});
export const dateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "long",
  month: "long",
  day: "numeric",
});
export const clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  hour12: false,
});

export function timeLabel(iso: string | number): string {
  return timeFmt.format(new Date(iso)).toUpperCase();
}

export function durationLabel(ms: number): string {
  const mins = Math.max(0, Math.floor(ms / 60_000));
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h} h ${String(m).padStart(2, "0")} min`;
}
