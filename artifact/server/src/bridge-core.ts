// The bridge core, shared by the four apps: one bridge
// attempt to the app's backend over its privileged socket
// contract, plus the retry policy that turns on how the
// attempt died. The semantics are the workbench original's
// bridge.ts, unchanged — generalized only over which
// contract, address seam, and app label a call carries
// (each app's own bridge.ts binds those three):
//
// - A timeout means the server is up but busy (no retry —
//   a second attempt doubles the load it is drowning in).
// - A connection that never reached the server earns one
//   retry for reads (the mid-restart transient).
// - Writes are never retried: a save whose answer was lost
//   may already have landed.
// - Status 0 is the transport shape (timeout / unreachable
//   / malformed), surfaced in the envelope's error string
//   with the diagnosis named — a bridge failure, distinct
//   from any server state (contract 09).
import type { Ctx, PrivilegedContract } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { readServerEnv } from "./env";

export interface BackendAddress {
  host: string;
  port: number;
}

// One envelope for every proxied call, all four apps (the
// design's common shape): the HTTP status (0 = the socket
// never got an answer), the payload verbatim, and the
// server's error string when it sent one.
export interface BridgeReply<T> {
  status: number;
  payload: T | null;
  error: string | null;
}

// The raw-bytes read: one wbRaw attempt. No retry and no
// JSON anywhere — the caller (the workbench render action)
// decides what a status means; status 0 is the socket
// failure shape and is never an empty file.
export interface RawReply {
  status: number;
  contentType: string | null;
  bodyBase64: string;
}

// The four JSON contracts share wbApi's request/response
// schemas verbatim and differ only in their contract name,
// so the binding's contract type is the shared schema pair
// under the SDK's name-generic contract type (Name widened
// to string).
type JsonContract = PrivilegedContract<
  string,
  (typeof privileged.wbApi)["request"],
  (typeof privileged.wbApi)["response"]
>;
type RawContract = typeof privileged.wbRaw;

export interface BridgeBinding {
  /** The app's JSON socket contract (wbApi / schedulerApi / …). */
  contract: JsonContract;
  /** The app's config seam: env record → backend address. */
  address: (env: Record<string, string | undefined>) => BackendAddress;
  /** The app's unreachable sentence, naming its address. */
  unreachableMessage: (address: BackendAddress) => string;
  /** Sentence stem for the timeout ("busy") diagnosis. */
  label: string;
}

interface BridgeAttempt<T> {
  reply: BridgeReply<T>;
  timedOut: boolean;
}

async function callServerOnce<T>(
  ctx: Ctx,
  binding: BridgeBinding,
  address: BackendAddress,
  path: string,
  method: "GET" | "POST",
  body?: unknown,
): Promise<BridgeAttempt<T>> {
  const res = await ctx.executePrivileged(binding.contract, {
    host: address.host,
    port: address.port,
    method,
    path,
    body: body != null ? JSON.stringify(body) : null,
  });
  const json = res.json;
  const obj = json != null && typeof json === "object" ? (json as Record<string, unknown>) : null;
  const serverError = obj && typeof obj.error === "string" ? obj.error : null;
  if (res.status === 0) {
    // A bridge timeout is not "unreachable": the server is
    // up but slow. Say which one happened so a slow server
    // is never reported as down.
    if (serverError?.startsWith("timed out")) {
      return {
        timedOut: true,
        reply: {
          status: 0,
          payload: null,
          error:
            `${binding.label} on ${address.host}:${address.port} did not answer in time — ` +
            "it is running but busy.",
        },
      };
    }
    return {
      timedOut: false,
      reply: { status: 0, payload: null, error: binding.unreachableMessage(address) },
    };
  }
  if (serverError != null) {
    return { timedOut: false, reply: { status: res.status, payload: null, error: serverError } };
  }
  return { timedOut: false, reply: { status: res.status, payload: json as T, error: null } };
}

export async function callServerWith<T>(
  ctx: Ctx,
  binding: BridgeBinding,
  path: string,
  method: "GET" | "POST" = "GET",
  body?: unknown,
): Promise<BridgeReply<T>> {
  const address = binding.address(await readServerEnv(ctx));
  const first = await callServerOnce<T>(ctx, binding, address, path, method, body);
  if (first.reply.status !== 0 || method !== "GET") return first.reply;
  // A timeout earns NO retry (the workbench original's
  // second lesson): the server is busy computing the very
  // answer that just timed out, and stacked socket
  // timeouts blow past the privileged contract's cap, so
  // the platform tears the call down mid-retry and the
  // client never settles into data or an error. Return the
  // "busy" envelope at once.
  if (first.timedOut) return first.reply;
  // One retry for reads whose first attempt never reached
  // the server: the transient case — the server
  // mid-restart, its socket not yet accepting.
  const second = await callServerOnce<T>(ctx, binding, address, path, method, body);
  return second.reply;
}

export async function callRawWith(
  ctx: Ctx,
  contract: RawContract,
  addressOf: (env: Record<string, string | undefined>) => BackendAddress,
  path: string,
): Promise<RawReply> {
  const address = addressOf(await readServerEnv(ctx));
  const res = await ctx.executePrivileged(contract, {
    host: address.host,
    port: address.port,
    method: "GET",
    path,
    body: null,
  });
  return { status: res.status, contentType: res.contentType, bodyBase64: res.bodyBase64 };
}
