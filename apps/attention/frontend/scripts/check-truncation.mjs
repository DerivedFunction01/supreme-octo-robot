#!/usr/bin/env node
/**
 * check-truncation — the truncation / border-touch guard.
 *
 * Fails the build when app source reintroduces one of the
 * defect shapes the 2026-11-15 truncation sweep cured:
 *
 *   T1  Squeezable truncating control — a className that
 *       combines `truncate` + `min-w-0` on a pill
 *       (`rounded-full`) or a <button>, without shrink
 *       protection (`shrink-0` / `flex-none`). In a flex
 *       row the control shrinks below its label and the
 *       label ellipsizes even with free space beside it
 *       (the workbench PickChip defect).
 *   T2  Capped squeeze wrapper — a className with a
 *       percentage `max-w-[…%]` cap (< 100%) + `min-w-0`
 *       and no `truncate` of its own, wrapping a Chip /
 *       Badge component: the cap starves the chip, whose
 *       label then truncates inside it (the workbench
 *       Home project-row defect). A truncating value
 *       element (the Val form) is sanctioned and excluded
 *       by the no-`truncate` condition.
 *   T3  Fixed-height clip — a fixed height (`h-[…px]` /
 *       `h-<n>` class, or `height: <n>px` in CSS) combined
 *       with `overflow-hidden` / `overflow: hidden` on the
 *       same element or rule: text is clipped mid-word
 *       vertically behind the fixed height. Accessibility
 *       visually-hidden rules are allowlisted.
 *   T4  CSS squeeze — one CSS rule combining a percentage
 *       `max-width` (< 100%) with `text-overflow:
 *       ellipsis`: the stylesheet analogue of T2.
 *
 * The sanctioned two-line row form (truncated label +
 * badge, truncated sub + trailing chips) carries none of
 * these shapes: its truncating elements are plain text
 * spans, and its chips are never capped or squeezable.
 *
 * Classes this guard cannot express statically — a flex
 * row that fails to wrap so a control is squeezed by its
 * siblings, and glyph-to-border geometry — are covered
 * by the manual rendered sweep named in the sweep report
 * (390px + desktop renders, seed labels + the two stress
 * sentences, in-page overflow detector).
 *
 * Usage: node check-truncation.mjs [--selftest]
 * Scans ../src relative to this script (the app's src).
 * Exit 0 = clean; 1 = a defect shape found (or the
 * self-test failed).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
// Vendored kit output and other generated trees are not
// app source; the kit's own forms are guarded upstream.
const SKIP_DIRS = new Set(["kit", "node_modules", "dist"]);

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (!SKIP_DIRS.has(name)) yield* walk(p);
    } else if (/\.(tsx|ts|css)$/.test(name)) {
      yield p;
    }
  }
}

/** Every className literal in a TSX/TS source, with the
 *  tag that carries it (best-effort lookback) and line. */
function classNamesOf(source) {
  const out = [];
  const re = /className\s*=\s*(?:"([^"]*)"|\{\s*`([^`]*)`|\{\s*"([^"]*)")/g;
  let m;
  while ((m = re.exec(source)) !== null) {
    const raw = m[1] ?? m[2] ?? m[3] ?? "";
    // Template literals: keep the static parts only.
    const cls = raw.replace(/\$\{[^}]*\}/g, " ");
    const before = source.slice(Math.max(0, m.index - 240), m.index);
    const tagMatch = before.match(/<([A-Za-z][A-Za-z0-9.]*)\s[^<>]*$/);
    out.push({
      cls,
      tag: tagMatch ? tagMatch[1] : "",
      index: m.index,
      line: source.slice(0, m.index).split("\n").length,
    });
  }
  return out;
}

const has = (cls, tok) => cls.split(/\s+/).includes(tok);
const hasRe = (cls, re) => re.test(cls);

function t1({ cls, tag }) {
  if (!has(cls, "truncate") || !has(cls, "min-w-0")) return false;
  if (has(cls, "shrink-0") || has(cls, "flex-none") || hasRe(cls, /flex-\[0/)) return false;
  return has(cls, "rounded-full") || tag === "button";
}

function t2(source, entry) {
  const cap = entry.cls.match(/max-w-\[(\d+(?:\.\d+)?)%\]/);
  if (!cap || Number(cap[1]) >= 100) return false;
  if (!has(entry.cls, "min-w-0") || has(entry.cls, "truncate")) return false;
  const after = source.slice(entry.index, entry.index + 900);
  return /<(?:[A-Za-z]*Chip|[A-Za-z]*Badge)\b/.test(after);
}

function t3Class({ cls }) {
  const fixedH = hasRe(cls, /(?:^|\s)h-(?:\[\d+(?:\.\d+)?px\]|\d+)(?:\s|$)/);
  return fixedH && has(cls, "overflow-hidden");
}

/** CSS rule blocks: [selector, body] pairs. */
function cssRules(source) {
  const out = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(source)) !== null) out.push({ selector: m[1].trim(), body: m[2] });
  return out;
}

const ALLOW_SELECTOR = /sr-only|visually-hidden/;

function t3Css({ selector, body }) {
  if (ALLOW_SELECTOR.test(selector)) return false;
  return /(?:^|;)\s*height:\s*\d+(?:\.\d+)?px/.test(body) && /overflow:\s*hidden/.test(body);
}

function t4Css({ selector, body }) {
  if (ALLOW_SELECTOR.test(selector)) return false;
  const cap = body.match(/max-width:\s*(\d+(?:\.\d+)?)%/);
  return !!cap && Number(cap[1]) < 100 && /text-overflow:\s*ellipsis/.test(body);
}

function scanSource(path, source) {
  const hits = [];
  if (/\.css$/.test(path)) {
    for (const rule of cssRules(source)) {
      if (t3Css(rule)) hits.push(`T3 fixed-height clip in rule "${rule.selector.slice(0, 60)}"`);
      if (t4Css(rule)) hits.push(`T4 capped ellipsis in rule "${rule.selector.slice(0, 60)}"`);
    }
    return hits;
  }
  for (const entry of classNamesOf(source)) {
    // A named exemption: a `check-truncation-allow:T<n>`
    // comment on the element's line or the two lines above
    // it suppresses that one rule for that one element.
    // Exemptions are printed by the scan so they stay
    // auditable in gate output; the sanctioned case is a
    // fixed-height preview frame (a device viewport, not
    // a text container).
    const context = source.slice(Math.max(0, entry.index - 400), entry.index);
    const allowed = (rule) => context.includes(`check-truncation-allow:${rule}`);
    if (t1(entry) && !allowed("T1")) hits.push(`T1 squeezable truncating control at line ${entry.line}: "${entry.cls.slice(0, 90)}"`);
    if (t2(source, entry) && !allowed("T2")) hits.push(`T2 capped squeeze wrapper at line ${entry.line}: "${entry.cls.slice(0, 90)}"`);
    if (t3Class(entry) && !allowed("T3")) hits.push(`T3 fixed-height clip at line ${entry.line}: "${entry.cls.slice(0, 90)}"`);
    for (const rule of ["T1", "T2", "T3"]) {
      if (allowed(rule)) hits.push(`ALLOW ${rule} exemption used at line ${entry.line}`);
    }
  }
  return hits;
}

const FIXTURES = [
  // [name, source, expected rule ids] — one violating and
  // one clean fixture per rule; the pin for this guard.
  ["T1 violating (PickChip pre-cure)",
   `<button className="max-w-[260px] min-w-0 truncate rounded-full px-3 py-1">All</button>`, ["T1"]],
  ["T1 clean (PickChip cured)",
   `<button className="max-w-full shrink-0 truncate rounded-full px-3 py-1 whitespace-nowrap">All</button>`, []],
  ["T2 violating (Home chip wrapper pre-cure)",
   `<span className="ml-auto max-w-[45%] min-w-0">\n  <RuledChip status={s} />\n</span>`, ["T2"]],
  ["T2 clean (sanctioned Val value form)",
   `<span className="ml-auto max-w-[60%] min-w-0 truncate text-sm">{v}</span>`, []],
  ["T3 violating (fixed-height clip, class form)",
   `<div className="h-[38px] overflow-hidden text-sm">Label</div>`, ["T3"]],
  ["T3 clean (min-height is not a fixed height)",
   `<div className="min-h-[38px] overflow-hidden text-sm">Label</div>`, []],
  ["T3 violating (CSS form)",
   `.box { height: 38px; overflow: hidden; }`, ["T3"]],
  ["T3 clean (visually-hidden allowlist)",
   `.sr-only { height: 1px; overflow: hidden; }`, []],
  ["T4 violating (CSS capped ellipsis)",
   `.lab { max-width: 45%; text-overflow: ellipsis; overflow: hidden; }`, ["T4"]],
  ["T4 clean (row label ellipsis, uncapped)",
   `.lab { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }`, []],
  ["row form clean (sanctioned two-line row)",
   `<span className="min-w-0 flex-1"><span className="block truncate text-[14.5px]">Name</span></span><span className="ml-auto shrink-0"><Chip /></span>`, []],
  ["T3 exempted (preview frame, named allowance)",
   `{/* check-truncation-allow:T3 — device viewport frame, not a text container */}\n<div className="h-[720px] overflow-hidden rounded-[10px]"><App /></div>`, []],
];

function selftest() {
  let failed = 0;
  for (const [name, source, expected] of FIXTURES) {
    const isCss = source.trimStart().startsWith(".");
    const hits = scanSource(isCss ? "fixture.css" : "fixture.tsx", source).filter((h) => !h.startsWith("ALLOW"));
    const got = [...new Set(hits.map((h) => h.split(" ")[0]))].sort();
    const ok = JSON.stringify(got) === JSON.stringify([...expected].sort());
    if (!ok) failed += 1;
    console.log(`${ok ? "ok  " : "FAIL"} ${name}: expected [${expected}], got [${got}]`);
  }
  console.log(failed ? `selftest: ${failed} fixture(s) failed` : "selftest: all fixtures pass");
  return failed ? 1 : 0;
}

if (process.argv.includes("--selftest")) {
  process.exit(selftest());
}

let violations = 0;
for (const path of walk(SRC)) {
  const source = readFileSync(path, "utf8");
  for (const hit of scanSource(path, source)) {
    if (hit.startsWith("ALLOW")) {
      console.log(`${relative(process.cwd(), path)}: ${hit} (exempted, see source comment)`);
      continue;
    }
    violations += 1;
    console.log(`${relative(process.cwd(), path)}: ${hit}`);
  }
}
if (violations) {
  console.log(`check-truncation: ${violations} defect shape(s) found`);
  process.exit(1);
}
console.log("check-truncation: clean");
