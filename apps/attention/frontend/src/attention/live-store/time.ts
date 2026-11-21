// New York time helpers for the live store: formatters
// and wall-clock <-> instant conversion over the real
// clock (the mock store's scenario-zone helpers live
// with the mock).

// ---------------------------------------------------------------
// Time helpers — the real clock, America/New_York wall
// math (the app's zone; DST-correct via Intl).

export const NY = "America/New_York";
export const timeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});
export const dateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  weekday: "long",
  month: "long",
  day: "numeric",
});
export const clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  hour: "numeric",
  minute: "2-digit",
  hour12: false,
});
export const weekdayFmt = new Intl.DateTimeFormat("en-US", { timeZone: NY, weekday: "short" });
export const partsFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: NY,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
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

export function nyParts(d: Date): { y: number; mo: number; da: number; h: number; mi: number; s: number } {
  const out: Record<string, number> = {};
  for (const p of partsFmt.formatToParts(d)) {
    if (p.type !== "literal") out[p.type] = Number(p.value);
  }
  return {
    y: out.year,
    mo: out.month,
    da: out.day,
    h: out.hour % 24,
    mi: out.minute,
    s: out.second,
  };
}

export function nyOffsetMs(instantMs: number): number {
  const p = nyParts(new Date(instantMs));
  return Date.UTC(p.y, p.mo - 1, p.da, p.h, p.mi, p.s) - Math.floor(instantMs / 1000) * 1000;
}

/** The instant of a New York wall time (two-pass offset
 * resolution, correct across DST transitions). */
export function nyInstant(y: number, mo: number, da: number, h: number, mi: number): number {
  let guess = Date.UTC(y, mo - 1, da, h, mi);
  for (let i = 0; i < 2; i++) guess = Date.UTC(y, mo - 1, da, h, mi) - nyOffsetMs(guess);
  return guess;
}

export const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/** A wait class's display name: the name, title-cased
 * (the backend's class_label, mirrored as the mock's). */
export function classLabel(name: string): string {
  const text = name.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
