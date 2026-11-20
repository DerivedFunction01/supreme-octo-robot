// Headless exercise of the relay transport (rebuild
// step 3): the live store riding the shell relay instead
// of HTTP. Three legs —
//   1. route mapping: every path the store calls maps
//      onto its attentionApi action, args verbatim;
//   2. envelope translation: the bridge envelope becomes
//      the seam's answer (payload on 2xx; the composed
//      refusal on an HTTP error; the bridge's diagnosis
//      on status 0);
//   3. store integration: the real LiveAttentionStore
//      over a stub RelayCall serving canned envelopes —
//      portions load, a write posts, a refused write
//      lands the AC-2 notice, a status-0 portion reads
//      down (AC-1) — plus the wire leg: relayCallAction
//      itself against a fake parent window, proving the
//      postMessage shapes the shell relay states.
// The shell relay exercised here is a faithful stub: the
// real shell needs the space runtime (its single action
// client + the privileged bridge), which the coordinator
// integrates in the artifact client. Run: bun
// scripts/exercise-relay.ts. Exit 1 on any failure.

import { LiveAttentionStore } from "../src/attention/live-store";
import {
  RelayTransport,
  relayCallAction,
  type BridgeEnvelope,
  type RelayCall,
} from "../src/attention/transport";

let failures = 0;
function check(ok: boolean, label: string, detail = ""): void {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
}
function eq<T>(actual: T, expected: T, label: string): void {
  check(
    JSON.stringify(actual) === JSON.stringify(expected),
    label,
    `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );
}

const okEnvelope = (payload: unknown, status = 200): BridgeEnvelope => ({
  status,
  payload,
  error: null,
});

// ---------- 1. route mapping ----------
{
  const calls: { action: string; args?: Record<string, unknown> }[] = [];
  const stub: RelayCall = async (action, args) => {
    calls.push({ action, args });
    return okEnvelope({ ok: true });
  };
  const t = new RelayTransport(stub);
  const post = (body: unknown): RequestInit => ({
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const cases: [string, RequestInit | undefined, string, unknown][] = [
    ["/api/v1/glance", undefined, "getGlance", undefined],
    ["/api/v1/today", undefined, "getToday", undefined],
    ["/api/v1/digest", undefined, "getDigest", undefined],
    ["/api/v1/registries", undefined, "getRegistries", undefined],
    ["/api/v1/rules", undefined, "getRules", undefined],
    ["/api/v1/programmes", undefined, "getProgrammes", undefined],
    ["/api/v1/sends", undefined, "getSends", undefined],
    ["/api/v1/handlers/%40lane%20one", undefined, "getHandler", { handle: "@lane one" }],
    ["/api/v1/agent/waits/w-9", undefined, "getWait", { waitId: "w-9" }],
    ["/api/v1/presence", post({ mode: "away" }), "postPresence", { body: { mode: "away" } }],
    ["/api/v1/digest/prefs", post({ window_time: "morning" }), "postDigestPrefs", { body: { window_time: "morning" } }],
    ["/api/v1/items/it-1/action", post({ verb: "approve" }), "itemAction", { itemId: "it-1", body: { verb: "approve" } }],
    ["/api/v1/handlers/%40a/action", post({ verb: "nudge" }), "handlerAction", { handle: "@a", body: { verb: "nudge" } }],
    ["/api/v1/handlers/%40a/mute", post({ kind: "fyi" }), "muteHandler", { handle: "@a", kind: "fyi" }],
    ["/api/v1/handlers/%40a/unmute", post({ kind: "fyi" }), "unmuteHandler", { handle: "@a", kind: "fyi" }],
    ["/api/v1/rules", post({ when: {} }), "addRule", { body: { when: {} } }],
    ["/api/v1/rules/preview", post({ rule: { when: {} } }), "previewRule", { rule: { when: {} } }],
    ["/api/v1/vocab/status-codes", post({ code: "x" }), "addVocabStatusCode", { body: { code: "x" } }],
    ["/api/v1/vocab/fields", post({ key: "x" }), "addVocabField", { body: { key: "x" } }],
    ["/api/v1/vocab/classes", post({ key: "x" }), "addVocabClass", { body: { key: "x" } }],
    ["/api/v1/vocab/templates", post({ key: "x" }), "addVocabTemplate", { body: { key: "x" } }],
    ["/api/v1/vocab/kinds", post({ key: "x" }), "addVocabKind", { body: { key: "x" } }],
  ];
  for (const [path, init, action, args] of cases) {
    const before = calls.length;
    const out = await t.request(path, init);
    eq(out, { ok: true }, `route ${path} returns the payload`);
    eq(calls.length, before + 1, `route ${path} made exactly one relay call`);
    eq(calls[before]?.action, action, `route ${path} -> ${action}`);
    eq(calls[before]?.args, args, `route ${path} args`);
  }
  eq(calls.length, 22, "all 22 attentionApi actions exercised");
  let threw = "";
  try {
    await t.request("/api/v1/agent/status", post({}));
  } catch (err) {
    threw = err instanceof Error ? err.message : String(err);
  }
  check(threw.includes("no relay action for POST /api/v1/agent/status"), "agent-tier path has no action and names itself", threw);
}

// ---------- 2. envelope translation ----------
{
  const withEnvelope =
    (env: BridgeEnvelope): RelayCall =>
    async () =>
      env;
  const created = new RelayTransport(withEnvelope(okEnvelope({ id: "r-1" }, 201)));
  eq(await created.request("/api/v1/rules", { method: "POST", body: "{}" }), { id: "r-1" }, "201 serves the payload");

  const down = new RelayTransport(
    withEnvelope({ status: 0, payload: null, error: "Attention server on 127.0.0.1:8797 did not answer in time — it is running but busy." }),
  );
  let msg = "";
  try {
    await down.request("/api/v1/glance");
  } catch (err) {
    msg = err instanceof Error ? err.message : String(err);
  }
  check(msg.includes("did not answer in time"), "status 0 throws the bridge's diagnosis verbatim", msg);

  const refused = new RelayTransport(
    withEnvelope({
      status: 422,
      payload: {
        detail: "Rule failed validation.",
        field_errors: [{ field: "when", message: "is required" }],
      },
      error: null,
    }),
  );
  msg = "";
  try {
    await refused.request("/api/v1/rules", { method: "POST", body: "{}" });
  } catch (err) {
    msg = err instanceof Error ? err.message : String(err);
  }
  eq(msg, "Rule failed validation. when is required", "422 composes detail + field errors as the HTTP path does");

  const stripped = new RelayTransport(
    withEnvelope({ status: 500, payload: null, error: "bridge exploded" }),
  );
  msg = "";
  try {
    await stripped.request("/api/v1/today");
  } catch (err) {
    msg = err instanceof Error ? err.message : String(err);
  }
  eq(msg, "bridge exploded", "an envelope error sentence throws verbatim");
}

// ---------- 3. store integration over a stub relay ----------
const NOW = new Date().toISOString();
const canned: Record<string, unknown> = {
  getGlance: {
    presence: { mode: "active", mode_label: "Active", expires_at: null, expectation: "" },
    clock: { now: NOW, next_window_at: null },
    next_due: null,
    decision_count: 3,
    handler_dots: [],
    held_count: 0,
    breakthrough_count: 0,
    breakthrough_items: [],
    down_sources: [],
  },
  getToday: {
    presence: { mode: "active", mode_label: "Active", expires_at: null, expectation: "" },
    bands: [],
    headline_count: 3,
    decided_count: 0,
    generated_at: NOW,
  },
  getDigest: { generated_at: NOW, window: { next_at: null }, sections: [] },
  getRegistries: { handlers: [] },
  getRules: { rules: [] },
  getProgrammes: { programmes: [] },
  getSends: { sends: [] },
};

{
  const seen: { action: string; args?: Record<string, unknown> }[] = [];
  const stub: RelayCall = async (action, args) => {
    seen.push({ action, args });
    if (action === "postDigestPrefs") {
      return {
        status: 422,
        payload: { detail: "Unknown digest window.", field_errors: [] },
        error: null,
      };
    }
    return okEnvelope(canned[action] ?? {});
  };
  const store = new LiveAttentionStore({ transport: new RelayTransport(stub) });
  await store.ready();
  eq(store.getGlance().count, 3, "glance portion loaded through the relay");
  eq(store.getSurfaceHealth().glance.state, "ok", "glance portion healthy over the relay");
  check(
    seen.some((c) => c.action === "getToday") && seen.some((c) => c.action === "getSends"),
    "fast and slow portions both rode the relay",
  );

  store.setPresence("away", "none");
  await new Promise((r) => setTimeout(r, 25));
  const presence = seen.find((c) => c.action === "postPresence");
  check(!!presence, "presence write rode the relay as postPresence");
  eq((presence?.args?.body as { mode?: string })?.mode, "away", "presence body verbatim");

  store.setDigestWindow("morning", true);
  await new Promise((r) => setTimeout(r, 25));
  check(
    (store.getWriteNotice() ?? "").includes("That digest window change was not saved — the server refused it: Unknown digest window."),
    "a refused write over the relay lands the AC-2 notice",
    store.getWriteNotice() ?? "no notice",
  );
}

{
  const stub: RelayCall = async (action) =>
    action === "getGlance"
      ? { status: 0, payload: null, error: "Attention server unreachable." }
      : okEnvelope(canned[action] ?? {});
  const store = new LiveAttentionStore({ transport: new RelayTransport(stub) });
  await store.ready();
  eq(store.getSurfaceHealth().glance.state, "down", "status-0 glance reads down (AC-1 over the relay)");
  eq(store.getSurfaceHealth().today.state, "ok", "other portions unaffected");
}

// ---------- 4. the wire leg: relayCallAction itself ----------
{
  const listeners = new Set<(ev: MessageEvent) => void>();
  const posted: unknown[] = [];
  const fakeWindow = {
    addEventListener: (_type: string, fn: (ev: MessageEvent) => void) => listeners.add(fn),
    removeEventListener: (_type: string, fn: (ev: MessageEvent) => void) => listeners.delete(fn),
    parent: {
      postMessage: (data: unknown) => {
        posted.push(data);
        const req = data as { id: string };
        queueMicrotask(() => {
          const response = {
            type: "workhorse:action-response",
            id: req.id,
            result: { ok: true, value: { status: 200, payload: { pong: true }, error: null } },
          };
          listeners.forEach((fn) => fn({ data: response } as MessageEvent));
        });
      },
    },
  };
  const realWindow = (globalThis as { window?: unknown }).window;
  (globalThis as { window?: unknown }).window = fakeWindow;
  try {
    const envelope = await relayCallAction("getGlance");
    eq(envelope.payload, { pong: true }, "wire leg settles with the shell's envelope");
    const req = posted[0] as { type: string; app: string; action: string; id: string };
    eq(req.type, "workhorse:action-request", "wire request type");
    eq(req.app, "attention", "wire request app");
    eq(req.action, "getGlance", "wire request action");
    check(typeof req.id === "string" && req.id.length > 0, "wire request carries a correlation id");
  } finally {
    (globalThis as { window?: unknown }).window = realWindow;
  }
}

console.log(failures === 0 ? "\nALL PASS" : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
