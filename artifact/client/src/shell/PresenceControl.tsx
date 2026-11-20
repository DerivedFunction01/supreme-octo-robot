// PresenceControl — the TopBar presence control (kit
// sheet: PresenceChip, "state + expiry, visible on glance
// surfaces"; attention storyboard frame 2: the Today header
// carries "Active · until 5:00 PM"). One control, in the
// shell's TopBar chips slot on every app view, bound to the
// shell-held presence state.
//
// Binding: presence is attention's served state. The
// shell's state IS the served state (App.tsx holds
// useServedPresence from the attention lane: getGlance
// to read, postPresence to write, INTEGRATION.md §6),
// so this control and the Settings PresenceSection read
// and write the one state. The fuller Settings form
// (state descriptions + expiry) is the attention
// settings section mounted in Settings (storyboard
// frame 4).

import { SegmentedControl } from "@workhorse/kit/components/SegmentedControl";

export type PresenceState = "active" | "focus" | "away";

export const PRESENCE_OPTIONS: { value: PresenceState; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "focus", label: "Focus" },
  { value: "away", label: "Away" },
];

export const PRESENCE_LABELS: Record<PresenceState, string> = {
  active: "Active",
  focus: "Focus",
  away: "Away",
};

export interface PresenceControlProps {
  value: PresenceState;
  onChange: (value: PresenceState) => void;
}

export function PresenceControl({ value, onChange }: PresenceControlProps) {
  return (
    <SegmentedControl
      options={PRESENCE_OPTIONS}
      value={value}
      onChange={onChange}
      ariaLabel="Presence"
    />
  );
}
