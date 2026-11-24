// Boot for the space's ONE client bundle (owner ruling:
// one integrated frontend — one entry, one
// bundle, one router). There is no runtime branch: the
// entry document is the only document, and every surface
// is a view of this client, mounted by its hash router.
//
// Keep the QueryClientProvider + hatch-space-root wrapper
// exactly: the SDK styles select on them (the workbench
// original's main.tsx is the pattern). Appearance is
// applied to the document root before first paint so a
// saved palette/mode/density never flashes the default.

import { spaceQueryClient } from "@hatch/space-sdk/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { applyAppearance, loadAppearance } from "./lib/appearance";
import "./index.css";
// The kit's generated theme distribution, consumed from
// its home (repo-root kit/) through the @workhorse/kit
// package dependency — never copied into the client.
// Imported as its own stylesheet root so its fonts.css
// url()s resolve against the kit's home.
import "@workhorse/kit/themes/index.css";
// Syntax highlighting (.hljs-*), likewise consumed from
// the kit's home: the workbench original's hand-authored
// stylesheet, homed in kit/themes (INTEGRATION.md §4 —
// a surface needing more extends the kit once, in its
// home, never locally).
import "@workhorse/kit/themes/highlight.css";

applyAppearance(loadAppearance());

const rootEl = document.querySelector<HTMLElement>("[data-generated-space-root]");
if (!rootEl) {
  throw new Error("missing generated space root element");
}

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={spaceQueryClient}>
      <div className="hatch-space-root" data-hatch-space-root style={{ height: "100%" }}>
        <App />
      </div>
    </QueryClientProvider>
  </StrictMode>,
);
