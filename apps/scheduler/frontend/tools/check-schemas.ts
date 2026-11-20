#!/usr/bin/env tsx
// Mock-discipline check (plan §8, mock-first amendment): every
// mock payload is validated against the frozen contracts —
//
//   1. outbox pings        → contracts/schemas/outbox-ping.schema.json
//   2. ledger events (raw) → contracts/schemas/ledger-event.schema.json
//   3. job entries         → contract 14's field table (structural;
//                            the pinned scheduler carries no
//                            machine-readable entry schema — the
//                            table in contract 14 is the frozen
//                            statement, so the check encodes it)
//   4. served views        → contract 09's frozen field lists
//                            (presence of every named field)
//
// The contract fixtures' own ping/ledger specimens are validated
// as positive controls. Runtime-generated records count too: the
// checker drives actions first (run, suspend, ack), so minted
// pings, op events and run events are validated as served, not
// just as seeded. Exit 1 on any failure.

import { readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { MockSchedulerAdapter } from "../src/mock/mock-adapter";
import entriesJson from "../src/mock/seed-entries.json";
import { CLASSIFICATION, ENTRY_CONFIG } from "../src/mock/seeds";

const CONTRACTS = new URL("../../../../contracts/", import.meta.url);
const readJson = (rel: string) =>
  JSON.parse(readFileSync(new URL(rel, CONTRACTS), "utf8"));

let failures = 0;
let checks = 0;
function verdict(ok: boolean, label: string, detail?: string) {
  checks++;
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
}

const ajv = new Ajv2020({ strict: false });
addFormats(ajv);
const validatePing = ajv.compile(readJson("schemas/outbox-ping.schema.json"));
const validateLedger = ajv.compile(
  readJson("schemas/ledger-event.schema.json"),
);
// The job-view schema (contract 09, amendment 2026-11-13):
// the view object plus the config $defs the entry form and
// the served detail validate against.
ajv.addSchema(readJson("schemas/job-view.schema.json"));
const validateJobView = ajv.getSchema("job-view.schema.json")!;
const validateConfigBlock = ajv.getSchema(
  "job-view.schema.json#/$defs/configBlock",
)!;
const validateConfigView = ajv.getSchema(
  "job-view.schema.json#/$defs/configView",
)!;

// --- positive controls: the contracts' own fixtures ------------
const fixturePing = readJson("fixtures/outbox-ping.json");
verdict(
  validatePing(fixturePing) === true,
  "fixture outbox-ping.json validates against its schema",
  validatePing.errors ? ajv.errorsText(validatePing.errors) : undefined,
);
const fixtureLedger = readFileSync(
  new URL("fixtures/ledger-events.jsonl", CONTRACTS),
  "utf8",
)
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line));
for (const [i, event] of fixtureLedger.entries()) {
  verdict(
    validateLedger(event) === true,
    `fixture ledger-events.jsonl[${i}] (${event.kind}) validates`,
    validateLedger.errors ? ajv.errorsText(validateLedger.errors) : undefined,
  );
}

// --- contract 14 structural check on the seed entries ----------
const ALLOWED_TOP = new Set([
  "id", "title", "kind", "status", "suspend_reason", "suspended_on",
  "cadence", "timezone", "owner", "owner_reason", "run", "body",
  "escalate_body", "timeout_secs", "report", "state_paths",
  "classification", "lifetime", "self_removal", "source", "catalog",
  "catalog_version", "parameters", "writer", "project", "todo",
  "source_class",
]);
const MIGRATION_FAMILY = ["migrated", "migrated_at", "migration_note", "proof_pending"];

type EntryLike = Record<string, any>;
function entryProblems(e: EntryLike): string[] {
  const problems: string[] = [];
  for (const key of Object.keys(e)) {
    if (!ALLOWED_TOP.has(key)) problems.push(`unknown field ${key}`);
  }
  for (const field of MIGRATION_FAMILY) {
    if (field in e) problems.push(`migration family present: ${field}`);
  }
  if (!["scripted", "agent"].includes(e.kind)) problems.push("kind enum");
  if (!["active", "suspended"].includes(e.status)) problems.push("status enum");
  const cad = e.cadence ?? {};
  if (cad.type === "interval" && !/^\d+[smh]$/.test(String(cad.every)))
    problems.push("interval cadence form");
  if (cad.type === "daily" && !/^\d{2}:\d{2}$/.test(String(cad.at)))
    problems.push("daily cadence form");
  if (
    cad.type === "weekly" &&
    (!Array.isArray(cad.dow) || !/^\d{2}:\d{2}$/.test(String(cad.at)))
  )
    problems.push("weekly cadence form");
  if (!["interval", "daily", "weekly"].includes(cad.type))
    problems.push("cadence type enum");
  if (!("owner" in e)) problems.push("owner missing");
  if (e.owner === "none" && !e.owner_reason)
    problems.push("owner none without owner_reason");
  if (e.kind === "scripted" && !e.run?.argv) problems.push("scripted without argv");
  if (e.kind === "agent" && !e.body) problems.push("agent without body");
  if (!["permanent", "until_complete"].includes(e.lifetime))
    problems.push("lifetime enum");
  if (!e.classification) problems.push("classification missing");
  return problems;
}

const entries = entriesJson as EntryLike[];
verdict(entries.length === 26, `seed entries: 26 present`, `${entries.length}`);
for (const entry of entries) {
  const problems = entryProblems(entry);
  verdict(
    problems.length === 0,
    `entry ${entry.id} — contract 14 form`,
    problems.join("; ") || undefined,
  );
}

// --- the served classification (contract 09 amendment) ---------
// The store's classification table covers every seeded entry,
// with the ruled counts: 6 operator, 20 built-in (13 family,
// 7 direct); storage-watch is the direct-built-in
// reclassification.
{
  const ids = entries.map((e) => e.id);
  const unclassified = ids.filter((id) => !(id in CLASSIFICATION));
  verdict(
    unclassified.length === 0,
    "classification covers all 26 seeded entries",
    unclassified.join(", ") || undefined,
  );
  const all = ids.map((id) => CLASSIFICATION[id]!);
  const operators = all.filter((c) => c.audience === "operator");
  const builtins = all.filter((c) => c.audience === "builtin");
  const familied = builtins.filter((c) => c.family !== null);
  const direct = builtins.filter((c) => c.family === null);
  verdict(operators.length === 6, "classification: 6 operator", `${operators.length}`);
  verdict(builtins.length === 20, "classification: 20 built-in", `${builtins.length}`);
  verdict(familied.length === 13, "classification: 13 family built-ins", `${familied.length}`);
  verdict(direct.length === 7, "classification: 7 direct built-ins", `${direct.length}`);
  const byFamily = (fam: string) => familied.filter((c) => c.family === fam).length;
  verdict(
    byFamily("venue") === 6 &&
      byFamily("arming") === 2 &&
      byFamily("dispatch") === 2 &&
      byFamily("attention") === 1 &&
      byFamily("workbench") === 2,
    "classification: family split venue 6 / arming 2 / dispatch 2 / attention 1 / workbench 2",
  );
  verdict(
    CLASSIFICATION["storage-watch"]?.audience === "builtin" &&
      CLASSIFICATION["storage-watch"]?.family === null,
    "classification: storage-watch is a direct built-in (reclassified)",
  );
  verdict(
    familied.every((c) => c.open_in !== null) &&
      direct.every((c) => c.open_in === null),
    "classification: open_in served exactly for family built-ins",
  );
}

// --- entry config blocks (contract 09 amendment) ---------------
// The knob-bearing seeds validate against the schema's
// configBlock def; the knob-bearing set is exactly the two
// evidence-backed entries.
for (const [jobId, block] of Object.entries(ENTRY_CONFIG)) {
  verdict(
    validateConfigBlock(block) === true,
    `entry config ${jobId} — configBlock schema`,
    validateConfigBlock.errors
      ? ajv.errorsText(validateConfigBlock.errors)
      : undefined,
  );
}
verdict(
  Object.keys(ENTRY_CONFIG).sort().join(",") ===
    "memory-index-watchdog,storage-watch",
  "config: knob-bearing set is exactly the evidence-backed pair",
  Object.keys(ENTRY_CONFIG).sort().join(","),
);

// --- drive the mock, then validate everything it serves -------
const api = new MockSchedulerAdapter();
const unsub = api.subscribe(() => {});

const runResult = api.runNow("storage-watch");
verdict(runResult.ok === true, "action runNow(storage-watch) accepted");
const suspendResult = api.setJobEnabled("flap-watch", false);
verdict(suspendResult.ok === true, "action setJobEnabled(flap-watch, false) accepted");
const resumeResult = api.setJobEnabled("flap-watch", true);
verdict(resumeResult.ok === true, "action setJobEnabled(flap-watch, true) accepted");
const firstPing = api.listPings()[0];
verdict(!!firstPing, "pings view serves pending pings");
if (firstPing) {
  const ackResult = api.ackPing(firstPing.id, "owner");
  verdict(ackResult.ok === true, `action ackPing(${firstPing.id}) accepted`);
}

// Config writer (contract 09 amendment): round-trip, then the
// three refusals — out-of-range (whole), constraint, stale.
{
  const before = api.getJob("storage-watch")?.config;
  verdict(!!before && before.version === 1, "config served on storage-watch detail (version 1)");
  const save = await api.saveConfig("storage-watch", 1, {
    home_low_free_gb: 40,
    home_critical_free_gb: 30,
  });
  verdict(save.ok === true, "action saveConfig(storage-watch, tiers 50/45→40/30) accepted");
  const after = api.getJob("storage-watch")?.config;
  verdict(
    after?.version === 2 &&
      after.knobs.find((k) => k.key === "home_low_free_gb")?.value === 40 &&
      after.knobs.find((k) => k.key === "home_critical_free_gb")?.value === 30,
    "config round-trips through the store (values + version)",
  );
  const oor = await api.saveConfig("storage-watch", 2, {
    home_low_free_gb: 9999,
    home_critical_free_gb: 25,
  });
  verdict(
    oor.ok === false && oor.error === "bad_request",
    "config out-of-range save refused (bad_request)",
  );
  const afterOor = api.getJob("storage-watch")?.config;
  verdict(
    afterOor?.version === 2 &&
      afterOor.knobs.find((k) => k.key === "home_critical_free_gb")?.value === 30,
    "config out-of-range refusal applied NOTHING (whole refusal)",
  );
  const constraint = await api.saveConfig("storage-watch", 2, {
    home_low_free_gb: 40,
    home_critical_free_gb: 40,
  });
  verdict(
    constraint.ok === false && constraint.error === "bad_request",
    "config constraint violation refused (critical < low)",
  );
  const stale = await api.saveConfig("storage-watch", 1, {
    home_low_free_gb: 35,
    home_critical_free_gb: 30,
  });
  verdict(
    stale.ok === false && stale.error === "no_match",
    "config stale save refused (no_match — CAS guard)",
  );
  const knobless = await api.saveConfig("flap-watch", 1, { anything: 1 });
  verdict(
    knobless.ok === false,
    "config save on a knobless entry refused (no fabricated form)",
  );
}

// let the storage-watch run complete so a runtime run event and
// the bridge-wake wake pings exist in the store
await new Promise((resolve) => setTimeout(resolve, 3600));
unsub();

const snapshot = api.debugSnapshot();
for (const ping of snapshot.pings) {
  verdict(
    validatePing(ping) === true,
    `ping ${ping.id} (${ping.job_id}, ${ping.state}) — outbox schema`,
    validatePing.errors ? ajv.errorsText(validatePing.errors) : undefined,
  );
}
for (const event of snapshot.ledger) {
  verdict(
    validateLedger(event) === true,
    `ledger event ${event.kind}${event.job_id ? ` (${event.job_id})` : ""} — ledger schema`,
    validateLedger.errors ? ajv.errorsText(validateLedger.errors) : undefined,
  );
}

// --- contract 09 view shapes (field presence) ------------------
function hasKeys(obj: unknown, keys: string[]): string[] {
  if (typeof obj !== "object" || obj === null) return ["not an object"];
  const record = obj as Record<string, unknown>;
  return keys.filter((k) => !(k in record)).map((k) => `missing ${k}`);
}

const OVERVIEW_KEYS = [
  "served_at", "server_now", "server_status", "state_error",
  "registry_errors", "pid", "uptime_secs", "last_tick", "running_jobs",
  "totals_by_kind", "totals_by_status", "outbox_by_kind", "outbox_aged",
  "totals_24h", "expected_wakes_per_day", "storage", "config",
];
const JOB_VIEW_KEYS = [
  "id", "kind", "status", "suspend_reason", "owner", "cadence",
  "cadence_label", "timezone", "next_due", "next_due_in_secs",
  "last_run", "last_activity", "runs_24h", "failures_24h",
  "failure_streak", "expected_wakes_per_day", "report_mode",
  "audience", "family", "open_in",
];
const RUN_VIEW_KEYS = [
  "ts", "due", "status", "exit_code", "label", "matched_pattern",
  "collapsed", "error", "stdout_tail", "stderr_tail",
];
const DETAIL_KEYS = [
  "title", "timeout_secs", "ok_exit_codes", "run", "body",
  "escalate_body", "state_paths", "report", "classification",
  "lifetime", "recent_runs", "recent_dues", "ping_history",
  "config",
];

const overviewProblems = hasKeys(api.getOverview(), OVERVIEW_KEYS);
verdict(overviewProblems.length === 0, "overview view — contract 09 fields", overviewProblems.join("; ") || undefined);

for (const job of api.listJobs()) {
  const problems = hasKeys(job, JOB_VIEW_KEYS);
  verdict(problems.length === 0, `job view ${job.id} — contract 09 fields`, problems.join("; ") || undefined);
  verdict(
    validateJobView(job) === true,
    `job view ${job.id} — job-view.schema.json`,
    validateJobView.errors ? ajv.errorsText(validateJobView.errors) : undefined,
  );
  if (job.last_run) {
    const rp = hasKeys(job.last_run, RUN_VIEW_KEYS);
    verdict(rp.length === 0, `run view ${job.id} — contract 09 fields`, rp.join("; ") || undefined);
  }
  const detail = api.getJob(job.id);
  const dp = detail ? hasKeys(detail, DETAIL_KEYS) : ["detail missing"];
  verdict(dp.length === 0, `job detail ${job.id} — contract 09 fields`, dp.join("; ") || undefined);
  if (detail && detail.config) {
    verdict(
      validateConfigView(detail.config) === true,
      `job detail ${job.id} — configView schema`,
      validateConfigView.errors
        ? ajv.errorsText(validateConfigView.errors)
        : undefined,
    );
  }
  if (detail && !detail.config) {
    verdict(
      !(job.id in ENTRY_CONFIG),
      `job detail ${job.id} — config honestly absent`,
    );
  }
  if (detail) {
    verdict(
      detail.recent_runs.length <= 50 &&
        detail.recent_dues.length <= 50 &&
        detail.ping_history.length <= 20,
      `job detail ${job.id} — window caps (50/50/20)`,
    );
  }
}

for (const ping of [...api.listPings(), ...api.listRecentPings()]) {
  const problems = hasKeys(ping, ["age_secs", "overdue", "summary"]);
  verdict(problems.length === 0, `ping view ${ping.id} — contract 09 fields`, problems.join("; ") || undefined);
}
const ledgerView = api.getLedger(50);
verdict(
  hasKeys(ledgerView, ["served_at", "events"]).length === 0,
  "ledger view — contract 09 fields",
);
for (const event of ledgerView.events) {
  const problems = hasKeys(event, ["ts", "kind", "job_id", "detail"]);
  verdict(problems.length === 0, `ledger view event ${event.kind} — reduced form`, problems.join("; ") || undefined);
}

console.log(`\n${checks} checks, ${failures} failures`);
process.exit(failures > 0 ? 1 : 0);
