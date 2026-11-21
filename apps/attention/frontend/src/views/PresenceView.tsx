// Presence (storyboard frame 4): the one presence record —
// mode + expiry, expiry resolved at read time by the
// adapter. Changing state or expiry here re-filters the
// glance and re-labels every presence chip in the app,
// because all of them read the same record. The decision
// queue is never filtered (contract 09's asymmetry).
//
// The EXPIRES group carries the storyboard presets plus a
// Custom option (owner commission, 2026-11-15): the record
// itself holds only an absolute expires_at — the backend's
// presence write accepts any instant — so a custom duration
// or end date resolves to an instant and rides the exact
// same setPresence write the presets use.
import { useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";
import { Field, Input } from "@workhorse/kit/components/controls/Fields";
import { useDataSource, useStoreVersion } from "../attention/useStore";
import type { AttentionDataSource, ExpiryChoice, PresenceMode } from "../attention/types";
import { Group, GroupLabel, RadioRow } from "../components/groups";

const STATES: { mode: PresenceMode; label: string; sub: string }[] = [
  { mode: "active", label: "Active", sub: "Everything reaches you as it lands" },
  { mode: "focus", label: "Focus", sub: "Only breakthroughs and decisions" },
  { mode: "away", label: "Away", sub: "Items hold for the next digest window" },
];

const EXPIRIES: { choice: ExpiryChoice; label: string }[] = [
  { choice: "1h", label: "In 1 hour" },
  { choice: "17:00", label: "At 5:00 PM" },
  { choice: "tomorrow-08:00", label: "Tomorrow, 8:00 AM" },
  { choice: "none", label: "No expiry" },
];

// ---- scenario-zone wall helpers ----
// The app's wall clock is the fixed scenario zone (EST,
// UTC-5) — the same convention the adapter's time math
// uses. Date/time field values are wall times in this zone.

function wallPartsOf(d: Date): { y: number; mo: number; da: number; h: number; mi: number } {
  const shifted = new Date(d.getTime() - 5 * 3_600_000);
  return {
    y: shifted.getUTCFullYear(),
    mo: shifted.getUTCMonth() + 1,
    da: shifted.getUTCDate(),
    h: shifted.getUTCHours(),
    mi: shifted.getUTCMinutes(),
  };
}

const pad2 = (n: number): string => String(n).padStart(2, "0");

function dateValueOf(d: Date): string {
  const p = wallPartsOf(d);
  return `${p.y}-${pad2(p.mo)}-${pad2(p.da)}`;
}

function timeValueOf(d: Date): string {
  const p = wallPartsOf(d);
  return `${pad2(p.h)}:${pad2(p.mi)}`;
}

/** Wall date + time in the scenario zone -> absolute ISO. */
function scenarioIso(date: string, time: string): string | null {
  const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const tm = /^(\d{2}):(\d{2})$/.exec(time);
  if (!dm || !tm) return null;
  return new Date(Date.UTC(+dm[1], +dm[2] - 1, +dm[3], +tm[1] + 5, +tm[2], 0)).toISOString();
}

const untilDateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  month: "short",
  day: "numeric",
});
const untilTimeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/** The custom row's legible end: "Until Wed, Mar 4 · 6:04 PM". */
function untilLabel(iso: string): string {
  const d = new Date(iso);
  return `Until ${untilDateFmt.format(d)} · ${untilTimeFmt.format(d).toUpperCase()}`;
}

function CustomExpirySheet({
  ds,
  mode,
  currentExpiresAt,
  onClose,
}: {
  ds: AttentionDataSource;
  mode: PresenceMode;
  currentExpiresAt: string | null;
  onClose: () => void;
}) {
  // Opening over a live custom expiry starts on its end
  // date & time, so the current value is what gets edited;
  // otherwise the duration form starts at 2 hours.
  const [by, setBy] = useState<"duration" | "end">(currentExpiresAt ? "end" : "duration");
  const [hours, setHours] = useState("2");
  const [minutes, setMinutes] = useState("0");
  const [date, setDate] = useState(() =>
    currentExpiresAt
      ? dateValueOf(new Date(currentExpiresAt))
      : dateValueOf(new Date(ds.now().getTime() + 2 * 3_600_000)),
  );
  const [time, setTime] = useState(() =>
    currentExpiresAt
      ? timeValueOf(new Date(currentExpiresAt))
      : timeValueOf(new Date(ds.now().getTime() + 2 * 3_600_000)),
  );
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (by === "duration") {
      const h = hours.trim() === "" ? 0 : Number(hours);
      const m = minutes.trim() === "" ? 0 : Number(minutes);
      if (!Number.isFinite(h) || !Number.isFinite(m) || h < 0 || m < 0 || h * 60 + m <= 0) {
        setError("Enter a duration longer than zero — hours, minutes, or both.");
        return;
      }
      ds.setPresence(mode, "custom", new Date(ds.now().getTime() + (h * 60 + m) * 60_000).toISOString());
    } else {
      const iso = date && time ? scenarioIso(date, time) : null;
      if (!iso) {
        setError("Pick both an end date and a time.");
        return;
      }
      if (Date.parse(iso) <= ds.now().getTime()) {
        setError("That end time has already passed — pick a later one.");
        return;
      }
      ds.setPresence(mode, "custom", iso);
    }
    onClose();
  };

  const footer = (
    <>
      <Button variant="ghost" onClick={onClose}>
        Cancel
      </Button>
      <Button variant="primary" onClick={save}>
        Set expiry
      </Button>
    </>
  );

  return (
    <Sheet open title="Custom expiry" onClose={onClose} footer={footer}>
      <div className="flex flex-col gap-4">
        <div>
          <GroupLabel>Set by</GroupLabel>
          <Group>
            <RadioRow
              label="For a duration"
              sub="Hours and minutes from now"
              selected={by === "duration"}
              onSelect={() => setBy("duration")}
            />
            <RadioRow
              label="Until a date & time"
              sub="A specific end date and time"
              selected={by === "end"}
              onSelect={() => setBy("end")}
            />
          </Group>
        </div>
        {by === "duration" ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Hours">
              {(fid) => (
                <Input
                  id={fid}
                  type="number"
                  min="0"
                  inputMode="numeric"
                  value={hours}
                  onChange={(e) => setHours(e.target.value)}
                />
              )}
            </Field>
            <Field label="Minutes">
              {(fid) => (
                <Input
                  id={fid}
                  type="number"
                  min="0"
                  inputMode="numeric"
                  value={minutes}
                  onChange={(e) => setMinutes(e.target.value)}
                />
              )}
            </Field>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <Field label="End date">
              {(fid) => (
                <Input id={fid} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              )}
            </Field>
            <Field label="End time">
              {(fid) => (
                <Input id={fid} type="time" value={time} onChange={(e) => setTime(e.target.value)} />
              )}
            </Field>
          </div>
        )}
        {error ? (
          <p className="text-sm" role="alert" style={{ color: "var(--wb-status-hard-gate-text)" }}>
            {error}
          </p>
        ) : null}
      </div>
    </Sheet>
  );
}

export function PresenceView() {
  useStoreVersion();
  const ds = useDataSource();
  const presence = ds.getPresence();
  const [customOpen, setCustomOpen] = useState(false);

  return (
    <>
      <GroupLabel>State</GroupLabel>
      <Group>
        {STATES.map((s) => (
          <RadioRow
            key={s.mode}
            label={s.label}
            sub={s.sub}
            selected={presence.mode === s.mode}
            onSelect={() =>
              // Changing the state keeps the current expiry —
              // a custom instant rides the same write.
              ds.setPresence(
                s.mode,
                presence.expiry_choice,
                presence.expiry_choice === "custom" ? presence.expires_at : undefined,
              )
            }
          />
        ))}
      </Group>
      <GroupLabel>Expires</GroupLabel>
      <Group>
        {EXPIRIES.map((e) => (
          <RadioRow
            key={e.choice}
            label={e.label}
            selected={presence.expiry_choice === e.choice}
            onSelect={() => ds.setPresence(presence.mode, e.choice)}
          />
        ))}
        <RadioRow
          label="Custom…"
          sub={
            presence.expiry_choice === "custom" && presence.expires_at
              ? untilLabel(presence.expires_at)
              : "Your own duration or end date"
          }
          selected={presence.expiry_choice === "custom"}
          onSelect={() => setCustomOpen(true)}
        />
      </Group>
      {customOpen ? (
        <CustomExpirySheet
          ds={ds}
          mode={presence.mode}
          currentExpiresAt={presence.expiry_choice === "custom" ? presence.expires_at : null}
          onClose={() => setCustomOpen(false)}
        />
      ) : null}
    </>
  );
}
