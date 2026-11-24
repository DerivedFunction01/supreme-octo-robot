// Headless pin for the ?api= HIGH finding's cure
// (the runner entry's standard at b54ebb2
// applied to the scheduler entry): the published form's
// live base is the serving origin, and no injection can
// point the live adapter at another origin. Three legs:
//   A. The seam's base-url rule (sanitizeBaseUrl): an
//      absolute or protocol-relative base is refused to
//      the origin root; same-origin relative bases are
//      honoured as-is.
//   B. Behavioural: a LiveSchedulerApi built over a
//      hostile injected base sends EVERY request —
//      including the graduated config write POST — to
//      same-origin relative paths, and still answers its
//      snapshot from them.
//   C. The entry no longer reads the parameter: a static
//      check that integration.tsx carries no ?api= read.
//
//   ./node_modules/.bin/tsc src/live/live-adapter.ts \
//     --module commonjs --target es2022 --outDir dist-live \
//     --skipLibCheck --esModuleInterop
//   printf '{"type":"commonjs"}' > dist-live/package.json
//   node scripts/smoke-api-base.mjs

import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);

let passed = 0;
const ok = (name, cond) => {
  console.log(`${cond ? "PASS" : "FAIL"} ${name}`);
  if (cond) passed += 1;
  else process.exitCode = 1;
};

const { LiveSchedulerApi, sanitizeBaseUrl } = require("../dist-live/live/live-adapter.js");

// A. The rule's table.
const s = sanitizeBaseUrl;
ok("rule: absolute https base refused", s("https://evil.example") === "");
ok("rule: absolute http base refused", s("http://127.0.0.1:9999") === "");
ok("rule: protocol-relative base refused", s("//evil.example") === "");
ok("rule: scheme base refused", s("javascript:alert(1)") === "");
ok("rule: bare relative base refused", s("api") === "");
ok("rule: origin root honoured", s("") === "");
ok("rule: same-origin path base honoured", s("/panel") === "/panel");

// B. The adapter over a hostile injected base.
const overview = {
  served_at: "2026-11-16T00:00:00Z", server_now: "2026-11-16T00:00:00Z",
  status: "ok", state_error: null, registry_errors: [], pid: 1,
  uptime_secs: 60, last_tick: "2026-11-16T00:00:00Z", running: [],
  registry: {
    by_kind: { scripted: 1, agent: 0 }, by_status: { active: 1, suspended: 0 },
    total: 1, enabled: 1,
  },
  outbox: { by_kind: {}, aged: [] },
  totals_24h: { total: 0, ok: 0, failed: 0 }, expected_wake_per_day: 1,
  storage: {}, config: {},
};
const job = {
  id: "fixture-job", kind: "scripted", status: "active",
  suspend_reason: null, owner: "none", cadence: "hourly",
  cadence_label: "hourly", timezone: "UTC", next_due: null,
  next_due_in_secs: null, last_run: null, last_activity: null,
  runs_24h: { total: 0, failed: 0 }, failure_streak: 0,
  expected_wake_per_day: 1, report_when: "always",
  audience: "operator", family: null, open_in: null,
};
const requested = [];
const fetchFn = async (url, init) => {
  requested.push(String(url));
  const path = String(url);
  const reply = (payload) => ({ ok: true, status: 200, json: async () => payload });
  if (path.endsWith("/api/v1/overview")) return reply(overview);
  if (path.endsWith("/api/v1/jobs")) return reply({ jobs: [job] });
  if (path.includes("/api/v1/jobs/") && path.endsWith("/config"))
    return reply({ ok: true, version: 2, values: { knob: 2 } });
  if (path.includes("/api/v1/jobs/"))
    return reply({ id: job.id, detail: { config: null } });
  if (path.includes("/api/v1/pings")) return reply({ pings: [] });
  if (path.includes("/api/v1/ledger")) return reply({ served_at: "", events: [] });
  return reply({});
};
const a = new LiveSchedulerApi({ baseUrl: "https://evil.example", fetchFn });
await a.ready();
ok("behaviour: no request left the serving origin",
  requested.length > 0 && requested.every((u) => u.startsWith("/api/v1/") && !u.includes("evil.example")));
ok("behaviour: the adapter still answers from the legitimate base",
  a.getOverview().server_status === "ok" && a.listJobs().length === 1 && a.listJobs()[0].id === "fixture-job");
const saved = await a.saveConfig("fixture-job", 1, { knob: 2 });
ok("behaviour: the config write POST went to the origin's route",
  requested.some((u) => u === "/api/v1/jobs/fixture-job/config"));
ok("behaviour: the write answers ok from the legitimate base", saved.ok === true);

// C. The entry carries no ?api= read.
const entry = readFileSync(new URL("../src/integration.tsx", import.meta.url), "utf8");
ok("entry: integration.tsx does not read the api parameter",
  !entry.includes('get("api")') && !entry.includes("?api=<"));

console.log(`${passed} checks passed`);
process.exit(process.exitCode ?? 0);
