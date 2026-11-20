import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Integration build: the entry the Workhorse Superapp shell
// embeds (src/integration.tsx via integration.html), built
// with a relative base so the bundle's asset and font URLs
// resolve inside the shell's assets/workbench/ directory.
// The standalone preview build (vite.config.ts) is untouched;
// the @kit aliases and the React pins are that config's own,
// carried over unchanged so the integration bundle resolves
// the kit's home and one React instance exactly as the
// standalone build does.
const kitHome = fileURLToPath(
  new URL("../../../kit", import.meta.url),
);

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: "@kit/components", replacement: `${kitHome}/components` },
      { find: "@kit/lib", replacement: `${kitHome}/lib` },
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
  build: {
    outDir: "dist-integration",
    rollupOptions: {
      input: fileURLToPath(new URL("./integration.html", import.meta.url)),
    },
  },
});
