import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Integration build: the entry the Workhorse Superapp shell
// embeds (src/integration.tsx via integration.html), built
// with a relative base so the bundle's asset and font URLs
// resolve inside the shell's assets/scheduler/ directory.
// The standalone preview build (vite.config.ts) is untouched.
const KIT = fileURLToPath(
  new URL("../../../kit", import.meta.url),
);

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [{ find: /^@workhorse\/kit\/(.*)$/, replacement: `${KIT}/$1` }],
    // The kit's components import react from outside this root;
    // dedupe pins every react import to this app's copy.
    dedupe: ["react", "react-dom"],
  },
  build: {
    outDir: "dist-integration",
    rollupOptions: {
      input: fileURLToPath(new URL("./integration.html", import.meta.url)),
    },
  },
});
