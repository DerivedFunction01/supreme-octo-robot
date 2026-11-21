// Typed actions over the raw-socket bridge — a THIN proxy.
// Each action forwards exactly one feed/mutation call to
// the workbench backend through the privileged wbApi
// socket contract and returns the backend's payload
// verbatim: payload schemas are looseObjects (known fields
// typed, everything else carried through untouched), the
// HTTP status rides along, and a backend `{error}` body —
// or an unreachable backend — comes back in the same
// envelope shape, never as a hang or a thrown exception.
//
// The set is the workbench original's action set re-pointed
// at the mega workrecord surface's routes (design §1: the
// action set is the mega route set, not the original's 40
// verbatim), plus the routes the mega surface added since
// (feeds document, outbox, classification, entry segments,
// goal ping/status). The message verbs ride the mega
// surface's one /api/messages/{id}/{verb} route.
//
// Split for size: the payload schemas live in ./schemas
// and the action groups by area in ./actions-core,
// ./actions-entries, ./actions-messages, and
// ./actions-code; this barrel composes them into the one
// registry object, so the module's public surface is
// unchanged.
import { codeActions } from "./actions-code";
import { coreActions } from "./actions-core";
import { entryActions } from "./actions-entries";
import { messageActions } from "./actions-messages";

export type {
  ConfigResult,
  FeedResult,
  HealthResult,
  ProjectsResult,
  RawResult,
} from "./schemas";

// ---------------------------------------------------------------------------
// Actions — one per workrecord route
// ---------------------------------------------------------------------------

export const workbenchActions = {
  ...coreActions,
  ...entryActions,
  ...messageActions,
  ...codeActions,
};
