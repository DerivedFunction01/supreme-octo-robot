// Attention view mount — the shell's contract surface for
// the Attention app (INTEGRATION.md §2). Subroutes, from
// the restored original's screens (client/pages/attention
// — app.js renders Today, Digest, Handlers, Handler,
// Rules, Registries) cross-checked against the attention
// storyboard's 7 frames:
//
//   /                    Today (frame 2; the glance header
//                        is frame 1, the night state frame
//                        6 — presentations of this view)
//   /digest              Digest
//   /handlers            Handlers (frame 7)
//   /handlers/<handle>   Handler detail (frame 3)
//   /rules               Rules
//   /registries         Registries
//
// Presence and Digest settings are NOT routes here: they
// are the sections mounted in the shell's Settings view
// (./settings-sections.tsx, frames 4–5), bound there.
//
// The views are the original's behaviour re-composed on
// the unified kit: every read rides a portion with
// last-good fallback, every write goes through the one
// action layer, and the shared item card, note toast,
// confirm dialog, and presence dots live in ./ui.tsx and
// ./item-card.tsx.

import type { ReactNode } from "react";
import type { AppViewModule, ViewProps } from "../../lib/view-contract";
import { DigestView } from "./digest";
import { HandlerDetailView, HandlersView } from "./handlers";
import { RegistriesView } from "./registries";
import { RulesView } from "./rules";
import { TodayView } from "./today";
import { AttentionProvider } from "./ui";
import { attentionMeta } from "./meta";

function Component({ subroute, navigate, onBadges }: ViewProps) {
  let view: ReactNode;
  if (subroute === "/digest") {
    view = <DigestView />;
  } else if (subroute === "/handlers") {
    view = <HandlersView />;
  } else if (subroute.startsWith("/handlers/")) {
    view = (
      <HandlerDetailView
        handle={decodeURIComponent(subroute.slice("/handlers/".length))}
      />
    );
  } else if (subroute === "/rules") {
    view = <RulesView />;
  } else if (subroute === "/registries") {
    view = <RegistriesView />;
  } else {
    // "/" and "/today" — and any unknown subroute lands on
    // the app's home view, as the shell lands unknown
    // hashes on the Launcher.
    view = <TodayView onBadges={onBadges} />;
  }
  return <AttentionProvider navigate={navigate}>{view}</AttentionProvider>;
}

// The mount assembles from ./meta (the shell-facing
// half — nav, active key, crumb — which the shell
// imports statically for its chrome) and this module's
// Component. The shell loads this module lazily, as the
// attention chunk of the one bundle (per-view split;
// src/App.tsx holds the seam).
export const attentionView: AppViewModule = {
  ...attentionMeta,
  Component,
};
