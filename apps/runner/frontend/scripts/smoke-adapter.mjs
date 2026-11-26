// Headless exercise of the mock adapter: every verb and every
// flow the UI drives, asserted against the store's projections.
// Not a unit suite — a lane smoke check that the controls the
// report lists as "exercised" genuinely move state.
//
//   npx tsc src/venue/adapter.ts --module commonjs --target es2022 \
//     --outDir dist-adapter --resolveJsonModule --skipLibCheck --esModuleInterop
//   node scripts/smoke-adapter.mjs

import { parseOnly, USAGE_EXIT } from "../../../../tools/argv.mjs";
import { createRequire } from "node:module";

// The unified argv guard (tools/argv.mjs): this tool
// takes no arguments — any argument is a usage refusal
// (exit 2) and --help prints the generated help, so an
// invocation can never fall through to the full job on
// a stray or mistyped flag.
const _argvOutcome = parseOnly({ name: "smoke-adapter" }, process.argv.slice(2));
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
const { MockVenueAdapter } = require("../dist-adapter/adapter.js");

const a = new MockVenueAdapter();
let passed = 0;
const ok = (name, cond) => {
  console.log(`${cond ? "PASS" : "FAIL"} ${name}`);
  if (cond) passed += 1;
  else process.exitCode = 1;
};

const s0 = a.snapshot();
ok("seed: 3 leases, 2 running", s0.leases.length === 3 && s0.runningCount === 2);
ok("seed: budget 412 / 96 / 48", s0.budget.balanceCu === 412 && s0.budget.usedTodayCu === 96 && s0.budget.reservedCu === 48);
ok("seed: by-caller 52/28/16", s0.budget.byCaller.map((c) => c.cu).join(",") === "52,28,16");
ok("seed: 3 orphans (session-44, session-52, session-58)", s0.orphans.length === 3 && s0.orphans[0].session === "session-44" && s0.orphans[1].session === "session-52" && s0.orphans[2].session === "session-58");
ok("e4: session-52 deadline ahead, served time, 2 jobs in flight", s0.orphans[1].deadlinePast === false && s0.orphans[1].deadlineLabel === "11:20 PM" && s0.orphans[1].jobs.length === 2 && s0.orphans[1].jobs.every((j) => j.stateLabel === "Running"));
ok("e4: session-44 not past deadline, no jobs in flight", s0.orphans[0].deadlinePast === false && s0.orphans[0].jobs.length === 0);
ok("seed: every lease venue-keyed colab", s0.leases.every((l) => l.venue === "colab"));

// specs — the served catalog (V5): every shape the backend
// offers, labels and rates served, unpriced shape unconfirmed
ok("specs: 3 served shapes", s0.specs.length === 3 && s0.specs.map((s) => s.id).join(",") === "cpu-highram,cpu,t4");
ok("specs: labels + descriptors served", s0.specs[0].label === "High-RAM CPU" && s0.specs[0].descriptor === "CPU · High-RAM" && s0.specs[2].descriptor === "GPU · T4");
ok("specs: t4 rate unconfirmed, projects nothing", s0.specs[2].rateCuPerHour === null && s0.specs[2].rateLabel === "Cost unconfirmed");
ok("specs: session gate verdicts served", s0.specs[0].agentStartable === true && s0.specs[1].agentStartable === false);

// acquire — new shape (Standard) creates a lease and reserves budget
const before = a.snapshot().budget;
const lease = await a.acquire({ shape: "cpu", caller: "delta-thread", hours: 2 });
ok("acquire: creates a lease", a.snapshot().leases.some((l) => l.session === lease.session));
ok("acquire: reservation +10 CU (Standard, 2 h)", a.snapshot().budget.reservedCu === before.reservedCu + 10);

// acquire — same shape adopts the live lease (latest-deadline placement)
const adopted = await a.acquire({ shape: "cpu", caller: "beta-main", hours: 2 });
ok("acquire: adopts live lease at shape", adopted.session === lease.session && adopted.caller === "beta-main");

// acquire — unregistered caller refused (contract 01)
let refused = false;
try {
  await a.acquire({ shape: "cpu", caller: "nobody", hours: 2 });
} catch (e) {
  refused = e.code === "unregistered-caller";
}
ok("acquire: unregistered caller refused", refused);

// acquire — an unpriced shape (t4) starts and reserves nothing
const t4Before = a.snapshot().budget;
const t4 = await a.acquire({ shape: "t4", caller: "delta-thread", hours: 2 });
ok("acquire: unpriced shape startable", a.snapshot().leases.some((l) => l.session === t4.session) && t4.shapeLabel === "T4 GPU");
ok("acquire: unpriced shape reserves 0 CU", a.snapshot().budget.reservedCu === t4Before.reservedCu);

// extend (V2) — expired lease returns to running; the deadline
// moves by exactly the chosen hours, from the old deadline
const stormBefore = a.snapshot().leases.find((l) => l.session === "storm-compass-26");
const extended = await a.extend("storm-compass-26", 2);
ok("extend: storm back to Running", extended.lease.state === "running");
ok("extend: deadline += chosen hours", Date.parse(extended.lease.deadline) - Date.parse(stormBefore.deadline) === 2 * 3600000);
ok("extend: success note", /^Extended — new deadline/.test(extended.note));

// extend — a delta the budget cannot cover refuses, moving nothing
const cozyBefore = a.snapshot().leases.find((l) => l.session === "cozy-pilot-61");
const cozyRefused = await a.extend("cozy-pilot-61", 72);
ok("extend: budget refusal note", /budget refused/.test(cozyRefused.note) && cozyRefused.lease.deadline === cozyBefore.deadline);
ok("v8: budget refusal journaled as a budget event", a.snapshot().events.some((e) => e.kind === "budget" && e.category === "budget" && /extension of Cozy Pilot 61/.test(e.message)));
const cozyExt = await a.extend("cozy-pilot-61", 1);
ok("extend: priced delta moves deadline", Date.parse(cozyExt.lease.deadline) - Date.parse(cozyBefore.deadline) === 3600000);

// shorten (V1) — pulls the deadline in by the chosen hours
const cozyShort = await a.shorten("cozy-pilot-61", { hours: 2 });
ok("shorten: deadline -= chosen hours", Date.parse(cozyExt.lease.deadline) - Date.parse(cozyShort.lease.deadline) === 2 * 3600000);
ok("shorten: success note", /^Shortened — new deadline/.test(cozyShort.note));

// shorten — a target not earlier than the deadline refuses
const cozyNotEarlier = await a.shorten("cozy-pilot-61", { deadline: new Date(Date.parse(cozyShort.lease.deadline) + 3600000).toISOString() });
ok("shorten: not-earlier refusal", /not earlier than the current deadline/.test(cozyNotEarlier.note));

// shorten — a target already passed refuses
const cozyPast = await a.shorten("cozy-pilot-61", { deadline: "2026-11-13T10:00:00-05:00" });
ok("shorten: past-target refusal", /already passed/.test(cozyPast.note));

// exec — starts a run that completes with exactly one terminal event
const run = await a.exec("cozy-pilot-61", "gate · smoke", "alpha-thread");
ok("exec: run starts Running", run.stateLabel === "Running");
await new Promise((r) => setTimeout(r, 10000));
const doneRun = a.snapshot().runsBySession["cozy-pilot-61"].find((r) => r.runId === run.runId);
ok("exec: run completes Passed", doneRun && doneRun.stateLabel === "Passed");

// release — closes the lease, journals its segment as spend
await a.release("ember-comet-32");
ok("release: ember lease closed", !a.snapshot().leases.some((l) => l.session === "ember-comet-32"));
ok("journal: used-today grew after release", a.snapshot().budget.usedTodayCu > 96);

// exec — a closed lease refuses
let execRefused = false;
try {
  await a.exec("ember-comet-32", "gate · smoke", "beta-main");
} catch (e) {
  execRefused = e.code === "no-lease";
}
ok("exec: closed lease refused", execRefused);

// orphan adopt + release paths
const adoptedOrphan = await a.adoptOrphan("session-44", "delta-thread");
ok("adopt: orphan becomes a lease", adoptedOrphan.session === "session-44" && a.snapshot().orphans.length === 2 && a.snapshot().orphans[0].session === "session-52");
await a.release("session-44");
ok("release: adopted orphan lease closes", !a.snapshot().leases.some((l) => l.session === "session-44"));

// degraded: snapshot freezes, verbs refuse, probe reports, restart restores
a.setReachable(false);
ok("degraded: snapshot flagged", a.snapshot().degraded === true);
let verbRefused = false;
try {
  await a.extend("cozy-pilot-61", 1);
} catch (e) {
  verbRefused = e.code === "unreachable";
}
ok("degraded: verbs refused", verbRefused);
ok("probe: reports unreachable", (await a.probe()).reachable === false);
await a.restartServer();
ok("restart: reachable again", (await a.probe()).reachable === true && a.snapshot().degraded === false);

// grant lifecycle (V3) — start snapshots caps + shapes; an
// in-scope acquire carries the envelope stamp; extend moves
// the until; ungrant clears the grant but keeps the stamps
ok("grant: none at seed", a.snapshot().grant === null);
const grant = await a.startGrant({ hours: 8, burst: "cpu-highram" });
ok("grant: started, burst + snapshot caps served", grant.burstLabel === "High-RAM CPU" && grant.caps.daily === 250 && grant.caps.monthly === 1000 && grant.caps.standingDaily === 40);
ok("grant: scope serves standing + burst shapes", grant.shapes.join(",") === "cpu,cpu-highram");
const stamped = await a.acquire({ shape: "cpu-highram", caller: "alpha-thread", hours: 2 });
ok("grant: in-scope acquire envelope-stamped", stamped.envelopeId === grant.id);
ok("grant: envelope leases list the stamped lease", a.snapshot().grant.leases.some((l) => l.session === stamped.session));
const grantExt = await a.extendGrant(4);
ok("grant: extend moves until by chosen hours", Date.parse(grantExt.grant.until) - Date.parse(grant.until) === 4 * 3600000 && /Grant extended/.test(grantExt.note));
const grantRefused = await a.extendGrant(200);
ok("grant: budget refusal moves nothing", /budget refused/.test(grantRefused.note) && grantRefused.grant.until === grantExt.grant.until);
await a.ungrant();
ok("grant: ungrant clears the grant", a.snapshot().grant === null);
ok("grant: attributed lease keeps its stamp", a.snapshot().leases.find((l) => l.session === stamped.session).envelopeId === grant.id);
const grantInactive = await a.extendGrant(1);
ok("grant: extend with no grant refuses", grantInactive.grant === null && /no active grant/.test(grantInactive.note));

// access release (V4) — on a fresh store: the census serves
// every live session; only the unattributed carry a release
const b = new MockVenueAdapter();
const bs = b.snapshot();
ok("access: census serves 6 sessions", bs.access.length === 6);
ok("access: record-backed attributed, evidence-only unattributed", bs.access.find((x) => x.session === "cozy-pilot-61").unattributed === false && bs.access.find((x) => x.session === "session-52").unattributed === true);
let backedRefused = false;
try {
  await b.releaseAccess("cozy-pilot-61");
} catch (e) {
  backedRefused = e.code === "record-backed";
}
ok("access: record-backed release refused", backedRefused);
await b.releaseAccess("session-52");
ok("access: unattributed session released", !b.snapshot().access.some((x) => x.session === "session-52") && b.snapshot().resolvedOrphans[0].label === "Released");

// orphan adoption depth (V6) — the census's evidence lines,
// the class-ambiguous pick, and the core's refusals
const c = new MockVenueAdapter();
const cs = c.snapshot();
const c44 = cs.orphans.find((o) => o.session === "session-44");
const c52 = cs.orphans.find((o) => o.session === "session-52");
const c58 = cs.orphans.find((o) => o.session === "session-58");
ok("v6: evidenced orphan serves its derivation detail", c44.shapeEvidenced === true && c44.deadlineSource === "renewal config" && c44.conflicts.length === 1 && c44.conflicts[0].field === "deadline" && /renewal config says 11:36 PM/.test(c44.conflicts[0].text) && c44.creatorCaller === "beta-main" && c44.kitInstalled === true);
ok("v6: ambiguous orphan serves class + candidates", c52.shapeEvidenced === false && c52.shapeClassLabel === "GPU" && c52.shapeCandidates.map((x) => x.id).join(",") === "t4" && c52.deadlineStalePossible === true);
ok("v6: handover orphan flagged", c58.handoverPending === true && c58.firstClaim === "workhorse");
let handoverRefused = false;
try {
  await c.adoptOrphan("session-58", "delta-thread");
} catch (e) {
  handoverRefused = e.code === "adopt-handover-pending";
}
ok("v6: handover adoption refused", handoverRefused);
let conflictRefused = false;
try {
  await c.adoptOrphan("session-52", "delta-thread", "cpu");
} catch (e) {
  conflictRefused = e.code === "adopt-shape-conflict";
}
ok("v6: pick outside the class refused", conflictRefused);
let evidencedConflict = false;
try {
  await c.adoptOrphan("session-44", "delta-thread", "t4");
} catch (e) {
  evidencedConflict = e.code === "adopt-shape-conflict";
}
ok("v6: pick contradicting the evidenced shape refused", evidencedConflict);
const adoptedAmbiguous = await c.adoptOrphan("session-52", "delta-thread");
ok("v6: single-candidate pick posts the shape", adoptedAmbiguous.shape === "t4" && !c.snapshot().orphans.some((o) => o.session === "session-52"));

// lease diagnostics (V7) — listeners census with suspect
// flags, keepalive age, last pulse, burn, sync claim
const cozyDiag = cs.leases.find((l) => l.session === "cozy-pilot-61").diagnostics;
const emberDiag = cs.leases.find((l) => l.session === "ember-comet-32").diagnostics;
const stormDiag = cs.leases.find((l) => l.session === "storm-compass-26").diagnostics;
ok("v7: listeners census served with suspect flags", cozyDiag.listeners.length === 2 && cozyDiag.listeners[1].suspect.join(",") === "deleted-cwd" && cozyDiag.listeners[0].port === 8793);
ok("v7: heartbeat + pulse + burn served", cozyDiag.heartbeatLabel === "41s ago" && cozyDiag.pulseLabel === "ok" && cozyDiag.burnLabel === "12 CU/h" && stormDiag.heartbeatLabel === "unknown" && /timeout/.test(stormDiag.pulseLabel));
ok("v7: sync claim served", emberDiag.syncClaim.caller === "beta-main" && emberDiag.syncClaim.untilLabel === "2:20 PM" && cozyDiag.syncClaim === null);
const freshLease = await c.acquire({ shape: "cpu", caller: "delta-thread", hours: 2 });
ok("v7: a lease with no census serves no diagnostics", c.snapshot().leases.find((l) => l.session === freshLease.session).diagnostics === null);

// logs depth (V8) — the Budget category over the stream,
// served day groups, and the raw record expansion
ok("v8: seed budget event carries the Budget category", cs.events.some((e) => e.id === "ev-0009" && e.category === "budget" && e.kindLabel === "Budget"));
ok("v8: categories served across the stream", cs.events.filter((e) => e.kind === "grant").every((e) => e.category === "grants") && cs.events.filter((e) => e.kind === "run").every((e) => e.category === "leases"));
ok("v8: day key + label served", cs.events.every((e) => e.dayKey === "2026-11-13" && e.dayLabel === "Today"));
ok("v8: raw record served, parses, names the record", cs.events.every((e) => JSON.parse(e.raw).id === e.id && JSON.parse(e.raw).kind === e.kind));

console.log(`\n${passed} checks passed.`);
process.exit(process.exitCode ?? 0);
