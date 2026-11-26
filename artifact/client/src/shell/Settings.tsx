// Settings — the one client's unified Settings view
// (owner ruling: palette + mode + density
// stated once, here; superapp storyboard frames "Settings"
// and "Settings — Appearance").
//
// Composition (storyboard frame order): Presence (the
// attention section mount — storyboard attention frame 4),
// Appearance (Theme: System/Light/Dark; Palette: Olive/
// Teal; Density: Comfortable/Compact — the kit's own
// ModeControl / PaletteSelect / DensityToggle over the
// shell's appearance state, applied at the document root
// and persisted), Attention — Digest (the attention
// section mount, frame 5), Apps (the four apps, rows to
// their roots), About (Version). A shell-level view: it
// renders outside any app's AppShell, with the Apps
// back-row to the Launcher, as the frame shows.

import {
  GroupLabel,
  GroupedList,
  Row,
  StatRow,
} from "@workhorse/kit/components/display/GroupedList";
import { DensityToggle } from "@workhorse/kit/components/controls/DensityToggle";
import { ModeControl } from "@workhorse/kit/components/controls/ModeControl";
import { PaletteSelect } from "@workhorse/kit/components/controls/PaletteSelect";
import {
  PALETTE_OPTIONS,
  type Appearance,
} from "../lib/appearance";
import { appHref, launcherHref } from "../lib/router";
import type { AppId } from "../lib/view-contract";
import { DigestSection, PresenceSection } from "../views/attention/settings-sections";
import { APP_META, LAUNCHER_ORDER } from "./apps";
import type { PresenceState } from "./PresenceControl";

export interface SettingsProps {
  appearance: Appearance;
  onAppearanceChange: (patch: Partial<Appearance>) => void;
  presence: PresenceState;
  onPresenceChange: (value: PresenceState) => void;
  /** The served presence expiry (ISO) from the shell's
   *  served-presence state; the PresenceSection derives
   *  its Expires selection from it. */
  presenceExpiresAt?: string | null;
  /** Write mode + expiry together through the shell's
   *  served-presence state (postPresence). When given,
   *  the PresenceSection delegates every write to it, so
   *  the section and the TopBar control share the one
   *  served state and the one write path. */
  onSetPresence?: (value: PresenceState, expiresAt: Date | null) => Promise<unknown>;
  /** Whether the shell's served-presence state has
   *  landed; forwarded to the PresenceSection's
   *  readiness gate so it never presents postable
   *  rows while the delegated write path would
   *  refuse them. */
  presenceLoaded?: boolean;
  onOpen: (hash: string) => void;
}

export function Settings({
  appearance,
  onAppearanceChange,
  presence,
  onPresenceChange,
  presenceExpiresAt,
  onSetPresence,
  presenceLoaded,
  onOpen,
}: SettingsProps) {
  return (
    <main style={{ height: "100%", overflowY: "auto" }}>
      <div className="mx-auto max-w-[640px] px-5 py-6">
        <button
          type="button"
          onClick={() => onOpen(launcherHref())}
          className="flex cursor-pointer items-center gap-[3px] text-[16px]"
          style={{
            backgroundColor: "transparent",
            border: "none",
            padding: 0,
            color: "var(--ui-accent)",
            fontWeight: 550,
            fontFamily: "inherit",
          }}
        >
          ‹ Apps
        </button>
        <h1
          className="text-[32px] font-bold tracking-[-0.015em]"
          style={{ margin: "8px 0 18px" }}
        >
          Settings
        </h1>

        <GroupLabel>Presence</GroupLabel>
        <PresenceSection
          value={presence}
          onChange={onPresenceChange}
          expiresAt={presenceExpiresAt}
          onSetPresence={onSetPresence}
          servedLoaded={presenceLoaded}
        />

        <GroupLabel>Appearance</GroupLabel>
        <GroupedList>
          <Row
            label="Theme"
            end={
              <ModeControl
                value={appearance.mode}
                onChange={(mode) => onAppearanceChange({ mode })}
              />
            }
          />
          <Row
            label="Palette"
            end={
              <PaletteSelect
                value={appearance.palette}
                options={[...PALETTE_OPTIONS]}
                onChange={(id) =>
                  onAppearanceChange({ palette: id as Appearance["palette"] })
                }
              />
            }
          />
          <Row
            label="Density"
            end={
              <DensityToggle
                value={appearance.density}
                onChange={(density) => onAppearanceChange({ density })}
              />
            }
          />
        </GroupedList>

        <GroupLabel>Attention</GroupLabel>
        <DigestSection />

        <GroupLabel>Apps</GroupLabel>
        <GroupedList>
          {LAUNCHER_ORDER.map((app: AppId) => (
            <Row
              key={app}
              label={APP_META[app].name}
              badge={
                <span
                  className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px]"
                  style={{ color: "#fff", ...APP_META[app].tileStyle }}
                >
                  {APP_META[app].glyph}
                </span>
              }
              chevron
              onClick={() => onOpen(appHref(app))}
            />
          ))}
        </GroupedList>

        <GroupLabel>About</GroupLabel>
        <GroupedList>
          <StatRow label="Version">1.0</StatRow>
        </GroupedList>
      </div>
    </main>
  );
}
