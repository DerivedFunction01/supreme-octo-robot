// App identity — the storyboard's AppTiles (superapp
// storyboard, Launcher frame; kit sheet: "AppTile — the
// gradient app icon"). The gradients are the storyboard's
// own values (--tile-sched / --tile-wb / --tile-run /
// --tile-attn / --tile-set in its stylesheet); the glyphs
// are drawn in the kit's icon grammar (Lucide-style SVG,
// currentColor) — the kit imports no icon library, so app
// glyphs arrive through props, here.

import type { CSSProperties, ReactNode } from "react";
import type { AppId } from "../lib/view-contract";

export interface AppMeta {
  id: AppId;
  name: string;
  tileStyle: CSSProperties;
  glyph: ReactNode;
}

function glyphProps() {
  return {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  } as const;
}

function SchedulerGlyph() {
  return (
    <svg {...glyphProps()}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function WorkbenchGlyph() {
  return (
    <svg {...glyphProps()}>
      <rect x="3" y="3" width="8" height="8" rx="2" />
      <rect x="13" y="3" width="8" height="8" rx="2" />
      <rect x="3" y="13" width="8" height="8" rx="2" />
      <rect x="13" y="13" width="8" height="8" rx="2" />
    </svg>
  );
}

function RunnerGlyph() {
  return (
    <svg {...glyphProps()}>
      <path d="M13 2 4.5 13.5H11L9.5 22 19 10h-6.5L13 2z" />
    </svg>
  );
}

function AttentionGlyph() {
  return (
    <svg {...glyphProps()}>
      <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6" />
      <path d="M10 20a2 2 0 0 0 4 0" />
    </svg>
  );
}

export function SettingsGlyph() {
  return (
    <svg {...glyphProps()}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.51 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.24.6.86 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1z" />
    </svg>
  );
}

export const APP_META: Record<AppId, AppMeta> = {
  scheduler: {
    id: "scheduler",
    name: "Scheduler",
    tileStyle: { background: "linear-gradient(160deg,#67742f,#4b5320)" },
    glyph: <SchedulerGlyph />,
  },
  workbench: {
    id: "workbench",
    name: "Workbench",
    tileStyle: { background: "linear-gradient(160deg,#14b8a6,#0f766e)" },
    glyph: <WorkbenchGlyph />,
  },
  runner: {
    id: "runner",
    name: "Runner",
    tileStyle: { background: "linear-gradient(160deg,#56B4E9,#0072B2)" },
    glyph: <RunnerGlyph />,
  },
  attention: {
    id: "attention",
    name: "Attention",
    tileStyle: { background: "linear-gradient(160deg,#f0854c,#D55E00)" },
    glyph: <AttentionGlyph />,
  },
};

export const SETTINGS_TILE_STYLE: CSSProperties = {
  background: "linear-gradient(160deg,#8a8d7c,#6f7263)",
};

/** Launcher tile order (storyboard Launcher frame):
 *  Scheduler, Workbench, Runner, Attention, Settings. */
export const LAUNCHER_ORDER: AppId[] = [
  "scheduler",
  "workbench",
  "runner",
  "attention",
];
