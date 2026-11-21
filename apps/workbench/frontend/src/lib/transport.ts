// The workbench frame's client transport (REBUILD
// STEP 3): the channel beneath the live adapter's API
// seam in the rebuilt superapp's frame form.
//
// In the frame, the app NEVER calls the space's action
// channel directly — the step-1 spike proved a direct
// action call from inside an iframe does not settle.
// Every call rides the workhorse:* postMessage relay to
// the shell, which owns the space's single action
// client and executes the action there (the wire
// contract as artifact/client/src/relay.ts states it):
//
//   frame → shell  { type: "workhorse:action-request",
//                    id, app: "workbench", action, args? }
//   shell → frame  { type: "workhorse:action-response",
//                    id, result: { ok, value?, error? } }
//
// The action's own return value is the bridge envelope
// {status, payload, error}: the backend's HTTP status
// (0 = the bridge never got an answer), its payload
// verbatim, and its error string when it sent one. A
// bridge failure arrives as a RESOLVED envelope with
// status 0; the relay's ok:false is reserved for the
// call itself failing (unknown action, the action
// channel throwing) and rejects the channel promise.
//
// The adapter's semantics do not change with the
// channel (the W-C5 discipline): mutations land on the
// server first and local state moves only on the
// server's acceptance; a refusal surfaces the server's
// error text. This module is only the channel plus the
// route→action translation the adapter's path-shaped
// call sites need; platform's step-3 integration may
// rebind the channel to the artifact's own relay
// client — the protocol and the envelope are the
// contract, not this file.

/** The bridge envelope every workbench action returns:
 *  the backend's HTTP status (0 = unreachable), its
 *  payload verbatim, its error string when it sent one. */
export interface BridgeEnvelope {
  status: number;
  payload: unknown;
  error: string | null;
}

/** One call to a workbench action over the relay. A
 *  resolved promise carries the action's envelope
 *  (including status-0 unreachable envelopes); a
 *  rejection means the relay itself failed (no shell
 *  answered, the action channel threw). */
export type WbChannel = (
  action: string,
  args?: Record<string, unknown>,
) => Promise<BridgeEnvelope>;

const RELAY_TIMEOUT_MS = 30000;

let requestSeq = 0;

/** The relay channel over window.parent postMessage —
 *  the frame side of the workhorse:* protocol, shaped
 *  exactly as the artifact shell's relay states it. */
export function relayChannel(
  timeoutMs: number = RELAY_TIMEOUT_MS,
): WbChannel {
  return (action, args) => {
    requestSeq += 1;
    const id = `wh-workbench-${requestSeq}-${Date.now()}`;
    return new Promise<BridgeEnvelope>((resolve, reject) => {
      const timer = setTimeout(() => {
        window.removeEventListener("message", onMessage);
        reject(
          new Error(
            `shell did not answer workbench.${action} within ${timeoutMs}ms`,
          ),
        );
      }, timeoutMs);
      const onMessage = (event: MessageEvent) => {
        const data = event.data as {
          type?: string;
          id?: string;
          result?: { ok?: boolean; value?: unknown; error?: string };
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
              data.result.error ??
                `shell call to workbench.${action} failed`,
            ),
          );
        }
      };
      window.addEventListener("message", onMessage);
      window.parent.postMessage(
        {
          type: "workhorse:action-request",
          id,
          app: "workbench",
          action,
          ...(args ? { args } : {}),
        },
        "*",
      );
    });
  };
}

// ---------------------------------------------------------------------------
// Route → action translation for the adapter's POST
// paths (its one mutation path, postJson). The mapping
// is the server set's own (artifact/server/src/
// workbench/actions.ts): most verbs are {slug|id, body}
// passthroughs of the route's body; the exceptions are
// resolvePlanQuestions (its action extracts the body's
// fields under camelCase names), the two file saves
// (handled at their call sites, not through postJson),
// updateMessageBody (the body string rides as `body`),
// and updateReposRegistry ({id, patch} verbatim).
// ---------------------------------------------------------------------------

const dec = (s: string): string => {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
};

export function actionForPost(
  path: string,
  body: unknown,
): { action: string; args: Record<string, unknown> } | null {
  const b = (body ?? {}) as Record<string, unknown>;
  let m: RegExpMatchArray | null;

  if (path === "/api/messages") {
    return { action: "createMessage", args: { body: b } };
  }
  if (path === "/api/messages/cleanup") {
    return { action: "cleanupMessages", args: { body: b } };
  }
  if (path === "/api/projects/registry") {
    return {
      action: "updateReposRegistry",
      args: { id: b.id, patch: b.patch },
    };
  }
  if ((m = path.match(/^\/api\/projects\/([^/]+)\/todos$/))) {
    return { action: "todoAction", args: { slug: dec(m[1]), body: b } };
  }
  if (
    (m = path.match(/^\/api\/projects\/([^/]+)\/entries\/([^/]+)\/action$/))
  ) {
    return {
      action: "entryAction",
      args: { slug: dec(m[1]), entryId: dec(m[2]), body: b },
    };
  }
  if ((m = path.match(/^\/api\/projects\/([^/]+)\/plan\/resolve$/))) {
    return {
      action: "resolvePlanQuestions",
      args: {
        slug: dec(m[1]),
        path: b.path,
        baseSha256: b.base_sha256,
        answers: b.answers,
      },
    };
  }
  if ((m = path.match(/^\/api\/goals\/([^/]+)\/ping$/))) {
    return { action: "goalPing", args: { slug: dec(m[1]), body: b } };
  }
  if ((m = path.match(/^\/api\/goals\/([^/]+)\/status$/))) {
    return { action: "goalStatus", args: { slug: dec(m[1]), body: b } };
  }
  if ((m = path.match(/^\/api\/messages\/([^/]+)\/body$/))) {
    return {
      action: "updateMessageBody",
      args: { id: Number(dec(m[1])), body: b.body },
    };
  }
  if (
    (m = path.match(/^\/api\/messages\/([^/]+)\/(send|done|archive)$/))
  ) {
    const action =
      m[2] === "send"
        ? "sendMessage"
        : m[2] === "done"
          ? "doneMessage"
          : "archiveMessage";
    return { action, args: { id: Number(dec(m[1])) } };
  }
  return null;
}
