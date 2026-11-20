// Appearance — the one client's unified appearance state
// (owner ruling 2026-11-13: the shared axes stated once, in
// one Settings view; kit sheet: palettes olive/teal, modes
// dark/light as peers with the Auto override, density sets).
//
// The axes ride the document root's data attributes, which
// is exactly what the kit themes select on:
// `[data-palette="olive"]`, `[data-mode="dark"]`,
// `[data-density="compact"]`. Mode "system" = NO data-mode
// attribute (the themes' `prefers-color-scheme` peer takes
// over). Palette always set (olive is the kit default —
// `:root:not([data-palette])` also resolves to olive).
// Density always set (comfortable is the `:root` default).
//
// Applied once at the document root by the shell — never
// per view, never pushed into another surface. Persisted
// in localStorage; the space SDK exposes no client storage
// API. Applied before first paint in main.tsx so a saved
// appearance never flashes the default. (The workbench
// original's preferences module is the semantic source;
// its storage key was its own — this client has its own.)

import { useSyncExternalStore } from "react";

export type PaletteId = "olive" | "teal";
export type ModeId = "system" | "light" | "dark";
export type DensityId = "comfortable" | "compact";

export interface Appearance {
  palette: PaletteId;
  mode: ModeId;
  density: DensityId;
}

export const APPEARANCE_DEFAULTS: Appearance = {
  palette: "olive",
  mode: "system",
  density: "comfortable",
};

export const PALETTE_OPTIONS: { id: PaletteId; label: string }[] = [
  { id: "olive", label: "Olive" },
  { id: "teal", label: "Teal" },
];

const STORAGE_KEY = "workhorse.appearance";

const PALETTES: readonly string[] = ["olive", "teal"];
const MODES: readonly string[] = ["system", "light", "dark"];
const DENSITIES: readonly string[] = ["comfortable", "compact"];

export function loadAppearance(): Appearance {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return APPEARANCE_DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Record<keyof Appearance, unknown>>;
    return {
      palette: PALETTES.includes(parsed.palette as string)
        ? (parsed.palette as PaletteId)
        : APPEARANCE_DEFAULTS.palette,
      mode: MODES.includes(parsed.mode as string)
        ? (parsed.mode as ModeId)
        : APPEARANCE_DEFAULTS.mode,
      density: DENSITIES.includes(parsed.density as string)
        ? (parsed.density as DensityId)
        : APPEARANCE_DEFAULTS.density,
    };
  } catch {
    return APPEARANCE_DEFAULTS;
  }
}

export function applyAppearance(appearance: Appearance): void {
  const root = document.documentElement;
  root.setAttribute("data-palette", appearance.palette);
  if (appearance.mode === "system") {
    root.removeAttribute("data-mode");
  } else {
    root.setAttribute("data-mode", appearance.mode);
  }
  root.setAttribute("data-density", appearance.density);
}

export function saveAppearance(appearance: Appearance): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(appearance));
  } catch {
    // Storage unavailable: the appearance still applies for
    // the session; persistence is best-effort by design.
  }
}

/* ---------------- the one shared store ----------------
 * The appearance state is a single module-level store,
 * not per-hook React state: the shell (App.tsx), the
 * unified Settings view, and the workbench app's own
 * Settings view (through views/workbench/lib/preferences'
 * delegation to this module) all read and write THIS
 * state, so a change made in any one surface is the value
 * every other surface displays — live, with no remount
 * and no re-read. Applying to the document root and
 * persisting happen here, on write, exactly once. */

let current: Appearance | null = null;
const listeners = new Set<() => void>();

function ensureCurrent(): Appearance {
  if (current === null) current = loadAppearance();
  return current;
}

function subscribeAppearance(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getAppearanceSnapshot(): Appearance {
  return ensureCurrent();
}

/** Merge a patch (one axis per Settings control) into the
 *  one state: apply at the root, persist, notify. */
export function updateAppearance(patch: Partial<Appearance>): void {
  current = { ...ensureCurrent(), ...patch };
  applyAppearance(current);
  saveAppearance(current);
  for (const listener of listeners) listener();
}

/** The appearance hook: subscribes the caller to the one
 *  shared store above. Every consumer sees the same state
 *  and the same updater. */
export function useAppearance(): [
  Appearance,
  (patch: Partial<Appearance>) => void,
] {
  const appearance = useSyncExternalStore(
    subscribeAppearance,
    getAppearanceSnapshot,
  );
  return [appearance, updateAppearance];
}
