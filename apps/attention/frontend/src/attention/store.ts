// The mock adapter: a stateful store behind the
// AttentionDataSource seam, seeded with fictional,
// contract-shaped data. It implements plan §9 / contract 05's
// decision semantics against the mock ledger:
//
//   verdict at the tap, validated against the served verb set
//   -> the item leaves the open queue into the "Decided —
//      awaiting fulfillment" band (states queued / sent /
//      recorded)
//   -> fulfillment is derived, never assumed: from the send
//      ledger for send-backed decisions, from the push-fact
//      feed for push_needed, recorded for snooze
//   -> fulfilled: the item clears and its effect is shown
//   -> failed or unfulfilled past 120 minutes (stalled): the
//      item returns to the queue with decision_history and
//      the failure on its face
//   -> replay guards: an idempotency key short-circuits; a
//      repeated tap on a standing decision records and sends
//      nothing; a fulfilled decision is never changed.
//
// The simulated dispatch consumer settles outstanding claimed
// sends before claiming new ones (contract 05, §9.2a),
// claims on a 15-minute lease, and delivers only via an ack
// carrying the fulfillment's submission reference (ATT6).
// Shadow sends are never dispatchable (ATT5). Replies route
// direct to the owning thread, main copied (ATT3).
//
// Scenario clock: the mock scenario is Wednesday, March 4,
// 2026, America/New_York (EST, UTC-5 throughout the scenario
// window). The default clock starts at 14:04 scenario time
// and advances 1:1 with real time; tests inject a manual
// clock. All wall-clock math goes through the scenario zone.//
// The store is assembled from sections under ./store/:
// constants and scenario time, the record shapes, and
// one factory per closure section (engine, derivations,
// labels, learning, steering, digest, rules) plus the
// three api surfaces — all sharing the one state tree
// through the section context (./store/context.ts).

import handlersSeed from "./seed/handlers.json";
import programmesSeed from "./seed/programmes.json";
import waitsSeed from "./seed/waits.json";
import sendsSeed from "./seed/sends.json";
import presenceSeed from "./seed/presence.json";
import itemsSeed from "./seed/items.json";
import surfacesSeed from "./seed/surfaces.json";
import statusesSeed from "./seed/statuses.json";
import registriesSeed from "./seed/registries.json";
import rulesSeed from "./seed/rules.json";
import digestSeed from "./seed/digest.json";
import type {
  AttentionDataSource,
  DigestSettings,
  FulfilledEntry,
  HandlerRow,
  HandlerSurface,
  OwnerItem,
  PresenceRow,
  ProgrammeRow,
  RuleRecord,
  SendRow,
  WaitRow,
} from "./types";
import type {
  DigestSeedState,
  MockClock,
  RegistriesState,
  StatusRecord,
  StoreState,
} from "./store/records";
import { SCENARIO_START, clone } from "./store/constants";
import type { MockStoreCtx } from "./store/context";
import { createEngine } from "./store/engine";
import { createDerivations } from "./store/derivations";
import { createLabels } from "./store/labels";
import { createLearning } from "./store/learning";
import { createSteering } from "./store/steering";
import { createDigest } from "./store/digest";
import { createRules } from "./store/rules";
import { createApiReads } from "./store/api-reads";
import { createApiDecide } from "./store/api-decide";
import { createApiRules } from "./store/api-rules";

export { manualClock } from "./store/records";
export type { MockClock } from "./store/records";

export function createMockAttentionStore(clock?: MockClock): AttentionDataSource {
  const realStart = Date.now();
  const clk: MockClock = clock ?? {
    now: () => SCENARIO_START + (Date.now() - realStart),
    advance: () => undefined,
  };
  const nowMs = () => clk.now();
  const nowIso = () => new Date(nowMs()).toISOString();

  const surfaces = surfacesSeed as unknown as {
    handler_surfaces: Record<string, HandlerSurface>;
    digest: DigestSettings;
    fulfilled: FulfilledEntry[];
  };
  const state: StoreState = {
    handlers: clone(handlersSeed) as HandlerRow[],
    programmes: clone(programmesSeed) as ProgrammeRow[],
    waits: clone(waitsSeed) as WaitRow[],
    sends: clone(sendsSeed) as SendRow[],
    presence: clone(presenceSeed) as PresenceRow,
    items: clone(itemsSeed) as OwnerItem[],
    fulfilled: clone(surfaces.fulfilled),
    handlerSurfaces: clone(surfaces.handler_surfaces),
    digest: clone(surfaces.digest),
    statuses: clone(statusesSeed) as Record<string, StatusRecord>,
    registries: clone(registriesSeed) as RegistriesState,
    rules: clone(rulesSeed) as RuleRecord[],
    digestContent: clone(digestSeed) as DigestSeedState,
    ownerActions: [],
    pings: {},
    ownerDirected: {},
    pendingStatus: {},
    sendCounter: 7,
    actionCounter: 0,
    commissionCounter: 0,
    ruleCounter: 0,
    tickCount: 0,
    pushFact: { state: "current", flipAtTick: null },
    recordedResolveAt: {},
    tapCounts: {},
    actionRules: [],
    mutedItems: new Set<string>(),
    failures: [],
    idempotency: {},
    handlerIdempotency: {},
  };

  const listeners = new Set<() => void>();
  let version = 0;
  const bump = () => {
    version += 1;
    listeners.forEach((fn) => fn());
  };

  const handlerOf = (handle: string): HandlerRow =>
    state.handlers.find((h) => h.handle === handle) ?? state.handlers[0];

  const ctx = {
    state, nowMs, nowIso, bump, handlerOf,
    lastPresenceWrite: null,
  } as MockStoreCtx;

  /** Minting is only through record_send (contract 05). */
  ctx.recordSend = (args) => {
    state.sendCounter += 1;
    const id = `s${String(state.sendCounter).padStart(4, "0")}`;
    const send: SendRow = {
      id,
      at: nowIso(),
      rule_id: null,
      wait_id: args.wait_id,
      handle: args.handle,
      target: args.target,
      template: args.template,
      version: 1,
      attempt: 1,
      presence: ctx.derivations.resolvePresence(state.presence).mode,
      text: args.text,
      fact_hash: `mock-${id}`,
      mode: "active",
      outcome: "recorded",
      dispatch: {
        attempts: 0,
        claim_expires_at: null,
        claimed_at: null,
        consumer: null,
        delivered_at: null,
        delivery_ref: null,
      },
      bridge_request_id: `bridge-${id}`,
    };
    state.sends.push(send);
    return id;
  };

  ctx.engine = createEngine(ctx);
  ctx.derivations = createDerivations(ctx);
  ctx.labels = createLabels(ctx);
  ctx.learning = createLearning(ctx);
  ctx.steering = createSteering(ctx);
  ctx.digest = createDigest(ctx);
  ctx.rules = createRules(ctx);

  // ---------- the seam ----------

  const api: AttentionDataSource = {
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    getVersion: () => version,
    now: () => new Date(nowMs()),
    ...createApiReads(ctx),
    ...createApiDecide(ctx),
    ...createApiRules(ctx),
  };

  return api;
}
