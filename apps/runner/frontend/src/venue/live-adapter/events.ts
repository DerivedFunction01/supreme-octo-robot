// The live adapter's outbox projections: the event and
// access-log views composed from the outbox portion, and
// the resolved-orphan roll. Split from live-adapter.ts
// along the outbox seam; LiveVenueAdapter delegates.

import type {
  AccessLogView,
  EventKind,
  EventView,
  ResolvedOrphanView,
  Tone,
} from "../types";
import { fmtDateToken, fmtTime, fmtTimeLong } from "../adapter/format";
import { CLASS_LABEL, TZ, baseName, liveSessionName, str, venueLabel } from "./helpers";
import { recordEntries, shapeLabel } from "./projections";
import type { LiveContext } from "./projections";
import type { OutboxEvent } from "./served";

export function dayKey(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function dayLabel(ctx: LiveContext, iso: string): string {
  const key = dayKey(iso);
  if (key === dayKey(ctx.now())) return "Today";
  const yesterday = new Date(Date.parse(ctx.now()) - 86400000).toISOString();
  if (key === dayKey(yesterday)) return "Yesterday";
  const weekday = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    weekday: "short",
  }).format(new Date(iso));
  return `${weekday}, ${fmtDateToken(iso)}`;
}

export function fmtDayTime(ctx: LiveContext, iso: string): string {
  const sameDay =
    new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(new Date(iso)) ===
    new Intl.DateTimeFormat("en-US", { timeZone: TZ, dateStyle: "short" }).format(new Date(ctx.now()));
  return `${sameDay ? "Today" : fmtDateToken(iso)} · ${fmtTimeLong(iso)}`;
}

/** The outbox kind's place in the app's event vocabulary:
 *  kind, tone, and the logs category (the panel's
 *  logCategory rule: grant-* are Grants, budget events are
 *  Budget, the rest are Leases). */
export function eventKindOf(ev: OutboxEvent): { kind: EventKind; tone: Tone } {
  const k = ev.kind;
  if (k === "run-terminal") {
    const state = str(ev.detail.state);
    return { kind: "run", tone: state === "failed" ? "fail" : state === "complete" ? "ok" : "info" };
  }
  if (k.startsWith("grant-") || k.startsWith("envelope-")) {
    return { kind: "grant", tone: k === "grant-started" ? "ok" : "info" };
  }
  if (k.startsWith("budget")) {
    return { kind: "budget", tone: k.includes("refused") ? "fail" : "info" };
  }
  if (k.endsWith("-failed") || k === "budget-refused") {
    return { kind: "error", tone: "fail" };
  }
  if (k === "lease-started" || k === "lease-adopted") return { kind: "lease", tone: "ok" };
  if (k === "approval-needed" || k === "unattributed-session" || k === "keepalive-stale") {
    return { kind: "lease", tone: "warn" };
  }
  return { kind: "lease", tone: "info" };
}

/** Compose the event's headline + meta from its served
 *  kind and detail — the panel composes its log rows the
 *  same way (kind phrase + the variable part). */
export function eventText(ctx: LiveContext, ev: OutboxEvent): { headline: string; meta?: string } {
  const d = ev.detail;
  const r = (d.result ?? {}) as Record<string, unknown>;
  const rec = (r.record ?? {}) as Record<string, unknown>;
  const session = str(d.session) ?? str(rec.session) ?? str(d.new_session);
  const name = session ? liveSessionName(session) : null;
  const shape = str(d.shape) ?? str(rec.shape);
  const shapeText = shape ? shapeLabel(ctx, shape) : null;
  switch (ev.kind) {
    case "lease-started":
      return {
        headline: "lease granted",
        meta: [name, str(rec.caller) ?? str(d.caller) ? `→ ${str(rec.caller) ?? str(d.caller)}` : null, shapeText]
          .filter(Boolean)
          .join(" · ") || undefined,
      };
    case "lease-extended":
      return {
        headline: "lease extended",
        meta: [name, str(d.new_deadline) ? `new deadline ${fmtTime(str(d.new_deadline)!)}` : null]
          .filter(Boolean)
          .join(" · ") || undefined,
      };
    case "lease-shortened":
      return {
        headline: "lease shortened",
        meta: [name, str(d.new_deadline) ? `new deadline ${fmtTime(str(d.new_deadline)!)}` : null]
          .filter(Boolean)
          .join(" · ") || undefined,
      };
    case "lease-stopped":
      return { headline: "lease released", meta: name ?? undefined };
    case "lease-adopted":
      return { headline: "orphan adopted", meta: name ?? undefined };
    case "lease-renewed":
      return {
        headline: "lease renewed",
        meta: str(d.new_session) ? liveSessionName(str(d.new_session)!) : undefined,
      };
    case "run-terminal": {
      const state = str(d.state);
      const word = state === "complete" ? "passed" : state === "failed" ? "failed" : state ?? "";
      return {
        headline: `${str(d.job) ?? "run"} ${word}`.trim(),
        meta: name ?? undefined,
      };
    }
    case "approval-needed":
      return { headline: "approval needed", meta: [name, shapeText].filter(Boolean).join(" · ") || undefined };
    case "unattributed-session":
      return {
        headline: "unattributed session",
        meta: [str(d.shape_class) ? `${CLASS_LABEL[str(d.shape_class)!] ?? str(d.shape_class)} class` : null]
          .filter(Boolean)
          .join(" · ") || undefined,
      };
    case "unattributed-cleared":
      return { headline: "unattributed session cleared", meta: name ?? undefined };
    case "session-released":
      return { headline: "session released", meta: name ?? undefined };
    case "budget-caps-changed": {
      const caps = (d.caps ?? {}) as Record<string, unknown>;
      const fmt = (v: unknown) => (v == null ? "no cap" : `${v} CU`);
      return {
        headline: "budget caps changed",
        meta: `daily ${fmt(caps.daily ?? caps.daily_cu_budget)} · monthly ${fmt(caps.monthly ?? caps.monthly_cu_budget)} · standing ${fmt(caps.standing_daily ?? caps.standing_daily_cu_cap)}`,
      };
    }
    case "grant-started":
      return {
        headline: "two-tier grant started",
        meta: [str(d.burst) ? `burst ${shapeLabel(ctx, str(d.burst)!)}` : null].filter(Boolean).join(" · ") || undefined,
      };
    case "envelope-lease-started":
      return {
        headline: "lease granted · envelope",
        meta: [shapeText, str(d.caller) ? `→ ${str(d.caller)}` : null].filter(Boolean).join(" · ") || undefined,
      };
    case "envelope-lease-released":
      return { headline: "envelope lease released", meta: str(d.reason) ?? undefined };
    default: {
      if (ev.kind.endsWith("-failed")) {
        return {
          headline: ev.kind.replace(/-/g, " "),
          meta: str(d.error) ?? str(r.action) ?? name ?? undefined,
        };
      }
      return { headline: ev.kind.replace(/-/g, " "), meta: name ?? undefined };
    }
  }
}

export function eventViews(ctx: LiveContext): EventView[] {
  const events = [...(ctx.parts.outbox?.events ?? [])]
    .sort((a, b) => b.seq - a.seq)
    .slice(0, 500);
  const leaseByBase = new Map(
    recordEntries(ctx).map(
      (e) => [baseName(e.record.session), e] as const,
    ),
  );
  return events.map((ev) => {
    const { kind, tone } = eventKindOf(ev);
    const { headline, meta } = eventText(ctx, ev);
    const message = meta ? `${headline} · ${meta}` : headline;
    const d = ev.detail;
    const sessionRaw = str(d.session) ?? str(d.new_session);
    const entry = sessionRaw ? leaseByBase.get(baseName(sessionRaw)) : undefined;
    const entity = entry
      ? {
          groupLabel: "Session",
          session: entry.record.session,
          title: liveSessionName(entry.record.session),
          sub: [
            "Lease",
            entry.record.caller ? `held by ${entry.record.caller}` : null,
            shapeLabel(ctx, entry.record.shape),
          ]
            .filter(Boolean)
            .join(" · "),
        }
      : undefined;
    const kindLabel =
      kind === "lease" ? "Lease" : kind === "run" ? "Run" : kind === "grant" ? "Grant" : kind === "budget" ? "Budget" : "Error";
    // The event's venue: the linked lease record's own venue
    // first, then a venue the event detail itself carries,
    // else the home venue (every pre-venue event is its).
    const evVenue = entry?.record.venue ?? str(d.venue) ?? "colab";
    return {
      id: `seq-${ev.seq}`,
      at: ev.ts,
      kind,
      kindLabel,
      tone,
      message,
      venue: evVenue,
      venueLabel: venueLabel(evVenue),
      dateToken: fmtDateToken(ev.ts),
      time: fmtTime(ev.ts),
      headline,
      meta,
      category: kind === "budget" ? "budget" : kind === "grant" ? "grants" : "leases",
      dayKey: dayKey(ev.ts),
      dayLabel: dayLabel(ctx, ev.ts),
      raw: JSON.stringify(ev, null, 2),
      detail: {
        message,
        facts: [
          { label: "Time", value: fmtDayTime(ctx, ev.ts), mono: true },
          { label: "Kind", value: kindLabel },
          { label: "Venue", value: venueLabel(evVenue) },
        ],
        ...(entity ? { entity } : {}),
      },
    };
  });
}

export function accessLogViews(ctx: LiveContext): AccessLogView[] {
  const ACCESS_KINDS = new Set([
    "unattributed-session",
    "unattributed-cleared",
    "lease-adopted",
    "envelope-lease-started",
    "session-released",
    "approval-needed",
  ]);
  const events = [...(ctx.parts.outbox?.events ?? [])]
    .filter((ev) => ACCESS_KINDS.has(ev.kind))
    .sort((a, b) => b.seq - a.seq)
    .slice(0, 50);
  return events.map((ev) => {
    const d = ev.detail;
    const session = str(d.session) ?? str(d.new_session);
    const name = session ? liveSessionName(session) : null;
    let headline: string;
    let chip: { label: string; tone: Tone } | undefined;
    switch (ev.kind) {
      case "unattributed-session":
        headline = "Unattributed session";
        chip = { label: "Unattributed", tone: "warn" };
        break;
      case "unattributed-cleared":
        headline = "Unattributed cleared";
        break;
      case "lease-adopted":
        headline = "Ride granted";
        break;
      case "envelope-lease-started":
        headline = "Ride granted";
        break;
      case "session-released":
        headline = "Session released";
        break;
      case "approval-needed":
        headline = "Approval needed";
        chip = { label: "Approval", tone: "warn" };
        break;
      default:
        headline = ev.kind;
    }
    const meta = [
      str(d.caller) && ev.kind !== "unattributed-session" ? str(d.caller) : null,
      name,
    ]
      .filter(Boolean)
      .join(" · ");
    return {
      id: `seq-${ev.seq}`,
      at: ev.ts,
      dateToken: fmtDateToken(ev.ts),
      time: fmtTime(ev.ts),
      headline,
      ...(meta ? { meta } : {}),
      ...(chip ? { kind: chip } : {}),
    };
  });
}

export function resolvedOrphanViews(ctx: LiveContext): ResolvedOrphanView[] {
  const out: ResolvedOrphanView[] = [];
  const events = [...(ctx.parts.outbox?.events ?? [])].sort((a, b) => b.seq - a.seq);
  for (const ev of events) {
    if (out.length >= 5) break;
    const session = str(ev.detail.session);
    if (!session) continue;
    if (ev.kind === "lease-adopted") {
      out.push({
        session,
        displayName: liveSessionName(session),
        sub: `Adopted by panel · ${dayLabel(ctx, ev.ts).toLowerCase()}`,
        label: "Adopted",
        tone: "ok",
      });
    } else if (ev.kind === "session-released") {
      out.push({
        session,
        displayName: liveSessionName(session),
        sub: `Released · ${dayLabel(ctx, ev.ts).toLowerCase()}`,
        label: "Released",
        tone: "idle",
      });
    }
  }
  return out;
}
