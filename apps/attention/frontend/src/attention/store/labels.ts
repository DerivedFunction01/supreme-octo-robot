// The mock store's registry lookups and label
// derivations: status/kind/class labels from the seeded
// registries, age labels, and the served snooze options.
import type { MockStoreCtx } from "./context";
import type {
  SnoozeOptionsView,
} from "../types";
import {
  wallParts,
  scenarioInstant,
  timeLabel,
} from "./time";

export function createLabels(ctx: MockStoreCtx): MockStoreCtx["labels"] {
  const { state, nowMs } = ctx;

  // ---------- registry lookups (labels come from the seed) ----------

function statusCodeOf(code: string) {
  return state.registries.status_codes.find((c) => c.code === code) ?? null;
}
function statusLabelOf(code: string): string {
  return statusCodeOf(code)?.label ?? code;
}
function kindLabel(kind: string): string {
  return state.registries.item_kinds.find((k) => k.kind === kind)?.label ?? kind;
}
/** A wait class's display name: the name, title-cased. */
function classLabel(name: string): string {
  const text = name.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
/** Backend waiting_label: "just now" / "N h" / "N days". */
function ageLabel(atIso: string): string {
  const mins = Math.floor((nowMs() - Date.parse(atIso)) / 60_000);
  if (mins < 60) return "just now";
  if (mins < 60 * 24) return `${Math.floor(mins / 60)} h`;
  const days = Math.floor(mins / (60 * 24));
  return days === 1 ? "1 day" : `${days} days`;
}

// ---------- snooze options (served per item) ----------

const weekdayFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
});

/** The snooze choices the backend serves on every item
 * (snooze_options): tomorrow at 9:00 and the next digest
 * window, with return-on-activity offered. Labels ride
 * the view so the panel renders served text. */
function snoozeOptionsFor(): SnoozeOptionsView {
  const p = wallParts(new Date(nowMs()));
  const tomorrowNine = scenarioInstant(p.y, p.mo, p.da, 9, 0) + 86_400_000;
  const times: SnoozeOptionsView["times"] = [
    {
      at: new Date(tomorrowNine).toISOString(),
      label: `${weekdayFmt.format(new Date(tomorrowNine))} · ${timeLabel(tomorrowNine)}`,
    },
  ];
  const nd = ctx.derivations.nextDigestAt();
  if (nd !== null && nd !== tomorrowNine) {
    times.push({
      at: new Date(nd).toISOString(),
      label: `${weekdayFmt.format(new Date(nd))} · ${timeLabel(nd)}`,
    });
  }
  return { times, on_activity: true };
}

function snoozeTimeLabel(atIso: string): string {
  const found = snoozeOptionsFor().times.find(
    (t) => Date.parse(t.at) === Date.parse(atIso),
  );
  if (found) return found.label;
  return `${weekdayFmt.format(new Date(atIso))} · ${timeLabel(atIso)}`;
}

  return { statusCodeOf, statusLabelOf, kindLabel, classLabel, ageLabel, snoozeOptionsFor, snoozeTimeLabel };
}
