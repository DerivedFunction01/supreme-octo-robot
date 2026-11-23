// validate-mocks.mjs — the mock discipline check.
//
// Bundles the app's own seam code (arming + mock adapter +
// seed) and drives it headlessly:
//   1. every armed row the mock store produces validates
//      against contracts/schemas/armed-row.schema.json;
//   2. the row this code renders for the S0 fixture todo is
//      field-identical to the pinned writer's own fixture
//      (contracts/fixtures/armed-row.json);
//   3. a status post recorded through the adapter validates
//      against contracts/schemas/status-post.schema.json;
//   4. the scheduler-entry render carries contract 14's
//      fixture fields and none of the migrated family
//      (amendment 3);
//   5. the flows are exercised: doing arms, done/blocked
//      retire, opt-out disarms, checkpoint line format, todo
//      id scheme, guarded-save CAS (fresh sha saves, stale
//      sha refuses untouched), goal ping + terminal post
//      clearing the sticky owner-waiting declaration.
// Viewer shapes without a schema (feeds, board, classification)
// are validated by construction against the review's shape
// tables — see the lane report.
//
// Run: npm run validate:mocks   (exit 1 on any failure)

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = join(here, "..");
const contracts = join(appRoot, "..", "..", "..", "contracts");

let failures = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures++;
}

// Bundle the seam code (TypeScript) to a temp ESM file.
const tmp = mkdtempSync(join(tmpdir(), "wb-validate-"));
const entry = join(tmp, "entry.ts");
writeFileSync(
  entry,
  [
    `export { MockWorkbenchAdapter } from ${JSON.stringify(join(appRoot, "src/lib/mockAdapter.ts"))};`,
    `export * as arming from ${JSON.stringify(join(appRoot, "src/lib/arming.ts"))};`,
  ].join("\n"),
);
const bundle = join(tmp, "bundle.mjs");
execFileSync(join(appRoot, "node_modules/.bin/esbuild"), [
  entry,
  "--bundle",
  "--format=esm",
  `--outfile=${bundle}`,
  "--log-level=error",
]);
const { MockWorkbenchAdapter, arming } = await import(pathToFileURL(bundle).href);

const ajv = new Ajv2020({ strict: false });
const armedRowSchema = JSON.parse(readFileSync(join(contracts, "schemas/armed-row.schema.json"), "utf8"));
const statusPostSchema = JSON.parse(readFileSync(join(contracts, "schemas/status-post.schema.json"), "utf8"));
const validateArmedRow = ajv.compile(armedRowSchema);
const validateStatusPost = ajv.compile(statusPostSchema);

const NOW = new Date("2026-11-13T14:36:00.000Z");
const adapter = new MockWorkbenchAdapter(() => NOW);

// 1. All seeded armed rows validate against the schema.
const rows = adapter.armedRows();
check("seed produces armed rows", rows.length >= 3, `${rows.length} armed`);
for (const row of rows) {
  const ok = validateArmedRow(row);
  check(`armed row valid: ${row.todo}`, ok, ok ? "" : JSON.stringify(validateArmedRow.errors));
}

// 2. Fixture equivalence — the pinned writer's own output.
const fixtureRow = JSON.parse(readFileSync(join(contracts, "fixtures/armed-row.json"), "utf8"));
const fixtureTodo = {
  id: "long-work",
  project: "fixture-proj",
  bundle: "2026-11-01-work",
  title: "Long work",
  status: "doing",
  created: "2026-11-01",
  updated: "2026-11-01",
  progressCheck: "30m",
  progressArmed: "2026-11-01T11:30:00+00:00",
  checkpoints: [],
  notes: "",
  extra: {},
};
const rendered = arming.renderArmedRow(fixtureTodo);
const canon = (o) => JSON.stringify(o, Object.keys(o).sort());
const deepCanon = (o) =>
  JSON.stringify(o, (k, v) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  );
check(
  "rendered row == S0 fixture row (field-identical)",
  deepCanon(rendered) === deepCanon(fixtureRow),
  deepCanon(rendered) === deepCanon(fixtureRow) ? "" : `${canon(rendered)} vs ${canon(fixtureRow)}`,
);
check("fixture row itself validates", validateArmedRow(fixtureRow));

// 3. Status post through the adapter validates (wire shape:
//    the store's postedAt bookkeeping is stripped).
const goal = await adapter.postGoalStatus("workhorse-superapp-build", {
  handle: "@workbench-viewer",
  status_code: "WORKING",
  summary: "Validation pass running",
  refs: { project: "workbench-viewer", plan: null, todo_ids: [] },
  ongoing: ["Validation pass running"],
});
const { postedAt, ...wirePost } = goal.lastPost;
check("status post valid against schema", validateStatusPost(wirePost), validateStatusPost.errors ? JSON.stringify(validateStatusPost.errors) : "");
check("status post carries postedAt in store only", typeof postedAt === "string");

// 4. Scheduler entry render — contract 14 fields, no migrated.
const doingTodo = adapter.todo("step-4-workbench-storyboard");
const entryRender = arming.renderProgressEntry(doingTodo);
const entryJson = JSON.stringify(entryRender);
check("entry id is wb-progress-<project>-<todo>", entryRender.id === "wb-progress-fennelwick-step-4-workbench-storyboard");
check(
  "entry argv runs wb progress-check <id>",
  Array.isArray(entryRender.run.argv) && entryRender.run.argv.includes("progress-check") && entryRender.run.argv.includes(doingTodo.id),
);
check(
  "entry carries catalog block + machine source stamp",
  entryRender.catalog?.origin === "machine" && entryRender.source?.writer === "workbench-harness",
);
check(
  "entry has NO migrated field family (amendment 3)",
  !("migrated" in entryRender) && !("migrated_at" in entryRender) && !entryJson.includes("migration"),
);
check(
  "armed row filename form (ARM2)",
  arming.armedRowFilename(rows[0]) === `wb-armed-${rows[0].project}-${rows[0].todo.toLowerCase()}.json`,
);

// 5a. Arming flows.
const step5 = adapter.todo("step-5-close-report-to-main");
const before = adapter.armedRows().length;
await adapter.writeTodo(step5.id, { status: "doing" });
check("todo → doing arms (row appears, stamp set)", adapter.armedRows().length === before + 1 && Boolean(adapter.todo(step5.id).progressArmed));
await adapter.writeTodo(step5.id, { status: "done" });
check("doing → done retires the row", adapter.armedRows().length === before && !adapter.todo(step5.id).progressArmed);
await adapter.writeTodo(step5.id, { status: "doing" });
await adapter.writeTodo(step5.id, { progressCheck: "off" });
check("cadence → off disarms a doing todo", !adapter.armedRows().some((r) => r.todo === step5.id));
await adapter.writeTodo(step5.id, { progressCheck: "30m" });
check("cadence off → 30m re-arms", adapter.armedRows().some((r) => r.todo === step5.id && r.cadence_minutes === 30));
await adapter.writeTodo(step5.id, { status: "blocked" });
check("doing → blocked retires (stop status)", !adapter.armedRows().some((r) => r.todo === step5.id));

// 5b. Stall derivation (contract 03: 2 missed intervals).
const cls = adapter.classification("aldercrest");
const genre = cls.find((c) => c.todo.id === "genre-defect-ruling-line-cure");
check(
  "genre todo derives stalled (2h cadence, checkpoint 4.5h old at seed-now)",
  genre?.armed === true && genre?.derivation?.verdict === "stalled",
  genre ? `missed=${genre.derivation?.missedChecks}` : "row missing",
);
const sdsCls = adapter.classification("fennelwick");
const step4 = sdsCls.find((c) => c.todo.id === "step-4-workbench-storyboard");
check(
  "step-4 todo derives on-track (30m cadence, checkpoint 12 min old)",
  step4?.derivation?.verdict === "on-track" && step4?.derivation?.missedChecks === 0,
);
const optOut = adapter.classification("scheduler").find((c) => c.todo.id === "storage-watch-retune-home-tiers");
check("progress_check: off derives optOut and never arms", optOut?.optOut === true && optOut?.armed === false);
const defaultArm = adapter.classification("owner-attention").find((c) => c.todo.id === "in-service-dispatch-consumption");
check(
  "no cadence declared → arms at the 15-minute default",
  defaultArm?.armed === true && defaultArm?.derivation?.cadenceMinutes === 15,
);

// 5c. Checkpoint line + todo id scheme.
const withCp = await adapter.addCheckpoint(step5.id, "validation checkpoint");
const line = arming.checkpointLine(new Date(withCp.checkpoints[0].at), withCp.checkpoints[0].text);
check(
  "checkpoint line matches the preserved format",
  /^progress-checkpoint: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z — .+$/.test(line),
  line,
);
const allIds = adapter.raw().todos.map((t) => t.id);
check("every seed todo id is a slug name", allIds.every((id) => arming.TODO_ID_RE.test(id)), `${allIds.length} ids`);
const minted = await adapter.addTodo("fennelwick", step5.bundle, "Validation-minted todo");
check("derived todo id is a slug name", arming.TODO_ID_RE.test(minted.id), minted.id);
let titleRefused = false;
try {
  await adapter.writeTodo(minted.id, { title: "   " });
} catch {
  titleRefused = true;
}
check("empty title refused by the writer", titleRefused && adapter.todo(minted.id).title === "Validation-minted todo");

// 5d. Guarded save — config gate, then CAS.
const repo = adapter.repo("aldercrest");
const agentsFile = repo.files.find((f) => f.name === "AGENTS.md");
const offSave = await adapter.guardedSave("aldercrest", "AGENTS.md", "x", agentsFile.sha);
check("save refused while guarded saves are off (config gate)", offSave.ok === false);
adapter.updateSettings({ guardedSaves: true });
const shaBefore = agentsFile.sha; // capture the value — the file object is live store state
const goodSave = await adapter.guardedSave("aldercrest", "AGENTS.md", `${agentsFile.content}\n- Validation line.\n`, shaBefore);
check("save with the served sha succeeds and re-shas", goodSave.ok === true && goodSave.sha !== shaBefore);
const shaAfterGood = adapter.repo("aldercrest").files.find((f) => f.name === "AGENTS.md").sha;
const staleSave = await adapter.guardedSave("aldercrest", "AGENTS.md", "clobber", shaBefore);
check(
  "save with a stale sha refuses and leaves the file untouched",
  staleSave.ok === false && adapter.repo("aldercrest").files.find((f) => f.name === "AGENTS.md").sha === shaAfterGood,
);
const datasetSave = await adapter.guardedSave("aldercrest", "data/records.csv", "x", "c81d22");
check("dataset save refused (not editable)", datasetSave.ok === false);

// 5e. Goal ping + terminal post clearing owner_waiting.
const aldercrestGoal = adapter.goals("aldercrest")[0];
check("aldercrest goal starts with a sticky owner_waiting", aldercrestGoal.lastPost?.owner_waiting?.label === "Genre ruling-line cure");
await adapter.postGoalStatus("document-parsing-successor", {
  handle: "@aldercrest-data",
  status_code: "DONE",
  summary: "Successor programme closed on the audit",
  refs: { project: "aldercrest", plan: null, todo_ids: [] },
});
const afterTerminal = adapter.goals("aldercrest")[0];
check(
  "terminal post clears the sticky owner_waiting",
  afterTerminal.lastPost?.owner_waiting === null || afterTerminal.lastPost?.owner_waiting === undefined,
);
const disarmed = await adapter.setGoalPing("document-parsing-successor", false);
check("goal ping disarms through the record", disarmed.ping.armed === false);

// 6. The Goals section's records (storyboard
//    storyboard-goals.html + contract 11
//    amendment). Run against a fresh adapter: §5e mutated
//    the first one's posts.
const a2 = new MockWorkbenchAdapter(() => NOW);

// 6a. The served vocabulary mirrors the pinned fixture rows
//     exactly (contract 06: contents are data; the mirror is
//     checked, never trusted).
const vocabFixture = JSON.parse(
  readFileSync(join(contracts, "fixtures/attention-status-codes.json"), "utf8"),
);
check(
  "status vocabulary == contract 06 fixture rows",
  deepCanon(a2.statusVocabulary()) === deepCanon(vocabFixture),
  deepCanon(a2.statusVocabulary()) === deepCanon(vocabFixture)
    ? ""
    : `${deepCanon(a2.statusVocabulary())} vs ${deepCanon(vocabFixture)}`,
);

// 6b. Census + the nav count: 3 active, 1 closed.
const allGoals = a2.allGoals();
const terminalCodes = new Set(a2.statusVocabulary().filter((r) => r.terminal).map((r) => r.code));
const activeGoals = allGoals.filter((g) => !g.lastPost || !terminalCodes.has(g.lastPost.status_code));
check("goal census: 4 records, 3 active", allGoals.length === 4 && activeGoals.length === 3, `${allGoals.length} records`);
check("counts().goalsActive is the active count", a2.counts().goalsActive === 3);

// 6c. The completed goal: closed post, retired ping, and
//     its steps all landed — the Completed group derives.
const closed = a2.goal("aldercrest-greenfield-tagger");
check("completed goal exists with a CLOSED post", closed?.lastPost?.status_code === "CLOSED");
check("completed goal's ping is retired (disarmed)", closed?.ping.armed === false);
const closedTodos = closed ? a2.goalTodos(closed) : [];
check(
  "completed goal derives 11 of 11 steps landed",
  closedTodos.length === 11 && closedTodos.every((t) => t.status === "done"),
  `${closedTodos.filter((t) => t.status === "done").length}/${closedTodos.length}`,
);
let rearmRefused = false;
try {
  await a2.setGoalPing("aldercrest-greenfield-tagger", true);
} catch {
  rearmRefused = true;
}
check("a retired ping refuses re-arming at the writer", rearmRefused && closed?.ping.armed === false);

// 6d. Goal 1's bundle: the consolidation plan is seeded, so
//     its row derives progress like goals 2 and 3.
const g1 = a2.goal("workhorse-superapp-build");
check(
  "goal 1 resolves its consolidation bundle",
  a2.goalBundle(g1)?.bundle === "2026-11-12-consolidation-plan",
  a2.goalBundle(g1)?.bundle ?? "none",
);
const g1Todos = a2.goalTodos(g1);
check(
  "goal 1 derives 2 of 6 todos done",
  g1Todos.length === 6 && g1Todos.filter((t) => t.status === "done").length === 2,
  `${g1Todos.filter((t) => t.status === "done").length}/${g1Todos.length}`,
);
check(
  "goal 3 (no post) derives its bundle by the single in-progress fallback",
  a2.goalBundle(a2.goal("copperleaf-dag"))?.bundle === "2026-11-10-step6-reparse-cadence",
);

// 6e. The blocked post carries the amendment's pair, and
//     the whole post still validates against the schema.
const blockedPost = a2.goal("document-parsing-successor")?.lastPost;
check(
  "blocked post carries basis_citation (thread + time)",
  typeof blockedPost?.basis_citation?.thread === "string" &&
    blockedPost.basis_citation.thread.length > 0 &&
    !Number.isNaN(new Date(blockedPost.basis_citation.at).getTime()),
  blockedPost?.basis_citation ? `${blockedPost.basis_citation.thread} · ${blockedPost.basis_citation.at}` : "absent",
);
check(
  "blocked post carries the verification stamp (by + at)",
  blockedPost?.verification?.by === "main" &&
    !Number.isNaN(new Date(blockedPost?.verification?.at ?? "").getTime()),
);
const { postedAt: bpAt, ...blockedWire } = blockedPost ?? {};
check(
  "blocked post (pair included) validates against the status-post schema",
  Boolean(blockedPost) && validateStatusPost(blockedWire),
  validateStatusPost.errors ? JSON.stringify(validateStatusPost.errors) : "",
);

// 6f. The writer refuses an uncited blocked post; a cited
//     one is recorded and stamped by the verifying party.
let uncitedRefused = false;
try {
  await a2.postGoalStatus("copperleaf-dag", {
    handle: "@copperleaf",
    status_code: "BLOCKED-OWNER",
    summary: "Cadence ruling missing",
    refs: { project: "copperleaf", plan: null, todo_ids: [] },
  });
} catch {
  uncitedRefused = true;
}
check(
  "uncited blocked post refused at the writer, nothing recorded",
  uncitedRefused && a2.goal("copperleaf-dag")?.lastPost === null,
);
const cited = await a2.postGoalStatus("copperleaf-dag", {
  handle: "@copperleaf",
  status_code: "BLOCKED-OWNER",
  summary: "Cadence ruling missing",
  refs: { project: "copperleaf", plan: null, todo_ids: [] },
  basis_citation: { thread: "copperleaf thread", at: "2026-11-13T13:00:00.000Z" },
});
check(
  "cited blocked post records with the pair; verification stamped at ingest",
  cited.lastPost?.basis_citation?.thread === "copperleaf thread" &&
    cited.lastPost?.verification?.by === "main" &&
    cited.lastPost?.verification?.at === NOW.toISOString(),
);

// 6g. The arms strings the work view renders match the
//     storyboard's specimens byte-for-byte.
const genreTodo = a2.todo("genre-defect-ruling-line-cure");
check(
  "scheduler entry filename matches the storyboard specimen",
  `${arming.progressEntryId(genreTodo)}.yaml` === "wb-progress-aldercrest-genre-defect-ruling-line-cure.yaml",
  `${arming.progressEntryId(genreTodo)}.yaml`,
);
check(
  "armed row filename matches the storyboard specimen",
  arming.armedRowFilename(arming.renderArmedRow(genreTodo)) ===
    "wb-armed-aldercrest-genre-defect-ruling-line-cure.json",
);

// 7. Entry pages (W1): the mock serves a stand-in page in
//    the byte route's shape for a specimen — a complete
//    document in the entry's recorded mode — and refuses
//    a by-reference entry with the live store's reason.
const mockPage = await a2.entryPage("e-launcher");
check(
  "mock serves a stand-in page for a specimen",
  mockPage.ok === true &&
    mockPage.contentType.includes("text/html") &&
    mockPage.body.startsWith("<!doctype html>") &&
    mockPage.body.includes("Superapp storyboard — launcher"),
  mockPage.ok ? `${mockPage.body.length} bytes` : mockPage.reason,
);
const byRefPage = await a2.entryPage("e-fundamentals");
check(
  "by-reference entry refuses with its reason",
  byRefPage.ok === false && byRefPage.reason.includes("held by reference"),
  byRefPage.ok ? "served a page" : byRefPage.reason,
);
const unknownPage = await a2.entryPage("e-no-such-entry");
check(
  "unknown entry refuses, never throws",
  unknownPage.ok === false && unknownPage.reason.includes("Unknown entry"),
);

console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
