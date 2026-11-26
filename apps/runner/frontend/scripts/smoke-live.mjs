// Headless exercise of the live adapter over served
// panel portions — the recordless-entry pin. The fixture
// is a records portion in the specimen's exact form
// (panel state, specimen drive): three record-carrying
// entries, two with runtime: null, plus one entry in the
// backend's "no-lease" form — NO record key (a record
// torn, mid-write, or deleted between the records
// listing and the per-record load; the same session
// appears both ways because the read caught its acquire
// mid-flight). Before the cure, snapshot() threw
// "TypeError: Cannot read properties of undefined
// (reading 'deadline')" at leaseView and the frame
// rendered nothing.
//
//   npx tsc src/venue/live-adapter.ts --module commonjs --target es2022 \
//     --outDir dist-live --resolveJsonModule --skipLibCheck --esModuleInterop
//   printf '{"type":"commonjs"}' > dist-live/package.json
//   node scripts/smoke-live.mjs

import { parseOnly, USAGE_EXIT } from "../../../../tools/argv.mjs";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

// The unified argv guard (tools/argv.mjs): this tool
// takes no arguments — any argument is a usage refusal
// (exit 2) and --help prints the generated help, so an
// invocation can never fall through to the full job on
// a stray or mistyped flag.
const _argvOutcome = parseOnly({ name: "smoke-live" }, process.argv.slice(2));
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
const { LiveVenueAdapter } = require("../dist-live/live-adapter.js");

const records = JSON.parse(
  readFileSync(new URL("./fixtures/panel-records-recordless.json", import.meta.url), "utf8"),
);
const empty = {
  specs: { specs: [] },
  budget: null,
  grant: { grant: null, envelope: null },
  orphans: { orphans: [] },
  listeners: { listeners: {} },
  outbox: { events: [], last_seq: 0 },
};
const fetchFn = async (url) => {
  const path = String(url);
  const m = path.match(/\/api\/state\/(\w+)/);
  if (m) return { ok: true, status: 200, json: async () => (m[1] === "records" ? records : empty[m[1]]) };
  if (path.includes("/api/outbox")) return { ok: true, status: 200, json: async () => empty.outbox };
  return { ok: false, status: 404, json: async () => ({}) };
};

let passed = 0;
const ok = (name, cond) => {
  console.log(`${cond ? "PASS" : "FAIL"} ${name}`);
  if (cond) passed += 1;
  else process.exitCode = 1;
};

const a = new LiveVenueAdapter({ fetchFn });
await a.ready();
await new Promise((r) => setTimeout(r, 300));

let snap = null;
let threw = null;
try {
  snap = a.snapshot();
} catch (err) {
  threw = err;
}
ok("recordless: snapshot() does not throw", threw === null);
if (threw) console.log("  threw:", threw.message);
if (snap) {
  ok("recordless: the 3 record-carrying leases render", snap.leases.length === 3);
  ok(
    "recordless: brisk-dune-34-r1000000002 renders from its record entry",
    snap.leases.some((l) => l.session === "brisk-dune-34-r1000000002"),
  );
  ok("recordless: no lease is invented for the recordless entry", snap.leases.every((l) => l.deadline));
  ok("recordless: callers and events projections survive", Array.isArray(snap.callers) && Array.isArray(snap.events));
}
console.log(`${passed} checks passed`);
process.exit(process.exitCode ?? 0);
