// Mock validation: every seed payload that carries a frozen
// schema in contracts/schemas/ is validated against it
// (AJV, draft 2020-12 + formats). The owner item's schema
// froze at S6 (owner-item.schema.json), so items.json is
// validated against it, plus the structural cross-checks
// the schema cannot state: the id scheme
// (handle:source_ref), the wait_id link, and the served
// verb set.
//
// Run: npm run validate:mocks   (exit 1 on any failure)

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = dirname(fileURLToPath(import.meta.url));
const seedDir = join(here, "..", "src", "attention", "seed");
const schemaDir = join(here, "..", "..", "..", "..", "contracts", "schemas");

const readJson = (dir, name) => JSON.parse(readFileSync(join(dir, name), "utf8"));

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);

let failures = 0;
const check = (ok, label, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
};

function validateRows(seedFile, schemaFile, label) {
  const schema = readJson(schemaDir, schemaFile);
  const rows = readJson(seedDir, seedFile);
  const validate = ajv.compile(schema);
  rows.forEach((row, i) => {
    const ok = validate(row);
    check(ok, `${label}[${i}] vs ${schemaFile}`, ok ? row.id ?? row.handle ?? row.slug : JSON.stringify(validate.errors));
  });
  return rows;
}

const handlers = validateRows("handlers.json", "attention-handler.schema.json", "handler");
const programmes = validateRows("programmes.json", "attention-programme.schema.json", "programme");
const waits = validateRows("waits.json", "attention-wait.schema.json", "wait");
const sends = validateRows("sends.json", "attention-send.schema.json", "send");

{
  const validate = ajv.compile(readJson(schemaDir, "attention-presence.schema.json"));
  const presence = readJson(seedDir, "presence.json");
  const ok = validate(presence);
  check(ok, "presence vs attention-presence.schema.json", ok ? "" : JSON.stringify(validate.errors));
}

// ---- items: schema validation (S6 freeze) + structural
// cross-checks against contract 05 ----

const items = validateRows("items.json", "owner-item.schema.json", "item");
const handlerHandles = new Set(handlers.map((h) => h.handle));
const waitIds = new Set(waits.map((w) => w.id));
const sendIds = new Set(sends.map((s) => s.id));
const DECISION_KEYS = new Set(["verb", "at", "option_id", "note", "send_id"]);
// The contract verb vocabulary: the storyboard subset plus
// the learning loop's promotion verbs (rule_it,
// approve_rule), which the backend serves on decision
// items (verbs_for) and the parity pass wires into the UI.
const KNOWN_VERBS = new Set(["decide", "snooze", "done", "renew", "approve", "push", "release", "rule_it", "approve_rule"]);

const seenIds = new Set();
for (const item of items) {
  const at = `item ${item.id}`;
  check(typeof item.id === "string" && item.id.startsWith(`${item.handle}:`), `${at} — id scheme handle:source_ref`);
  check(!seenIds.has(item.id), `${at} — id unique`);
  seenIds.add(item.id);
  check(handlerHandles.has(item.handle), `${at} — handler resolves`);
  check(item.wait_id === null || waitIds.has(item.wait_id), `${at} — wait_id resolves`);
  if (item.kind === "decision" || item.kind === "breakthrough") {
    check(Array.isArray(item.verbs) && item.verbs.length > 0, `${at} — served verb set non-empty`);
    check(item.verbs.every((v) => KNOWN_VERBS.has(v)), `${at} — verbs in the storyboard/contract vocabulary`);
    if (item.verbs.includes("decide")) {
      check(Array.isArray(item.options) && item.options.length > 0, `${at} — decide verb carries options`);
    }
  }
  const checkDecision = (d, label) => {
    if (d === null) return;
    const keys = Object.keys(d);
    check(keys.every((k) => DECISION_KEYS.has(k) || k === "outcome" || k === "failure"), `${at} — ${label} keys within the decision subrecord`);
    check(typeof d.verb === "string" && typeof d.at === "string", `${at} — ${label} carries verb + at`);
    if (d.send_id !== null && d.send_id !== undefined) {
      check(sendIds.has(d.send_id), `${at} — ${label} send_id resolves in the ledger`);
    }
  };
  checkDecision(item.decision, "decision");
  (item.decision_history ?? []).forEach((h, i) => checkDecision(h, `history[${i}]`));
}

// ---- steering + rules + digest seeds: structural
// cross-checks (no frozen schemas exist for these payloads;
// the checks pin the references the store composes from) ----

const registries = readJson(seedDir, "registries.json");
const statusCodes = new Set(registries.status_codes.map((c) => c.code));
const waitClasses = new Map(registries.wait_classes.map((c) => [c.name, c.hard_stop]));
const fieldNames = new Set(registries.fields.map((f) => f.name));
const templateKinds = new Set(registries.templates.map((t) => t.kind));
const actionTypes = new Set(registries.actions.map((a) => a.type));
const triggerKinds = new Set(registries.triggers.map((t) => t.on));
const itemKinds = new Map(registries.item_kinds.map((k) => [k.kind, k]));

check(registries.status_codes.length === 8, "registries carry the eight status codes");
check(templateKinds.has("verdict") && templateKinds.has("status-ping"), "steering templates registered");

const statuses = readJson(seedDir, "statuses.json");
for (const [handle, rec] of Object.entries(statuses)) {
  check(handlerHandles.has(handle), `status ${handle} — handler resolves`);
  check(statusCodes.has(rec.status_code), `status ${handle} — code registered`, rec.status_code);
  for (const t of rec.tail ?? []) {
    check(itemKinds.has(t.kind), `status ${handle} — tail kind registered`, t.kind);
  }
}

const rules = readJson(seedDir, "rules.json");
check(new Set(rules.map((r) => r.id)).size === rules.length, "rule ids unique");
for (const rule of rules) {
  const at = `rule ${rule.id}`;
  check(rule.match.wait_class === null || waitClasses.has(rule.match.wait_class), `${at} — match class registered`);
  const codes = rule.match.status_code === null ? [] : Array.isArray(rule.match.status_code) ? rule.match.status_code : [rule.match.status_code];
  check(codes.every((c) => statusCodes.has(c)), `${at} — match codes registered`);
  check(actionTypes.has(rule.action.type), `${at} — action type registered`);
  check(triggerKinds.has(rule.trigger.on), `${at} — trigger registered`);
  check(["always", "away", "active"].includes(rule.scope), `${at} — scope in vocabulary`);
  check(["active", "shadow"].includes(rule.mode), `${at} — mode in vocabulary`);
  check((rule.requires ?? []).every((f) => fieldNames.has(f)), `${at} — requires resolve to fields`);
  if (rule.action.template) check(templateKinds.has(rule.action.template), `${at} — template registered`);
  if (["auto_apply", "post_and_apply"].includes(rule.action.type) && rule.match.wait_class) {
    check(waitClasses.get(rule.match.wait_class) === false, `${at} — the floor: no applying rule selects a hard-stop class`);
  }
}

const digestSeed = readJson(seedDir, "digest.json");
for (const section of digestSeed.sections) {
  check(itemKinds.get(section.kind)?.digest_owner === "owner", `digest section ${section.kind} — kind is owner-placed`);
  for (const row of section.rows) {
    check(handlerHandles.has(row.handle), `digest section ${section.kind} — row handler resolves`, row.handle);
  }
}
const STAFFING_KINDS = new Set(["understaffed", "fleet_idle", "idle_unlanded", "no_successor", "record_gap", "phantom_stop", "unrouted_defect", "blocked_uncited", "blocked_unverified", "serial_plan", "steer_undeliverable", "owner_waiting", "owner_waiting_unanswered", "armed_unposted"]);
for (const row of digestSeed.staffing.rows) {
  check(STAFFING_KINDS.has(row.kind), `staffing row — kind in the measure vocabulary`, row.kind);
  check(row.handle === null || handlerHandles.has(row.handle), "staffing row — handler resolves", row.handle ?? "");
}
for (const plan of digestSeed.parked_plans.plans) {
  check(typeof plan.project === "string" && typeof plan.title === "string", "parked plan carries project + title", plan.title);
}

// Cross-checks on the ledger + registries.
check(new Set(sends.map((s) => s.id)).size === sends.length, "send ids unique");
check(
  sends.every((s) => s.wait_id === null || s.wait_id === undefined || waitIds.has(s.wait_id)),
  "send wait_ids resolve",
);
check(
  programmes.every((p) => p.handles.every((h) => handlerHandles.has(h))),
  "programme handles resolve in the handler registry",
);

console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
