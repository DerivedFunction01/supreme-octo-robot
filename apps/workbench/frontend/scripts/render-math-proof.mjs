// Rendered proof for the math adoption (the segment
// feed): bundles scripts/render-math-harness.tsx with
// esbuild — the render-smoke arrangement, plus the
// KaTeX alias vite.config.ts pins and empty loaders for
// the kit Math component's own CSS/font imports (a node
// render has no stylesheet consumer) — and runs its
// checks over both adapters' segment shapes.
//
//   npm run proof:math   (exit 1 on any failure)

import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const appRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);

const tmp = mkdtempSync(join(tmpdir(), "ui-math-"));
const entry = join(tmp, "entry.tsx");
writeFileSync(
  entry,
  `export { run } from ${JSON.stringify(join(appRoot, "scripts/render-math-harness.tsx"))};`,
);
const bundle = join(tmp, "bundle.cjs");
execFileSync(join(appRoot, "node_modules/.bin/esbuild"), [
  entry,
  "--bundle",
  "--format=cjs",
  "--jsx=automatic",
  "--platform=node",
  `--alias:react=${join(appRoot, "node_modules/react")}`,
  `--alias:react-dom=${join(appRoot, "node_modules/react-dom")}`,
  `--alias:@kit/components=${join(appRoot, "../../../kit/components")}`,
  `--alias:@kit/lib=${join(appRoot, "../../../kit/lib")}`,
  `--alias:katex=${join(appRoot, "node_modules/katex/dist/katex.mjs")}`,
  "--loader:.css=empty",
  "--loader:.woff2=empty",
  `--outfile=${bundle}`,
  "--log-level=error",
]);

const { run } = require(bundle);
const results = await run();
let failures = 0;
for (const r of results) {
  if (r.ok) {
    console.log(`PASS  ${r.name}`);
  } else {
    failures += 1;
    console.log(`FAIL  ${r.name} — missing: ${r.missing.join("; ")}`);
  }
}
process.exit(failures ? 1 : 0);
