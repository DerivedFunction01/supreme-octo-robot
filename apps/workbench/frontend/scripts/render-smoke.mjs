// Render smoke test — mounts every section server-side
// against the mock adapter and verifies each renders its
// storyboard marker content without throwing. Two bundles:
// the desktop harness, and the phone harness (matchMedia
// stubbed to <= 480px, so the shell's phone presentation and
// the explorer/peek phone forms render — and the desktop
// sidebar provably does not).
//
//   npm run smoke:render

import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);

function bundleResults(harnessRel, tag) {
  const tmp = mkdtempSync(join(tmpdir(), `wb-render-${tag}-`));
  const entry = join(tmp, "entry.tsx");
  writeFileSync(entry, `export { results } from ${JSON.stringify(join(appRoot, harnessRel))};`);
  const bundle = join(tmp, "bundle.cjs");
  execFileSync(join(appRoot, "node_modules/.bin/esbuild"), [
    entry,
    "--bundle",
    "--format=cjs",
    "--jsx=automatic",
    "--platform=node",
    // The kit's primitives import React from the kit's home,
    // which has no node_modules — pin them to this app's copy,
    // exactly as vite.config.ts does for the real build.
    `--alias:react=${join(appRoot, "node_modules/react")}`,
    `--alias:react-dom=${join(appRoot, "node_modules/react-dom")}`,
    `--alias:@kit/components=${join(appRoot, "../../../kit/components")}`,
    `--alias:@kit/lib=${join(appRoot, "../../../kit/lib")}`,
    // The kit Math component's KaTeX, pinned to this
    // app's copy exactly as vite.config.ts pins it; its
    // own CSS/font imports are emptied — a node render
    // has no stylesheet consumer (the math adoption).
    `--alias:katex=${join(appRoot, "node_modules/katex/dist/katex.mjs")}`,
    "--loader:.css=empty",
    "--loader:.woff2=empty",
    `--outfile=${bundle}`,
    "--log-level=error",
  ]);
  return require(bundle).results;
}

const all = [
  ...bundleResults("scripts/render-harness.tsx", "desktop"),
  ...bundleResults("scripts/render-harness-phone.tsx", "phone"),
];

let failures = 0;
for (const r of all) {
  if (r.ok) {
    console.log(`PASS  ${r.name} — ${r.length} chars, marker present`);
  } else {
    failures += 1;
    console.log(
      `FAIL  ${r.name} — marker ${JSON.stringify(r.marker)} missing${r.absent ? ` or absent-string ${JSON.stringify(r.absent)} present` : ""}${r.error ? `; error: ${r.error}` : ` (rendered ${r.length} chars)`}`,
    );
  }
}
console.log(failures === 0 ? "\nALL SECTIONS RENDERED" : `\n${failures} SECTION(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
