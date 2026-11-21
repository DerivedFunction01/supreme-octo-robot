// The mock store's section context: the shared closure
// state of createMockAttentionStore, named once so the
// store's sections (engine, derivations, labels,
// learning, steering, digest, rules, and the api
// surfaces) can live in their own modules and still call
// each other exactly as the single closure did. Sections
// read cross-section functions through this object at
// call time; the assembly in ../store.ts fills every
// slot before the api is served.

import type {
  ActionRuleRecord,
  StoreState,
} from "./records";
import type {
  AwaitingView,
  BandState,
  DecisionRecord,
  DigestContentView,
  ExpiryChoice,
  HandlerActionResult,
  HandlerRow,
  HandlerStatusView,
  ItemView,
  OwnerActionView,
  OwnerItem,
  PresenceRow,
  PresenceView,
  RuleRecord,
  RuleView,
  SendRow,
  Severity,
  SnoozeOptionsView,
  StatusCodeEntry,
  VerbEntry,
  WaitRow,
} from "../types";

export interface MockStoreCtx {
  state: StoreState;
  nowMs: () => number;
  nowIso: () => string;
  bump: () => void;
  handlerOf: (handle: string) => HandlerRow;
  lastPresenceWrite: { choice: ExpiryChoice; expires_at: string | null } | null;
  recordSend: (args: {
    handle: string;
    target: string;
    template: string;
    text: string;
    wait_id: string | null;
  }) => string;
  engine: {
    returnToQueue: (item: OwnerItem, outcome: "failed" | "stalled", failure: string) => void;
    runEvaluator: () => boolean;
    fulfill: (item: OwnerItem, effect: string) => void;
    recordFailure: (send: SendRow, reason: string) => void;
    runConsumer: () => boolean;
  };
  derivations: {
    resolvePresence: (p: PresenceRow) => PresenceView;
    itemSeverity: (item: OwnerItem) => Severity;
    handlerSeverity: (handle: string) => Severity;
    toItemView: (item: OwnerItem) => ItemView;
    bandState: (item: OwnerItem) => BandState;
    toAwaitingView: (item: OwnerItem) => AwaitingView;
    openItems: () => OwnerItem[];
    waitingItems: (items: OwnerItem[]) => OwnerItem[];
    nextDigest: () => { label: string; detail: string; time: string };
    digestDetail: (at: number) => string;
    nextDigestAt: () => number | null;
  };
  labels: {
    statusCodeOf: (code: string) => StatusCodeEntry | null;
    statusLabelOf: (code: string) => string;
    kindLabel: (kind: string) => string;
    classLabel: (name: string) => string;
    ageLabel: (atIso: string) => string;
    snoozeOptionsFor: () => SnoozeOptionsView;
    snoozeTimeLabel: (atIso: string) => string;
  };
  learning: {
    waitOf: (item: OwnerItem) => WaitRow | undefined;
    classOf: (item: OwnerItem) => string;
    createActionRule: (args: {
      match: ActionRuleRecord["match"];
      verb: string;
      mode: string;
      created_from: string;
      option_id?: string | null;
    }) => ActionRuleRecord;
    actionRuleMatches: (rule: ActionRuleRecord, item: OwnerItem, verb: string) => boolean;
    shadowHintFor: (item: OwnerItem) => string | null;
    countTap: (item: OwnerItem, verb: string) => void;
  };
  steering: {
    verbEntry: (verb: string) => VerbEntry;
    quickVerbsFor: (code: string) => VerbEntry[];
    statusViewOf: (handle: string) => HandlerStatusView | null;
    handlerVerbsFor: (handle: string) => VerbEntry[];
    ownerActionsFor: (handle: string) => OwnerActionView[];
    windowStartMs: () => number;
  };
  digest: {
    topicOf: (handle: string) => string;
    digestStalls: () => DigestContentView["stalls"];
    digestTopics: (stalls: DigestContentView["stalls"]) => DigestContentView["topics"];
    digestContent: () => DigestContentView;
  };
  rules: {
    titleCaseId: (id: string) => string;
    ruleViewOf: (rule: RuleRecord) => RuleView;
    normalizeRule: (rule: RuleRecord) => RuleRecord;
    validateRule: (rule: RuleRecord) => string[];
    renderTemplate: (kind: string, facts: Record<string, unknown>) => string;
    waitFacts: (wait: WaitRow) => Record<string, unknown>;
    leafHolds: (leaf: { field: string; op: string; value: unknown }, facts: Record<string, unknown>) => boolean;
    ruleMatchesWait: (rule: RuleRecord, facts: Record<string, unknown>) => boolean;
  };
}

export type { DecisionRecord, HandlerActionResult };
