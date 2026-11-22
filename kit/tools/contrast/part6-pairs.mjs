// Part 6 pairs — non-text pairs and composite grounds.
// Split from verify-contrast.mjs (the 2026-11-22
// decomposition); the block runs verbatim as the
// single file ran it, inside runPart6Pairs().

import {
  BADGE_FG_HUE_PCT, BADGE_TINT_PCT, SURFACES, hexToRgb,
  mixRgb, overRgba, ratio, ratioRgb, resolveHue, rgbToHex,
  semHex6, semRgba6, surfHex6, tokens, verbose,
} from "./core.mjs";

export function runPart6Pairs() {
const NON_TEXT_BAR = 3;
let ntChecked = 0;
let ntFailures = 0;
function checkNT(family, label, r) {
  ntChecked += 1;
  const ok = r >= NON_TEXT_BAR;
  if (!ok) ntFailures += 1;
  if (verbose || !ok) {
    console.log(`${ok ? "PASS" : "FAIL"} [${family}] ${label}: ${r.toFixed(2)}:1`);
  }
}
let mix6Checked = 0;
let mix6Failures = 0;
function checkMix6(family, label, fgRgb, bgRgb) {
  const r = ratioRgb(fgRgb, bgRgb);
  mix6Checked += 1;
  const ok = r >= 4.5;
  if (!ok) mix6Failures += 1;
  if (verbose || !ok) {
    console.log(
      `${ok ? "PASS" : "FAIL"} [${family}] ${label}: ` +
        `${rgbToHex(fgRgb)} on ${rgbToHex(bgRgb)}: ${r.toFixed(2)}:1`,
    );
  }
}
// The palette x mode semantic helpers (semHex6 and its
// kin) live in core.mjs with the other resolvers.

// F1 — focus-ring x every surface.
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const focus = semHex6(palette, mode, "focus-ring");
    for (const surface of SURFACES) {
      checkNT(
        "F1",
        `focus-ring on surface-${surface} / ${palette}/${mode}`,
        ratio(focus, surfHex6(palette, mode, surface)),
      );
    }
  }
}
// F2 — focus-ring x tint grounds: status tints at
// 14%/22% over every surface (the pressable chip's ring
// ground), and the NoticeRow opaque blends into
// surface-2 (hard-gate 12%, orange 20%).
for (const [name, st] of Object.entries(tokens.status)) {
  if (name === "chart") continue;
  for (const mode of ["light", "dark"]) {
    for (const palette of Object.keys(tokens.semantic)) {
      const hue = hexToRgb(resolveHue(st.hue.$value, palette, mode));
      const focus = hexToRgb(semHex6(palette, mode, "focus-ring"));
      for (const surface of SURFACES) {
        const bg = hexToRgb(surfHex6(palette, mode, surface));
        for (const pct of [14, 22]) {
          checkNT(
            "F2",
            `focus-ring on status-${name} tint ${pct}% / ${palette}/${mode}/surface-${surface}`,
            ratioRgb(focus, mixRgb(hue, pct, bg)),
          );
        }
      }
    }
  }
}
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const focus = hexToRgb(semHex6(palette, mode, "focus-ring"));
    const s2 = hexToRgb(surfHex6(palette, mode, "2"));
    const hgHue = hexToRgb(resolveHue(tokens.status["hard-gate"].hue.$value, palette, mode));
    checkNT(
      "F2",
      `focus-ring on NoticeRow hard-gate blend 12% / ${palette}/${mode}`,
      ratioRgb(focus, mixRgb(hgHue, 12, s2)),
    );
    const orange = hexToRgb(resolveHue("{primitive.color.okabe.orange}", palette, mode));
    checkNT(
      "F2",
      `focus-ring on NoticeRow orange blend 20% / ${palette}/${mode}`,
      ratioRgb(focus, mixRgb(orange, 20, s2)),
    );
  }
}
// F3 — the separator pairs: the inset band a solid-fill
// focusable carries, priced against its fill. on-accent
// against the accent-family fills (the Toggle's checked
// track, rest and hover); white — the Checkbox's check
// colour, a constant in the generator's theme rule —
// against the done hue (the checked disc's fill).
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const onAccent = semHex6(palette, mode, "on-accent");
    for (const fill of ["accent", "accent-hover"]) {
      checkNT(
        "F3",
        `separator on-accent on ${fill} / ${palette}/${mode}`,
        ratio(onAccent, semHex6(palette, mode, fill)),
      );
    }
    const doneHue = resolveHue(tokens.status.done.hue.$value, palette, mode);
    checkNT("F3", `separator white on done fill / ${palette}/${mode}`, ratio("#ffffff", doneHue));
  }
}
// B1 — field-border role x every surface: the priced
// boundary for Fields (the shared FIELD_STYLE),
// PaletteSelect, Checkbox/Radio unchecked, the Toggle
// off-state track, and the segmented controls' checked
// segment (whose grounds are the sunken track and its
// surface-2 fill — both in the surface set).
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const field = semHex6(palette, mode, "field-border");
    for (const surface of SURFACES) {
      checkNT(
        "B1",
        `field-border on surface-${surface} / ${palette}/${mode}`,
        ratio(field, surfHex6(palette, mode, surface)),
      );
    }
  }
}
// B2 — the accent border spends that stay (Radio
// checked; Toggle off-state hover; the accented Lane's
// left bar): the accent against every surface.
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const accent = semHex6(palette, mode, "accent");
    for (const surface of SURFACES) {
      checkNT(
        "B2",
        `accent border on surface-${surface} / ${palette}/${mode}`,
        ratio(accent, surfHex6(palette, mode, surface)),
      );
    }
  }
}
// M3 — accent-soft grounds: content primary on the
// accent-soft composite over every surface (the
// AppShell active nav row's label).
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const soft = semRgba6(palette, mode, "accent-soft");
    const text = hexToRgb(semHex6(palette, mode, "content.primary"));
    for (const surface of SURFACES) {
      checkMix6(
        "M3",
        `content-primary on accent-soft / ${palette}/${mode}/surface-${surface}`,
        text,
        overRgba(soft, hexToRgb(surfHex6(palette, mode, surface))),
      );
    }
  }
}
// M4 — the AppShell hot-count stack: the vermilion
// badge's mix text on its tint over accent-soft over
// surface-1 (the SidebarNav ground — see the header
// note). The badge percentages are Part 3 family B's
// mirrored constants.
const VERMILION_RGB = hexToRgb(resolveHue("{primitive.color.okabe.vermilion}", "olive", "light"));
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const primary = hexToRgb(semHex6(palette, mode, "content.primary"));
    const text = mixRgb(VERMILION_RGB, BADGE_FG_HUE_PCT, primary);
    const soft = semRgba6(palette, mode, "accent-soft");
    const ground = overRgba(soft, hexToRgb(surfHex6(palette, mode, "1")));
    checkMix6(
      "M4",
      `hot badge text on tint ${BADGE_TINT_PCT}% over accent-soft / ${palette}/${mode}/surface-1`,
      text,
      mixRgb(VERMILION_RGB, BADGE_TINT_PCT, ground),
    );
  }
}
// M6 — the highlight fills under text: content primary
// on the selection/annotation fill composites over
// every surface (the AnnotationBadge marks).
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const text = hexToRgb(semHex6(palette, mode, "content.primary"));
    for (const fillName of ["selection-fill", "annotation-fill"]) {
      const fill = semRgba6(palette, mode, `highlight.${fillName}`);
      for (const surface of SURFACES) {
        checkMix6(
          "M6",
          `content-primary on ${fillName} / ${palette}/${mode}/surface-${surface}`,
          text,
          overRgba(fill, hexToRgb(surfHex6(palette, mode, surface))),
        );
      }
    }
  }
}
// M7 — the highlight bars as indicators: each bar
// against every surface, and against its own fill
// composited over every surface.
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    for (const kind of ["selection", "annotation"]) {
      const bar = hexToRgb(semHex6(palette, mode, `highlight.${kind}-bar`));
      const fill = semRgba6(palette, mode, `highlight.${kind}-fill`);
      for (const surface of SURFACES) {
        const bg = hexToRgb(surfHex6(palette, mode, surface));
        checkNT("M7", `${kind}-bar on surface-${surface} / ${palette}/${mode}`, ratioRgb(bar, bg));
        checkNT(
          "M7",
          `${kind}-bar on own fill / ${palette}/${mode}/surface-${surface}`,
          ratioRgb(bar, overRgba(fill, bg)),
        );
      }
    }
  }
}

return { ntChecked, ntFailures, mix6Checked, mix6Failures };
}
