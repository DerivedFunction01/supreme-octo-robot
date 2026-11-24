// Client build — ONE client, ONE bundle, ONE document
// (owner ruling, audit Addendum 3: a single
// integrated frontend shell; the four apps are views of
// this client).
//
// This module performs the SDK's canonical build
// (@hatch/space-sdk's buildClient, mirrored
// parameter-for-parameter below): ONE bundle — the
// bundler inlines the dynamic imports at src/App.tsx's
// mount seam into the single entry chunk. One build
// graph, one entry document, one router, one action
// layer; no per-app document, page build, or relay.
//
// The per-view split this build once carried (perf
// lane L-D's `splitting: true` delta, one lazy chunk
// per app view) is RETIRED: the platform's CVM publish
// stage requires exactly one JS bundle in the staged
// client, and the split build failed that stage with
// 85 JS files on a republish attempt — a split bundle
// cannot be published at all, so the delta's perf
// intent has no served surface to act on. The
// canonical single bundle is the published form. The
// mount seam's dynamic
// imports stay in the source; if the platform grows a
// split-capable publish stage, the delta can return
// behind this file's shape check.
//
// Everything else — the driver guard, the production
// define, the platform version, the asset naming, the
// tailwind plugin (the SDK's own, resolved from this
// install as the SDK resolves it), the asset-URL
// re-prefixing, the pdfjs staging — is the SDK's build,
// unchanged.
//
// The shape check at the end keeps the ruled form: the
// staging holds exactly ONE document (no frame pages,
// no sibling documents — the daemon's sibling-document
// mechanism the frame shell rode stays unused), and
// exactly ONE JS bundle, so a build that silently
// split again fails here instead of at the publish
// stage.
import { cp, readFile, rm } from "node:fs/promises";
import { readdirSync } from "node:fs";
import { basename, join } from "node:path";
import tailwindPlugin from "bun-plugin-tailwind";

const ENTRY = "./client/index.html";
const OUTDIR = "./client/dist";
const PDFJS_ASSET_ROOT = "./assets/pdfjs/";

// The SDK build's driver guard, verbatim in effect (see
// @hatch/space-sdk/dist/build.js for its full text): a
// web artifact is built, verified, and published ONLY by
// the artifact create/edit tools, which set this env var;
// running this build by hand compiles source but does NOT
// migrate, verify, register, or deploy anything.
if (process.env.HATCH_SPACES_BUILD_DRIVER !== "1") {
  console.error(
    "This web artifact cannot be built by hand. To make this change, call the `artifact.edit` tool " +
      "(or `artifact.create_web_static` / `artifact.create_web_fullstack` for a new one); it rebuilds and re-publishes the web artifact " +
      "automatically. Speak to the user as you would about any edit you are " +
      "making for them: conversational, focused on what is changing and that it " +
      "will be ready shortly.",
  );
  process.exit(1);
}
if (typeof Bun === "undefined" || typeof Bun.build !== "function") {
  throw new Error("buildClient() must run under Bun");
}
await rm(OUTDIR, { force: true, recursive: true });
// An edit adopting managed upgrades ships this bundle before the platform writes the new
// version to space.json, so the build driver passes the version being adopted.
const adopted = Number(process.env.HATCH_SPACE_CLIENT_PLATFORM_VERSION);
const platformVersion =
  Number.isInteger(adopted) && adopted > 0
    ? adopted
    : await readFile("./space.json", "utf8")
        .then((text) => JSON.parse(text).platformVersion)
        .catch(() => undefined);
const result = await Bun.build({
  entrypoints: [ENTRY],
  outdir: OUTDIR,
  minify: true,
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
    __HATCH_SPACE_PLATFORM_VERSION__: JSON.stringify(
      typeof platformVersion === "number" ? platformVersion : 0,
    ),
  },
  naming: {
    asset: "assets/[name]-[hash].[ext]",
    chunk: "assets/[name]-[hash].[ext]",
    entry: "[name].[ext]",
  },
  plugins: [tailwindPlugin],
});
if (!result.success) {
  for (const log of result.logs) {
    console.error(log);
  }
  throw new Error("buildClient() failed; see logged diagnostics");
}
// Bun writes imported assets to `naming.asset` (`assets/<name>-<hash>.<ext>`)
// but emits the JS/CSS import URL as a bare `./<name>-<hash>.<ext>` — without
// the `assets/` directory prefix. The browser then resolves it against the
// document base (`/spaces/v2/<slug>/`) and requests `/spaces/v2/<slug>/<file>`,
// which 404s because the daemon only serves built files under `/assets/`.
// (Bun's `publicPath` would fix asset URLs but double-prefixes the entry/chunk
// refs, which already carry `assets/` from `naming.chunk`.) Re-prefix only the
// bare imported-asset URLs to `./assets/...`. This is idempotent
// (`./assets/<f>` does not contain `./<f>`) and never rewrites chunk refs.
// Keep `assets/` in sync with `naming.asset` above.
const assetFiles = result.outputs
  .filter((output) => output.kind === "asset")
  .map((output) => basename(output.path));
let needsPdfjsAssets = false;
for (const output of result.outputs) {
  if (!/\.(js|css|html)$/.test(output.path)) {
    continue;
  }
  let text = await output.text();
  needsPdfjsAssets ||= text.includes(PDFJS_ASSET_ROOT);
  let changed = false;
  for (const name of assetFiles) {
    const bare = `./${name}`;
    if (text.includes(bare)) {
      text = text.split(bare).join(`./assets/${name}`);
      changed = true;
    }
  }
  if (changed) {
    await Bun.write(output.path, text);
  }
}
if (needsPdfjsAssets) {
  // The SDK's staged pdfjs assets, from its own home in
  // this install (the SDK's build copies them from beside
  // its build module; this mirror names the same place).
  await cp(
    join(import.meta.dir, "..", "node_modules", "@hatch", "space-sdk", "dist", "pdfjs-assets"),
    join(OUTDIR, "assets", "pdfjs"),
    { recursive: true },
  );
}

/* ---------------- the shape check ---------------- */

const distDir = join(import.meta.dir, "dist");
const assetsDir = join(distDir, "assets");
const staged = readdirSync(distDir).sort();
const assets = readdirSync(assetsDir).sort();
const documents = [...staged, ...assets].filter((f) => f.endsWith(".html"));
if (documents.length !== 1 || documents[0] !== "index.html") {
  throw new Error(
    `one-client build must stage exactly one document (index.html); staged documents: ${documents.join(", ") || "(none)"}`,
  );
}
const jsFiles = [...staged, ...assets].filter((f) => f.endsWith(".js"));
if (jsFiles.length !== 1) {
  throw new Error(
    `canonical build must stage exactly one JS bundle (the CVM publish stage accepts no split); staged: ${jsFiles.join(", ") || "(none)"}`,
  );
}

console.log(
  `client staged: dist/index.html + assets/{${assets.join(", ")}} — one bundle, one document`,
);
