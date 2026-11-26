// Headless pin for the ?api= HIGH finding's cure
// The published form's live base is the
// serving origin, and no injection can point the live
// adapter at another origin. Three legs:
//   A. The seam's base-url rule (sanitizeBaseUrl): an
//      absolute or protocol-relative base is refused to
//      the origin root; same-origin relative bases are
//      honoured as-is.
//   B. Behavioural: a LiveVenueAdapter built over the
//      sanitized form of a hostile base sends EVERY
//      request — including the session-carrying
//      /api/access/release POST — to same-origin relative
//      paths, and still answers its snapshot from them.
//   C. Selection: with a hostile __RUNNER_LIVE__
//      injection in place, the seam still selects the
//      live adapter (the cure refuses the base, not the
//      surface).
//
//   npx tsc src/venue/index.ts --module commonjs --target es2022 \
//     --outDir dist-live --resolveJsonModule --skipLibCheck --esModuleInterop \
//     --jsx react-jsx
//   printf '{"type":"commonjs"}' > dist-live/package.json
//   node scripts/smoke-api-base.mjs

import { parseOnly, USAGE_EXIT } from "../../../../tools/argv.mjs";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

// The unified argv guard (tools/argv.mjs): this tool
// takes no arguments — any argument is a usage refusal
// (exit 2) and --help prints the generated help, so an
// invocation can never fall through to the full job on
// a stray or mistyped flag.
const _argvOutcome = parseOnly({ name: "smoke-api-base" }, process.argv.slice(2));
if (!_argvOutcome.ok) {
  console.error(_argvOutcome.error);
  console.error(_argvOutcome.usage);
  process.exit(USAGE_EXIT);
}
if ("help" in _argvOutcome) {
  console.log(_argvOutcome.help);
  process.exit(0);
}

const require = createRequire(import.meta.url);

let passed = 0;
const ok = (name, cond) => {
  console.log(`${cond ? "PASS" : "FAIL"} ${name}`);
  if (cond) passed += 1;
  else process.exitCode = 1;
};

// C first, while the injection is fresh: the seam module
// selects its singleton at load.
globalThis.__RUNNER_LIVE__ = { baseUrl: "https://evil.example" };
const seam = require("../dist-live/index.js");
const { LiveVenueAdapter } = require("../dist-live/live-adapter.js");
ok("selection: hostile injection still selects the live adapter", seam.adapter instanceof LiveVenueAdapter);

// A. The rule's table.
const s = seam.sanitizeBaseUrl;
ok("rule: absolute https base refused", s("https://evil.example") === "");
ok("rule: absolute http base refused", s("http://127.0.0.1:9999") === "");
ok("rule: protocol-relative base refused", s("//evil.example") === "");
ok("rule: scheme base refused", s("javascript:alert(1)") === "");
ok("rule: bare relative base refused", s("api") === "");
ok("rule: origin root honoured", s("") === "");
ok("rule: same-origin path base honoured", s("/panel") === "/panel");

// B. The adapter over the sanitized hostile base.
const records = JSON.parse(
  readFileSync(new URL("./fixtures/panel-records-recordless.json", import.meta.url), "utf8"),
);
const requested = [];
const fetchFn = async (url, init) => {
  requested.push(String(url));
  const path = String(url);
  if (path.includes("/api/state/records")) return { ok: true, status: 200, json: async () => records };
  if (path.includes("/api/access/release")) return { ok: true, status: 200, json: async () => ({ action: "session-released" }) };
  if (path.includes("/api/outbox")) return { ok: true, status: 200, json: async () => ({ events: [], last_seq: 0 }) };
  return { ok: true, status: 200, json: async () => ({}) };
};
const a = new LiveVenueAdapter({ baseUrl: s("https://evil.example"), fetchFn });
await a.ready();
await a.releaseAccess("brisk-dune-34-r1000000002");
ok("behaviour: no request left the serving origin", requested.every((u) => u.startsWith("/api/") && !u.includes("evil.example")));
ok("behaviour: the release POST went to the origin's route", requested.some((u) => u === "/api/access/release"));
const snap = a.snapshot();
ok("behaviour: the adapter still answers from the legitimate base", snap.leases.length === 3);

console.log(`${passed} checks passed`);
process.exit(process.exitCode ?? 0);
