// The mock store's decision surface: decide() and
// handlerAction() — verdict at the tap, validated
// against the served verb sets, with the replay guards
// (idempotency keys, standing decisions, fulfillment).
import type { MockStoreCtx } from "./context";
import type {
  DecideInput,
  DecideResult,
  DecisionRecord,
  HandlerActionResult,
  WaitRow,
  AttentionDataSource,
} from "../types";
import {
  MAIN_THREAD,
  HANDLER_VERBS,
  STATUS_QUICK_VERBS,
  PASS_VERBS,
  DIRECTED_STATUS,
} from "./constants";
import { VERB_LABELS, verbLabel } from "../verb-labels";

export function createApiDecide(ctx: MockStoreCtx): Pick<AttentionDataSource, "decide" | "handlerAction"> {
  const { state, nowMs, nowIso, bump, handlerOf, recordSend } = ctx;

  return {
    decide(itemId, input: DecideInput): DecideResult {
      // Replay guard 1: an idempotency key short-circuits.
      const seen = state.idempotency[input.idempotency_key];
      if (seen) return seen;

      const item = state.items.find((i) => i.id === itemId);
      if (!item) return { ok: false, error: `unknown item ${itemId}` };
      // Replay guard 2: a repeated tap on a standing decision
      // records and sends nothing. A fulfilled decision is
      // never changed — the item has cleared, so it is not
      // found above and a fresh item would carry a new id.
      if (item.decision) {
        const replayed: DecideResult = { ok: true, decision: item.decision, replayed: true };
        state.idempotency[input.idempotency_key] = replayed;
        return replayed;
      }
      // The verb is validated against the served verb set.
      if (!item.verbs.includes(input.verb)) {
        return { ok: false, error: `verb "${input.verb}" is not served for ${itemId}` };
      }
      if (input.verb === "decide" || input.verb === "rule_it") {
        if (!item.options?.some((o) => o.id === input.option_id)) {
          return { ok: false, error: `option required for ${itemId}` };
        }
      } else if (input.option_id) {
        return { ok: false, error: `option not accepted for verb "${input.verb}"` };
      }
      // Promotion validations run before any effect (the
      // backend's messages, mirrored): approve_rule already
      // promotes, and a hard-stop approval is approved
      // once, never ruled.
      if (input.make_rule && input.verb === "approve_rule") {
        return { ok: false, error: "make_rule: approve_rule already promotes" };
      }
      const wait = ctx.learning.waitOf(item);
      const waitClass = wait
        ? state.registries.wait_classes.find((c) => c.name === wait.wait_class)
        : undefined;
      if (input.verb === "approve_rule") {
        if (!wait) {
          return { ok: false, error: "approve_rule: no wait stands behind this item" };
        }
        if (waitClass?.hard_stop) {
          return {
            ok: false,
            error: "hard-stop approvals are approved once, never ruled",
          };
        }
      }
      if (input.make_rule && wait && waitClass?.hard_stop) {
        return {
          ok: false,
          error: "make_rule: a hard-stop approval can never become a rule",
        };
      }

      const at = nowIso();

      // mute_type is a bookmark, not a decision (backend
      // triage): the item and every open item of its type
      // from its handler are held until the type unmutes
      // on the handler's page. No decision is recorded and
      // nothing is sent; the returned record is the tap's
      // receipt only.
      if (input.verb === "mute_type") {
        if (!item.notice_type) {
          return { ok: false, error: "mute_type: this item carries no type" };
        }
        const surface = state.handlerSurfaces[item.handle];
        if (surface) {
          const row = surface.muted_types.find((m) => m.type === item.notice_type);
          if (row) row.muted = true;
          else surface.muted_types.push({ type: item.notice_type, muted: true });
        }
        for (const other of state.items) {
          if (other.handle === item.handle && other.notice_type === item.notice_type) {
            state.mutedItems.add(other.id);
          }
        }
        const result: DecideResult = {
          ok: true,
          decision: {
            verb: "mute_type",
            at,
            option_id: null,
            note: input.note ?? "",
            send_id: null,
          },
          replayed: false,
        };
        state.idempotency[input.idempotency_key] = result;
        bump();
        return result;
      }

      // Proposal verdicts (the learning loop's other
      // half): accepting creates the rule in shadow and
      // resets the counter for its next cycle; rejecting
      // only resets it. Recorded acts — no send is minted.
      if (input.verb === "accept_proposal" || input.verb === "reject_proposal") {
        if (item.kind !== "rule_proposal" || !item.proposal) {
          return { ok: false, error: `${input.verb}: not a rule proposal` };
        }
        const proposal = item.proposal;
        if (input.verb === "accept_proposal") {
          ctx.learning.createActionRule({
            match: { handle: item.handle, kind: proposal.cls },
            verb: proposal.verb,
            mode: "shadow",
            created_from: "proposal",
          });
        }
        const entry = state.tapCounts[proposal.key];
        if (entry) {
          entry.count = 0;
          entry.cycles += 1;
        }
        const decision: DecisionRecord = {
          verb: input.verb,
          at,
          option_id: null,
          note: input.note ?? "",
          send_id: null,
        };
        item.decision = decision;
        state.recordedResolveAt[item.id] = {
          tick: state.tickCount + 1,
          effect:
            input.verb === "accept_proposal"
              ? `Rule created · ${verbLabel(proposal.verb)} on ${proposal.cls} items from ${handlerOf(item.handle).label} stands in shadow`
              : "Proposal dismissed · the tap count restarts",
        };
        const result: DecideResult = { ok: true, decision, replayed: false };
        state.idempotency[input.idempotency_key] = result;
        bump();
        return result;
      }

      // approve_rule promotes first, then applies as the
      // approval itself (the backend's verb_effective).
      let verb = input.verb;
      if (verb === "approve_rule") {
        ctx.learning.createActionRule({
          match: { handle: item.handle, wait_class: (wait as WaitRow).wait_class },
          verb: "approve",
          mode: "active",
          created_from: "approve_rule",
        });
        verb = "approve";
      }

      const decision: DecisionRecord = {
        verb,
        at,
        option_id:
          input.verb === "decide" || input.verb === "rule_it"
            ? (input.option_id as string)
            : null,
        note: input.note ?? "",
        send_id: null,
      };

      if (input.verb === "snooze") {
        // The snooze payload (backend triage): the return
        // instant must be one of the served times; activity
        // and the resume note ride the item until it
        // resurfaces. Recorded fulfillment: no send.
        const options = ctx.labels.snoozeOptionsFor();
        let returnAt = options.times[0]?.at ?? at;
        if (input.return_at) {
          const served = options.times.find(
            (t) => Date.parse(t.at) === Date.parse(input.return_at as string),
          );
          if (!served) {
            return {
              ok: false,
              error: "snooze: the return time is not one of the served times",
            };
          }
          returnAt = served.at;
        }
        const onActivity = input.return_on_activity ?? options.on_activity;
        const resumeNote = input.resume_note ?? (input.note ? input.note : null);
        item.snooze_return_at = returnAt;
        item.snooze_on_activity = onActivity;
        item.resume_note = resumeNote;
        state.recordedResolveAt[item.id] = {
          tick: state.tickCount + 1,
          effect:
            `Snoozed · resurfaces ${ctx.labels.snoozeTimeLabel(returnAt)}` +
            (onActivity ? " · or on new activity" : ""),
        };
      } else if (item.fulfillment === "push_needed") {
        // Fulfillment derives from the push-fact feed.
        state.pushFact.flipAtTick = state.tickCount + 2;
      } else {
        // Send-backed: mint through record_send (owner verbs
        // producer class). Reply routing (ATT3): direct to
        // the owning thread; main copied unless the owning
        // handle IS main, which gets the single send.
        const h = handlerOf(item.handle);
        const optLabel = decision.option_id
          ? item.options?.find((o) => o.id === decision.option_id)?.label
          : null;
        const text = `${optLabel ?? verbLabel(verb)} — ${item.title}${decision.note ? ` · ${decision.note}` : ""}`;
        decision.send_id = recordSend({
          handle: item.handle,
          target: h.thread_id,
          template: "decision-reply",
          text,
          wait_id: item.wait_id,
        });
        if (item.handle !== "main") {
          recordSend({
            handle: item.handle,
            target: MAIN_THREAD,
            template: "owner:reply-copy",
            text,
            wait_id: item.wait_id,
          });
        }
        // The decision lands on the wait through the item.
        if (item.wait_id) {
          const wait = state.waits.find((w) => w.id === item.wait_id);
          if (wait) {
            wait.decision = decision.option_id === "hold" ? "owner_denied" : "owner_approved";
            wait.decided_at = at;
            wait.owner_note = decision.note ?? "";
          }
        }
      }

      // rule_it: the pick lands (the send above carries
      // the option's verdict) and the rule stands in
      // shadow from this tap (D-A8's sibling act).
      if (input.verb === "rule_it") {
        ctx.learning.createActionRule({
          match: { handle: item.handle, kind: item.kind },
          verb: "decide",
          mode: "shadow",
          created_from: "rule_it",
          option_id: decision.option_id,
        });
      }
      // The deliberate make_rule tap (D-A8): a wait
      // approval promotes to an active rule on its class;
      // anything else promotes to a shadow rule on the
      // item's kind. Hard-stop classes were refused above,
      // and bookmarks never promote (triage consumes them
      // first in the backend, as here).
      if (input.make_rule && !["snooze", "done", "leave_it"].includes(input.verb)) {
        if (wait) {
          ctx.learning.createActionRule({
            match: { handle: item.handle, wait_class: wait.wait_class },
            verb: "approve",
            mode: "active",
            created_from: "make_rule",
          });
        } else {
          ctx.learning.createActionRule({
            match: { handle: item.handle, kind: item.kind },
            verb: verb,
            mode: "shadow",
            created_from: "make_rule",
            option_id: decision.option_id,
          });
        }
      }

      item.decision = decision;
      item.failure = undefined;
      // Repetition proposes the rule: the tap counts
      // after it lands (bookmarks and promotions are not
      // in the counted set).
      ctx.learning.countTap(item, input.verb);
      const result: DecideResult = { ok: true, decision, replayed: false };
      state.idempotency[input.idempotency_key] = result;
      bump();
      return result;
    },

    handlerAction(handle, verb, idempotencyKey): HandlerActionResult {
      // A replayed key returns the standing act: nothing is
      // recorded or sent twice.
      const seen = state.handlerIdempotency[idempotencyKey];
      if (seen) return seen;
      if (!state.handlers.some((h) => h.handle === handle)) {
        return { ok: false, error: "No such handler." };
      }
      const served =
        (HANDLER_VERBS as readonly string[]).includes(verb) ||
        (STATUS_QUICK_VERBS as readonly string[]).includes(verb);
      if (!served) return { ok: false, error: "verb not served for a handler" };
      const h = handlerOf(handle);
      const status = state.statuses[handle];
      const summary = status?.summary || handle;
      // The ping cooldown is checked before anything is
      // recorded: a second ping inside the digest window is
      // a conflict, exactly as the backend raises it.
      if (verb === "status_ping") {
        const mine = state.pings[handle];
        if (mine?.last_at != null && mine.last_at >= ctx.steering.windowStartMs()) {
          return {
            ok: false,
            error: "A status ping already went out this digest window.",
          };
        }
      }
      state.actionCounter += 1;
      const actionId = `oa${String(state.actionCounter).padStart(4, "0")}`;
      if (verb === "status_ping") {
        const mine = state.pings[handle] ?? { count: 0, last_at: null };
        mine.count += 1;
        mine.last_at = nowMs();
        state.pings[handle] = mine;
        const kind = mine.count === 1 ? "status-ping" : "status-ping-urgent";
        recordSend({
          handle,
          target: h.thread_id,
          template: kind,
          text: ctx.rules.renderTemplate(kind, { summary }),
          wait_id: null,
        });
      } else if (verb === "parallelize") {
        state.ownerDirected[ctx.digest.topicOf(handle)] = { at: nowIso(), handle };
        recordSend({
          handle,
          target: h.thread_id,
          template: "parallelize",
          text: ctx.rules.renderTemplate("parallelize", { summary }),
          wait_id: null,
        });
      } else if (verb in PASS_VERBS) {
        // A pass commission lands as an agent-clearable
        // action item on the handler, decidable like any
        // other item.
        const title = `${PASS_VERBS[verb]} — ${h.label}`;
        state.items.push({
          id: `${handle}:commission:${verb}:${actionId}`,
          handle,
          wait_id: null,
          kind: "action",
          title,
          detail: "Owner commission",
          waiting_since: nowIso(),
          due_at: null,
          notice_type: null,
          verbs: ["continue", "reply", "snooze", "done", "leave_it"],
          options: null,
          fulfillment: "send",
          clears_at_source: false,
          decision: null,
          decision_history: [],
        });
        recordSend({
          handle,
          target: h.thread_id,
          template: "commission",
          text: ctx.rules.renderTemplate("commission", { summary: title }),
          wait_id: null,
        });
      } else if (verb === "leave_it") {
        // A bookmark even at status level: recorded, sends nothing.
      } else {
        // Directed control + the status quick verbs ride the
        // verdict template; the lane's answering status post
        // lands on the next tick.
        recordSend({
          handle,
          target: h.thread_id,
          template: "verdict",
          text: ctx.rules.renderTemplate("verdict", {
            summary,
            verb: verbLabel(verb),
            note: "",
          }),
          wait_id: null,
        });
        const next = DIRECTED_STATUS[verb];
        if (next) state.pendingStatus[handle] = next;
      }
      state.ownerActions.push({
        id: actionId,
        handle,
        verb,
        note: "",
        at: nowIso(),
        actor: "owner",
        rule_id: null,
      });
      const result: HandlerActionResult = { ok: true, action_id: actionId, verb };
      state.handlerIdempotency[idempotencyKey] = result;
      bump();
      return result;
    },
  };
}
