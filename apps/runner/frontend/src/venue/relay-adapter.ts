// The relay data seam (rebuild step 3): the same
// VenueAdapter interface the mock and live adapters
// implement, over the rebuilt superapp's action channel —
// the frame NEVER calls the space's action client
// directly (the step-1 spike: a client constructed inside
// an iframe does not settle its call); it posts an action
// request to the shell, the shell executes it through its
// single client, and the result rides back over the
// workhorse:* postMessage relay (artifact/client/src/
// relay.ts's callAppAction, injected here as
// __RUNNER_RELAY__ by the frame's composition — the
// seam's established injection pattern, the live form's
// __RUNNER_LIVE__ beside it).
//
// The transport is a fetch-shaped binding under the live
// adapter, not a second projection stack: every route the
// live adapter polls or posts is one runnerApi action
// (artifact/server/src/runner/actions.ts — payload
// verbatim, the common envelope {status, payload,
// error}), so the translation is route-for-route and the
// projections, poll cadences, single-flight loads, and
// last-good-at-read-time behaviour are the live adapter's
// own, unchanged. A bridge failure arrives as a resolved
// envelope with status 0 and reads exactly like the live
// surface being down (portions fail alone, the snapshot
// serves last-good); a relay failure (the shell not
// answering) rejects and the load fails the same way.

import { LiveVenueAdapter } from "./live-adapter";

/** The bridge envelope every runnerApi action returns:
 *  the backend's HTTP status, its body verbatim as the
 *  payload, and the bridge's own error text (status 0 =
 *  unreachable, never a fabricated body). */
export interface BridgeEnvelope {
  status?: number;
  payload?: unknown;
  error?: string | null;
}

/** The frame-side relay transport, callAppAction's own
 *  signature narrowed to this app: resolves with the
 *  action's envelope, rejects only when the relay itself
 *  fails (unknown app/action at the shell, the action
 *  channel throwing, the relay timeout). */
export type RelayCall = (
  app: "runner",
  action: string,
  args?: Record<string, unknown>,
) => Promise<BridgeEnvelope>;

type RelayFetchInit = {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
  signal?: AbortSignal;
};

type RelayFetchResponse = {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
};

/** POST route → runnerApi action. The action names are
 *  the canonical VenueAdapter verb names (the lease-card
 *  unification) — the same names the adapter's methods
 *  carry, so no verb-name translation remains; the table
 *  is only the route-to-action binding. The sets are the
 *  panel's own contracts: the action takes the posted
 *  body as a record and the panel validates it, exactly
 *  as the live adapter posts it today. */
const POST_ACTIONS: Record<string, string> = {
  "/api/lease/start": "acquire",
  "/api/lease/stop": "release",
  "/api/lease/extend": "extend",
  "/api/lease/adopt": "adoptOrphan",
  "/api/lease/shorten": "shorten",
  "/api/access/release": "releaseAccess",
  "/api/grant": "startGrant",
  "/api/grant/extend": "extendGrant",
  "/api/ungrant": "ungrant",
  "/api/config/budget": "setBudgetCaps",
  "/api/server/restart": "restartServer",
};

function envelopeResponse(envelope: BridgeEnvelope): RelayFetchResponse {
  const status = typeof envelope?.status === "number" ? envelope.status : 0;
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (envelope?.payload !== null && envelope?.payload !== undefined) {
        return envelope.payload;
      }
      // No body rode the envelope (a bridge-level
      // failure): surface the bridge's error text in the
      // body shape the live adapter reads errors from.
      return envelope?.error ? { error: envelope.error } : {};
    },
  };
}

/** The live adapter's fetch seam, backed by the relay:
 *  a URL the live adapter composes (its base URL is
 *  empty in this form, so the URL is the panel route
 *  itself) becomes the route's runnerApi action call,
 *  and the action's envelope becomes the response. An
 *  unmapped route is a programming error in the adapter,
 *  thrown as one — never silently fetched. */
export function createRelayFetch(call: RelayCall) {
  return async (
    url: string,
    init?: RelayFetchInit,
  ): Promise<RelayFetchResponse> => {
    const parsed = new URL(url, "http://runner.frame");
    const path = parsed.pathname;
    const method = (init?.method ?? "GET").toUpperCase();

    let action: string;
    let args: Record<string, unknown> | undefined;
    if (method === "GET" && path === "/api/state") {
      action = "getState";
    } else if (method === "GET" && path.startsWith("/api/state/")) {
      action = "getStatePart";
      args = { part: decodeURIComponent(path.slice("/api/state/".length)) };
    } else if (method === "GET" && path === "/api/outbox") {
      action = "getLeaseOutbox";
      const after = parsed.searchParams.get("after");
      if (after !== null) args = { after: Number(after) };
    } else if (method === "POST" && POST_ACTIONS[path]) {
      action = POST_ACTIONS[path];
      args = { body: JSON.parse(init?.body ?? "{}") as Record<string, unknown> };
    } else {
      throw new Error(`relay transport: no runner action for ${method} ${path}`);
    }

    const signal = init?.signal;
    if (signal?.aborted) {
      throw new Error(`relay transport: ${action} aborted before it was sent`);
    }
    const pending = call("runner", action, args);
    if (!signal) return envelopeResponse(await pending);
    // The caller's own bound (the live adapter aborts a
    // fetch that outlives it) releases this reader; the
    // relay call itself settles or times out on the
    // shell's side and its late answer is dropped.
    const aborted = new Promise<never>((_resolve, reject) => {
      signal.addEventListener(
        "abort",
        () => reject(new Error(`relay transport: ${action} aborted`)),
        { once: true },
      );
    });
    return envelopeResponse(await Promise.race([pending, aborted]));
  };
}

/** The VenueAdapter for the published frame form: the
 *  live adapter's whole behaviour, with its HTTP fetch
 *  replaced by the shell relay. Constructed by the seam
 *  (src/venue/index.ts) when the frame's composition has
 *  injected the relay transport. */
export class RelayVenueAdapter extends LiveVenueAdapter {
  constructor(call: RelayCall) {
    super({ baseUrl: "", fetchFn: createRelayFetch(call) });
  }
}
