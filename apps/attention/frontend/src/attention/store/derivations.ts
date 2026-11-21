// The mock store's derivations (served ready): presence
// resolution, item/handler severity, the item and
// awaiting views, the open/waiting sets, and the next
// digest computation.
import type { MockStoreCtx } from "./context";
import type {
  AwaitingView,
  BandState,
  DecisionRecord,
  ExpiryChoice,
  ItemView,
  OwnerItem,
  PresenceRow,
  PresenceView,
  Severity,
} from "../types";
import {
  wallParts,
  scenarioInstant,
  timeLabel,
  durationLabel,
} from "./time";
import { VERB_LABELS, verbLabel } from "../verb-labels";

export function createDerivations(ctx: MockStoreCtx): MockStoreCtx["derivations"] {
  const { state, nowMs, handlerOf } = ctx;

  // ---------- derivations (served ready) ----------

  function resolvePresence(p: PresenceRow): PresenceView {
    // Expiry resolves at read time: an expired non-active
    // mode serves as active (presence schema), and the dead
    // window no longer bounds the served record.
    let mode = p.mode;
    let expires = p.expires_at;
    if (expires && Date.parse(expires) <= nowMs() && mode !== "active") {
      mode = "active";
      expires = null;
    }
    const wp = wallParts(new Date(nowMs()));
    let choice: ExpiryChoice = "none";
    if (expires) {
      if (ctx.lastPresenceWrite && ctx.lastPresenceWrite.expires_at === expires) {
        // Written through this adapter's write path: the
        // recorded option stays selected as time passes.
        choice = ctx.lastPresenceWrite.choice;
      } else {
        // Not written this session (a seed, a served
        // record): exact preset instants map to their
        // preset; any other instant is a custom one.
        const at = Date.parse(expires);
        if (at === scenarioInstant(wp.y, wp.mo, wp.da, 17, 0)) choice = "17:00";
        else if (at === scenarioInstant(wp.y, wp.mo, wp.da, 8, 0) + 86_400_000) choice = "tomorrow-08:00";
        else choice = "custom";
      }
    }
    return {
      mode,
      expires_at: expires,
      expiry_choice: choice,
      expectation: p.expectation,
      chip_label: `${mode[0].toUpperCase()}${mode.slice(1)}${expires ? ` · until ${timeLabel(expires)}` : ""}`,
      chip_severity: mode === "active" ? "ok" : mode === "focus" ? "info" : "warn",
    };
  }

  function itemSeverity(item: OwnerItem): Severity {
    if (item.failure) return "fail";
    if (item.kind === "breakthrough") {
      if (item.due_at && Date.parse(item.due_at) - nowMs() < 60 * 60_000) return "fail";
      return "warn";
    }
    const age = nowMs() - Date.parse(item.waiting_since);
    if (age >= 60 * 60_000) return "fail";
    if (age >= 15 * 60_000) return "warn";
    return "info";
  }

  function handlerSeverity(handle: string): Severity {
    const open = state.items.filter(
      (i) => i.handle === handle && !i.decision && !state.mutedItems.has(i.id),
    );
    if (open.some((i) => itemSeverity(i) === "fail")) return "fail";
    if (open.some((i) => itemSeverity(i) === "warn")) return "warn";
    if (open.length > 0) return "info";
    return "idle";
  }

  function toItemView(item: OwnerItem): ItemView {
    const h = handlerOf(item.handle);
    return {
      id: item.id,
      handle: item.handle,
      handler_label: h.label,
      color_slot: h.color_slot,
      kind: item.kind,
      title: item.title,
      waiting_label: `Waiting ${durationLabel(nowMs() - Date.parse(item.waiting_since))}`,
      severity: handlerSeverity(item.handle),
      verbs: item.verbs,
      options: item.options,
      failure: item.failure ?? null,
      history: item.decision_history,
      due_label: item.due_at ? timeLabel(item.due_at) : null,
      clears_at_source: item.clears_at_source,
      snooze_options: ctx.labels.snoozeOptionsFor(),
      rule_hint: ctx.learning.shadowHintFor(item),
      proposal: item.proposal ?? null,
    };
  }

  function bandState(item: OwnerItem): BandState {
    if (!item.decision) return "recorded";
    if (item.decision.verb === "snooze" || item.fulfillment !== "send") return "recorded";
    const send = state.sends.find((s) => s.id === item.decision?.send_id);
    return send?.dispatch.consumer ? "sent" : "queued";
  }

  function toAwaitingView(item: OwnerItem): AwaitingView {
    const bs = bandState(item);
    const d = item.decision as DecisionRecord;
    const optLabel = d.option_id
      ? item.options?.find((o) => o.id === d.option_id)?.label
      : null;
    let decided = `Decided ${durationLabel(nowMs() - Date.parse(d.at))} ago · ${optLabel ?? verbLabel(d.verb)}`;
    if (d.verb === "snooze" && item.snooze_return_at) {
      decided += ` · until ${ctx.labels.snoozeTimeLabel(item.snooze_return_at)}`;
      if (item.snooze_on_activity) decided += " · or on new activity";
      if (item.resume_note) decided += ` · Resume: ${item.resume_note}`;
    }
    return {
      ...toItemView(item),
      band_state: bs,
      band_label: bs === "queued" ? "Queued" : bs === "sent" ? "Sent · awaiting delivery" : "Recorded",
      decided_label: decided,
      decision: d,
    };
  }

  function openItems(): OwnerItem[] {
    return state.items.filter((i) => !i.decision && !state.mutedItems.has(i.id));
  }

  // The one "waiting on the owner" set. Backend api/1
  // serves this count as glance decision_count and today
  // headline_count: the owner-actionable live items,
  // breakthrough items included — in the backend a
  // breakthrough is a tier over any kind, never an
  // exclusion from the count, and in this store's kind
  // taxonomy the breakthrough kind is the same owner-
  // decision concept (both kinds render as decision rows,
  // take decision verbs and carry the decision subrecord).
  // Every surface that reports how much is waiting on the
  // owner — Today/badge, glance, handlers, programmes,
  // digest — derives from this one set, never a local
  // recount. (The away/night glance is a different,
  // presence-filtered concept: breakthroughs only.)
  function waitingItems(items: OwnerItem[]): OwnerItem[] {
    return items.filter(
      (i) =>
        i.kind === "decision" ||
        i.kind === "breakthrough" ||
        i.kind === "rule_proposal",
    );
  }

  function nextDigest(): { label: string; detail: string; time: string } {
    const enabled = state.digest.windows.filter((w) => w.enabled);
    const p = wallParts(new Date(nowMs()));
    const todayStart = scenarioInstant(p.y, p.mo, p.da, 0, 0);
    const candidates: { at: number; label: string; day: string }[] = [];
    for (const w of enabled) {
      const [h, mi] = w.time.split(":").map(Number);
      const todayAt = todayStart + (h * 60 + mi) * 60_000;
      if (todayAt > nowMs()) candidates.push({ at: todayAt, label: w.label, day: "Today" });
      candidates.push({ at: todayAt + 86_400_000, label: w.label, day: "Tomorrow" });
    }
    candidates.sort((a, b) => a.at - b.at);
    const next = candidates[0];
    if (!next) return { label: "No window enabled", detail: "", time: "" };
    return {
      label: next.label,
      detail: `${next.day} · ${next.label}`,
      time: timeLabel(next.at),
    };
  }

  function digestDetail(at: number): string {
    return `${timeLabel(at)} · in ${durationLabel(at - nowMs())}`;
  }

  function nextDigestAt(): number | null {
    const enabled = state.digest.windows.filter((w) => w.enabled);
    const p = wallParts(new Date(nowMs()));
    const todayStart = scenarioInstant(p.y, p.mo, p.da, 0, 0);
    let best: number | null = null;
    for (const w of enabled) {
      const [h, mi] = w.time.split(":").map(Number);
      const todayAt = todayStart + (h * 60 + mi) * 60_000;
      const at = todayAt > nowMs() ? todayAt : todayAt + 86_400_000;
      if (best === null || at < best) best = at;
    }
    return best;
  }

  return { resolvePresence, itemSeverity, handlerSeverity, toItemView, bandState, toAwaitingView, openItems, waitingItems, nextDigest, digestDetail, nextDigestAt };
}
