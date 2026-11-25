// Settings — the app-level route (#/settings), the ONE
// home for settings (repo-home spec §3): Appearance
// (mode, palette, density — the ONLY appearance controls
// in the app; the shell chrome carries a Settings nav
// entry and nothing else) and Workspace (the server's
// effective configuration, read-only) — the Workspace
// panel lives in settings/SettingsPanels.tsx.
//
// The controls are the kit's (Subplan 04), consumed against
// their contracted props: ModeControl / PaletteSelect /
// DensityToggle. Applying a change is instant (selector
// switching over the shipped themes bundle, SPEC §11.2) and
// persisted client-side by the caller (lib/preferences).

import { DensityToggle } from "@workhorse/kit/components/controls/DensityToggle";
import { ModeControl } from "@workhorse/kit/components/controls/ModeControl";
import { PaletteSelect } from "@workhorse/kit/components/controls/PaletteSelect";
import type { Appearance, Density, Mode } from "../../lib/preferences";
import { PALETTE_OPTIONS } from "../../lib/preferences";
import { ProjectsTrackingPanel } from "./ProjectsTrackingPanel";
import { SettingsPanels } from "./SettingsPanels";

const rowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "var(--ui-space-24)",
  padding: "var(--ui-space-16) 0",
  borderBottom: "1px solid var(--ui-border-default)",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  fontSize: "var(--ui-font-size-sm)",
  lineHeight: "var(--ui-line-height-sm)",
};

export function SettingsSection({
  appearance,
  onChange,
}: {
  appearance: Appearance;
  onChange: (next: Appearance) => void;
}) {
  return (
    <section data-anchor="settings/appearance-panel">
      <h2
        style={{
          fontSize: "var(--ui-font-size-xs)",
          lineHeight: "var(--ui-line-height-xs)",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--ui-content-secondary)",
        }}
      >
        Appearance
      </h2>
      <div style={rowStyle}>
        <div>
          <div style={labelStyle}>Mode</div>
        </div>
        <ModeControl
          value={appearance.mode}
          onChange={(mode: Mode) => onChange({ ...appearance, mode })}
        />
      </div>
      <div style={rowStyle}>
        <div>
          <div style={labelStyle}>Palette</div>
        </div>
        <PaletteSelect
          value={appearance.palette}
          options={PALETTE_OPTIONS}
          onChange={(palette: string) => onChange({ ...appearance, palette })}
        />
      </div>
      <div style={rowStyle}>
        <div>
          <div style={labelStyle}>Density</div>
        </div>
        <DensityToggle
          value={appearance.density}
          onChange={(density: Density) => onChange({ ...appearance, density })}
        />
      </div>
      <SettingsPanels />
      <ProjectsTrackingPanel />
    </section>
  );
}
