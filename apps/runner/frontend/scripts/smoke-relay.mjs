// Headless exercise of the relay adapter (rebuild step
// 3): the transport behind the venue seam, proven in two
// legs. Not a unit suite — a lane rig check that the
// transport the hand-back claims genuinely carries the
// adapter's reads and verbs.
//
//   npx tsc src/venue/relay-adapter.ts --module commonjs \
//     --target es2022 --outDir dist-relay --resolveJsonModule \
//     --skipLibCheck --esModuleInterop
//   cp -r src/venue/seed dist-relay/seed
//   node scripts/smoke-relay.mjs
//
// Leg A (translation): a recording stub relay call —
// every route the live adapter uses maps to its exact
// runnerApi action and args, envelopes map to responses
// (200 ok, a 409 verdict rides through, status 0 carries
// the bridge's error text), and one verb (extend) runs
// end to end over canned served shapes.
//
// Leg B (live): a faithful stub relay call that performs
// the bridge's own HTTP call against the real panel
// (127.0.0.1:8793) and returns its envelope — the shell
// and SDK hop are the platform's integration surface
// (proven by the step-2 frame stub); everything from the
// frame-side transport inward is exercised for real,
// and the snapshot is cross-checked against direct panel
// reads. No mutation runs in this leg.

import { parseOnly, USAGE_EXIT } from "../../../../tools/argv.mjs";
import { createRequire } from "node:module";

// The unified argv guard (tools/argv.mjs): this tool
// takes no arguments — any argument is a usage refusal
// (exit 2) and --help prints the generated help, so an
// invocation can never fall through to the full job on
// a stray or mistyped flag.
const _argvOutcome = parseOnly({ name: "smoke-relay" }, process.argv.slice(2));
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
const { RelayVenueAdapter, createRelayFetch } = require("../dist-relay/relay-adapter.js");

let passed = 0;
const ok = (name, cond) => {
  console.log(`${cond ? "PASS" : "FAIL"} ${name}`);
  if (cond) passed += 1;
  else process.exitCode = 1;
};

/* ---------- Leg A: translation over a recording stub ---------- */

const calls = [];
const CANNED = {
  getState: () => ({ status: 200, payload: {}, error: null }),
  getStatePart: (args) => {
    switch (args.part) {
      case "records":
        return {
          status: 200,
          payload: {
            records: [
              {
                action: "active",
                record: {
                  session: "rig-session-1",
                  shape: "cpu-highram",
                  shape_spec: { gpu: null, tpu: null, high_mem: true },
                  rate_cu_per_hour: 4,
                  caller: "rig",
                  acquired_at: "2026-11-15T20:00:00Z",
                  deadline: "2999-01-01T00:00:00Z",
                  last_used_at: "2026-11-15T20:00:00Z",
                  jobs: [],
                  budget_at_acquire: { projected: 8 },
                },
                sync_claim: null,
                keepalive_heartbeat_age_s: null,
                caller: "rig",
              },
            ],
            access: [],
          },
          error: null,
        };
      case "specs":
        return { status: 200, payload: { specs: [] }, error: null };
      case "budget":
        return {
          status: 200,
          payload: {
            budget: {
              balance: 10, day_spent: 1, month_spent: 2, standing_day_spent: 0,
              caps: { daily: null, monthly: null, standing_daily: null }, accounts: [],
            },
          },
          error: null,
        };
      case "grant":
        return { status: 200, payload: { grant: null, envelope: null }, error: null };
      case "orphans":
        return {
          status: 200,
          payload: {
            orphans: [
              // The backend's exact nameless form
              // (nameless_census): an assignment that lost
              // its name server-side — session null,
              // nameless true, keyed by endpoint, the
              // recovered prior name or null.
              {
                acquired_at: null,
                conflicts: [],
                creator_caller: null,
                deadline_past: false,
                deadline_source: null,
                deadline_stale_possible: false,
                derived_deadline: null,
                endpoint: "m-hm-use1d0-1uj7tzpjz04km",
                first_claim: null,
                first_seen: "2026-11-16T07:24:31.257871+00:00",
                handover_pending: false,
                jobs_in_flight: 0,
                jobs_in_flight_entries: [],
                kit_installed: false,
                nameless: true,
                prior_session: null,
                rate_cu_per_hour: null,
                session: null,
                shape: null,
                shape_candidates: ["t4-highram", "g4-highram", "h100-highram", "a100-highram", "cpu-highram"],
                shape_class: "high_ram",
                shape_evidenced: false,
                shape_spec: null,
              },
            ],
          },
          error: null,
        };
      case "listeners":
        return { status: 200, payload: { listeners: {} }, error: null };
      default:
        return { status: 200, payload: {}, error: null };
    }
  },
  getLeaseOutbox: () => ({ status: 200, payload: { events: [], last_seq: 0 }, error: null }),
  extend: () => ({
    status: 200,
    payload: { action: "extended", new_deadline: "2999-01-02T00:00:00Z" },
    error: null,
  }),
  adoptOrphan: () => ({
    status: 200,
    payload: {
      action: "adopted",
      adopted_nameless: {
        endpoint: "m-hm-use1d0-1uj7tzpjz04km",
        prior_session: null,
        session: "rig-session-1",
      },
    },
    error: null,
  }),
  releaseAccess: (args) =>
    args?.body?.endpoint === "m-hm-use1d0-1uj7tzpjz04km"
      ? { status: 200, payload: { action: "session-released" }, error: null }
      : { status: 409, payload: { action: "release-absent" }, error: null },
};
const recordingCall = async (app, action, args) => {
  calls.push({ app, action, args });
  const fn = CANNED[action];
  if (!fn) throw new Error(`rig: no canned envelope for ${action}`);
  return fn(args ?? {});
};

const fetchA = createRelayFetch(recordingCall);
await fetchA("/api/state");
ok("A: GET /api/state → getState", calls.at(-1).action === "getState" && calls.at(-1).app === "runner");
await fetchA("/api/state/records");
ok("A: GET /api/state/records → getStatePart {part}", calls.at(-1).action === "getStatePart" && calls.at(-1).args.part === "records");
await fetchA("/api/outbox?after=0");
ok("A: GET /api/outbox?after=0 → getLeaseOutbox {after:0}", calls.at(-1).action === "getLeaseOutbox" && calls.at(-1).args.after === 0);

const POST_ROUTES = {
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
let postsOk = true;
for (const [path, action] of Object.entries(POST_ROUTES)) {
  // extend is the one canned POST; the rest are
  // translated by the same table — exercise translation
  // through a per-route canned envelope instead.
  const before = calls.length;
  const res = await createRelayFetch(async (app, a, args) => {
    calls.push({ app, action: a, args });
    return { status: 200, payload: { action: "ok" }, error: null };
  })(path, { method: "POST", body: JSON.stringify({ probe: path }) });
  const c = calls.at(-1);
  if (!(calls.length === before + 1 && c.action === action && c.args.body.probe === path && res.ok)) postsOk = false;
}
ok("A: all 11 POST routes → their actions, body as record", postsOk);

const verdict = await createRelayFetch(async () => ({
  status: 409, payload: { action: "extend-no-lease" }, error: null,
}))("/api/lease/extend", { method: "POST", body: "{}" });
ok("A: 409 envelope → !ok, status 409, verdict payload intact",
  verdict.ok === false && verdict.status === 409 && (await verdict.json()).action === "extend-no-lease");
const down = await createRelayFetch(async () => ({
  status: 0, payload: null, error: "backend unreachable",
}))("/api/state/records");
ok("A: status 0 → !ok and the bridge error text rides the body",
  down.ok === false && down.status === 0 && (await down.json()).error === "backend unreachable");
let unmappedThrew = false;
try {
  await fetchA("/api/nope");
} catch {
  unmappedThrew = true;
}
ok("A: an unmapped route throws instead of fetching", unmappedThrew);

calls.length = 0;
const adapterA = new RelayVenueAdapter(recordingCall);
await adapterA.ready();
const snapA = adapterA.snapshot();
ok("A: adapter over the stub serves the canned lease",
  snapA.leases.length === 1 && snapA.leases[0].session === "rig-session-1" && snapA.degraded === false);
const ext = await adapterA.extend("rig-session-1", 2);
const extCall = calls.find((c) => c.action === "extend");
ok("A: extend verb → extend {body:{session,hours}} and the extended note",
  extCall?.args.body.session === "rig-session-1" && extCall?.args.body.hours === 2 &&
  ext.note.startsWith("Extended — new deadline"));

// The nameless census row: the snapshot must admit the
// backend's session-null form (it threw inside
// orphanViews before the cure — liveSessionName over a
// null session) and project the row's endpoint identity
// honestly.
const namelessView = snapA.orphans.find((o) => o.nameless);
ok("A: nameless row projects without throwing, session null admitted",
  snapA.orphans.length === 1 && namelessView !== undefined && namelessView.session === null);
ok("A: nameless view carries the endpoint identity + honest name",
  namelessView?.endpoint === "m-hm-use1d0-1uj7tzpjz04km" &&
  namelessView?.priorSession === null &&
  namelessView?.displayName === "Unnamed session" &&
  namelessView?.shapeCandidates.length === 5);
const adoptedNameless = await adapterA.adoptNamelessOrphan(
  "m-hm-use1d0-1uj7tzpjz04km", "rig", "cpu-highram");
const adoptCall = calls.find((c) => c.action === "adoptOrphan");
ok("A: nameless adopt → adoptOrphan {body:{endpoint,shape}}, no session key, minted lease view",
  adoptCall?.args.body.endpoint === "m-hm-use1d0-1uj7tzpjz04km" &&
  adoptCall?.args.body.shape === "cpu-highram" &&
  !("session" in (adoptCall?.args.body ?? {})) &&
  adoptedNameless.session === "rig-session-1");
await adapterA.releaseNamelessOrphan("m-hm-use1d0-1uj7tzpjz04km");
const releaseCall = calls.find((c) => c.action === "releaseAccess");
ok("A: nameless release → releaseAccess {body:{endpoint}}, no session key",
  releaseCall?.args.body.endpoint === "m-hm-use1d0-1uj7tzpjz04km" &&
  !("session" in (releaseCall?.args.body ?? {})));
let absentErr = null;
try {
  await adapterA.releaseNamelessOrphan("m-absent-endpoint");
} catch (e) {
  absentErr = e;
}
ok("A: release-absent refusal maps to the family's sentence",
  absentErr?.code === "release-absent" &&
  absentErr?.message === "m-absent-endpoint is not an orphan assignment.");

/* ---------- Leg B: live panel through a bridge-faithful stub ---------- */

const PANEL = "http://127.0.0.1:8793";
const ACTION_ROUTES = {
  getState: () => "/api/state",
  getStatePart: (args) => `/api/state/${encodeURIComponent(args.part)}`,
  getLeaseOutbox: (args) => `/api/outbox${args?.after !== undefined ? `?after=${args.after}` : ""}`,
};
const bridgeCall = async (app, action, args) => {
  const route = ACTION_ROUTES[action];
  if (!route) throw new Error(`rig live leg: read-only stub, no route for ${action}`);
  try {
    const res = await fetch(`${PANEL}${route(args ?? {})}`);
    const payload = await res.json().catch(() => null);
    return { status: res.status, payload, error: res.ok ? null : `HTTP ${res.status}` };
  } catch (err) {
    return { status: 0, payload: null, error: String(err) };
  }
};

const adapterB = new RelayVenueAdapter(bridgeCall);
await adapterB.ready();
const probe = await adapterB.probe();
ok("B: probe reports the live panel reachable", probe.reachable === true);
const directRecords = await (await fetch(`${PANEL}/api/state/records`)).json();
const directBudget = await (await fetch(`${PANEL}/api/state/budget`)).json();
// ready() awaits the fast loop only, by the adapter's own
// design — the budget rides the slow loop, so wait for it
// to land before cross-checking it.
const expectedBalance = Math.round(directBudget.budget.balance * 100) / 100;
const slowDeadline = Date.now() + 120000;
while (adapterB.snapshot().budget.balanceCu !== expectedBalance && Date.now() < slowDeadline) {
  await new Promise((r) => setTimeout(r, 1000));
}
const snapB = adapterB.snapshot();
ok("B: snapshot lease count matches the panel's records",
  snapB.leases.length === directRecords.records.length);
ok("B: snapshot budget balance matches the panel's budget",
  snapB.budget.balanceCu === Math.round(directBudget.budget.balance * 100) / 100);
ok("B: snapshot is not degraded over the live stub", snapB.degraded === false);

console.log(`\n${passed} checks passed${process.exitCode ? " (with failures)" : ""}`);
process.exit(process.exitCode ?? 0);
