// ---------- Handler steering (api/1: handler payload) ----------

/** A served verb: the verb plus its registry label. The
 * frontend renders the label, never a local mapping. */
export interface VerbEntry {
  verb: string;
  label: string;
  primary?: boolean;
  rule_hint?: string | null;
}

export interface StatusBlockerView {
  summary: string;
  clearing_act: string | null;
  /** "hard stop" when whose is hard, else "yours". */
  whose_label: string;
}

export interface StatusTailView {
  kind: string;
  kind_label: string;
  title: string;
  /** "your tap" for owner items, "closeout" otherwise. */
  owner_label: string;
}

export interface HandlerStatusView {
  status_code: string;
  status_label: string;
  need: "owner_actionable" | "agent_clearable" | "unclassified";
  summary: string;
  /** When the status was posted, scenario-local. */
  at_label: string;
  /** Whole hours since the post (the stall measure). */
  age_hours: number;
  done: string[] | null;
  ongoing: string[] | null;
  tail: StatusTailView[] | null;
  blockers: StatusBlockerView[] | null;
  quick_verbs: VerbEntry[];
  /** The status's derived workbench line (api/1
   * build_handler's status.derived), composed from the
   * served block in the original page's words, with any
   * conflict messages verbatim. Null when the status
   * carries no refs to derive from. */
  derived: { label: string; conflicts: string[] } | null;
}

export interface OwnerActionView {
  id: string;
  verb: string;
  verb_label: string;
  at_label: string;
  note: string;
  /** "owner", or "rule <id>" for rule-applied acts. */
  actor_label: string;
  /** The act was a shadow rule's — it recorded what it
   * would do and did nothing (served on the backend's
   * owner-action entries; the original page marked it). */
  shadow: boolean;
}

export type HandlerActionResult =
  | { ok: true; action_id: string; verb: string }
  | { ok: false; error: string };
