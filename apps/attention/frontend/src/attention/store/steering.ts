// The mock store's handler steering derivations: the
// served verb entries, the status view composed from
// the seeded status record, the handler verb set, and
// the owner-action history.
import type { MockStoreCtx } from "./context";
import type {
  HandlerStatusView,
  OwnerActionView,
  VerbEntry,
} from "../types";
import {
  HANDLER_VERBS,
} from "./constants";
import {
  timeLabel,
} from "./time";
import { VERB_LABELS, verbLabel } from "../verb-labels";

export function createSteering(ctx: MockStoreCtx): MockStoreCtx["steering"] {
  const { state, nowMs } = ctx;

// ---------- handler steering ----------

function verbEntry(verb: string): VerbEntry {
  return { verb, label: VERB_LABELS[verb] ?? verb };
}

/** The status's quick verbs (backend quick_verbs_for_status):
 * the primary steering acts ride the status card itself. */
function quickVerbsFor(code: string): VerbEntry[] {
  let verbs: string[] = [];
  if (code === "REVIEW") verbs = ["accept_review", "reject_incomplete"];
  else if (code === "DONE") verbs = ["close"];
  else if (["WORKING", "CONTINUE", "BLOCKED-OWNER", "BLOCKED-HARD"].includes(code))
    verbs = ["park"];
  if (code !== "CLOSED") verbs.push("leave_it");
  return verbs.map(verbEntry);
}

function statusViewOf(handle: string): HandlerStatusView | null {
  const rec = state.statuses[handle];
  if (!rec) return null;
  const code = ctx.labels.statusCodeOf(rec.status_code);
  return {
    status_code: rec.status_code,
    status_label: code?.label ?? rec.status_code,
    need: (code?.need as HandlerStatusView["need"]) ?? "unclassified",
    summary: rec.summary,
    at_label: timeLabel(rec.at),
    age_hours: Math.round(((nowMs() - Date.parse(rec.at)) / 3_600_000) * 10) / 10,
    done: rec.done ?? null,
    ongoing: rec.ongoing ?? null,
    tail: rec.tail
      ? rec.tail.map((t) => ({
          kind: t.kind,
          kind_label: ctx.labels.kindLabel(t.kind),
          title: t.title,
          owner_label: t.owner === "owner" ? "your tap" : "closeout",
        }))
      : null,
    blockers: rec.blockers
      ? rec.blockers.map((b) => ({
          summary: b.summary,
          clearing_act: b.clearing_act,
          whose_label: b.whose === "hard" ? "hard stop" : "yours",
        }))
      : null,
    quick_verbs: quickVerbsFor(rec.status_code),
    // The mock's statuses carry no workbench refs; it
    // serves no derived line.
    derived: null,
  };
}

/** HANDLER_VERBS minus the status's quick-verb ids: a verb
 * rides exactly one surface (backend build_handler). */
function handlerVerbsFor(handle: string): VerbEntry[] {
  const quick = new Set(quickVerbsFor(state.statuses[handle]?.status_code ?? "").map((v) => v.verb));
  return HANDLER_VERBS.filter((v) => !quick.has(v)).map(verbEntry);
}

function ownerActionsFor(handle: string): OwnerActionView[] {
  return state.ownerActions
    .filter((a) => a.handle === handle)
    .slice(-10)
    .reverse()
    .map((a) => ({
      id: a.id,
      verb: a.verb,
      verb_label: VERB_LABELS[a.verb] ?? a.verb,
      at_label: timeLabel(a.at),
      note: a.note,
      actor_label:
        a.actor === "rule" ? `rule ${a.rule_id ?? ""}`.trim() : "owner",
      shadow: false,
    }));
}

/** The start of the current digest window: the most recent
 * configured window instant at or before now (the ping
 * cooldown's unit, backend _window_start). */
function windowStartMs(): number {
  const now = new Date(nowMs());
  let best = Number.NEGATIVE_INFINITY;
  for (const dayOff of [0, -1]) {
    for (const w of state.digest.windows) {
      const [hh, mm] = w.time.split(":").map(Number);
      const d = new Date(now);
      d.setDate(d.getDate() + dayOff);
      d.setHours(hh, mm, 0, 0);
      if (d.getTime() <= nowMs() && d.getTime() > best) best = d.getTime();
    }
  }
  return best;
}

  return { verbEntry, quickVerbsFor, statusViewOf, handlerVerbsFor, ownerActionsFor, windowStartMs };
}
