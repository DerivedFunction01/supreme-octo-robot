// The live store's channel (rebuild step 3). Every
// backend call the store makes rides one request(path,
// init) — the shape fetch() takes — so the store's logic
// is channel-blind and both channels answer identically:
// the payload on a 2xx; a thrown Error naming the failure
// otherwise (the problem document's detail + field errors
// on an HTTP error status; the failure's own words when
// the backend never answered).
//
// Two channels exist:
//
//   HttpTransport — fetch against the backend origin.
//     The standalone form and the current shell embed.
//
//   RelayTransport — the rebuild's frame form. The path
//     maps onto one of the attentionApi actions (the set
//     artifact/server/src/attention/actions.ts defines —
//     the app's reads AND writes; the agent tier stays
//     excluded, its one read in the set is the wait
//     detail) and rides the workhorse:* postMessage relay
//     to the shell, which executes it through the space's
//     single action client and posts the result back. A
//     frame never calls the action channel directly —
//     the SDK action client constructed inside an iframe
//     does not settle its call (the step-1 spike ruling).
//     Wire contract: artifact/client/src/relay.ts.

interface Problem {
  title?: string;
  detail?: string;
  field_errors?: { field: string; message: string }[];
}

const REQUEST_TIMEOUT_MS = 30_000;

/** The refusal sentence both channels throw on an HTTP
 * error status — composed from the problem document
 * exactly as the store's original fetch path composed
 * it, so a refusal reads the same on either channel. */
function problemMessage(status: number, data: unknown): string {
  const problem = (data ?? {}) as Problem;
  const fields = (problem.field_errors ?? [])
    .map((e) => `${e.field} ${e.message}`)
    .join("; ");
  const message = problem.detail ?? `request failed (${status})`;
  return fields ? `${message} ${fields}` : message;
}

export interface AttentionTransport {
  request(path: string, init?: RequestInit): Promise<unknown>;
}

/** The live base's one rule (the ?api= HIGH finding's
 * cure, 2026-11-16 — the runner cure b54ebb2 is the
 * class standard): the live base is the serving origin,
 * so the only bases honoured are "" (the origin root)
 * and a same-origin relative path ("/...", never
 * "//..."). An absolute, protocol-relative, scheme, or
 * bare-relative base is refused to "" — no injection,
 * from a query parameter or anywhere else, can point
 * the store off-origin. The cure refuses the base, not
 * the surface. */
export function sanitizeBaseUrl(base: string): string {
  if (base === "") return "";
  if (base.startsWith("/") && !base.startsWith("//")) return base;
  return "";
}

// ---------------------------------------------------------------
// HTTP channel
// ---------------------------------------------------------------

export class HttpTransport implements AttentionTransport {
  private baseUrl: string;

  constructor(baseUrl = "") {
    this.baseUrl = sanitizeBaseUrl(baseUrl).replace(/\/$/, "");
  }

  async request(path: string, init?: RequestInit): Promise<unknown> {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, { ...init, signal: ctl.signal });
      const data = (await res.json().catch(() => null)) as unknown;
      if (!res.ok) throw new Error(problemMessage(res.status, data));
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
}

// ---------------------------------------------------------------
// Relay channel
// ---------------------------------------------------------------

/** The attention action envelope (the bridge's common
 * form): the backend's HTTP status, its payload verbatim,
 * and the bridge's own diagnosis when the backend never
 * answered (status 0) or its error sentence when it sent
 * one (the payload is null then). */
export interface BridgeEnvelope {
  status: number;
  payload: unknown;
  error: string | null;
}

export type RelayCall = (
  action: string,
  args?: Record<string, unknown>,
) => Promise<BridgeEnvelope>;

interface RelayResult {
  ok: boolean;
  value?: unknown;
  error?: string;
}

let requestSeq = 0;

/** The frame side of the workhorse:* relay, in the wire
 * shapes artifact/client/src/relay.ts states: post an
 * action-request to the parent (the shell), settle with
 * the matching action-response's envelope; the relay's
 * own failure (unknown app/action, the channel throwing,
 * no answer in time) rejects. */
export function relayCallAction(
  action: string,
  args?: Record<string, unknown>,
): Promise<BridgeEnvelope> {
  requestSeq += 1;
  const id = `wh-attention-${requestSeq}-${Date.now()}`;
  return new Promise<BridgeEnvelope>((resolve, reject) => {
    const timer = setTimeout(() => {
      window.removeEventListener("message", onMessage);
      reject(new Error(`shell did not answer attention.${action} within ${REQUEST_TIMEOUT_MS}ms`));
    }, REQUEST_TIMEOUT_MS);
    const onMessage = (event: MessageEvent) => {
      const data = event.data as { type?: string; id?: string; result?: RelayResult } | null;
      if (!data || data.type !== "workhorse:action-response" || data.id !== id || !data.result) {
        return;
      }
      window.removeEventListener("message", onMessage);
      clearTimeout(timer);
      if (data.result.ok) {
        resolve(data.result.value as BridgeEnvelope);
      } else {
        reject(new Error(data.result.error ?? `shell call to attention.${action} failed`));
      }
    };
    window.addEventListener("message", onMessage);
    window.parent.postMessage(
      {
        type: "workhorse:action-request",
        id,
        app: "attention",
        action,
        ...(args ? { args } : {}),
      },
      "*",
    );
  });
}

interface Route {
  action: string;
  args?: Record<string, unknown>;
}

const READ_ACTIONS: Record<string, string> = {
  glance: "getGlance",
  today: "getToday",
  digest: "getDigest",
  registries: "getRegistries",
  rules: "getRules",
  programmes: "getProgrammes",
  sends: "getSends",
};

const VOCAB_ACTIONS: Record<string, string> = {
  "status-codes": "addVocabStatusCode",
  fields: "addVocabField",
  classes: "addVocabClass",
  templates: "addVocabTemplate",
  kinds: "addVocabKind",
};

/** Map one store path onto its attentionApi action. The
 * store's paths are the contract of record (the backend
 * routes); a path with no action in the set is a
 * programming error and names itself. */
function routeFor(path: string, method: string, body: Record<string, unknown> | undefined): Route {
  const seg = path.replace(/^\/api\/v1\//, "").split("/").map(decodeURIComponent);
  if (method === "GET") {
    if (seg.length === 1 && READ_ACTIONS[seg[0]]) return { action: READ_ACTIONS[seg[0]] };
    if (seg.length === 2 && seg[0] === "handlers") return { action: "getHandler", args: { handle: seg[1] } };
    if (seg.length === 3 && seg[0] === "agent" && seg[1] === "waits") {
      return { action: "getWait", args: { waitId: seg[2] } };
    }
  }
  if (method === "POST") {
    const withBody = (action: string): Route => ({ action, args: { body: body ?? {} } });
    if (seg.length === 1 && seg[0] === "presence") return withBody("postPresence");
    if (seg.length === 2 && seg[0] === "digest" && seg[1] === "prefs") return withBody("postDigestPrefs");
    if (seg.length === 3 && seg[0] === "items" && seg[2] === "action") {
      return { action: "itemAction", args: { itemId: seg[1], body: body ?? {} } };
    }
    if (seg.length === 3 && seg[0] === "handlers" && seg[2] === "action") {
      return { action: "handlerAction", args: { handle: seg[1], body: body ?? {} } };
    }
    if (seg.length === 3 && seg[0] === "handlers" && (seg[2] === "mute" || seg[2] === "unmute")) {
      return {
        action: seg[2] === "mute" ? "muteHandler" : "unmuteHandler",
        args: { handle: seg[1], kind: String(body?.kind ?? "") },
      };
    }
    if (seg.length === 1 && seg[0] === "rules") return withBody("addRule");
    if (seg.length === 2 && seg[0] === "rules" && seg[1] === "preview") {
      return { action: "previewRule", args: { rule: (body?.rule ?? {}) as Record<string, unknown> } };
    }
    if (seg.length === 2 && seg[0] === "vocab" && VOCAB_ACTIONS[seg[1]]) {
      return withBody(VOCAB_ACTIONS[seg[1]]);
    }
  }
  throw new Error(`no relay action for ${method} ${path}`);
}

export class RelayTransport implements AttentionTransport {
  private call: RelayCall;

  constructor(call: RelayCall = relayCallAction) {
    this.call = call;
  }

  async request(path: string, init?: RequestInit): Promise<unknown> {
    const method = (init?.method ?? "GET").toUpperCase();
    const body = (
      typeof init?.body === "string" ? JSON.parse(init.body) : undefined
    ) as Record<string, unknown> | undefined;
    const route = routeFor(path, method, body);
    const envelope = await this.call(route.action, route.args);
    if (envelope.status >= 200 && envelope.status < 300) return envelope.payload;
    if (envelope.status === 0) {
      throw new Error(envelope.error ?? "Attention server unreachable.");
    }
    // An HTTP error status: the bridge carries the problem
    // document in the payload (its error member is set
    // only when the body carried an error sentence of its
    // own, the payload null then) — either way the thrown
    // sentence is the one the HTTP channel composes.
    if (envelope.error) throw new Error(envelope.error);
    throw new Error(problemMessage(envelope.status, envelope.payload));
  }
}
