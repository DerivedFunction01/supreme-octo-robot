import type {
  DecisionRecord,
  PresenceMode,
  SendRow,
} from "./rows";
import type {
  DigestView,
  GlanceView,
  HandlerDetailView,
  HandlersView,
  PresenceView,
  ProgrammeCardView,
  SurfaceHealth,
  TodayView,
} from "./views";
import type { HandlerActionResult } from "./steering";
import type { RegistriesView } from "./registries";
import type {
  ActionRuleView,
  RulePreviewResult,
  RuleRecord,
  RuleSaveResult,
  RuleView,
} from "./rules";
import type {
  FieldInput,
  ItemKindInput,
  StatusCodeInput,
  TemplateInput,
  VocabResult,
  WaitClassInput,
} from "./vocab";

export type DecideResult =
  | { ok: true; decision: DecisionRecord; replayed: boolean }
  | { ok: false; error: string };

export interface DecideInput {
  verb: string;
  option_id?: string | null;
  note?: string;
  idempotency_key: string;
  /** Snooze payload (backend triage fields): the chosen
   * return instant from the item's served snooze_options,
   * whether new activity returns it sooner, and the note
   * it resumes with. */
  return_at?: string | null;
  return_on_activity?: boolean;
  resume_note?: string | null;
  /** The deliberate promotion flag (backend D-A8): the
   * tap also makes a standing action rule. Refused with
   * approve_rule, which already promotes. */
  make_rule?: boolean;
}

export type ExpiryChoice = "1h" | "17:00" | "tomorrow-08:00" | "none" | "custom";

/** The data seam. The mock adapter below implements it over a
 * stateful in-memory store; at S8 the live adapter implements
 * the same interface over the attention app's api/1 shapes,
 * with no frontend change. */
export interface AttentionDataSource {
  subscribe(fn: () => void): () => void;
  getVersion(): number;
  now(): Date;
  getPresence(): PresenceView;
  /** Presence write — the same path every expiry option
   * uses. The record itself carries only the absolute
   * expires_at (the backend's POST /api/v1/presence shape);
   * the presets resolve to instants at write time, and a
   * "custom" choice carries its instant in customExpiresAt
   * (an ISO timestamp, or null to clear). */
  setPresence(mode: PresenceMode, expiry: ExpiryChoice, customExpiresAt?: string | null): void;
  getGlance(night?: boolean): GlanceView;
  getToday(): TodayView;
  /** Fetch health per surface portion (the honest-failure
   * seam): views render unreachable/stale states from this,
   * never an affirmative empty queue for a down surface. */
  getSurfaceHealth(): SurfaceHealth;
  /** The latest write verdict the server refused, in
   * words, or null. Live writes return their optimistic
   * result synchronously (the seam's shape); when the
   * server then refuses the write, the refusal lands here
   * and the shell renders it — a refused decision, rule,
   * or vocab act never stands as accepted. Cleared when a
   * later write is accepted. */
  getWriteNotice(): string | null;
  getHandlers(): HandlersView;
  getHandlerDetail(handle: string): HandlerDetailView | null;
  getProgrammes(): ProgrammeCardView[];
  getDigest(): DigestView;
  setDigestWindow(id: string, enabled: boolean): void;
  setDigestInclude(key: "decisions" | "waiting" | "fyi", enabled: boolean): void;
  setMutedType(handle: string, type: string, muted: boolean): void;
  decide(itemId: string, input: DecideInput): DecideResult;
  /** Handler steering (POST /api/v1/handlers/{h}/action):
   * the verb is validated against the served handler +
   * status quick verb sets; the act records an owner
   * action and dispatches through the send ledger. */
  handlerAction(handle: string, verb: string, idempotencyKey: string): HandlerActionResult;
  /** The vocabularies the rule editor's pickers serve. */
  getRegistries(): RegistriesView;
  /** Stored rules as rule views (When / Then composed). */
  getRules(): RuleView[];
  /** POST /api/v1/rules: validated against the registries;
   * a saved rule replaces a stored rule of the same id. */
  saveRule(rule: RuleRecord): RuleSaveResult;
  /** POST /api/v1/rules/preview: a dry run over the open
   * waits — nothing is sent or decided. */
  previewRule(rule: RuleRecord): RulePreviewResult;
  /** The standing action rules the learning loop has
   * created (served with the registries in the backend). */
  getActionRules(): ActionRuleView[];
  /** POST /api/v1/vocab/status-codes: validated and
   * registered; an existing code is replaced. */
  addStatusCode(entry: StatusCodeInput): VocabResult;
  /** POST /api/v1/vocab/fields: a poster-settable field. */
  addField(entry: FieldInput): VocabResult;
  /** POST /api/v1/vocab/classes: a new wait class is
   * never a hard stop; hard-stop classes are not editable. */
  addWaitClass(entry: WaitClassInput): VocabResult;
  /** POST /api/v1/vocab/templates: saving a kind again
   * stores its next version. */
  addTemplate(entry: TemplateInput): VocabResult;
  /** POST /api/v1/vocab/kinds: a new item kind. */
  addItemKind(entry: ItemKindInput): VocabResult;
  /** One simulated dispatch/evaluator pass. The browser
   * drives it on an interval; tests drive it by hand. */
  tick(): void;
  /** Test/inspection surface: the send ledger as it stands. */
  getSends(): SendRow[];
}
