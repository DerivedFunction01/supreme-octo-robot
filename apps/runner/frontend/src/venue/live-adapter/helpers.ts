// Small served-form helpers: the venue label, the shape
// class rule, session display names, and the served-value
// guards. Split from live-adapter.ts along the helper
// seam; live-adapter.ts re-exports liveSessionName.

import type { ShapeSpec } from "../types";

/** Display labels for the venue kinds the core serves. A
 *  venue with no label here renders as its own id — the id is
 *  served data, the label is presentation, and an unlabelled
 *  venue is never silently dressed as another venue. */
export const VENUE_LABELS: Record<string, string> = { colab: "Colab", local: "Local" };

export function venueLabel(venue: string): string {
  return VENUE_LABELS[venue] ?? venue;
}
export const TZ = "America/New_York";

export const CLASS_LABEL: Record<string, string> = {
  gpu: "GPU",
  tpu: "TPU",
  high_ram: "High-RAM",
  standard: "Standard",
};

/** A catalog entry's shape class, the gate's own rule (the
 *  mock's shapeClass, over the served spec). */
export function shapeClass(spec: ShapeSpec | null): string {
  if (spec?.gpu) return "gpu";
  if (spec?.tpu) return "tpu";
  return spec?.high_mem ? "high_ram" : "standard";
}

/** Session display names are served by the adapter, never
 *  derived in the frontend (the mock's rule). Live session
 *  ids carry a renewal suffix (-r<digits>) the display name
 *  drops; the base name title-cases word by word. */
export function liveSessionName(session: string): string {
  if (session === "?") return "Unnamed session";
  const base = session.replace(/-r\d+$/, "");
  return base
    .split("-")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** The base name a run event names its session by (the
 *  outbox's run events carry the base name, not the
 *  renewal-suffixed record id). */
export function baseName(session: string): string {
  return session.replace(/-r\d+$/, "");
}

export function fmtRemaining(ms: number): string {
  const mins = Math.max(0, Math.round(ms / 60000));
  const h = Math.floor(mins / 60);
  return `${h} h ${String(mins % 60).padStart(2, "0")} min left`;
}

export function str(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}
export function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
