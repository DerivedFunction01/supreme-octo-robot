// Attention's Settings sections — mounted by the shell's
// unified Settings view (INTEGRATION.md §5–§6), bound by
// the attention lane to the served state:
//
//   Frame 4 · Presence — the state rows with their ruled
//   descriptions and the Expires options, their times
//   computed at binding (presence.ts), never the frame's
//   instance labels. Reads ride getGlance; the mode half
//   drives the shell's presence state through the props
//   (the shell's state becomes the served state — the
//   section syncs it from the glance on load), and every
//   change posts through postPresence with the original's
//   body {mode, expires_at, expectation: ""}.
//   Frame 5 · Digest — the windows as switches over the
//   digest's served times (enabled state from the
//   digest's enabled_times), the Next window line, the
//   owner's own window-times editor (times + the
//   browser's timezone, the hardcoded-time cure), and
//   the Include switches; writes ride postDigestPrefs
//   ({window_time, window_enabled} / {window_times,
//   window_tz} / {include_key, include_enabled} — the
//   backend's stored prefs).
//
// These sections render inside the shell's Settings view,
// outside the attention mount's provider: failures surface
// as an inline line in the section, not the note toast.

import { useEffect, useState } from "react";
import {
  GroupLabel,
  GroupedList,
  RadioRow,
  StatRow,
  SwitchRow,
} from "@workhorse/kit/components/display/GroupedList";
import type { PresenceState } from "../../shell/PresenceControl";
import {
  clock,
  dayWord,
  windowClock,
  windowName,
  minutesUntil,
  type DigestPayload,
  type GlancePayload,
} from "./model";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Field, Input } from "@workhorse/kit/components/controls/Fields";
import {
  customExpiryDate,
  customExpiryFields,
  expiryDateFor,
  expiryOptions,
  expirySelectionFor,
  postPresenceMode,
  type ExpirySelection,
} from "./presence";
import { api, call, usePortion } from "./transport";

/* ---------------- Presence (storyboard frame 4) ---------------- */

const STATE_ROWS: { value: PresenceState; label: string; sub: string }[] = [
  { value: "active", label: "Active", sub: "Everything reaches you as it lands" },
  { value: "focus", label: "Focus", sub: "Only breakthroughs and decisions" },
  { value: "away", label: "Away", sub: "Items hold for the next digest window" },
];

export interface PresenceSectionProps {
  value: PresenceState;
  onChange: (value: PresenceState) => void;
  /** The served expiry (ISO) from the shell's
   *  served-presence state (App.tsx's useServedPresence).
   *  When `onSetPresence` is also given, the section is
   *  DELEGATED: its mode + expiry read from the shell's
   *  one served state and every write goes through it —
   *  the section and the TopBar control can never
   *  disagree, and no second post path exists. Without
   *  them the section binds itself, as it did before the
   *  shell adopted the hook. */
  expiresAt?: string | null;
  onSetPresence?: (value: PresenceState, expiresAt: Date | null) => void;
}

/** Two reads of the same served expiry corroborate when
 *  they name the same instant (string forms may differ —
 *  the served stamps and a posted Date's ISO are not
 *  byte-identical forms of one instant). */
function sameInstant(a: string | null, b: string | null): boolean {
  if (a === b) return true;
  if (a == null || b == null) return false;
  return Math.abs(new Date(a).getTime() - new Date(b).getTime()) <= 1000;
}

export function PresenceSection({
  value,
  onChange,
  expiresAt,
  onSetPresence,
}: PresenceSectionProps) {
  const glance = usePortion<GlancePayload>("glance", () => call(api.getGlance({})), 0);
  const [localExpiry, setLocalExpiry] = useState<ExpirySelection>("none");
  const [postedExpiry, setPostedExpiry] = useState<string | null | undefined>(undefined);
  const [lastPostedIso, setLastPostedIso] = useState<string | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  // The custom expiry editor (owner commission,
  // restored): open state + the wall date/time fields. The
  // fields seed from the served expiry when one stands,
  // else from two hours out.
  const [customOpen, setCustomOpen] = useState(false);
  const [customDate, setCustomDate] = useState("");
  const [customTime, setCustomTime] = useState("");

  function openCustom() {
    const seed = servedExpiryIso ? new Date(servedExpiryIso) : new Date(Date.now() + 2 * 3_600_000);
    const fields = customExpiryFields(seed);
    setCustomDate(fields.date);
    setCustomTime(fields.time);
    setCustomOpen(true);
  }
  const served = glance.data?.presence;
  const delegated = onSetPresence != null;
  // The served expiry this section represents: delegated,
  // the shell hook's value; self-bound, the glance's —
  // or the last post's response, which is fresher than
  // the glance until the glance refetches.
  const servedExpiryIso = delegated
    ? (expiresAt ?? null)
    : postedExpiry !== undefined
      ? postedExpiry
      : (served?.expires_at ?? null);
  const expiry: ExpirySelection = delegated
    ? expirySelectionFor(expiresAt ?? null, new Date())
    : localExpiry;

  // Readiness (critic M-6): the groups render postable
  // only when the served presence is KNOWN. The shell
  // prop is a standing default null until its glance
  // lands, and a failed one-shot read there left it null
  // while this section's own glance showed the real
  // expiry — the group checked "No expiry" beside a
  // status line stating the expiry, and a mode change
  // posted the null, silently clearing it. So: until
  // this section's own read has landed AND (delegated)
  // the shell prop agrees with it — or with the last
  // expiry this section itself posted through the
  // shell, which the prop follows from the POST
  // response — the section renders an honest
  // non-postable state instead of the groups. The
  // shell hook's retry lands its read, the prop
  // converges, and the groups return with the served
  // selection (the "Current" behaviour) intact.
  const glanceExpiry = served?.expires_at ?? null;
  const propExpiry = expiresAt ?? null;
  const ready = delegated
    ? served != null &&
      (sameInstant(propExpiry, glanceExpiry) ||
        (lastPostedIso !== undefined && sameInstant(propExpiry, lastPostedIso)))
    : served != null;

  // The posted bridge is spent only once the prop has
  // converged to the posted value AND the section's own
  // read corroborates the prop. Spending it on prop–
  // glance agreement alone spends it in the very commit
  // that sets it — prop and glance still hold the
  // pre-post expiry there — and when the POST response
  // then moves the prop to the new expiry, the glance
  // (fetched once, at mount) never agrees again: the
  // section sat in "still syncing" for the life of the
  // mount after any expiry-changing post (gate run
  // workhorse-s4-gate-20261119T091942Z: the "At 5:00 PM"
  // and "Tomorrow, 8:00 AM" rows unmeasured behind an
  // "In 1 hour" click).
  useEffect(() => {
    if (
      lastPostedIso !== undefined &&
      sameInstant(propExpiry, lastPostedIso) &&
      sameInstant(propExpiry, glanceExpiry)
    ) {
      setLastPostedIso(undefined);
    }
  }, [lastPostedIso, propExpiry, glanceExpiry]);

  // Self-bound form only: sync the shell state + the
  // expiry selection from the served presence when the
  // glance lands. (Delegated, the shell's hook already
  // holds the served state; syncing through onChange
  // would post it straight back.)
  useEffect(() => {
    if (delegated || !served) return;
    if (served.mode !== value) onChange(served.mode);
    setPostedExpiry(undefined);
    setLocalExpiry(expirySelectionFor(served.expires_at, new Date()));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [served, delegated]);

  async function post(mode: PresenceState, selection: ExpirySelection, customDate?: Date | null) {
    // "current" posts the served expiry itself: the
    // selection carries the served value, so choosing it
    // — or changing the mode while it stands — preserves
    // the real expiry instead of clearing it.
    const expiryDate =
      selection === "custom"
        ? (customDate ?? null)
        : selection === "current"
          ? servedExpiryIso
            ? new Date(servedExpiryIso)
            : null
          : expiryDateFor(selection, new Date());
    if (delegated) {
      // One write path: the shell's served-presence
      // state posts (mode, expiry) together and its
      // state follows the POST response. The posted
      // expiry is remembered so the readiness check
      // above keeps the section postable while the
      // prop converges to it.
      onSetPresence(mode, expiryDate);
      setLastPostedIso(expiryDate ? expiryDate.toISOString() : null);
      return;
    }
    setError(null);
    try {
      // The original paints presence from the POST
      // response — the shell state follows the served
      // state, never an optimistic local guess.
      const p = await postPresenceMode(mode, expiryDate);
      onChange(p.mode);
      setPostedExpiry(p.expires_at);
      setLocalExpiry(expirySelectionFor(p.expires_at, new Date()));
    } catch (e) {
      setError(`Presence failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  const options = expiryOptions(new Date());

  return (
    <>
      {!ready ? (
        // The served presence has not arrived (or the
        // shell's copy has not converged to it): no
        // selectable "No expiry", no mode control that
        // can submit — the DigestSection's honest form.
        <p className="text-sm" style={{ color: "var(--ui-content-secondary)" }}>
          {glance.data == null
            ? glance.loading
              ? "Loading presence…"
              : "Presence is unreachable."
            : "Presence is still syncing."}
        </p>
      ) : (
        <>
          <GroupedList>
            {STATE_ROWS.map((row) => (
              <RadioRow
                key={row.value}
                label={row.label}
                sub={row.sub}
                selected={value === row.value}
                onSelect={() => void post(row.value, expiry)}
              />
            ))}
          </GroupedList>
          <GroupLabel>Expires</GroupLabel>
          <GroupedList>
        {/* The served expiry, when it matches no preset,
            stands as its own checked choice carrying the
            served value (critic M-6) — the presets below
            remain the change options. A served presence
            with no expiry checks "No expiry" instead, and
            this row does not render. */}
        {expiry === "current" && servedExpiryIso ? (
          <RadioRow
            label={`Current — ${dayWord(servedExpiryIso)} · ${clock(servedExpiryIso)}`}
            sub="The expiry in force"
            selected={!customOpen}
            onSelect={() => {
              setCustomOpen(false);
              void post(value, "current");
            }}
          />
        ) : null}
        {options.map((option) => (
          <RadioRow
            key={option.value}
            label={option.label}
            sub={option.sub}
            selected={expiry === option.value && !customOpen}
            onSelect={() => {
              setCustomOpen(false);
              if (!delegated) setLocalExpiry(option.value);
              void post(value, option.value);
            }}
          />
        ))}
        <RadioRow
          label="Custom"
          sub="A duration, or an end date and time"
          selected={customOpen}
          onSelect={openCustom}
        />
          </GroupedList>
      {customOpen ? (
        <div className="mt-2">
          <div className="flex flex-wrap gap-1.5">
            {[2, 4, 8, 24].map((hours) => (
              <Button
                key={hours}
                variant="secondary"
                onClick={() => {
                  const fields = customExpiryFields(new Date(Date.now() + hours * 3_600_000));
                  setCustomDate(fields.date);
                  setCustomTime(fields.time);
                }}
              >
                {hours}h
              </Button>
            ))}
          </div>
          <Field label="End date">
            {(id) => (
              <Input id={id} type="date" value={customDate} onChange={(e) => setCustomDate(e.target.value)} />
            )}
          </Field>
          <Field label="End time">
            {(id) => (
              <Input id={id} type="time" value={customTime} onChange={(e) => setCustomTime(e.target.value)} />
            )}
          </Field>
          <Button
            variant="primary"
            disabled={!customExpiryDate(customDate, customTime)}
            onClick={() => {
              const at = customExpiryDate(customDate, customTime);
              if (!at) return;
              if (!delegated) setLocalExpiry("custom");
              setCustomOpen(false);
              void post(value, "custom", at);
            }}
          >
            Set expiry
          </Button>
        </div>
      ) : null}
        </>
      )}
      {served?.expires_at ? (
        <p className="mt-2 text-[13px]" style={{ color: "var(--ui-content-secondary)" }}>
          {served.mode_label} until {clock(served.expires_at)}
          {served.expectation ? ` — ${served.expectation}` : ""}
        </p>
      ) : null}
      {error ? (
        <p className="mt-2 text-[13px]" role="alert" style={{ color: "var(--ui-status-hard-gate-text)" }}>
          {error}
        </p>
      ) : null}
    </>
  );
}

/* ---------------- Digest (storyboard frame 5) ---------------- */

const INCLUDE_ROWS: { key: "decisions" | "waiting" | "fyi"; label: string }[] = [
  { key: "decisions", label: "Decisions waiting" },
  { key: "waiting", label: "Waiting on others" },
  { key: "fyi", label: "FYI items" },
];

export function DigestSection() {
  const digest = usePortion<DigestPayload>("digest", () => call(api.getDigest({})), 0);
  const [error, setError] = useState<string | null>(null);
  // The window-times editor (hardcoded-time cure): the
  // owner's own times, posted with the browser's timezone
  // — the zone the wall times are read in. null = the
  // editor has not been touched; the fields then follow
  // the served times.
  const [editedTimes, setEditedTimes] = useState<string[] | null>(null);
  const d = digest.data;

  async function post(body: Record<string, unknown>) {
    setError(null);
    try {
      await call(api.postDigestPrefs({ body }));
      digest.refresh();
    } catch (e) {
      setError(`Digest preferences failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  if (!d) {
    return (
      <p className="text-sm" style={{ color: "var(--ui-content-secondary)" }}>
        {digest.loading
          ? "Loading digest preferences…"
          : "Digest preferences are unreachable."}
      </p>
    );
  }

  const times = d.window.times;
  const nextAt = d.window.next_at;
  let nextLabel = "No window enabled";
  if (nextAt) {
    const dt = new Date(nextAt);
    const hhmm = `${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`;
    const idx = times.indexOf(hhmm);
    const name = idx >= 0 ? windowName(times, idx) : null;
    const mins = minutesUntil(nextAt);
    nextLabel = [dayWord(nextAt), name, clock(nextAt), mins >= 0 ? `in ${mins} min` : ""]
      .filter(Boolean)
      .join(" · ");
  }

  return (
    <>
      <GroupLabel>Windows</GroupLabel>
      <GroupedList>
        {times.map((time, i) => (
          <SwitchRow
            key={time}
            label={windowName(times, i)}
            sub={times.length === 3 ? windowClock(time) : undefined}
            checked={d.window.enabled_times.includes(time)}
            onChange={(checked) =>
              void post({ window_time: time, window_enabled: checked })
            }
          />
        ))}
        <StatRow label="Next window">{nextLabel}</StatRow>
      </GroupedList>
      <GroupLabel>Window times</GroupLabel>
      <div>
        {(editedTimes ?? times).map((time, i) => (
          <Field key={i} label={windowName(times, i) || `Window ${i + 1}`}>
            {(id) => (
              <Input
                id={id}
                type="time"
                value={time}
                onChange={(e) => {
                  const next = [...(editedTimes ?? times)];
                  next[i] = e.target.value;
                  setEditedTimes(next);
                }}
              />
            )}
          </Field>
        ))}
        <Button
          variant="primary"
          disabled={
            editedTimes == null ||
            editedTimes.some((t) => !/^([01]\d|2[0-3]):[0-5]\d$/.test(t))
          }
          onClick={() => {
            if (!editedTimes) return;
            void post({
              window_times: editedTimes,
              window_tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
            }).then(() => setEditedTimes(null));
          }}
        >
          Set window times
        </Button>
      </div>
      <GroupLabel>Include</GroupLabel>
      <GroupedList>
        {INCLUDE_ROWS.map((row) => (
          <SwitchRow
            key={row.key}
            label={row.label}
            checked={d.include[row.key]}
            onChange={(checked) =>
              void post({ include_key: row.key, include_enabled: checked })
            }
          />
        ))}
      </GroupedList>
      {error ? (
        <p className="mt-2 text-[13px]" role="alert" style={{ color: "var(--ui-status-hard-gate-text)" }}>
          {error}
        </p>
      ) : null}
    </>
  );
}
