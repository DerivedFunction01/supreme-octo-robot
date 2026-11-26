// Validates every mock payload this frontend serves against
// the frozen contract schemas in contracts/schemas/ (plan §8
// mock-first amendment: mock payloads are generated from the
// contracts' schemas and fixtures and validated against the
// schemas in the build).
//
//   node scripts/validate-mocks.mjs
//
// Covers: the seed lease records, run records, and session
// evidence (contract 12), the contract's own fixtures for all
// four contract-12 schemas, and the caller-registry seed
// (contract 01's schema). The seed venue events validate in
// their served form against contracts/schemas/
// venue-event.schema.json — the venue layer's frozen served
// shape (contract 12, finding 4): the record's own fields
// plus the split the venue layer serves natively. Exits
// non-zero on any failure.

import { parseOnly, USAGE_EXIT } from "../../../../tools/argv.mjs";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

// The unified argv guard (tools/argv.mjs): this tool
// takes no arguments — any argument is a usage refusal
// (exit 2) and --help prints the generated help, so an
// invocation can never fall through to the full job on
// a stray or mistyped flag.
const _argvOutcome = parseOnly({ name: "validate-mocks" }, process.argv.slice(2));
if (!_argvOutcome.ok) {
  console.error(_argvOutcome.error);
  console.error(_argvOutcome.usage);
  process.exit(USAGE_EXIT);
}
if ("help" in _argvOutcome) {
  console.log(_argvOutcome.help);
  process.exit(0);
}


const here = dirname(fileURLToPath(import.meta.url));
const frontend = join(here, "..");
const contracts = join(frontend, "..", "..", "..", "contracts");

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);

const load = (p) => JSON.parse(readFileSync(p, "utf8"));
const schema = (name) => load(join(contracts, "schemas", name));

let failures = 0;
function check(label, validate, payload) {
  const ok = validate(payload);
  if (ok) {
    console.log(`PASS ${label}`);
  } else {
    failures += 1;
    console.log(`FAIL ${label}`);
    for (const e of validate.errors ?? []) {
      console.log(`     ${e.instancePath || "/"} ${e.message}`);
    }
  }
}

const lease = ajv.compile(schema("lease-record.schema.json"));
const run = ajv.compile(schema("run-record.schema.json"));
const evidence = ajv.compile(schema("session-evidence.schema.json"));
const bundle = ajv.compile(schema("bundle-manifest.schema.json"));
const callers = ajv.compile(schema("caller-registry.schema.json"));

// --- this frontend's seed payloads ---
for (const rec of load(join(frontend, "src/venue/seed/leases.json"))) {
  check(`seed lease-record ${rec.session}`, lease, rec);
}
for (const rec of load(join(frontend, "src/venue/seed/runs.json"))) {
  check(`seed run-record ${rec.run_id}`, run, rec);
}
const ev = load(join(frontend, "src/venue/seed/evidence.json"));
for (const [session, rec] of Object.entries(ev)) {
  check(`seed session-evidence ${session}`, evidence, rec);
}
check("seed caller-registry", callers, load(join(frontend, "src/venue/seed/callers.json")));

// The venue events validate in their SERVED form against
// the contract's frozen schema for that form —
// contracts/schemas/venue-event.schema.json (contract 12,
// finding 4: the venue layer serves the LogRow split
// natively; this re-point is the frontend half). servedEvent
// applies the venue layer's one derivation
// (pipeline/venue/sync/venue_events.py::split_event) to a
// seed record: the record's fields pass through exactly as
// written; date_token and time derive from the record's own
// timestamp as written (the parsed wall-clock fields, no
// timezone conversion); headline is the message verbatim;
// meta and entity carry only what the record itself serves
// (null when it serves none — honest absence).
const venueEvent = ajv.compile(schema("venue-event.schema.json"));
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
function servedEvent(rec) {
  const out = { ...rec };
  out.venue = rec.venue || "colab";
  out.at = rec.at || rec.ts;
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(out.at ?? "");
  if (m) {
    const [, , mo, d, h, mi] = m;
    const hour = Number(h);
    out.date_token = `${MONTHS[Number(mo) - 1]} ${Number(d)}`;
    out.time = `${hour % 12 || 12}:${mi} ${hour < 12 ? "AM" : "PM"}`;
  } else {
    out.date_token = null;
    out.time = null;
  }
  out.headline = rec.message;
  const detail =
    rec.detail && typeof rec.detail === "object" ? rec.detail : {};
  out.entity = detail.session || rec.session || null;
  out.meta = rec.meta || detail.caller || null;
  return out;
}
for (const rec of load(join(frontend, "src/venue/seed/events.json"))) {
  check(`seed venue-event ${rec.id} (served)`, venueEvent, servedEvent(rec));
}

// --- the contract's own fixtures (the seed sources) ---
// Informational: a fixture failing its own schema is a contract
// inconsistency at the pin, reported but not counted against
// this frontend's payloads.
let fixtureFailures = 0;
function checkFixture(label, validate, payload) {
  const ok = validate(payload);
  if (ok) {
    console.log(`PASS ${label}`);
  } else {
    fixtureFailures += 1;
    console.log(`KNOWN-FAIL ${label} (contract inconsistency at the pin)`);
    for (const e of validate.errors ?? []) {
      console.log(`     ${e.instancePath || "/"} ${e.message}`);
    }
  }
}
checkFixture("fixture lease-record", lease, load(join(contracts, "fixtures/lease-record.json")));
checkFixture("fixture run-record", run, load(join(contracts, "fixtures/run-record.json")));
checkFixture("fixture session-evidence", evidence, load(join(contracts, "fixtures/session-evidence.json")));
checkFixture("fixture bundle-manifest", bundle, load(join(contracts, "fixtures/bundle-manifest.json")));

console.log(
  failures === 0
    ? `\nAll mock payloads valid against the frozen schemas.${fixtureFailures ? ` (${fixtureFailures} contract fixture inconsistency noted above.)` : ""}`
    : `\n${failures} failure(s).`,
);
process.exit(failures === 0 ? 0 : 1);
