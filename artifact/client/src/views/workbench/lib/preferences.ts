// Appearance seam (INTEGRATION.md §5): the original
// viewer's preferences module owned mode / palette /
// density with its own storage key ("wb-viewer.appearance")
// and applied them to the document root. In the one
// client the unified appearance state is the shell's
// (src/lib/appearance.ts — one state, one key,
// "workhorse.appearance", applied once at the root), and
// no per-app appearance state exists. This module keeps
// the original's type + helper surface for the ported
// Settings view and delegates storage and application to
// the shell's module, so the app's own Settings view
// drives the SAME state the unified Settings view drives.
//
// Type delta: the original's Appearance.palette was a
// free string; the unified state narrows palette to the
// kit's ids ("olive" | "teal"). The conversion validates
// at the boundary — anything else resolves to olive,
// the kit default (the shell module's own load path
// applies the same rule to stored values).

import {
  applyAppearance as shellApply,
  loadAppearance as shellLoad,
  saveAppearance as shellSave,
  PALETTE_OPTIONS,
  type Appearance as ShellAppearance,
} from "../../../lib/appearance";

export type Mode = "system" | "light" | "dark";
export type Density = "comfortable" | "compact";

export interface Appearance {
  mode: Mode;
  palette: string;
  density: Density;
}

export { PALETTE_OPTIONS };

export const DEFAULT_APPEARANCE: Appearance = {
  mode: "system",
  palette: "olive",
  density: "comfortable",
};

function toShell(appearance: Appearance): ShellAppearance {
  return {
    mode: appearance.mode,
    density: appearance.density,
    palette: appearance.palette === "teal" ? "teal" : "olive",
  };
}

export function loadAppearance(): Appearance {
  const shell = shellLoad();
  return { mode: shell.mode, palette: shell.palette, density: shell.density };
}

export function saveAppearance(appearance: Appearance): void {
  shellSave(toShell(appearance));
}

/** Apply instantly: the shell module writes the root's
 *  data-mode / data-palette / data-density attributes,
 *  which the kit themes select on. */
export function applyAppearance(appearance: Appearance): void {
  shellApply(toShell(appearance));
}
