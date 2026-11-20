// The scheduler frame's relay transport (rebuild step 3):
// the channel beneath the live adapter when the app runs
// as a frame of the workhorse shell. The wire contract's
// canonical statement is artifact/client/src/relay.ts —
// frames route via workhorse:* postMessage to the shell,
// which owns the space's action client; a frame never
// calls the action channel directly (the direct call does
// not settle from inside an iframe). This module is the
// scheduler frame's client of that contract, shaped to
// the live adapter's existing seam: it implements the
// adapter's FetchLike, mapping each /api/v1 request onto
// the schedulerApi action set (the seven actions in
// artifact/server/src/scheduler/actions.ts), so no view
// and no adapter state changes — the D-6 three-state
// reachability and the mount-earlier behaviour ride on
// top untouched.
//
// Envelope discipline (the server set's own): an action
// resolves with the backend's envelope {status, payload,
// error} untouched. A bridge failure arrives as status 0
// — this transport surfaces it as a thrown error, the
// same shape a refused fetch gives the adapter standalone,
// so a dead backend reads as a failed attempt in both
// channels. The relay's own failure (no answer within
// the timeout, an unknown app/action on the shell side)
// likewise rejects.

import type { FetchLike } from "./live-adapter";

const RELAY_TIMEOUT_MS = 30_000;

interface BridgeEnvelope {
  status: number;
  payload: unknown;
  error: string | null;
}

let requestSeq = 0;

/** One action round trip through the shell relay. */
export function callSchedulerAction(
  action: string,
  args?: Record<string, unknown>,
): Promise<BridgeEnvelope> {
  requestSeq += 1;
  const id = `wh-scheduler-${requestSeq}-${Date.now()}`;
  return new Promise<BridgeEnvelope>((resolve, reject) => {
    const timer = setTimeout(() => {
      window.removeEventListener("message", onMessage);
      reject(
        new Error(
          `shell did not answer scheduler.${action} within ${RELAY_TIMEOUT_MS}ms`,
        ),
      );
    }, RELAY_TIMEOUT_MS);
    const onMessage = (event: MessageEvent) => {
      const data = event.data as {
        type?: unknown;
        id?: unknown;
        result?: { ok?: unknown; value?: unknown; error?: unknown };
      } | null;
      if (
        !data ||
        data.type !== "workhorse:action-response" ||
        data.id !== id ||
        !data.result
      ) {
        return;
      }
      window.removeEventListener("message", onMessage);
      clearTimeout(timer);
      if (data.result.ok) {
        resolve(data.result.value as BridgeEnvelope);
      } else {
        reject(
          new Error(
            typeof data.result.error === "string"
              ? data.result.error
              : `shell call to scheduler.${action} failed`,
          ),
        );
      }
    };
    window.addEventListener("message", onMessage);
    window.parent.postMessage(
      {
        type: "workhorse:action-request",
        id,
        app: "scheduler",
        action,
        ...(args ? { args } : {}),
      },
      "*",
    );
  });
}

function limitArg(raw: string | null): Record<string, unknown> {
  if (raw === null) return {};
  const limit = Number(raw);
  return Number.isFinite(limit) && limit > 0 ? { limit } : {};
}

/** The adapter's fetch seam over the relay: each /api/v1
 *  path maps to its schedulerApi action; the envelope's
 *  payload becomes the response body, its status the
 *  response status. */
export const relayFetch: FetchLike = async (url, init) => {
  const parsed = new URL(url, "http://workhorse.frame");
  const path = parsed.pathname;
  const method = (init?.method ?? "GET").toUpperCase();
  let envelope: BridgeEnvelope;

  const jobMatch = path.match(/^\/api\/v1\/jobs\/([^/]+)$/);
  const configMatch = path.match(/^\/api\/v1\/jobs\/([^/]+)\/config$/);

  if (method === "GET" && path === "/api/v1/overview") {
    envelope = await callSchedulerAction("getOverview");
  } else if (method === "GET" && path === "/api/v1/jobs") {
    envelope = await callSchedulerAction("getJobs");
  } else if (method === "POST" && configMatch) {
    const body = JSON.parse(init?.body ?? "{}") as {
      version: number;
      values: Record<string, unknown>;
      caller?: string;
    };
    envelope = await callSchedulerAction("saveJobConfig", {
      jobId: decodeURIComponent(configMatch[1]!),
      version: body.version,
      values: body.values,
      ...(body.caller ? { caller: body.caller } : {}),
    });
  } else if (method === "GET" && jobMatch) {
    envelope = await callSchedulerAction("getJob", {
      jobId: decodeURIComponent(jobMatch[1]!),
    });
  } else if (method === "GET" && path === "/api/v1/pings") {
    envelope = await callSchedulerAction("getPings");
  } else if (method === "GET" && path === "/api/v1/pings/recent") {
    envelope = await callSchedulerAction(
      "getPingsRecent",
      limitArg(parsed.searchParams.get("limit")),
    );
  } else if (method === "GET" && path === "/api/v1/ledger") {
    envelope = await callSchedulerAction(
      "getLedger",
      limitArg(parsed.searchParams.get("limit")),
    );
  } else {
    throw new Error(`relay transport: no action for ${method} ${path}`);
  }

  if (envelope.status === 0) {
    throw new Error(
      envelope.error ?? "scheduler backend unreachable through the shell relay",
    );
  }
  return {
    ok: envelope.status >= 200 && envelope.status < 300,
    status: envelope.status,
    json: async () => envelope.payload,
  };
};
