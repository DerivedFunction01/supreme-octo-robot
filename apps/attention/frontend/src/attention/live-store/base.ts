// Live store base: snapshot state, the transport/refresh
// machinery, and the item/presence derivations the read
// and write surfaces share. LiveStoreWrites extends this;
// LiveAttentionStore (../live-store.ts) completes the
// seam. Members are protected because the three classes
// are one store split by surface, not a public hierarchy.

import type {
  AwaitingView,
  DecideResult,
  ExpiryChoice,
  HandlerActionResult,
  ItemKind,
  ItemView,
  PresenceView,
  Severity,
  SurfaceHealth,
  WouldFire,
} from "../types";
import {
  ServerPresence,
  ServerVerb,
  ServerItem,
  ServerToday,
  ServerGlance,
  ServerDigest,
  ServerHandlerRow,
  ServerRegistries,
  ServerRuleView,
  ServerProgramme,
  ServerHandlerDetail,
  ServerSend,
  ServerWait,
  frontendVerb,
  backendVerb,
} from "./server-types";
import {
  timeLabel,
  durationLabel,
  nyParts,
  nyInstant,
  weekdayFmt,
} from "./time";
import { HttpTransport, sanitizeBaseUrl, type AttentionTransport } from "../transport";

const FAST_MS = 15_000;
const DETAIL_MS = 30_000;
const SLOW_MS = 60_000;

export class LiveStoreBase {
  protected readonly baseUrl: string;
  /** The channel every backend call rides (transport.ts):
   * HTTP against the backend origin by default; the
   * rebuild's frame form passes the shell-relay transport.
   * The store's logic is channel-blind below fetchJson. */
  protected readonly transport: AttentionTransport;
  protected listeners = new Set<() => void>();
  protected version = 0;

  protected glance: ServerGlance | null = null;
  protected today: ServerToday | null = null;
  protected digest: ServerDigest | null = null;
  protected registries: ServerRegistries | null = null;
  protected rules: ServerRuleView[] = [];
  protected programmes: ServerProgramme[] = [];
  protected sends: ServerSend[] = [];
  protected handlerDetails = new Map<string, ServerHandlerDetail>();
  protected waits = new Map<string, ServerWait>();
  /** The presence slice: today's payload carries it; a
   * write overrides it until the next fast fetch lands. */
  protected presence: ServerPresence | null = null;
  protected presenceOverride = false;
  /** Write-path annotation, the mock's own device: which
   * expiry option produced the current expires_at, keyed
   * by the timestamp it produced (a relative preset is
   * indistinguishable from a custom instant once written). */
  protected lastPresenceWrite: { choice: ExpiryChoice; expires_at: string | null } | null = null;

  protected inflight = new Map<string, Promise<void>>();
  protected portionJson = new Map<string, string>();
  /** Per-portion fetch health (the original page's
   * portion() semantics): when a portion last loaded, and
   * whether its latest attempt failed. A portion that has
   * never loaded is down; one failing after a load is
   * stale — the getters keep serving the last good copy
   * and the views tag it, never an affirmative empty. */
  protected portionHealth = new Map<string, { lastOkAt: number | null; failing: boolean }>();
  protected decideCache = new Map<string, DecideResult>();
  protected handlerCache = new Map<string, HandlerActionResult>();
  protected previewCache = new Map<string, WouldFire[]>();
  protected ownPings = new Map<string, number>();
  /** The latest server-refused write, in words (AC-2):
   * the seam's write results are synchronous and
   * optimistic, so a refusal that arrives with the POST
   * lands here and the shell renders it — a refused act
   * never stands as accepted. Cleared when a later write
   * is accepted. */
  protected writeNotice: { text: string; at: number } | null = null;

  protected noteWriteRefusal(text: string): void {
    this.writeNotice = { text, at: Date.now() };
    this.bump();
  }
  protected lastFastStart = 0;

  constructor(opts: { baseUrl?: string; transport?: AttentionTransport } = {}) {
    this.baseUrl = sanitizeBaseUrl(opts.baseUrl ?? "").replace(/\/$/, "");
    this.transport = opts.transport ?? new HttpTransport(this.baseUrl);
    setInterval(() => void this.refreshFast(), FAST_MS);
    setInterval(() => void this.refreshDetails(), DETAIL_MS);
    setInterval(() => void this.refreshSlow(), SLOW_MS);
    // The clock tick: labels the backend computed at fetch
    // time stay put between polls; the version still turns
    // over so wall-clock derivations (ages, expiry) move.
    setInterval(() => this.bump(), 30_000);
  }

  // ---------- transport ----------

  /** The store's one channel seam: every read and write
   * rides the configured transport (transport.ts), which
   * answers with the payload on a 2xx and throws the
   * failure's sentence otherwise — identically on the
   * HTTP and shell-relay channels. */
  protected async fetchJson(path: string, init?: RequestInit): Promise<unknown> {
    return this.transport.request(path, init);
  }

  /** One load per portion in flight; a changed portion
   * bumps the version, a failed one keeps the last-good. */
  protected load(key: string, path: string, apply: (data: never) => void): Promise<void> {
    const existing = this.inflight.get(key);
    if (existing) return existing;
    const run = (async () => {
      const health = this.portionHealth.get(key) ?? { lastOkAt: null, failing: false };
      try {
        const data = await this.fetchJson(path);
        const recovered = health.failing;
        health.lastOkAt = Date.now();
        health.failing = false;
        this.portionHealth.set(key, health);
        const json = JSON.stringify(data);
        if (this.portionJson.get(key) !== json) {
          this.portionJson.set(key, json);
          apply(data as never);
          this.bump();
        } else if (recovered) {
          this.bump();
        }
      } catch {
        /* last-good stands; the next poll retries — and
         * the failure is recorded, so the views can say
         * the surface is stale or unreachable instead of
         * presenting the last good copy (or an empty
         * snapshot) as current truth. */
        if (!health.failing) {
          health.failing = true;
          this.portionHealth.set(key, health);
          this.bump();
        }
      } finally {
        this.inflight.delete(key);
      }
    })();
    this.inflight.set(key, run);
    return run;
  }

  protected async refreshFast(): Promise<void> {
    this.lastFastStart = Date.now();
    await Promise.all([
      this.load("glance", "/api/v1/glance", (d: ServerGlance) => {
        this.glance = d;
        if (!this.presenceOverride) this.presence = d.presence;
      }),
      this.load("today", "/api/v1/today", (d: ServerToday) => {
        this.today = d;
        if (!this.presenceOverride) this.presence = d.presence;
      }),
      this.load("digest", "/api/v1/digest", (d: ServerDigest) => {
        this.digest = d;
      }),
    ]);
    this.presenceOverride = false;
  }

  protected async refreshSlow(): Promise<void> {
    await Promise.all([
      this.load("registries", "/api/v1/registries", (d: ServerRegistries) => {
        this.registries = d;
      }),
      this.load("rules", "/api/v1/rules", (d: { rules: ServerRuleView[] }) => {
        this.rules = d.rules;
      }),
      this.load("programmes", "/api/v1/programmes", (d: { programmes: ServerProgramme[] }) => {
        this.programmes = d.programmes;
      }),
      this.load("sends", "/api/v1/sends", (d: { sends: ServerSend[] }) => {
        this.sends = d.sends;
      }),
    ]);
  }

  protected async refreshDetails(): Promise<void> {
    const handles = (this.registries?.handlers ?? []).map((h) => h.handle);
    const jobs: Promise<void>[] = handles.map((handle) =>
      this.load(`handler:${handle}`, `/api/v1/handlers/${encodeURIComponent(handle)}`, (d: ServerHandlerDetail) => {
        this.handlerDetails.set(handle, d);
      }),
    );
    // The waits behind open items: the decide mirror
    // validates promotions against the wait's class.
    const waitIds = new Set<string>();
    for (const band of this.today?.bands ?? []) {
      if (band.band === "decided") continue;
      for (const item of band.items) if (item.wait_id) waitIds.add(item.wait_id);
    }
    for (const waitId of waitIds) {
      jobs.push(
        this.load(`wait:${waitId}`, `/api/v1/agent/waits/${encodeURIComponent(waitId)}`, (d: ServerWait) => {
          this.waits.set(waitId, d);
        }),
      );
    }
    await Promise.all(jobs);
  }

  /** The first load, awaited by the integration entry so
   * the published app never mounts on an empty snapshot.
   * Resolves even when the surface is down — the getters
   * serve their empty forms and polling keeps retrying. */
  async ready(): Promise<void> {
    await this.refreshSlow().catch(() => undefined);
    await this.refreshFast().catch(() => undefined);
    await this.refreshDetails().catch(() => undefined);
  }

  // ---------- seam plumbing ----------

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getVersion = (): number => this.version;

  protected bump(): void {
    this.version += 1;
    this.listeners.forEach((fn) => fn());
  }

  now = (): Date => new Date();

  tick = (): void => {
    // AppMain ticks on a short interval (the mock's
    // simulated consumer driver). Live, the tick is a
    // refresh nudge only — the polls own the cadence.
    if (Date.now() - this.lastFastStart >= 10_000) {
      void this.refreshFast();
    }
  };

  // ---------- shared derivations over the snapshot ----------

  protected bandItems(band: string): ServerItem[] {
    return this.today?.bands.find((b) => b.band === band)?.items ?? [];
  }

  protected allOpenItems(): ServerItem[] {
    const out: ServerItem[] = [];
    for (const band of this.today?.bands ?? []) {
      if (band.band !== "decided") out.push(...band.items);
    }
    return out;
  }

  protected findItem(itemId: string): ServerItem | null {
    for (const band of this.today?.bands ?? []) {
      const found = band.items.find((i) => i.id === itemId);
      if (found) return found;
    }
    for (const detail of this.handlerDetails.values()) {
      const found = detail.items.find((i) => i.id === itemId);
      if (found) return found;
    }
    return null;
  }

  protected handlerRow(handle: string): ServerHandlerRow | null {
    return this.registries?.handlers.find((h) => h.handle === handle) ?? null;
  }

  /** Verb labels as served (item verbs, handler verbs,
   * quick verbs all carry theirs); the map is the only
   * label source — an unserved verb labels itself. */
  protected verbLabelOf(verb: string): string {
    const map = new Map<string, string>();
    const take = (entries: ServerVerb[] | undefined) => {
      for (const e of entries ?? []) if (!map.has(e.verb)) map.set(e.verb, e.label);
    };
    for (const band of this.today?.bands ?? []) {
      for (const item of band.items) take(item.verbs);
    }
    for (const detail of this.handlerDetails.values()) {
      take(detail.handler_verbs);
      take(detail.status?.quick_verbs);
      for (const item of detail.items) take(item.verbs);
    }
    return map.get(verb) ?? map.get(backendVerb(verb)) ?? map.get(frontendVerb(verb)) ?? verb;
  }

  protected itemFailure(item: ServerItem): string | null {
    if (item.fulfillment && (item.fulfillment.state === "failed" || item.fulfillment.state === "stalled")) {
      return item.fulfillment.label;
    }
    return null;
  }

  /** The mock's severity derivation, over served fields:
   * a returned item fails its handler; a breakthrough
   * tier warns (fails inside its due hour); age grades
   * the rest. An item's served severity is its handler's
   * aggregate — the mock's own form. */
  protected itemSeverity(item: ServerItem): Severity {
    const nowMs = Date.now();
    if (this.itemFailure(item)) return "fail";
    if (item.tier === "breakthrough") {
      if (item.due_at && Date.parse(item.due_at) - nowMs < 3_600_000) return "fail";
      return "warn";
    }
    const age = nowMs - Date.parse(item.waiting_since);
    if (age >= 3_600_000) return "fail";
    if (age >= 900_000) return "warn";
    return "info";
  }

  protected handlerSeverity(handle: string): Severity {
    const open = this.allOpenItems().filter((i) => i.handler.handle === handle);
    if (open.some((i) => this.itemSeverity(i) === "fail")) return "fail";
    if (open.some((i) => this.itemSeverity(i) === "warn")) return "warn";
    if (open.length > 0) return "info";
    return "idle";
  }

  protected snoozeLabel(atIso: string, options: ServerItem["snooze_options"]): string {
    const match = options.times.find((t) => Date.parse(t) === Date.parse(atIso));
    const at = match ?? atIso;
    return `${weekdayFmt.format(new Date(at))} · ${timeLabel(at)}`;
  }

  protected toItemView(item: ServerItem): ItemView {
    const failure = this.itemFailure(item);
    return {
      id: item.id,
      handle: item.handler.handle,
      handler_label: item.handler.label,
      color_slot: item.handler.color_slot,
      kind: item.kind as ItemKind,
      title: item.title,
      waiting_label: `Waiting ${item.waiting_label}`,
      severity: this.handlerSeverity(item.handler.handle),
      verbs: item.verbs.map((v) => frontendVerb(v.verb)),
      options: item.options && item.options.length > 0 ? item.options : null,
      failure,
      history: (item.decision_history ?? []).map((h) => ({
        verb: frontendVerb(h.verb),
        at: h.at,
        option_id: h.option_id,
        note: h.note,
        send_id: h.send_id,
        outcome: (h.outcome ?? "recorded") as "fulfilled" | "failed" | "stalled" | "queued" | "sent" | "recorded",
        failure: undefined,
      })),
      due_label: item.due_at ? timeLabel(item.due_at) : null,
      clears_at_source: item.clears_at_source,
      snooze_options: {
        times: item.snooze_options.times.map((at) => ({
          at,
          label: `${weekdayFmt.format(new Date(at))} · ${timeLabel(at)}`,
        })),
        on_activity: item.snooze_options.on_activity,
      },
      rule_hint: item.verbs.find((v) => v.rule_hint)?.rule_hint ?? null,
      proposal: item.proposal ?? null,
    };
  }

  protected toAwaitingView(item: ServerItem): AwaitingView {
    const base = this.toItemView(item);
    const decision = item.decision;
    const state = (item.fulfillment?.state ?? "recorded") as "queued" | "sent" | "recorded";
    const verb = decision ? frontendVerb(decision.verb) : "";
    const optLabel = decision?.option_id
      ? item.options?.find((o) => o.id === decision.option_id)?.label
      : null;
    let decided = decision
      ? `Decided ${durationLabel(Date.now() - Date.parse(decision.at))} ago · ${optLabel ?? this.verbLabelOf(decision.verb)}`
      : "";
    if (decision?.verb === "snooze" && item.snooze_return_at) {
      decided += ` · until ${this.snoozeLabel(item.snooze_return_at, item.snooze_options)}`;
      if (item.snooze_on_activity) decided += " · or on new activity";
      if (item.resume_note) decided += ` · Resume: ${item.resume_note}`;
    }
    return {
      ...base,
      band_state: state,
      band_label: state === "queued" ? "Queued" : state === "sent" ? "Sent · awaiting delivery" : "Recorded",
      decided_label: decided,
      decision: {
        verb,
        at: decision?.at ?? "",
        option_id: decision?.option_id ?? null,
        note: decision?.note ?? null,
        send_id: decision?.send_id ?? null,
      },
    };
  }

  protected resolvePresence(p: ServerPresence): PresenceView {
    const nowMs = Date.now();
    let mode = p.mode;
    let expires = p.expires_at;
    if (expires && Date.parse(expires) <= nowMs && mode === "active") {
      // The served mode already resolved the expiry; the
      // dead window no longer bounds the record.
      expires = null;
    }
    let choice: ExpiryChoice = "none";
    if (expires) {
      if (this.lastPresenceWrite && this.lastPresenceWrite.expires_at === expires) {
        choice = this.lastPresenceWrite.choice;
      } else {
        const at = Date.parse(expires);
        const parts = nyParts(new Date(nowMs));
        if (at === nyInstant(parts.y, parts.mo, parts.da, 17, 0)) choice = "17:00";
        else if (at === nyInstant(parts.y, parts.mo, parts.da, 8, 0) + 86_400_000) choice = "tomorrow-08:00";
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

  protected emptyPresence(): PresenceView {
    return {
      mode: "active",
      expires_at: null,
      expiry_choice: "none",
      expectation: "",
      chip_label: "Active",
      chip_severity: "ok",
    };
  }

  // ---------- reads ----------

  getSurfaceHealth = (): SurfaceHealth => {
    const portion = (key: string) => {
      const h = this.portionHealth.get(key);
      if (!h || h.lastOkAt === null) return { state: "down" as const, last_good_at: null };
      return {
        state: h.failing ? ("stale" as const) : ("ok" as const),
        last_good_at: new Date(h.lastOkAt).toISOString(),
      };
    };
    return {
      glance: portion("glance"),
      today: portion("today"),
      digest: portion("digest"),
    };
  };

  getPresence = (): PresenceView => {
    return this.presence ? this.resolvePresence(this.presence) : this.emptyPresence();
  };


  protected post(
    path: string,
    body: unknown,
    after?: () => void,
    act = "That write",
    onRefusal?: (message: string) => void,
  ): void {
    void (async () => {
      try {
        await this.fetchJson(path, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        if (this.writeNotice) {
          this.writeNotice = null;
          this.bump();
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (onRefusal) onRefusal(message);
        else this.noteWriteRefusal(`${act} was not saved — the server refused it: ${message}`);
      } finally {
        after?.();
        void this.refreshFast();
      }
    })();
  }

  getWriteNotice = (): string | null => this.writeNotice?.text ?? null;
}
