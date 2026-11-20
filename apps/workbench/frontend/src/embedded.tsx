// The mounted tree for the integration entry. Loaded by
// integration.tsx only after its data selection has run
// (an injected feeds document, a fetched one, or the
// explicit mock opt-out), so the seam in lib/store.tsx
// reads the document at module evaluation and the app
// mounts on the chosen adapter, never flashing another.
//
// Theme follows the shell the same way the other embedded
// apps do: the shell's data-palette / data-mode / data-density
// are mirrored onto this document's element — by the plain
// shell bridge in the embedded page and re-asserted here —
// because the kit themes key off those document data
// attributes. App.tsx's
// standalone mode handling drives data-mode from the OS; in
// the embed the shell owns it, so this entry re-applies the
// shell's values whenever either document's attributes move.
// The app's "Apps" back-row returns to the shell's launcher
// through the bridge's workhorse:apps post (the kit AppShell
// renders that row without a hook class, so the bridge matches
// the button whose label is "Apps", as in the other embeds).
import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./app.css";

function parentAttr(name: string): string | null {
  try {
    return window.parent.document.documentElement.getAttribute(name);
  } catch {
    return null;
  }
}

function ThemeSync() {
  useEffect(() => {
    const sync = () => {
      const d = document.documentElement;
      const pal = parentAttr("data-palette");
      if (pal && d.getAttribute("data-palette") !== pal) {
        d.setAttribute("data-palette", pal);
      }
      const mode = parentAttr("data-mode");
      if (mode && d.getAttribute("data-mode") !== mode) {
        d.setAttribute("data-mode", mode);
      }
      const density = parentAttr("data-density");
      if (density && d.getAttribute("data-density") !== density) {
        d.setAttribute("data-density", density);
      }
    };
    sync();
    let parentObserver: MutationObserver | null = null;
    try {
      parentObserver = new MutationObserver(sync);
      parentObserver.observe(window.parent.document.documentElement, {
        attributes: true,
        attributeFilter: ["data-palette", "data-mode", "data-density"],
      });
    } catch {
      /* standalone: keep the initial read */
    }
    // App.tsx writes data-mode from the OS in standalone form;
    // re-assert the shell's value whenever this document's
    // attributes are written by anything else.
    let selfObserver: MutationObserver | null = null;
    try {
      selfObserver = new MutationObserver(sync);
      selfObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-palette", "data-mode", "data-density"],
      });
    } catch {
      /* as above */
    }
    return () => {
      parentObserver?.disconnect();
      selfObserver?.disconnect();
    };
  }, []);
  return null;
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <ThemeSync />
    <App />
  </StrictMode>,
);
