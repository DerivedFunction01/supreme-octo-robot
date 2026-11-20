// Launcher — the one client's home (seed plan §2: "an
// iOS-inspired home of app icons… Opening an icon enters
// that workhorse's app, full functionality, unified theme
// and navigation chrome"; kit sheet: "Launcher — iOS home:
// date/clock header, Today widget, app grid").
//
// Form per the superapp storyboard's Launcher frame:
//   - the date line and the large clock (the frame's
//     header: "Wednesday, November 11" over "11:42");
//   - the Today widget: "Attention · Today" — the decision
//     line, the next digest window, the presence line;
//   - the AppTile grid: Scheduler, Workbench, Runner,
//     Attention (badge), Settings.
// The widget's decision count and next-digest values are
// attention's served data (getGlance) — the attention lane
// binds them through the props below (INTEGRATION.md §6);
// until bound, the widget carries the lines it can state
// honestly: the presence line (shell state) and the
// decision row that opens Attention.

import { useEffect, useState } from "react";
import { Card } from "@workhorse/kit/components/Card";
import { GroupedList, Row } from "@workhorse/kit/components/GroupedList";
import { appHref, settingsHref } from "../lib/router";
import type { AppId } from "../lib/view-contract";
import { clock } from "../views/attention/model";
import { APP_META, LAUNCHER_ORDER, SETTINGS_TILE_STYLE, SettingsGlyph } from "./apps";
import { PRESENCE_LABELS, type PresenceState } from "./PresenceControl";

export interface LauncherProps {
  presence: PresenceState;
  /** Attention's waiting-decision count (getGlance, bound
   *  by the attention lane); null while unbound. */
  attentionCount?: number | null;
  /** The next digest window's label (getGlance, bound by
   *  the attention lane); null while unbound. */
  nextDigestLabel?: string | null;
  /** The served presence expiry (getGlance's
   *  presence.expires_at, bound by the attention lane);
   *  the Presence row renders it beside the state — the
   *  kit's PresenceChip form (state + expiry on glance
   *  surfaces). Null when no expiry is served. */
  presenceExpiresAt?: string | null;
  onOpen: (hash: string) => void;
}

function useClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(t);
  }, []);
  return now;
}

/** The clock form: 12-hour WITH meridiem ("10:47 PM") —
 *  the same rendering the app's own Glance card uses
 *  (attention's clock(): toLocaleTimeString, hour +
 *  minute), so the Launcher and the Glance never state
 *  the same time two ways (critic M-2). */
function clockLabel(d: Date): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).formatToParts(d);
  const hour = parts.find((p) => p.type === "hour")?.value ?? "";
  const minute = parts.find((p) => p.type === "minute")?.value ?? "";
  const meridiem = parts.find((p) => p.type === "dayPeriod")?.value ?? "";
  return `${hour}:${minute} ${meridiem}`;
}

function dateLabel(d: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(d);
}

function AppTile({
  app,
  badge,
  onOpen,
}: {
  app: AppId;
  badge?: number | null;
  onOpen: (hash: string) => void;
}) {
  const meta = APP_META[app];
  return (
    <button
      type="button"
      onClick={() => onOpen(appHref(app))}
      className="flex cursor-pointer flex-col items-start gap-[10px] rounded-[var(--wb-radius-lg)] border p-[14px] text-left"
      style={{
        backgroundColor: "var(--wb-surface-2)",
        borderColor: "var(--wb-border-default)",
        color: "var(--wb-content-primary)",
        fontFamily: "inherit",
      }}
    >
      <span className="relative flex">
        <span
          className="flex h-[52px] w-[52px] items-center justify-center rounded-[13px]"
          style={{ color: "#fff", ...meta.tileStyle }}
        >
          {meta.glyph}
        </span>
        {badge != null && badge > 0 ? (
          <span
            className="absolute -top-[6px] -right-[6px] flex h-[20px] min-w-[20px] items-center justify-center rounded-full px-[5px] text-[12px] font-bold"
            style={{
              backgroundColor: "var(--wb-notify)",
              color: "var(--wb-on-notify)",
            }}
          >
            {badge}
          </span>
        ) : null}
      </span>
      <span className="text-[15px] font-semibold">{meta.name}</span>
    </button>
  );
}

export function Launcher({ presence, attentionCount, nextDigestLabel, presenceExpiresAt, onOpen }: LauncherProps) {
  const now = useClock();
  return (
    <main style={{ height: "100%", overflowY: "auto" }}>
      <div className="mx-auto flex max-w-[620px] flex-col px-5 py-7">
        {/* The route's ONE H1, shell-provided (critic
            M-5/m-2): visually hidden — the Launcher's
            clock is its visual hero, by design. */}
        <h1 className="sr-only">Workhorse Superapp</h1>
        <div
          className="text-[15px] font-semibold"
          style={{ color: "var(--wb-content-secondary)" }}
        >
          {dateLabel(now)}
        </div>
        <div
          className="text-[64px] leading-none font-extrabold tracking-[-0.02em]"
          style={{ margin: "2px 0 20px" }}
        >
          {clockLabel(now)}
        </div>

        <Card title="Attention · Today">
          <GroupedList>
            <Row
              label={
                attentionCount != null
                  ? `${attentionCount} thing${attentionCount === 1 ? "" : "s"} need${attentionCount === 1 ? "s" : ""} your decision`
                  : "Decisions waiting"
              }
              sub={nextDigestLabel ? `Next · Digest window · ${nextDigestLabel}` : undefined}
              chevron
              onClick={() => onOpen(appHref("attention"))}
            />
            <Row
              label="Presence"
              end={
                <span style={{ color: "var(--wb-content-secondary)" }}>
                  {PRESENCE_LABELS[presence]}
                  {presenceExpiresAt
                    ? ` · until ${clock(presenceExpiresAt)}`
                    : ""}
                </span>
              }
            />
          </GroupedList>
        </Card>

        <div className="mt-6 grid grid-cols-2 gap-3 min-[560px]:grid-cols-3">
          {LAUNCHER_ORDER.map((app) => (
            <AppTile
              key={app}
              app={app}
              badge={app === "attention" ? attentionCount : undefined}
              onOpen={onOpen}
            />
          ))}
          <button
            type="button"
            onClick={() => onOpen(settingsHref())}
            className="flex cursor-pointer flex-col items-start gap-[10px] rounded-[var(--wb-radius-lg)] border p-[14px] text-left"
            style={{
              backgroundColor: "var(--wb-surface-2)",
              borderColor: "var(--wb-border-default)",
              color: "var(--wb-content-primary)",
              fontFamily: "inherit",
            }}
          >
            <span
              className="flex h-[52px] w-[52px] items-center justify-center rounded-[13px]"
              style={{ color: "#fff", ...SETTINGS_TILE_STYLE }}
            >
              <SettingsGlyph />
            </span>
            <span className="text-[15px] font-semibold">Settings</span>
          </button>
        </div>
      </div>
    </main>
  );
}
