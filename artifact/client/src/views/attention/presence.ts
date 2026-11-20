// Presence binding (INTEGRATION.md §6): presence is
// attention's served state. Reads ride getGlance; writes
// ride postPresence with the original's body —
// {mode, expires_at, expectation: ""} (the original
// always posted a null expiry and an empty expectation;
// the Settings frame's expiry picker is the one place a
// concrete expiry is chosen, and it is computed here,
// never the frame's instance labels).

import { useCallback, useEffect, useRef, useState } from "react";
import {
  clock,
  dayWord,
  windowName,
  type GlancePayload,
  type PresenceMode,
  type PresenceView,
} from "./model";
import { api, call } from "./transport";

export type { PresenceMode };

/** Post a presence state; resolves to the served
 *  presence view the backend returns. */
export async function postPresenceMode(
  mode: PresenceMode,
  expiresAt: Date | null,
): Promise<PresenceView> {
  return call<PresenceView>(
    api.postPresence({
      body: { mode, expires_at: expiresAt ? expiresAt.toISOString() : null, expectation: "" },
    }),
  );
}

/* ---------------- the frame-4 expiry options, computed ---------------- */

export type PresenceExpiry = "hour" | "evening" | "morning" | "none";

export interface ExpiryOption {
  value: PresenceExpiry;
  label: string;
  sub?: string;
  /** The concrete expiry this option posts; null = none. */
  at: Date | null;
}

function atTime(base: Date, hour: number, minute: number, plusDays: number): Date {
  const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() + plusDays, hour, minute, 0, 0);
  return d;
}

/** Frame 4's four options with their times computed from
 *  `now`: in one hour; the next 5:00 PM (today's, or
 *  tomorrow's once today's has passed); tomorrow at
 *  8:00 AM; no expiry. */
export function expiryOptions(now: Date): ExpiryOption[] {
  const hourAt = new Date(now.getTime() + 60 * 60 * 1000);
  const eveningToday = atTime(now, 17, 0, 0);
  const eveningAt = eveningToday.getTime() > now.getTime() ? eveningToday : atTime(now, 17, 0, 1);
  const morningAt = atTime(now, 8, 0, 1);
  return [
    { value: "hour", label: "In 1 hour", sub: clock(hourAt.toISOString()), at: hourAt },
    {
      value: "evening",
      label:
        eveningAt.getDate() === now.getDate()
          ? `At ${clock(eveningAt.toISOString())}`
          : `Tomorrow, ${clock(eveningAt.toISOString())}`,
      at: eveningAt,
    },
    { value: "morning", label: `Tomorrow, ${clock(morningAt.toISOString())}`, at: morningAt },
    { value: "none", label: "No expiry", at: null },
  ];
}

/** Which option a served expires_at corresponds to
 *  (within two minutes — the option's computed time and
 *  the served time are the same instant chosen earlier). */
export function expiryValueFor(expiresAt: string | null, now: Date): PresenceExpiry {
  if (!expiresAt) return "none";
  const target = new Date(expiresAt).getTime();
  for (const option of expiryOptions(now)) {
    if (option.at && Math.abs(option.at.getTime() - target) <= 120_000) return option.value;
  }
  return "none";
}

/** The Expires group's selection, as the section renders
 *  it: a preset value, "none", or "current" — the served
 *  expiry matches no preset (it was set from another
 *  surface, or time has carried it out of the matching
 *  window). "current" is a real selection carrying the
 *  served value, never a fall-through to "none":
 *  collapsing an unmatched real expiry into "No expiry"
 *  made the group contradict the served state on the
 *  same screen (critic M-6) and made a mode change post
 *  a null expiry, silently clearing the real one. */
export type ExpirySelection = PresenceExpiry | "current";

export function expirySelectionFor(expiresAt: string | null, now: Date): ExpirySelection {
  if (!expiresAt) return "none";
  const matched = expiryValueFor(expiresAt, now);
  return matched === "none" ? "current" : matched;
}

/** The concrete Date a chosen option posts right now. */
export function expiryDateFor(value: PresenceExpiry, now: Date): Date | null {
  return expiryOptions(now).find((o) => o.value === value)?.at ?? null;
}

/* ---------------- the Launcher widget's digest label ---------------- */

/** "Today · Midday · 3:00 PM" for the glance's next
 *  window (the frame's form), the window named from the
 *  digest's served window times when they are known. */
export function digestWindowLabel(
  glance: GlancePayload,
  times: string[] | undefined,
  now: Date = new Date(),
): string | null {
  const nextAt = glance.clock.next_window_at;
  if (!nextAt) return null;
  let name: string | null = null;
  if (times && times.length) {
    const d = new Date(nextAt);
    const hhmm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    const idx = times.indexOf(hhmm);
    if (idx >= 0) name = windowName(times, idx);
  }
  return [dayWord(nextAt, now), name, clock(nextAt)].filter(Boolean).join(" · ");
}

/* ---------------- the served-presence hook ----------------
 * The shell-adoption form of the binding (INTEGRATION.md
 * §6/§7): App.tsx swaps its local useState for this hook
 * and the shell state becomes the served state — the
 * TopBar control writes through postPresence, the
 * Launcher widget takes its label from the same glance,
 * and PresenceSection's mode half and the TopBar can
 * never disagree. It lives here, in the attention lane's
 * folder, so the shell change is a one-spot adoption the
 * coordinator makes; PresenceSection already binds
 * through the same helpers below. */

export interface ServedPresence {
  mode: PresenceMode;
  expiresAt: string | null;
  /** True once a served presence has actually landed —
   *  the mount glance (after any retries) or a post
   *  response. Until then mode/expiresAt are standing
   *  defaults, NOT served state: the default expiry is
   *  null, so presenting it as a served "No expiry" —
   *  or posting it — would silently clear a real expiry
   *  the shell simply failed to read (critic M-6).
   *  Writes are refused while this is false. */
  loaded: boolean;
  /** Set the mode, keeping the current expiry. */
  setMode: (mode: PresenceMode) => void;
  /** Set mode + expiry together (the Settings form). */
  setPresence: (mode: PresenceMode, expiresAt: Date | null) => void;
  /** The Launcher widget's next-digest label. */
  nextDigestLabel: string | null;
  /** The glance's served decision count (the Launcher
   *  Today widget's headline count and the Attention
   *  tile's badge) — from the same getGlance this hook
   *  already rides at shell mount, so the Launcher
   *  carries the count from first paint, not only after
   *  the Today view has mounted and reported a badge.
   *  Null until the glance lands. */
  decisionCount: number | null;
}

export function useServedPresence(): ServedPresence {
  const [mode, setModeState] = useState<PresenceMode>("active");
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const loadedRef = useRef(false);
  const [nextDigestLabel, setNextDigestLabel] = useState<string | null>(null);
  const [decisionCount, setDecisionCount] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    const attempt = () => {
      call<GlancePayload>(api.getGlance({}))
        .then((gl) => {
          if (!live) return;
          loadedRef.current = true;
          setLoaded(true);
          setModeState(gl.presence.mode);
          setExpiresAt(gl.presence.expires_at);
          setNextDigestLabel(digestWindowLabel(gl, undefined));
          setDecisionCount(gl.decision_count);
        })
        .catch(() => {
          if (!live) return;
          // The served state has not arrived: the
          // standing defaults stay visibly unloaded
          // (loaded stays false, writes stay refused)
          // and the read retries until it lands. The
          // one-shot silent failure this replaces is
          // what let a failed read pose as a served
          // "No expiry" in the Settings group and ride
          // a mode change as a postable null (M-6).
          timer = window.setTimeout(attempt, 3000);
        });
    };
    attempt();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, []);

  const setPresence = useCallback((nextMode: PresenceMode, nextExpiry: Date | null) => {
    // Never post from state that has not landed: the
    // expiry argument would be derived from the standing
    // default, and a null derived from ignorance clears
    // a real served expiry (M-6). Once any glance or
    // post has landed, writes flow as before.
    if (!loadedRef.current) return;
    postPresenceMode(nextMode, nextExpiry)
      .then((p) => {
        loadedRef.current = true;
        setLoaded(true);
        setModeState(p.mode);
        setExpiresAt(p.expires_at);
      })
      .catch(() => {
        /* the served state stands; the views surface failures */
      });
  }, []);

  const setMode = useCallback(
    (nextMode: PresenceMode) => {
      setPresence(nextMode, expiresAt ? new Date(expiresAt) : null);
    },
    [setPresence, expiresAt],
  );

  return { mode, expiresAt, loaded, setMode, setPresence, nextDigestLabel, decisionCount };
}
