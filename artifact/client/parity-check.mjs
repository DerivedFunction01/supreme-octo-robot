// Parity check — the durable spec-parity assertions for
// the workhorse superapp's ONE client (owner ruling
// 2026-11-16: one app, one bundle, the four apps as
// views on the unified kit; INTEGRATION.md is the
// contract this guards). Plain node, no dependencies:
//
//   node client/parity-check.mjs        (from artifact/)
//
// Asserts, over client/src and the built client/dist:
//   (a) dist holds exactly one HTML document and
//       exactly one JS bundle (the canonical single
//       bundle — the per-view split retired 2026-11-22;
//       the CVM publish stage accepts no split): the
//       document loads exactly one script (the bundle)
//       and exactly one stylesheet, and no other JS
//       asset is staged — never a second entry, a
//       second document, or an orphan bundle;
//   (b) no frame-shell iframes and no `workhorse:`
//       postMessage relay markers in src or in the
//       bundle — the frame shell's transport never
//       returns. An iframe may appear ONLY as the
//       workbench entry preview page's content area: a
//       sandboxed srcDoc rendering of a served entry
//       document (views/workbench/sections/entries/
//       EntryPage.tsx — the full-page form of the
//       original viewer's stage, FU-1) — it loads no
//       document, frames no app, and speaks no
//       protocol. Any iframe bearing a src, lacking a
//       sandbox, or built dynamically fails;
//   (c) exactly one createActionClient call site in src,
//       in src/lib/actions.ts — the single action layer;
//   (d) no src import reaches the (removed) reference
//       trees under client/pages/, and no src import
//       pulls a per-app theme copy — stylesheets come
//       from the kit's home or the client's own
//       index.css only;
//   (e) the four app ids and their nav route roots are
//       present in the built bundle;
//   (f) the workbench entry preview is a full-page
//       route (FU-1): the page component exists, the
//       embedded stage of the pre-FU-1 form is gone,
//       the route grammar parses and builds the
//       preview href, and the drill-in navigates
//       through that builder.
//
// Exit 0 when every assertion holds; exit 1 with each
// failure named otherwise.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const clientDir = dirname(fileURLToPath(import.meta.url));
const srcDir = join(clientDir, "src");
const distDir = join(clientDir, "dist");

const failures = [];
function check(name, ok, detail) {
  if (ok) {
    console.log(`ok   ${name}`);
  } else {
    failures.push(name);
    console.log(`FAIL ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...walk(path));
    else out.push(path);
  }
  return out;
}

const rel = (path) => relative(clientDir, path);
const read = (path) => readFileSync(path, "utf8");

/* ---------------- (a) the dist shape ---------------- */

if (!existsSync(distDir)) {
  check("dist exists", false, "client/dist is missing — run the client build first");
  process.exit(1);
}
const distFiles = walk(distDir);
const htmlFiles = distFiles.filter((f) => f.endsWith(".html"));
const jsFiles = distFiles.filter((f) => f.endsWith(".js"));
const cssFiles = distFiles.filter((f) => f.endsWith(".css"));
check(
  "dist: exactly one HTML document",
  htmlFiles.length === 1 && htmlFiles[0].endsWith("index.html"),
  `found ${htmlFiles.map(rel).join(", ") || "(none)"}`,
);
// The one bundle, in its canonical single-bundle form:
// the document loads exactly one script and exactly one
// stylesheet, and that script is the only JS asset
// staged — the mount seam's dynamic imports are inlined
// into it by the canonical build. Any other JS asset
// would be a second bundle by another name (the orphan
// test below still applies, trivially).
const documentText = htmlFiles.length === 1 ? read(htmlFiles[0]) : "";
const scriptRefs = [...documentText.matchAll(/<script[^>]+src="\.\/assets\/([^"]+\.js)"/g)].map(
  (m) => m[1],
);
const styleRefs = [...documentText.matchAll(/<link[^>]+href="\.\/assets\/([^"]+\.css)"/g)].map(
  (m) => m[1],
);
check(
  "dist: the document loads exactly one script (the bundle's entry chunk)",
  scriptRefs.length === 1 && jsFiles.some((f) => f.endsWith(scriptRefs[0])),
  `found ${scriptRefs.join(", ") || "(none)"}`,
);
check(
  "dist: the document loads exactly one stylesheet",
  styleRefs.length === 1 && cssFiles.some((f) => f.endsWith(styleRefs[0])),
  `found ${styleRefs.join(", ") || "(none)"}`,
);
const jsTexts = jsFiles.map((f) => read(f));
const orphanJs = jsFiles.filter((f) => {
  const name = f.split("/").pop();
  if (scriptRefs.includes(name)) return false;
  return !jsTexts.some((text) => text.includes(`./${name}`));
});
check(
  "dist: exactly one JS bundle staged, no orphan JS",
  jsFiles.length === 1 && orphanJs.length === 0,
  `js assets: ${jsFiles.length}; orphans: ${orphanJs.map(rel).join(", ") || "(none)"}`,
);

/* ---------------- src + bundle text ---------------- */

const srcFiles = walk(srcDir).filter((f) => /\.(ts|tsx|js|mjs|css)$/.test(f));
const bundleText = jsFiles.length > 0 ? jsFiles.map(read).join("\n") : "";

/* ---------------- (b) no frames, no relay ----------------
 * A frame-shell iframe loads a sibling document through
 * its src and talks back over postMessage. The one
 * permitted iframe — the entry preview page's content
 * area — is recognized structurally: sandbox + srcDoc,
 * and NO src attribute in its tag (src) or props
 * (bundle). Dynamic construction (createElement) is
 * banned outright. */

function iframeOffences(text, inBundle) {
  const offences = [];
  if (/createElement\(\s*["']iframe["']/.test(text)) {
    offences.push("createElement('iframe')");
  }
  // In the bundle, a bare "iframe" string is not a usage
  // (React DOM and the sanitizer carry tag-name tables);
  // a usage is a call with "iframe" as the element type
  // and a props object — C("iframe",{...}) — which is
  // what the one real usage compiles to.
  const tagRe = inBundle ? /\(\s*["']iframe["']\s*,\s*\{/g : /<iframe\b/g;
  for (const match of text.matchAll(tagRe)) {
    const window = text.slice(match.index, match.index + 1200);
    const hasSandbox = inBundle
      ? /sandbox\s*:/.test(window)
      : /\bsandbox\s*=/.test(window);
    const hasSrcDoc = inBundle
      ? /\bsrcDoc\s*:/.test(window)
      : /\bsrcDoc\s*=/.test(window);
    const hasSrc = inBundle
      ? /\bsrc\s*:/.test(window)
      : /\ssrc\s*=/.test(window);
    if (!hasSandbox || !hasSrcDoc || hasSrc) {
      offences.push(
        `iframe at offset ${match.index} (sandbox=${hasSandbox}, srcDoc=${hasSrcDoc}, src=${hasSrc})`,
      );
    }
  }
  return offences;
}

const RELAY_RE = /["']workhorse:/;
const srcIframeOffences = srcFiles.flatMap((f) =>
  iframeOffences(read(f), false).map((o) => `${rel(f)}: ${o}`),
);
check(
  "src: no frame-shell iframes (sandboxed srcDoc preview page only)",
  srcIframeOffences.length === 0,
  srcIframeOffences.join("; "),
);
const bundleIframeOffences = iframeOffences(bundleText, true);
check(
  "bundle: no frame-shell iframes (sandboxed srcDoc preview page only)",
  bundleIframeOffences.length === 0,
  bundleIframeOffences.join("; "),
);
const relayHits = srcFiles.filter((f) => RELAY_RE.test(read(f)));
check(
  "src: no workhorse: postMessage markers",
  relayHits.length === 0,
  relayHits.map(rel).join(", "),
);
check("bundle: no workhorse: postMessage markers", !RELAY_RE.test(bundleText));

/* ---------------- (c) one action client ---------------- */

const CALL_RE = /createActionClient\s*(?:<[^()]*>)?\s*\(/g;
const callSites = [];
for (const file of srcFiles) {
  if (!/\.tsx?$/.test(file)) continue;
  const matches = read(file).match(CALL_RE);
  if (matches) callSites.push({ file, count: matches.length });
}
const totalCalls = callSites.reduce((sum, s) => sum + s.count, 0);
check(
  "src: exactly one createActionClient call site, in lib/actions.ts",
  totalCalls === 1 &&
    callSites.length === 1 &&
    callSites[0].file === join(srcDir, "lib", "actions.ts"),
  `found ${totalCalls} in ${callSites.map((s) => rel(s.file)).join(", ") || "(none)"}`,
);

/* ---------------- (d) no reference trees, no theme copies ---------------- */

const IMPORT_RE = /(?:from\s+|import\s*\(?\s*)["']([^"']+)["']/g;
const badImports = [];
for (const file of srcFiles) {
  if (!/\.tsx?$/.test(file)) continue;
  for (const match of read(file).matchAll(IMPORT_RE)) {
    const spec = match[1];
    if (spec.includes("pages/")) {
      badImports.push(`${rel(file)} → ${spec} (reference tree)`);
    } else if (
      spec.endsWith(".css") &&
      spec !== "./index.css" &&
      !spec.includes("kit/")
    ) {
      badImports.push(`${rel(file)} → ${spec} (stylesheet outside the kit's home)`);
    } else if (spec.includes("/themes/") && !spec.includes("kit")) {
      badImports.push(`${rel(file)} → ${spec} (per-app theme copy)`);
    }
  }
}
check(
  "src: no imports of client/pages/ or per-app theme copies",
  badImports.length === 0,
  badImports.join("; "),
);

/* ---------------- (e) the four apps in the bundle ---------------- */

for (const app of ["workbench", "scheduler", "attention", "runner"]) {
  check(
    `bundle: app id "${app}" present`,
    bundleText.includes(app),
  );
  check(
    `bundle: nav route root "#/${app}" present`,
    bundleText.includes(`#/${app}`),
  );
}

/* ---------------- (f) the preview is a full page ----------------
 * FU-1 (owner ruling 2026-11-16): the workbench entry
 * preview is a full-page route of the one client — the
 * drill-in's door navigates to it; the page is not an
 * embedded stage. Asserted in src text, in the same
 * idiom as the rest of this check: the page component
 * exists and carries the one permitted iframe (its
 * shape is scanned in (b)), the embedded stage
 * component of the pre-FU-1 form is gone by name, the
 * route grammar parses and builds the preview href,
 * and the drill-in navigates through that builder. */

const entryPagePath = join(
  srcDir,
  "views/workbench/sections/entries/EntryPage.tsx",
);
check(
  "src: the full-page entry preview exists (EntryPage.tsx)",
  existsSync(entryPagePath),
);
const stageLeftovers = srcFiles.filter((f) => read(f).includes("PreviewStage"));
check(
  "src: no embedded preview stage remains",
  stageLeftovers.length === 0,
  stageLeftovers.map(rel).join(", "),
);
const routingText = read(join(srcDir, "views/workbench/lib/routing.ts"));
check(
  "src: the preview route parses and builds hrefs",
  routingText.includes('"entry-page"') && routingText.includes("entryPageHref"),
);
const entryDetailText = read(
  join(srcDir, "views/workbench/sections/entries/EntryDetail.tsx"),
);
check(
  "src: the drill-in navigates to the full page",
  entryDetailText.includes("entryPageHref"),
);

/* ---------------- verdict ---------------- */

if (failures.length > 0) {
  console.error(`\nparity check: ${failures.length} assertion(s) failed`);
  process.exit(1);
}
console.log("\nparity check: all assertions hold");
