// Live store writes: the seam's write surface (presence,
// digest settings, mutes, decisions, handler actions,
// rules, vocabulary) — optimistic results composed at the
// tap, POSTed in the background through the base's post().

import { LiveStoreBase } from "./base";
import type {
  DecideInput,
  DecideResult,
  DecisionRecord,
  ExpiryChoice,
  FieldInput,
  HandlerActionResult,
  ItemKindInput,
  PresenceMode,
  RulePreviewResult,
  RuleRecord,
  RuleSaveResult,
  StatusCodeInput,
  TemplateInput,
  VocabResult,
  WaitClassInput,
  WouldFire,
} from "../types";
import {
  ServerRuleView,
  frontendVerb,
  backendVerb,
  HANDLER_VERBS,
} from "./server-types";
import {
  nyParts,
  nyInstant,
  clone,
} from "./time";

export class LiveStoreWrites extends LiveStoreBase {
  setPresence = (mode: PresenceMode, expiry: ExpiryChoice, customExpiresAt?: string | null): void => {
    const nowMs = Date.now();
    const parts = nyParts(new Date(nowMs));
    let expires: string | null = null;
    if (expiry === "1h") expires = new Date(nowMs + 3_600_000).toISOString();
    if (expiry === "17:00") expires = new Date(nyInstant(parts.y, parts.mo, parts.da, 17, 0)).toISOString();
    if (expiry === "tomorrow-08:00") {
      expires = new Date(nyInstant(parts.y, parts.mo, parts.da, 8, 0) + 86_400_000).toISOString();
    }
    if (expiry === "custom") expires = customExpiresAt ?? null;
    // The write carries the owner's standing expectation
    // text verbatim — the backend's write replaces the
    // record, and a mode/expiry change is not an
    // expectation edit.
    const expectation = this.presence?.expectation ?? "";
    this.lastPresenceWrite = { choice: expiry, expires_at: expires };
    this.presence = { mode, mode_label: mode, expires_at: expires, expectation };
    this.presenceOverride = true;
    this.bump();
    this.post("/api/v1/presence", { mode, expires_at: expires, expectation }, () => {
      this.presenceOverride = false;
    }, "That presence change");
  };

  setDigestWindow = (id: string, enabled: boolean): void => {
    // A real server write (AC-8): the prefs live on the
    // backend's state, and the served digest's window —
    // next_at, the glance clock, the snooze times — reads
    // them. The shell Settings row drives this same path.
    this.post("/api/v1/digest/prefs", { window_time: id, window_enabled: enabled }, undefined, "That digest window change");
  };

  setDigestInclude = (key: "decisions" | "waiting" | "fyi", enabled: boolean): void => {
    this.post("/api/v1/digest/prefs", { include_key: key, include_enabled: enabled }, undefined, "That digest include change");
  };

  setMutedType = (handle: string, type: string, muted: boolean): void => {
    const detail = this.handlerDetails.get(handle);
    // The served muted_types carry their kind; an
    // unlisted type resolves through the registries'
    // item-kind labels. Unresolvable is refused aloud.
    const kind =
      detail?.muted_types.find((m) => m.label === type)?.kind ??
      this.registries?.item_kinds.find((k) => k.label === type)?.kind;
    if (!kind) {
      this.noteWriteRefusal(`That type is not served for ${handle}.`);
      return;
    }
    this.post(
      `/api/v1/handlers/${encodeURIComponent(handle)}/${muted ? "mute" : "unmute"}`,
      { kind },
      () => {
        void this.refreshDetails();
      },
      muted ? "That mute" : "That unmute",
    );
  };

  decide = (itemId: string, input: DecideInput): DecideResult => {
    const seen = this.decideCache.get(input.idempotency_key);
    if (seen) return seen;
    const fail = (error: string): DecideResult => ({ ok: false, error });

    const item = this.findItem(itemId);
    if (!item) return fail(`unknown item ${itemId}`);

    // A standing decision in an open fulfillment state
    // replays: the verdict already stands, nothing is
    // recorded or sent twice. A returned item (failed /
    // stalled) is decidable again, as on the backend.
    const standing = item.decision;
    const fulfillmentState = item.fulfillment?.state ?? null;
    if (standing && (fulfillmentState === null || ["queued", "sent", "recorded"].includes(fulfillmentState))) {
      const replayed: DecideResult = {
        ok: true,
        decision: {
          verb: frontendVerb(standing.verb),
          at: standing.at,
          option_id: standing.option_id,
          note: standing.note ?? "",
          send_id: standing.send_id,
        },
        replayed: true,
      };
      this.decideCache.set(input.idempotency_key, replayed);
      return replayed;
    }

    const view = this.toItemView(item);
    if (!view.verbs.includes(input.verb)) {
      return fail(`verb "${input.verb}" is not served for ${itemId}`);
    }
    if (input.verb === "decide" || input.verb === "rule_it") {
      if (!view.options?.some((o) => o.id === input.option_id)) {
        return fail(`option required for ${itemId}`);
      }
    } else if (input.option_id) {
      return fail(`option not accepted for verb "${input.verb}"`);
    }
    if (input.make_rule && input.verb === "approve_rule") {
      return fail("make_rule: approve_rule already promotes");
    }
    const wait = item.wait_id ? this.waits.get(item.wait_id) : undefined;
    const waitClass = wait
      ? this.registries?.wait_classes.find((c) => c.name === wait.wait_class)
      : undefined;
    if (input.verb === "approve_rule") {
      if (!wait) return fail("approve_rule: no wait stands behind this item");
      if (waitClass?.hard_stop) {
        return fail("hard-stop approvals are approved once, never ruled");
      }
    }
    if (input.make_rule && wait && waitClass?.hard_stop) {
      return fail("make_rule: a hard-stop approval can never become a rule");
    }
    if (input.verb === "snooze" && input.return_at) {
      const served = view.snooze_options.times.find(
        (t) => Date.parse(t.at) === Date.parse(input.return_at as string),
      );
      if (!served) return fail("snooze: the return time is not one of the served times");
    }

    const effectiveVerb = input.verb === "approve_rule" ? "approve" : input.verb;
    const decision: DecisionRecord = {
      verb: effectiveVerb,
      at: new Date().toISOString(),
      option_id:
        input.verb === "decide" || input.verb === "rule_it" ? (input.option_id as string) : null,
      note: input.note ?? "",
      send_id: null,
    };
    const result: DecideResult = { ok: true, decision, replayed: false };
    this.decideCache.set(input.idempotency_key, result);
    this.post(`/api/v1/items/${encodeURIComponent(itemId)}/action`, {
      verb: backendVerb(input.verb),
      option_id: input.option_id ?? null,
      note: input.note ?? "",
      idempotency_key: input.idempotency_key,
      return_at: input.return_at ?? null,
      return_on_activity: input.return_on_activity ?? undefined,
      resume_note: input.resume_note ?? undefined,
      make_rule: input.make_rule ?? undefined,
    }, undefined, "That decision", (message) => {
      // The optimistic ok unwinds: the cached result is
      // evicted so the same key can be decided again, and
      // the refusal is stated — the item never recorded.
      this.decideCache.delete(input.idempotency_key);
      this.noteWriteRefusal(`That decision was not recorded — the server refused it: ${message}`);
    });
    this.bump();
    return result;
  };

  handlerAction = (handle: string, verb: string, idempotencyKey: string): HandlerActionResult => {
    const seen = this.handlerCache.get(idempotencyKey);
    if (seen) return seen;
    if (!this.handlerRow(handle)) return { ok: false, error: "No such handler." };
    if (!HANDLER_VERBS.has(verb)) {
      return { ok: false, error: "verb not served for a handler" };
    }
    if (verb === "status_ping") {
      // The ping cooldown (one per digest window),
      // mirrored from this session's own pings against
      // the served window times — the backend raises the
      // same conflict for a ping this session cannot see.
      const last = this.ownPings.get(handle);
      if (last !== undefined && last >= this.windowStartMs()) {
        return { ok: false, error: "A status ping already went out this digest window." };
      }
      this.ownPings.set(handle, Date.now());
    }
    // The server assigns the action id; it arrives with
    // the refreshed owner-actions ledger, where ids are
    // read. The tap's receipt carries the verb only.
    const result: HandlerActionResult = { ok: true, action_id: "", verb };
    this.handlerCache.set(idempotencyKey, result);
    this.post(`/api/v1/handlers/${encodeURIComponent(handle)}/action`, {
      verb,
      idempotency_key: idempotencyKey,
    }, () => {
      void this.refreshDetails();
    }, "That handler action", (message) => {
      // Unwind the optimistic ok: the cached receipt is
      // evicted, a refused status ping frees its window
      // mark, and the refusal is stated.
      this.handlerCache.delete(idempotencyKey);
      if (verb === "status_ping") this.ownPings.delete(handle);
      this.noteWriteRefusal(`That handler action was not recorded — the server refused it: ${message}`);
    });
    this.bump();
    return result;
  };

  /** The most recent digest window instant at or before
   * now, from the served window times in the server's
   * own zone (the offset rides the glance clock's ISO). */
  protected windowStartMs(): number {
    const times = this.digest?.window.times ?? [];
    const nowIso = this.glance?.clock.now;
    if (!times.length || !nowIso) return Number.NEGATIVE_INFINITY;
    const offset = /([+-]\d{2}):(\d{2})$/.exec(nowIso);
    const offsetMs = offset
      ? (Number(offset[1]) * 60 + Number(offset[2]) * (offset[1].startsWith("-") ? -1 : 1)) * 60_000
      : 0;
    const nowMs = Date.parse(nowIso);
    const wallNow = new Date(nowMs + offsetMs);
    let best = Number.NEGATIVE_INFINITY;
    for (const dayOff of [0, -1]) {
      for (const time of times) {
        const [h, mi] = time.split(":").map(Number);
        const wall = Date.UTC(
          wallNow.getUTCFullYear(),
          wallNow.getUTCMonth(),
          wallNow.getUTCDate() + dayOff,
          h,
          mi,
        );
        const at = wall - offsetMs;
        if (at <= nowMs && at > best) best = at;
      }
    }
    return best;
  }

  // ---------- rules ----------

  /** normalize_rule, mirrored from the mock (which
   * mirrors the backend): defaults for mode, scope,
   * on_scope_miss, requires, priority, trigger, guards. */
  protected normalizeRule(rule: RuleRecord): RuleRecord {
    const out = clone(rule);
    const action = out.action as unknown;
    if (typeof action === "string") out.action = { type: action };
    out.match = {
      wait_class: out.match?.wait_class ?? null,
      status_code: out.match?.status_code ?? null,
      kind: out.match?.kind ?? null,
      handle: out.match?.handle ?? null,
    };
    out.scope = out.scope || "always";
    out.mode = out.mode || "shadow";
    out.on_scope_miss = out.on_scope_miss || "pending";
    out.requires = out.requires ?? [];
    out.priority = out.priority || 100;
    out.trigger = out.trigger?.on ? out.trigger : { on: "on_enter" };
    out.guards = out.guards ?? {};
    return out;
  }

  saveRule = (rule: RuleRecord): RuleSaveResult => {
    // Validation and label composition are the server's
    // (AC-13): no mirrored validator, no client-composed
    // sentences. The POST returns the served rule view;
    // it joins the rules portion when it lands, and a
    // refusal surfaces through the write notice. The
    // synchronous receipt carries the served view when
    // the rule already stands, else the record with the
    // name-derived display name — labels arrive with the
    // refresh, composed by the one home that owns them.
    const stored = this.normalizeRule(rule);
    void (async () => {
      try {
        const view = (await this.fetchJson("/api/v1/rules", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(stored),
        })) as ServerRuleView;
        const idx = this.rules.findIndex((r) => r.id === view.id);
        if (idx >= 0) this.rules[idx] = view;
        else this.rules.push(view);
        if (this.writeNotice) this.writeNotice = null;
        this.bump();
        void this.refreshSlow();
      } catch (err) {
        this.noteWriteRefusal(
          `That rule was not saved — the server refused it: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    })();
    const standing = this.rules.find((r) => r.id === stored.id);
    if (standing) return { ok: true, rule: { ...standing, name: standing.name ?? null } };
    return {
      ok: true,
      rule: {
        ...clone(stored),
        display_name:
          stored.name || stored.id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        when_label: "",
        then_label: "",
      },
    };
  };

  previewRule = (rule: RuleRecord): RulePreviewResult => {
    const candidate = this.normalizeRule(rule);
    // The dry run is the server's own evaluation over
    // live waits — it cannot be composed at the tap.
    // The first tap fires it; the result is cached by
    // the candidate's own shape and a second tap on the
    // unchanged rule reads it back.
    const key = JSON.stringify(candidate);
    const cached = this.previewCache.get(key);
    if (cached) return { ok: true, would_fire: cached };
    void (async () => {
      try {
        const data = (await this.fetchJson("/api/v1/rules/preview", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ rule: candidate }),
        })) as { would_fire: WouldFire[] };
        this.previewCache.set(key, data.would_fire);
        this.bump();
      } catch (err) {
        this.noteWriteRefusal(
          `That rule preview failed on the server: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    })();
    return {
      ok: false,
      error: "Preview runs on the server against the live waits — tap Preview again to read its result for this rule.",
    };
  };

  // ---------- vocab writes ----------

  addStatusCode = (entry: StatusCodeInput): VocabResult => {
    const errors: string[] = [];
    for (const field of ["code", "short", "label", "need"] as const) {
      if (!entry[field]) errors.push(`${field} is required`);
    }
    const needs = ["owner_actionable", "agent_clearable", "unclassified"];
    if (entry.need && !needs.includes(entry.need)) errors.push("need unknown need");
    if (errors.length) {
      return { ok: false, error: `Status code failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/status-codes", entry, () => void this.refreshSlow(), "That status code");
    return { ok: true };
  };

  addField = (entry: FieldInput): VocabResult => {
    const errors: string[] = [];
    if (!entry.name) errors.push("name is required");
    if (!entry.type) errors.push("type is required");
    const types = ["bool", "enum", "number", "datetime", "string"];
    if (entry.type && !types.includes(entry.type)) errors.push("type unknown field type");
    if (errors.length) {
      return { ok: false, error: `Field failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/fields", entry, () => void this.refreshSlow(), "That field");
    return { ok: true };
  };

  addWaitClass = (entry: WaitClassInput): VocabResult => {
    if (!entry.name) {
      return { ok: false, error: "Class failed validation. name is required" };
    }
    const existing = this.registries?.wait_classes.find((c) => c.name === entry.name);
    if (existing?.hard_stop) {
      return {
        ok: false,
        error: "Class failed validation. name hard-stop classes are not editable",
      };
    }
    this.post("/api/v1/vocab/classes", entry, () => void this.refreshSlow(), "That wait class");
    return { ok: true };
  };

  addTemplate = (entry: TemplateInput): VocabResult => {
    const errors: string[] = [];
    if (!entry.kind) errors.push("kind is required");
    if (!entry.text) errors.push("text is required");
    if (!["chat", "main"].includes(entry.audience)) {
      errors.push("audience must be chat or main");
    }
    if (errors.length) {
      return { ok: false, error: `Template failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/templates", entry, () => void this.refreshSlow(), "That template");
    return { ok: true };
  };

  addItemKind = (entry: ItemKindInput): VocabResult => {
    const errors: string[] = [];
    if (!entry.kind) errors.push("kind is required");
    if (!entry.label) errors.push("label is required");
    if (entry.digest_owner !== null && !["owner", "lane", "self"].includes(entry.digest_owner)) {
      errors.push("digest_owner must be owner, lane, or self");
    }
    if (errors.length) {
      return { ok: false, error: `Item kind failed validation. ${errors.join("; ")}` };
    }
    this.post("/api/v1/vocab/kinds", entry, () => void this.refreshSlow(), "That item kind");
    return { ok: true };
  };
}
