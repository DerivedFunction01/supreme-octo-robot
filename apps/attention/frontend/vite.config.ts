import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The Workhorse Kit v1's source of truth is the spec-driven
// starter; this repo carries a vendored copy (kit/ at the repo
// root — see kit/PROVENANCE.md). This standalone stage build
// aliases it so the app imports the kit's primitives from the
// kit itself — never a per-app copy.
// In the consolidated repo's one frontend build (plan §10.4) the
// same imports resolve through the workspace package instead.
const KIT = new URL(
  "../../../kit",
  import.meta.url,
).pathname;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [{ find: /^@workhorse\/kit\/(.*)$/, replacement: `${KIT}/$1` }],
    // The kit's components import react from outside this root;
    // dedupe pins every react import to this app's copy.
    dedupe: ["react", "react-dom"],
  },
});
