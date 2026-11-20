import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The kit's React primitives are consumed from the kit's
// vendored home in this repo (kit/ at the repo root; source of
// truth the spec-driven starter — see kit/PROVENANCE.md).
// Only the generated CSS distribution is additionally vendored
// per-app (src/kit/, plan §10.4). See src/kit/PROVENANCE.md.
const kitHome = fileURLToPath(
  new URL("../../../kit", import.meta.url),
);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: "@kit/components", replacement: `${kitHome}/components` },
      { find: "@kit/lib", replacement: `${kitHome}/lib` },
      // The kit lives outside this app's tree, so its own
      // `react` imports must resolve to this app's copies —
      // one React instance for the whole build.
      { find: /^react$/, replacement: fileURLToPath(new URL("./node_modules/react/index.js", import.meta.url)) },
      { find: /^react\/jsx-runtime$/, replacement: fileURLToPath(new URL("./node_modules/react/jsx-runtime.js", import.meta.url)) },
      { find: /^react-dom$/, replacement: fileURLToPath(new URL("./node_modules/react-dom/index.js", import.meta.url)) },
      { find: /^react-dom\/client$/, replacement: fileURLToPath(new URL("./node_modules/react-dom/client.js", import.meta.url)) },
      // Same seam for the kit Math component's KaTeX: the
      // kit declares the dependency (0.16.11, pinned by
      // the math study) but resolves it from this app's
      // copy, like React.
      { find: /^katex$/, replacement: fileURLToPath(new URL("./node_modules/katex/dist/katex.mjs", import.meta.url)) },
    ],
  },
  server: { port: 8799 },
  preview: { port: 8799 },
});
