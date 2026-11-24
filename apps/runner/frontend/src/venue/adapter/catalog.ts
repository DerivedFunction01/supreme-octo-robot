// Served catalog data (adapter-side, per venue): the
// spec catalog, the shared duration set, the mock venue's
// standing config, and the session-name catalog. Split
// from adapter.ts along the catalog seam; adapter.ts
// re-exports the public names.

import type { ShapeSpec, SpecView, VenueId } from "../types";
import specsSeed from "../seed/specs.json";

export const VENUE_LABEL: Record<VenueId, string> = { colab: "Colab", local: "Local" };

/** One shape of the core's served specs portion, in the
 *  portion's own record shape (seed/specs.json). */
export interface SpecRecord {
  id: string;
  /** The venue serving this shape; the seed catalog is the
   *  home venue's, so an absent venue is colab. */
  venue?: string;
  label: string;
  gpu: string | null;
  tpu: string | null;
  high_mem: boolean;
  rate_cu_per_hour: number | null;
  agent_startable: boolean;
}
export const SPEC_CATALOG: SpecRecord[] = (
  specsSeed as { specs: SpecRecord[] }
).specs.map((s) => ({ ...s }));

export function specRecord(shape: string): SpecRecord | null {
  return SPEC_CATALOG.find((s) => s.id === shape) ?? null;
}

/** The catalog entry for a shape, with the core's own
 *  fallbacks for a shape the catalog does not carry: the
 *  label falls back to the id, the rate stays unconfirmed
 *  (null — projects nothing, never a fabricated cost). */
export interface ShapeInfo {
  label: string;
  rateCuPerHour: number | null;
  spec: ShapeSpec;
}
export function shapeInfo(shape: string): ShapeInfo {
  const rec = specRecord(shape);
  if (rec) {
    return {
      label: rec.label,
      rateCuPerHour: rec.rate_cu_per_hour,
      spec: { gpu: rec.gpu, tpu: rec.tpu, high_mem: rec.high_mem },
    };
  }
  return {
    label: shape,
    rateCuPerHour: null,
    spec: { gpu: null, tpu: null, high_mem: false },
  };
}

/** The panel descriptor ("CPU · High-RAM" / "GPU · T4"):
 *  kind + shape, except that a CPU shape already named by
 *  the label is not repeated — the panel's own derivation,
 *  served display-ready. */
export function specDescriptor(rec: SpecRecord): string {
  const kind = rec.gpu ? "GPU" : rec.tpu ? "TPU" : "CPU";
  const shape = rec.gpu || rec.tpu || (rec.high_mem ? "High-RAM" : "Standard");
  return !rec.gpu && !rec.tpu && shape === rec.label ? kind : `${kind} · ${shape}`;
}

export function specView(rec: SpecRecord): SpecView {
  return {
    id: rec.id,
    venue: rec.venue ?? "colab",
    venueLabel: VENUE_LABEL[rec.venue ?? "colab"] ?? (rec.venue ?? "colab"),
    label: rec.label,
    descriptor: specDescriptor(rec),
    spec: { gpu: rec.gpu, tpu: rec.tpu, high_mem: rec.high_mem },
    rateCuPerHour: rec.rate_cu_per_hour,
    rateLabel:
      rec.rate_cu_per_hour != null ? `${rec.rate_cu_per_hour} CU/h` : "Cost unconfirmed",
    agentStartable: rec.agent_startable,
  };
}

/** The shared duration set the pickers offer (the panel's
 *  one set for start, extend, shorten, and grant), plus a
 *  custom-hours input wherever it renders. Labels follow
 *  the panel's fmtDur, with 24 served as "24h". */
export const DURATION_OPTIONS: { hours: number; label: string }[] = [
  { hours: 1, label: "1h" },
  { hours: 2, label: "2h" },
  { hours: 4, label: "4h" },
  { hours: 8, label: "8h" },
  { hours: 12, label: "12h" },
  { hours: 16, label: "16h" },
  { hours: 24, label: "24h" },
  { hours: 48, label: "2d" },
  { hours: 72, label: "3d" },
];
export function fmtDurHours(hours: number): string {
  return hours >= 24 && hours % 24 === 0 ? `${hours / 24}d` : `${hours}h`;
}

/** The mock venue's standing shape (config standing.shape,
 *  absent → the plain CPU shape, the core's own default)
 *  and its config budget caps — the values a grant
 *  snapshots at grant time. Adapter-side config data, like
 *  the opening balance below. */
export const STANDING_SHAPE = "cpu";
export const CONFIG_CAPS = { daily: 250, monthly: 1000, standing_daily: 40 };

// Session display names are served by the adapter (the venue's
// session catalog), never derived in the frontend.
export const SESSION_NAMES: Record<string, string> = {
  "cozy-pilot-61": "Cozy Pilot 61",
  "ember-comet-32": "Ember Comet 32",
  "storm-compass-26": "Storm Compass 26",
  "session-44": "Unnamed session 44",
  "session-52": "Unnamed session 52",
  "session-58": "Session 58",
  "session-39": "Session 39",
  "session-35": "Session 35",
};
export const NAME_A = ["Amber", "Brave", "Calm", "Daring", "Eager", "Fleet", "Golden", "Harbor", "Ivory", "Juniper"];
export const NAME_B = ["Falcon", "Voyager", "Compass", "Pilot", "Comet", "Lantern", "Summit", "Harbor", "Beacon", "Drift"];

/** A catalog entry's shape class, the gate's own rule:
 *  an accelerator is its own class even with high_mem. */
export function shapeClass(spec: ShapeSpec | null): string {
  if (spec?.gpu) return "gpu";
  if (spec?.tpu) return "tpu";
  return spec?.high_mem ? "high_ram" : "standard";
}
