// The mock store's evaluator and simulated dispatch
// consumer: failed/stalled decisions return to the
// queue, claimed sends settle on their lease, and
// fulfillment is derived from the send ledger.
import type { MockStoreCtx } from "./context";
import type {
  OwnerItem,
  SendRow,
} from "../types";
import {
  STALL_MS,
  CLAIM_LEASE_MS,
  CONSUMER,
  FAILING_TARGETS,
} from "./constants";

export function createEngine(ctx: MockStoreCtx): MockStoreCtx["engine"] {
  const { state, nowMs, nowIso, handlerOf } = ctx;

  // ---------- evaluator ----------

  /** Failed and stalled items return to the decision queue
   * with decision_history on the item's face (contract 05). */
  function returnToQueue(item: OwnerItem, outcome: "failed" | "stalled", failure: string): void {
    if (!item.decision) return;
    item.decision_history.push({ ...item.decision, outcome, failure });
    item.decision = null;
    item.failure = failure;
    delete state.recordedResolveAt[item.id];
  }

  function runEvaluator(): boolean {
    let changed = false;
    for (const item of state.items) {
      if (!item.decision) continue;
      const age = nowMs() - Date.parse(item.decision.at);
      if (age > STALL_MS) {
        returnToQueue(item, "stalled", "Fulfillment stalled — no delivery within 120 min");
        changed = true;
      }
    }
    return changed;
  }

  // ---------- dispatch consumer (simulated) ----------

  function fulfill(item: OwnerItem, effect: string): void {
    if (!item.decision) return;
    state.fulfilled.unshift({
      item_id: item.id,
      title: item.title,
      handle: item.handle,
      decision: item.decision,
      effect,
      at: item.decision.at,
      fulfilled_at: nowIso(),
    });
    state.items = state.items.filter((i) => i.id !== item.id);
    delete state.recordedResolveAt[item.id];
  }

  function recordFailure(send: SendRow, reason: string): void {
    // Deduped: one failure record per hour per send + reason (§9.2b).
    const dupe = state.failures.some(
      (f) => f.send_id === send.id && f.reason === reason && nowMs() - Date.parse(f.at) < 3_600_000,
    );
    if (!dupe) state.failures.push({ send_id: send.id, reason, at: nowIso() });
  }

  function runConsumer(): boolean {
    let changed = false;
    // Settle-first (§9.2a): resolve outstanding claimed sends
    // before claiming or enqueueing anything new.
    for (const send of [...state.sends]) {
      const d = send.dispatch;
      if (!d.consumer || d.delivered_at) continue;
      // A claim whose lease has expired at read time is not
      // in flight (ATT6) — it is an abandoned claim, left as
      // it stands (the seeded stalled send's picture).
      if (d.claim_expires_at && Date.parse(d.claim_expires_at) <= nowMs()) continue;
      const item = state.items.find((i) => i.decision?.send_id === send.id);
      const failReason = FAILING_TARGETS[send.target];
      if (failReason) {
        recordFailure(send, failReason);
        if (item) returnToQueue(item, "failed", `Delivery failed — ${failReason}`);
        changed = true;
      } else {
        // Delivered only via ack by the claiming consumer,
        // carrying the fulfillment's submission reference.
        d.delivered_at = nowIso();
        d.delivery_ref = `sub-${send.id}-${d.attempts}`;
        send.outcome = "delivered";
        if (item) {
          fulfill(item, `Reply delivered to ${handlerOf(item.handle).label} · ref ${d.delivery_ref}`);
        }
        changed = true;
      }
    }
    // Then claim the oldest queued send (shadow sends are
    // never dispatchable — ATT5).
    const next = state.sends.find(
      (s) => s.mode === "active" && s.outcome === "recorded" && !s.dispatch.consumer && !s.dispatch.delivered_at,
    );
    if (next) {
      next.dispatch.consumer = CONSUMER;
      next.dispatch.claimed_at = nowIso();
      next.dispatch.claim_expires_at = new Date(nowMs() + CLAIM_LEASE_MS).toISOString();
      next.dispatch.attempts += 1;
      changed = true;
    }
    // Recorded resolutions: a recorded decision (a snooze,
    // a proposal verdict) clears on the next pass with the
    // effect composed at the tap; a snoozed item's
    // resurface is a future wait-rule surfacing, outside
    // the frozen shapes.
    for (const item of [...state.items]) {
      const rec = state.recordedResolveAt[item.id];
      if (item.decision && rec && rec.tick <= state.tickCount) {
        fulfill(item, rec.effect);
        changed = true;
      }
    }
    // Push-fact feed: the measurement flips, then fulfills.
    if (state.pushFact.flipAtTick !== null && state.tickCount >= state.pushFact.flipAtTick) {
      state.pushFact.state = "pushed";
      state.pushFact.flipAtTick = null;
      changed = true;
    }
    if (state.pushFact.state === "pushed") {
      for (const item of [...state.items]) {
        if (item.decision && item.fulfillment === "push_needed") {
          fulfill(item, "Push measured · pushed");
          changed = true;
        }
      }
    }
    return changed;
  }

  // The seeded stalled decision returns on the first read,
  // exactly as the evaluator would derive it at assembly.
  runEvaluator();

  return { returnToQueue, runEvaluator, fulfill, recordFailure, runConsumer };
}
