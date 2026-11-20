import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The integration build: the artifact's embedded form of
// this app — same App, live data seam (src/integration.tsx
// selects the live adapter). Mirrors vite.config.ts (the
// kit alias, tailwind, relative base) with the integration
// entry; built into dist-integration so the standalone
// preview build (dist) is untouched.
const KIT = new URL(
  "../../../kit",
  import.meta.url,
).pathname;

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [{ find: /^@workhorse\/kit\/(.*)$/, replacement: `${KIT}/$1` }],
    dedupe: ["react", "react-dom"],
  },
  build: {
    outDir: "dist-integration",
    rollupOptions: {
      input: new URL("./integration.html", import.meta.url).pathname,
    },
  },
});
