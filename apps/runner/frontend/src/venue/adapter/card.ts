// The served lease card (lease-card unification, Step 1):
// the shape the venue backend assembles per lease in
// its state build (pipeline/venue/sync/lease/state/
// card.py) and rides on the records portion's entries —
// identity, labels, deadline presentation, and the
// capability set derived server-side, so every frontend
// renders the same card and derives nothing. This
// module is the panel's side of that contract: the
// served shape, and the one mapping from it to the
// LeaseView both adapters serve (live from the fetched
// card, the mock from its card fixture — one API, one
// mapping).

import type {
  LeaseCapabilities,
  LeaseCardVerb,
  LeaseDiagnosticsView,
  LeaseView,
  ListenerView,
  Tone,
} from "../types";

/** The card's diagnostics block as served: the
 *  heartbeat / pulse / burn labels and the sync claim,
 *  or null when nothing is known. The listeners census
 *  is NOT card content — it rides its own portion and
 *  the adapters compose it in (leaseDiagnosticsFromCard). */
export interface ServedCardDiagnostics {
  heartbeat_label: string;
  pulse_label: string | null;
  burn_label: string;
  sync_claim: { caller: string; until_label: string } | null;
}

/** One lease's card exactly as the backend serves it
 *  (snake_case, card.py's lease_card). */
export interface ServedLeaseCard {
  session: string;
  display_name: string;
  venue: string;
  venue_label: string;
  target: string | null;
  shape: string;
  shape_label: string;
  shape_descriptor: string;
  caller: string | null;
  account: string | null;
  state: "running" | "renewal-due";
  state_label: string;
  state_tone: Tone;
  action: string | null;
  standing: boolean;
  acquired_at: string;
  deadline: string;
  deadline_label: string;
  ends_label: string;
  expired: boolean;
  remaining_ms: number;
  remaining_label: string;
  rate_cu_per_hour: number | null;
  rate_label: string;
  reserved_cu: number;
  envelope_id: string | null;
  diagnostics: ServedCardDiagnostics | null;
  capabilities: LeaseCapabilities;
}

const CARD_VERBS: LeaseCardVerb[] = [
  "extend",
  "shorten",
  "release",
  "adopt",
  "exec",
];

/** The served capability set in the view's form: the
 *  five canonical verbs, each carried verbatim —
 *  applicability is backend work; the view renders the
 *  set (Step 4 wires the disabling). */
export function capabilitiesFromServed(
  card: ServedLeaseCard,
): LeaseCapabilities {
  const out = {} as LeaseCapabilities;
  for (const verb of CARD_VERBS) {
    const cap = card.capabilities[verb];
    out[verb] = { applicable: cap.applicable, reason: cap.reason };
  }
  return out;
}

/** The lease diagnostics the card family renders: the
 *  card's served diagnostics labels composed with the
 *  listeners census the portions carry (the census is
 *  portion data, not card content — card.py's split).
 *  Null when neither source knows anything (honest
 *  absence). A card with no diagnostics block still
 *  renders its census: heartbeat "unknown", the burn
 *  the card's own rate label, the pulse the census's
 *  error where the card serves none. */
export function leaseDiagnosticsFromCard(
  card: ServedLeaseCard,
  census: {
    present: boolean;
    listeners: ListenerView[];
    error: string | null;
  },
): LeaseDiagnosticsView | null {
  const d = card.diagnostics;
  if (!d && !census.present) return null;
  return {
    listeners: census.listeners,
    heartbeatLabel: d?.heartbeat_label ?? "unknown",
    pulseLabel: d?.pulse_label ?? census.error,
    burnLabel: d?.burn_label ?? card.rate_label,
    syncClaim: d?.sync_claim
      ? { caller: d.sync_claim.caller, untilLabel: d.sync_claim.until_label }
      : null,
  };
}

/** The one card → LeaseView mapping: every field the
 *  lease card family renders comes off the served
 *  card; the only adapter-composed field is
 *  diagnostics, whose census half rides its own
 *  portion. */
export function leaseViewFromCard(
  card: ServedLeaseCard,
  diagnostics: LeaseDiagnosticsView | null,
): LeaseView {
  return {
    session: card.session,
    displayName: card.display_name,
    venue: card.venue,
    venueLabel: card.venue_label,
    target: card.target,
    shape: card.shape,
    shapeLabel: card.shape_label,
    shapeDescriptor: card.shape_descriptor,
    caller: card.caller,
    account: card.account,
    state: card.state,
    stateLabel: card.state_label,
    stateTone: card.state_tone,
    action: card.action,
    standing: card.standing,
    acquiredAt: card.acquired_at,
    deadline: card.deadline,
    deadlineLabel: card.deadline_label,
    endsLabel: card.ends_label,
    remainingLabel: card.remaining_label,
    remainingMs: card.remaining_ms,
    expired: card.expired,
    rateCuPerHour: card.rate_cu_per_hour,
    rateLabel: card.rate_label,
    reservedCu: card.reserved_cu,
    envelopeId: card.envelope_id ?? undefined,
    capabilities: capabilitiesFromServed(card),
    diagnostics,
  };
}
