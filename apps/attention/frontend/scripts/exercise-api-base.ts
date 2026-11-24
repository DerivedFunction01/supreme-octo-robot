// Headless pin for the ?api= HIGH finding's cure
// (the runner cure b54ebb2 is the class
// standard): the published form's live base is the
// serving origin, and no injection can point the store
// off-origin. Four legs —
//   A. The seam's base-url rule (sanitizeBaseUrl): an
//      absolute, protocol-relative, scheme, or
//      bare-relative base is refused to the origin
//      root; "" and a same-origin relative path are
//      honoured.
//   B. Transport behaviour: an HttpTransport built over
//      a hostile base sends every request to the bare
//      same-origin relative path and returns payloads.
//   C. Store behaviour: a LiveAttentionStore built over
//      a hostile base loads its snapshot from relative
//      paths and answers; a write posts relative too.
//   D. The entry: integration.tsx no longer reads an
//      api parameter at all (a source pin — the entry
//      runs only in a browser, so its selection is
//      pinned where it is written).
// fetch is stubbed throughout; no socket, no server.
// Run: bun scripts/exercise-api-base.ts. Exit 1 on any
// failure.

import { readFileSync } from "node:fs";
import { LiveAttentionStore } from "../src/attention/live-store";
import { HttpTransport, sanitizeBaseUrl } from "../src/attention/transport";

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

const HOSTILE = "https://evil.example";

// ---------- A. the rule's table ----------
{
  const s = sanitizeBaseUrl;
  eq(s("https://evil.example"), "", "rule: absolute https base refused");
  eq(s("http://127.0.0.1:9999"), "", "rule: absolute http base refused");
  eq(s("//evil.example"), "", "rule: protocol-relative base refused");
  eq(s("javascript:alert(1)"), "", "rule: scheme base refused");
  eq(s("api"), "", "rule: bare relative base refused");
  eq(s(""), "", "rule: origin root honoured");
  eq(s("/panel"), "/panel", "rule: same-origin path base honoured");
}

// ---------- fetch stub ----------
const NOW = new Date().toISOString();
const byPath: Record<string, unknown> = {
  "/api/v1/glance": {
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
  "/api/v1/today": {
    presence: { mode: "active", mode_label: "Active", expires_at: null, expectation: "" },
    bands: [],
    headline_count: 3,
    decided_count: 0,
    generated_at: NOW,
  },
  "/api/v1/digest": { generated_at: NOW, window: { next_at: null }, sections: [] },
  "/api/v1/registries": { handlers: [] },
  "/api/v1/rules": { rules: [] },
  "/api/v1/programmes": { programmes: [] },
  "/api/v1/sends": { sends: [] },
  "/api/v1/presence": { ok: true },
};
const requested: string[] = [];
const realFetch = globalThis.fetch;
globalThis.fetch = (async (url: unknown) => {
  const path = String(url);
  requested.push(path);
  return {
    ok: true,
    status: 200,
    json: async () => byPath[path] ?? {},
  } as Response;
}) as typeof fetch;

// ---------- B. transport over a hostile base ----------
{
  requested.length = 0;
  const t = new HttpTransport(HOSTILE);
  const payload = (await t.request("/api/v1/glance")) as { decision_count?: number };
  eq(requested, ["/api/v1/glance"], "transport: hostile base refused — the request rode the bare relative path");
  eq(payload.decision_count, 3, "transport: the payload still answers");
  const honest = new HttpTransport("/panel");
  await honest.request("/api/v1/glance");
  eq(requested[1], "/panel/api/v1/glance", "transport: a same-origin path base is honoured");
}

// ---------- C. the store over a hostile base ----------
{
  requested.length = 0;
  const store = new LiveAttentionStore({ baseUrl: HOSTILE });
  await store.ready();
  eq(store.getGlance().count, 3, "store: snapshot answers from the legitimate base");
  check(
    requested.length > 0 && requested.every((u) => u.startsWith("/api/v1/")),
    "store: every load rode a same-origin relative path",
    requested.join(", "),
  );
  store.setPresence("away", "none");
  await new Promise((r) => setTimeout(r, 25));
  check(
    requested.includes("/api/v1/presence"),
    "store: a write posts to the relative presence path",
    requested.join(", "),
  );
}

globalThis.fetch = realFetch;

// ---------- D. the entry reads no api parameter ----------
{
  const entry = readFileSync(new URL("../src/integration.tsx", import.meta.url), "utf8");
  check(!entry.includes('params.get("api")'), "entry: integration.tsx reads no api parameter");
  check(entry.includes("new LiveAttentionStore()"), "entry: the live store is constructed with the serving origin unconditionally");
}

console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
