#!/usr/bin/env bun
// verify-contrast.mjs — the contrast discipline, rerunnable.
//
// Part 1 (Subplan-02): every status TEXT token must hold
// >= 4.5:1 (WCAG AA, normal text) against EVERY surface
// token, in both palettes x both modes. Status hues (glyph
// + border) are graphical and are NOT text-verified — the
// shipped set establishes exactly this split (e.g. stale's
// orange hue sits at ~2.3:1 on white while its text variant
// holds 5.3:1+). Alias texts (var(--ui-status-<other>-text))
// resolve to their target before checking.
//
// Part 2 (scanner rule 1 of the entries critic
// pass): the CONTENT tokens join the net. --ui-content-
// primary and --ui-content-secondary are the essential-
// content voices and must hold >= 4.5:1 against every
// surface token, both palettes x both modes — that bar is
// FATAL. --ui-content-muted is the META voice (slugs,
// timestamps, counts, card meta lines): the
// superapp critic pass (finding B-2) measured it at
// 2.91–3.71:1 across the surface set and filed it as a
// serious WCAG 2.2 AA failure on 4,229 rendered nodes.
// Muted holds the SAME fatal 4.5:1 bar
// on every surface, both palettes x both modes, and its
// token values sit on the muted->secondary scale step that
// clears the bar while staying the subordinate voice.
//
// Part 3 (superapp critic re-run, finding
// N-1): the TINT pairs join the net. Parts 1-2 check text
// against the five surface tokens, but the kit's chip
// family renders status text on the status's own TINT —
// color-mix(hue, N%, transparent) composited over the
// surface beneath — a background outside the surface set.
// The re-run measured that class at 436 rendered nodes
// (worst 3.42:1) while this gate stood green over its
// enumeration. Part 3 enumerates every text-on-tint pair
// the components can produce, from the same tokens:
//   A  status text on its own hue's tint at 14% (Chip,
//      StatusChip, Badge "approved", Lane count) and at
//      22% (the Chip's pressed state), over every surface,
//      both palettes x both modes, the full status table;
//   A2 the content voices (primary, secondary) on the
//      stale tint at 14% (DegradedBanner, FieldError);
//   B  the mix badges (LogRow's KindBadge, AppShell's
//      hot CountBadge): text = color-mix(okabe hue,
//      BADGE_FG_HUE_PCT%, content-primary) on the hue's
//      tint at BADGE_TINT_PCT% over every surface;
//   C  NoticeRow: hard-gate text on color-mix(hue, 12%,
//      surface-2); stale text on color-mix(orange, 20%,
//      surface-2).
// The Part 3 bar is the same fatal 4.5:1. The mix
// percentages are the components' own constants, mirrored
// here as data (BADGE_* below; Chip 14/22, NoticeRow
// 12/20 inline) — a component that changes its mix owes
// this file the same change.
//
// Part 4 (superapp critic confirmation,
// finding F-2): the SOLID pairs join the net. Parts 1–3
// check text against surfaces and tints; a solid fill is
// neither — it is an opaque token fill carrying its own
// on- token. The confirmation pass measured the client
// Launcher's AppTile count badge (white text on the raw
// Okabe vermilion primitive the component read directly)
// at 3.87:1 while this gate stood green over its
// enumeration. Part 4 enumerates the token-defined solid
// text pairs: the notify badge pair (on-notify on
// notify) and Button's rest-state pairs (on-accent on
// accent, accent-hover, danger), both palettes x both
// modes, same fatal 4.5:1 bar. A solid text fill reads
// its token pair, never a primitive — that is what keeps
// the pair inside this enumeration. (Button's
// hover/active color-mix states are the component's own
// constants, not token pairs; they join the net in
// Part 5 below, mirrored as data the way Part 3 mirrors
// the mix badges.)
//
// Part 5 (superapp critic confirmation
// follow-up — the Button danger active state F9 measured
// at 3.92:1 olive/dark and 3.67:1 teal/dark and named
// outside its scope): the BUTTON STATE pairs join the
// net. Button (components/controls/Button.tsx) paints its primary
// and danger fills per state from the accent/danger
// tokens and color-mix steps toward a shade endpoint;
// the text is on-accent in every state. Part 4 covers
// the rest-state token pairs; this part enumerates the
// full state matrix as the component defines it — rest,
// hover, active for both variants, both palettes x both
// modes, same fatal 4.5:1 bar. The mix percentages are
// the component's own constants, mirrored here as data
// (BTN_* below) — a component that changes its state
// mixes owes this file the same change, exactly as
// Part 3's badge mixes do; the shade endpoint is the
// press-shade token, resolved per palette x mode.
//
// Part 6 (the generic-kit sync — Step 7 of
// the starter's check-adoption plan): the NON-TEXT pairs
// and the COMPOSITE grounds join the net, with the spend
// census that keeps them honest. Parts 1–5 price text
// and Button's states; the failures this part names were
// never token values alone — they were SPENDS: a
// decorative hairline spent as a field's boundary, an
// accent spent as a focus indicator against its own
// fill. The non-text families hold the WCAG non-text
// bar of 3:1; the composite text families hold 4.5:1.
//   F1 the focus-ring role against every surface — the
//      adjacent ground an outset ring sits on (worst
//      measured 4.51:1, teal/light sunken: it holds, and
//      is now enumerated rather than assumed);
//   F2 the focus-ring role against the tint grounds a
//      pressable chip's ring sits on (status tints at
//      14%/22% over every surface; the NoticeRow
//      blends) — worst 3.37:1, holds;
//   F3 the SEPARATOR pairs. The focus-ring token IS the
//      accent, and the solid fills a focused control can
//      carry are the accent family and the done disc:
//      measured directly, focus-on-fill sits at
//      1.00–2.40:1 — the ring camouflages, the defect the
//      critic confirmation pass read as
//      switches painting no indicator. No step on the
//      scale cures it, so the Toggle track and the
//      Checkbox disc carry an inset separator band in
//      the fill's own on- colour, shipped as kit-owned
//      theme rules by the generator, and F3 prices the
//      bands: on-accent against accent and accent-hover
//      (the Toggle's checked fills); white — the
//      Checkbox's check colour — against the done hue.
//      Button carries no band: its outline is outset, on
//      the adjacent ground F1 prices. The notify fill
//      carries no pair: no focusable component renders
//      on or as the notify fill (it is a badge text
//      pair, Part 4) — a component that puts a focusable
//      control on a notify ground joins F3's separator
//      set in the same change.
//   B1 the field-border role against every surface —
//      the priced boundary the identifying spends were
//      re-pointed to. The role is new in this sync: the
//      kit spent border-default (measured 1.21–1.30:1)
//      and border-strong (1.66–1.83:1) as control
//      boundaries, both under the bar on every ground.
//      Each palette x mode takes the step of its own
//      scale nearest the ground that clears 3:1 on all
//      five surfaces (olive 400 light / 300 dark, teal
//      500 light / 400 dark; worst 4.00:1). The
//      decorative border tokens are NOT retuned.
//   B2 the remaining state-identifying border spends
//      that already hold the bar and stay: the accent
//      border (Radio checked, Toggle off-state hover,
//      the accented Lane's left bar) against every
//      surface.
//   M3 the accent-soft ground (the AppShell active nav
//      row): content primary on the composite over every
//      surface, at the text bar. Secondary is not a
//      priced voice on this ground — the row's only text
//      spend is its primary label, and the count badge
//      carries its own grounds (sunken for the plain
//      badge; the vermilion tint for the hot one, Part 3
//      B and M4) — and measured, secondary on the
//      composite fails (worst 3.96:1, teal/dark), so a
//      component that puts secondary text on accent-soft
//      owes this family the pair and the cure in the
//      same change.
//   M4 the AppShell hot-count stack: the vermilion
//      badge's mix text on its tint over accent-soft
//      over surface-1 — the one ground the stack can
//      occupy, because the sidebar spends surface-1 and
//      the active row spends accent-soft (recorded here
//      as gate data; a nav ground change owes this
//      family the same change). The inactive-row stack
//      is Part 3 family B's enumeration.
//   M6 the highlight fills under text: content primary
//      on the selection and annotation fill composites
//      over every surface (the AnnotationBadge mark
//      styles — the marks set no text colour; the text
//      they wrap is the row's primary voice). Secondary
//      and muted are not priced voices on a fill:
//      measured, secondary cannot clear the bar on the
//      selection fill at any strength that leaves the
//      fill visible (worst 4.02:1 even at 16% alpha,
//      olive/light) — the limitation is recorded here
//      rather than cured by erasing the fill.
//   M7 the highlight BARS as indicators, at the
//      non-text bar: each bar against every surface and
//      against its own fill composited over every
//      surface (the bar is the mark's inset underline —
//      it sits on the fill it bounds). Two cures, both
//      moves along the tokens' own values: the dark
//      selection-bar re-pointed from the accent alias
//      to each palette's 100 step (the accent step
//      measures 2.89:1 against its own olive fill — a
//      bar cannot be its own fill's hue at strength and
//      read against it; the light step holds at 3.38:1
//      and stays), and the light annotation-bar
//      darkened along its hue (#b97e00 -> #8f6100; it
//      measured 2.72:1 on sunken and 2.25:1 on its own
//      fill).
// The census (below, in code) scans components/ at gate
// time — never a hardcoded file list, because hardcoded
// lists rot the day a file splits. It names every focus
// spend (an outline spending any token but focus-ring
// is a finding), every outline-none (each classified
// below, compensated by a named mechanism; a
// classification whose spend vanished is itself a
// finding), the presence of the kit-owned focus rules
// in the generated themes, every border token spend
// (each classified as priced by a Part 6 family,
// decorative with its reason, or provisional: a
// re-point owed elsewhere, which the census prints as
// a NOTE on every run until the spend moves — the one
// entry of that kind, Button's secondary boundary,
// retired when its re-point to field-border landed),
// and every
// color-mix spend (each classified as priced by a named
// part or classified with its reason — the two backdrop
// composites). This kit's mix percentages are inline
// literals in the components, not exported constants,
// so each classification's needle carries the value: a
// component that changes its percentage breaks the
// needle and fails here, which is the mirrored-constant
// rule enforced in this kit's form.
//
// Usage: bun viewer/tools/verify-contrast.mjs [--verbose]
// Exit 1 on any failure.


// The shared colour math, resolvers, and token table
// live in contrast/core.mjs; Part 6 pairs and the
// Part 6 census live in their own modules beside it
// (the decomposition — this file had
// crossed the repo line cap). The parts run in the
// original order and the verdict is unchanged.
import {
  BADGE_FG_HUE_PCT, BADGE_TINT_PCT, SURFACES, hexToRgb,
  mixRgb, ratio, ratioRgb, resolveHue, resolveSemantic,
  resolveText, rgbToHex, tokens, verbose,
} from "./contrast/core.mjs";
import { runPart6Pairs } from "./contrast/part6-pairs.mjs";
import { runCensus6 } from "./contrast/census6.mjs";

let failures = 0;
let checked = 0;
for (const [name, st] of Object.entries(tokens.status)) {
  if (name === "chart") continue;
  for (const mode of ["light", "dark"]) {
    const text = resolveText(st.text[mode].$value, mode);
    for (const palette of Object.keys(tokens.semantic)) {
      for (const surface of SURFACES) {
        const bg = tokens.semantic[palette][mode].surface[surface].$value;
        const r = ratio(text, bg);
        checked += 1;
        const ok = r >= 4.5;
        if (!ok) failures += 1;
        if (verbose || !ok) {
          console.log(
            `${ok ? "PASS" : "FAIL"} status-${name} text ${text} on ` +
              `${palette}/${mode}/surface-${surface} ${bg}: ${r.toFixed(2)}:1`,
          );
        }
      }
    }
  }
}
// Part 2 — content tokens x surfaces (scanner rule 1).
// Every content voice — primary, secondary, and muted —
// holds the AA bar (4.5:1) on every surface, fatally.
// Muted joined the fatal set under the critic
// finding B-2 (see the header note).
const CONTENT_VOICES = ["primary", "secondary", "muted"];
let contentChecked = 0;
let contentFailures = 0;
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const content = tokens.semantic[palette][mode].content;
    for (const voice of CONTENT_VOICES) {
      const text = content[voice].$value;
      for (const surface of SURFACES) {
        const bg = tokens.semantic[palette][mode].surface[surface].$value;
        const r = ratio(text, bg);
        contentChecked += 1;
        const ok = r >= 4.5;
        if (!ok) contentFailures += 1;
        if (verbose || !ok) {
          console.log(
            `${ok ? "PASS" : "FAIL"} content-${voice} ${text} on ` +
              `${palette}/${mode}/surface-${surface} ${bg}: ${r.toFixed(2)}:1`,
          );
        }
      }
    }
  }
}

// Part 3 — text on status tints (finding N-1; see the
// header note). A tint is color-mix(hue, N%, transparent)
// composited over the surface beneath, so the rendered
// background is the per-channel blend of the hue at N%
// with that surface; a mix of two opaque colours is the
// same blend without the surface step.
let tintChecked = 0;
let tintFailures = 0;
function checkTint(family, label, fgRgb, bgRgb) {
  const r = ratioRgb(fgRgb, bgRgb);
  tintChecked += 1;
  const ok = r >= 4.5;
  if (!ok) tintFailures += 1;
  if (verbose || !ok) {
    console.log(
      `${ok ? "PASS" : "FAIL"} [${family}] ${label}: ` +
        `${rgbToHex(fgRgb)} on ${rgbToHex(bgRgb)}: ${r.toFixed(2)}:1`,
    );
  }
}

// A — status text on its own hue's tint (Chip 14% rest /
// 22% pressed; StatusChip, Badge, Lane ride the 14% step).
for (const [name, st] of Object.entries(tokens.status)) {
  if (name === "chart") continue;
  for (const mode of ["light", "dark"]) {
    const text = hexToRgb(resolveText(st.text[mode].$value, mode));
    for (const palette of Object.keys(tokens.semantic)) {
      const hue = hexToRgb(resolveHue(st.hue.$value, palette, mode));
      for (const surface of SURFACES) {
        const bg = hexToRgb(tokens.semantic[palette][mode].surface[surface].$value);
        for (const pct of [14, 22]) {
          checkTint(
            "A",
            `status-${name} text on own tint ${pct}% / ${palette}/${mode}/surface-${surface}`,
            text,
            mixRgb(hue, pct, bg),
          );
        }
      }
    }
  }
}
// A2 — content voices on the stale tint (DegradedBanner,
// StateControls FieldError: primary message, secondary
// detail, on color-mix(stale hue, 14%, transparent)).
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const hue = hexToRgb(resolveHue(tokens.status.stale.hue.$value, palette, mode));
    for (const voice of ["primary", "secondary"]) {
      const text = hexToRgb(tokens.semantic[palette][mode].content[voice].$value);
      for (const surface of SURFACES) {
        const bg = hexToRgb(tokens.semantic[palette][mode].surface[surface].$value);
        checkTint(
          "A2",
          `content-${voice} on stale tint 14% / ${palette}/${mode}/surface-${surface}`,
          text,
          mixRgb(hue, 14, bg),
        );
      }
    }
  }
}
// B — the mix badges (LogRow KindBadge tones, AppShell
// hot CountBadge): text = color-mix(hue, FG%, the
// palette/mode's content-primary) on the hue's tint.
// The percentages are the components' constants,
// mirrored here (see the header note).
const BADGE_TONES = {
  ok: "{primitive.color.okabe.bluish-green}",
  info: "{primitive.color.okabe.blue}",
  warn: "{primitive.color.okabe.orange}",
  fail: "{primitive.color.okabe.vermilion}",
};
for (const [tone, ref] of Object.entries(BADGE_TONES)) {
  const hue = hexToRgb(resolveHue(ref, "olive", "light"));
  for (const palette of Object.keys(tokens.semantic)) {
    for (const mode of ["light", "dark"]) {
      const primary = hexToRgb(tokens.semantic[palette][mode].content.primary.$value);
      const text = mixRgb(hue, BADGE_FG_HUE_PCT, primary);
      for (const surface of SURFACES) {
        const bg = hexToRgb(tokens.semantic[palette][mode].surface[surface].$value);
        checkTint(
          "B",
          `${tone} badge text (hue ${BADGE_FG_HUE_PCT}% mix) on tint ${BADGE_TINT_PCT}% / ${palette}/${mode}/surface-${surface}`,
          text,
          mixRgb(hue, BADGE_TINT_PCT, bg),
        );
      }
    }
  }
}
// C — NoticeRow: status text on the hue mixed INTO
// surface-2 (an opaque blend, not a transparent tint).
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const s2 = hexToRgb(tokens.semantic[palette][mode].surface["2"].$value);
    const hgHue = hexToRgb(resolveHue(tokens.status["hard-gate"].hue.$value, palette, mode));
    const hgText = hexToRgb(resolveText(tokens.status["hard-gate"].text[mode].$value, mode));
    checkTint(
      "C",
      `hard-gate text on mix(hue 12%, surface-2) / ${palette}/${mode}`,
      hgText,
      mixRgb(hgHue, 12, s2),
    );
    const orange = hexToRgb(resolveHue("{primitive.color.okabe.orange}", palette, mode));
    const staleText = hexToRgb(resolveText(tokens.status.stale.text[mode].$value, mode));
    checkTint(
      "C",
      `stale text on mix(orange 20%, surface-2) / ${palette}/${mode}`,
      staleText,
      mixRgb(orange, 20, s2),
    );
  }
}

// Part 4 — text on solid fills (finding F-2; see the
// header note). The fills are opaque, so the pair is the
// whole story: the fill token and its on- token, read
// straight from the semantic tokens (DTCG aliases
// resolved), per palette x mode.
let solidChecked = 0;
let solidFailures = 0;
function checkSolid(label, fgHex, bgHex) {
  const r = ratio(fgHex, bgHex);
  solidChecked += 1;
  const ok = r >= 4.5;
  if (!ok) solidFailures += 1;
  if (verbose || !ok) {
    console.log(
      `${ok ? "PASS" : "FAIL"} [solid] ${label}: ` +
        `${fgHex} on ${bgHex}: ${r.toFixed(2)}:1`,
    );
  }
}
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const sem = tokens.semantic[palette][mode];
    checkSolid(
      `on-notify on notify / ${palette}/${mode}`,
      resolveSemantic(sem["on-notify"].$value),
      resolveSemantic(sem.notify.$value),
    );
    for (const fill of ["accent", "accent-hover", "danger"]) {
      checkSolid(
        `on-accent on ${fill} / ${palette}/${mode}`,
        resolveSemantic(sem["on-accent"].$value),
        resolveSemantic(sem[fill].$value),
      );
    }
  }
}

// Part 5 — Button state pairs (see the header note).
// The component's state mixes, mirrored as data:
// primary active = accent at BTN_PRIMARY_ACTIVE_PCT
// toward the shade endpoint; danger hover = danger at
// BTN_DANGER_HOVER_PCT; danger active = danger at
// BTN_DANGER_ACTIVE_PCT. Rest and primary-hover states
// are the plain tokens (already in Part 4's net as
// pairs; they repeat here so the family reads whole, as
// the component defines it).
const BTN_PRIMARY_ACTIVE_PCT = 88;
const BTN_DANGER_HOVER_PCT = 88;
const BTN_DANGER_ACTIVE_PCT = 78;
// The component's mix endpoint: the press-shade token
// (black in light modes, white in dark), resolved per
// palette x mode in the loop below, the way Part 4
// resolves its pairs. The step direction is the
// token's, per mode — the same discipline as
// accent-hover, which steps darker under white text and
// lighter under dark text. A fixed step toward black
// spends the dark modes' contrast against their own
// dark on-accent text: at the uncured endpoint the
// danger active state (78% toward black) measured
// 3.92:1 olive/dark and 3.67:1 teal/dark — the failure
// this part was added to pin (see gate-red in the F9b
// evidence) — and danger hover cleared the bar by only
// 0.03 in teal/dark.
let buttonChecked = 0;
let buttonFailures = 0;
function checkButton(label, fgRgb, bgRgb) {
  const r = ratioRgb(fgRgb, bgRgb);
  buttonChecked += 1;
  const ok = r >= 4.5;
  if (!ok) buttonFailures += 1;
  if (verbose || !ok) {
    console.log(
      `${ok ? "PASS" : "FAIL"} [button] ${label}: ` +
        `${rgbToHex(fgRgb)} on ${rgbToHex(bgRgb)}: ${r.toFixed(2)}:1`,
    );
  }
}
for (const palette of Object.keys(tokens.semantic)) {
  for (const mode of ["light", "dark"]) {
    const sem = tokens.semantic[palette][mode];
    const onAccent = hexToRgb(resolveSemantic(sem["on-accent"].$value));
    const shade = hexToRgb(resolveSemantic(sem["press-shade"].$value));
    const accent = hexToRgb(resolveSemantic(sem.accent.$value));
    const danger = hexToRgb(resolveSemantic(sem.danger.$value));
    const states = [
      ["primary rest", accent],
      ["primary hover", hexToRgb(resolveSemantic(sem["accent-hover"].$value))],
      ["primary active", mixRgb(accent, BTN_PRIMARY_ACTIVE_PCT, shade)],
      ["danger rest", danger],
      ["danger hover", mixRgb(danger, BTN_DANGER_HOVER_PCT, shade)],
      ["danger active", mixRgb(danger, BTN_DANGER_ACTIVE_PCT, shade)],
    ];
    for (const [label, fill] of states) {
      checkButton(`on-accent on ${label} / ${palette}/${mode}`, onAccent, fill);
    }
  }
}


// Part 6 — non-text pairs, composite grounds, and the
// spend census (see the header note). Non-text families
// hold the WCAG non-text 3:1; composite text families
// hold the same fatal 4.5:1 as Parts 1–5.
const { ntChecked, ntFailures, mix6Checked, mix6Failures } = runPart6Pairs();

// Part 6 census — spends scanned from the tree at gate
// time (see the header note). Classifications are gate
// data; the scan itself is generated, never listed.
const {
  componentFiles6, focusSpends6, outlineNoneCount6,
  borderSpendKeys6, censusFailures6, mixSpendsClassified6,
  mixCensusFailures6,
} = runCensus6();

console.log(
  `verify-contrast: ${checked} status-text/surface pairs checked, ` +
    `${contentChecked} content/surface pairs checked, ` +
    `${failures + contentFailures} failure(s)`,
);
console.log(
  `verify-contrast: ${tintChecked} text-on-tint pairs checked (Part 3), ` +
    `${tintFailures} failure(s)`,
);
console.log(
  `verify-contrast: ${solidChecked} text-on-solid pairs checked (Part 4), ` +
    `${solidFailures} failure(s)`,
);
console.log(
  `verify-contrast: ${buttonChecked} button-state pairs checked (Part 5), ` +
    `${buttonFailures} failure(s)`,
);
console.log(
  `verify-contrast: ${ntChecked} non-text pairs checked (Part 6), ` +
    `${ntFailures} failure(s)`,
);
console.log(
  `verify-contrast: spend census (Part 6): ${componentFiles6.length} files scanned, ` +
    `${focusSpends6} focus spends, ${outlineNoneCount6} outline-none classified, ` +
    `${borderSpendKeys6.size} border spends classified, ${censusFailures6} failure(s)`,
);
console.log(
  `verify-contrast: ${mix6Checked} composite text pairs checked (Part 6), ` +
    `${mix6Failures} failure(s)`,
);
console.log(
  `verify-contrast: color-mix census (Part 6): ${componentFiles6.length} files scanned, ` +
    `${mixSpendsClassified6} color-mix spends classified, ${mixCensusFailures6} failure(s)`,
);
process.exit(
  failures ||
    contentFailures ||
    tintFailures ||
    solidFailures ||
    buttonFailures ||
    ntFailures ||
    censusFailures6 ||
    mix6Failures ||
    mixCensusFailures6
    ? 1
    : 0,
);