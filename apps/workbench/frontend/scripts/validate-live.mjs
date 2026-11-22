// validate-live.mjs — the live adapter contract check.
//
// Builds the fixture feeds document through the pipeline
// server half (scripts/fixture_feeds.py over the shared
// fixture workspace), bundles the live adapter, and drives
// it headlessly:
//   1. the adapter's armed rows are field-identical to the
//      rows the pipeline served (contract 03's shape is a
//      pass-through, not a re-render);
//   2. the status vocabulary is the contract fixture's,
//      exactly as served by the merged registry;
//   3. the classification derivation for the fixture's
//      armed todo is the SERVED progress block (verdict,
//      cadence, last activity; missed checks within one
//      interval of clock skew);
//   4. projections land: manifest/catalog on projects,
//      entry review states, plan state + steps, todo
//      checkpoints/notes parsed from the served body,
//      board lanes from the served portions, messages
//      minus drafts, repo tree + dataset;
//   5. the flows are exercised against live projections:
//      doing arms (default cadence), done retires,
//      guarded-save CAS (fresh sha saves, stale refuses
//      untouched), the goal writer rules over injected
//      contract-11 records riding the goal routes
//      (uncited blocked refused, cited blocked stamped by
//      the verifying party, terminal post clears
//      owner-waiting, a retired ping refuses re-arm), and
//      the annotation flows (served thread projects,
//      create carries the §12 selection payload, reply
//      appends through the root).
//
// Run: npm run validate:live   (exit 1 on any failure)

import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = join(here, "..");
const repoRoot = join(appRoot, "..", "..", "..");
const contracts = join(repoRoot, "contracts");

let failures = 0;
let passes = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
  if (ok) passes++;
  else failures++;
}

// -- the fixture document, from the pipeline itself -------
const venvPy = join(repoRoot, "pipeline", "workrecord", ".venv", "bin", "python");
const python = existsSync(venvPy) ? venvPy : "python3";
const raw = execFileSync(python, [join(here, "fixture_feeds.py")], {
  maxBuffer: 64 * 1024 * 1024,
}).toString("utf-8");
const doc = JSON.parse(raw);
const fx = doc._fixture;
delete doc._fixture;

// -- bundle the live adapter -------------------------------
const tmp = mkdtempSync(join(tmpdir(), "wb-live-"));
const entry = join(tmp, "entry.ts");
writeFileSync(
  entry,
  [
    `export { LiveWorkbenchAdapter } from ${JSON.stringify(join(appRoot, "src/lib/liveAdapter.ts"))};`,
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
const { LiveWorkbenchAdapter } = await import(pathToFileURL(bundle).href);

const adapter = new LiveWorkbenchAdapter(structuredClone(doc));

// 1. armed rows: pass-through parity with the served rows
const served = [...doc.armedRows].sort((a, b) => a.todo.localeCompare(b.todo));
const mine = [...adapter.armedRows()].sort((a, b) => a.todo.localeCompare(b.todo));
check("armed rows served", served.length === 1, `${served.length} row(s)`);
check(
  "armed rows field-identical to served",
  JSON.stringify(mine) === JSON.stringify(served),
  mine.length === served.length ? "" : "length differs",
);

// 2. vocabulary: served == contract fixture
const fixtureVocab = JSON.parse(
  readFileSync(join(contracts, "fixtures", "attention-status-codes.json"), "utf8"),
);
const fixtureRows = Array.isArray(fixtureVocab) ? fixtureVocab : fixtureVocab.codes;
check(
  "status vocabulary == contract fixture",
  JSON.stringify(adapter.statusVocabulary()) === JSON.stringify(fixtureRows),
);

// 3. classification: the served derivation, consumed
const rows = adapter.classification("alpha");
const doingRow = rows.find((r) => r.todo.id === fx.doing_todo);
const servedBlock = doc.projectFeeds.alpha.classification.progress.armed[0];
check("fixture todo armed in classification", doingRow?.armed === true);
check(
  "derivation is the served block",
  doingRow?.derivation?.verdict === (servedBlock.stalled ? "stalled" : "on-track") &&
    doingRow?.derivation?.cadenceMinutes === servedBlock.interval_seconds / 60 &&
    doingRow?.derivation?.lastActivity === servedBlock.last_activity &&
    Math.abs((doingRow?.derivation?.missedChecks ?? -99) - servedBlock.missed_checks) <= 1,
  `verdict ${doingRow?.derivation?.verdict}`,
);
const openRow = rows.find((r) => r.todo.id === fx.open_todo);
check("unarmed todo carries no derivation", openRow?.armed === false && openRow?.derivation === null);

// 4. projections
const projects = adapter.projects();
check("two projects projected", projects.length === 2);
const alpha = projects.find((p) => p.slug === "alpha");
check(
  "manifest + catalog projected (WR3)",
  alpha?.manifest?.registry === "workbench/registry.db" &&
    alpha?.manifest?.catalogOrigin === "machine" &&
    alpha?.manifest?.catalogGenerality === "deployment-specific" &&
    alpha?.manifest?.catalogUseCase === "work-tracking",
);
const entries = adapter.entries("alpha");
check(
  "entry review states projected",
  entries.find((e) => e.id === "tile-b")?.review === "needs-changes" &&
    entries.find((e) => e.id === "tile-a")?.review === "in-triage" &&
    entries.find((e) => e.id === "spec-doc")?.review === null &&
    entries.find((e) => e.id === "spec-doc")?.status === "canonical",
);
const plan = adapter.plan("2026-10-25-fixture-work");
check(
  "plan projected from bundle + doc",
  plan?.state === "in-progress" && plan?.executor === "fixture-lane" &&
    plan?.steps.length === 2 && plan?.raw.includes("Fixture plan"),
  plan ? `${plan.steps.length} steps` : "missing",
);
const doing = adapter.todo(fx.doing_todo);
check(
  "todo checkpoints + notes parsed from served body",
  doing?.checkpoints.length === 2 &&
    doing?.notes.includes("Notes ride under the checkpoints.") &&
    doing?.progressCheck === "30m" &&
    !("progress_check" in (doing?.extra ?? {})),
);
const board = adapter.board();
check(
  "board lanes from served portions",
  board.some((c) => c.lane === "review" && c.target.kind === "entry" && c.target.id === "tile-a") &&
    board.some((c) => c.lane === "doing" && c.target.kind === "plan") &&
    board.some((c) => c.lane === "todo" && c.target.kind === "todo" && c.title === "Open thing") &&
    board.some((c) => c.lane === "doing" && c.target.kind === "todo" && c.title === "Blocked thing"),
);
const messages = adapter.messages();
const drafts = doc.messages.messages.filter((m) => m.state === "draft");
check(
  "messages projected, drafts held back",
  messages.length === doc.messages.messages.length - drafts.length,
  `${messages.length} of ${doc.messages.messages.length}`,
);
const note = messages.find((m) => m.id === String(fx.annotation_id));
check(
  "annotation targets its plan bundle",
  note?.kind === "plan" && note?.target.section === "plans" &&
    note?.target.bundle === "2026-10-25-fixture-work",
);
const repo = adapter.repo("delta-repo");
const csv = repo?.files
  .flatMap(function walk(f) {
    return f.kind === "file" ? [f] : (f.children ?? []).flatMap(walk);
  })
  .find((f) => f.dataset);
check(
  "repo tree + dataset projected",
  repo?.branch === "main" && (repo?.modifiedCount ?? 0) >= 2 &&
    csv?.dataset?.tables[0]?.columns.join(",") === "form,cik,filed" &&
    csv?.dataset?.tables[0]?.rows.length === 2,
);
const summary = adapter.homeSummary();
check(
  "home summary from served rows",
  summary.sweptCount === 2 && summary.doingNow === 1 && summary.awaitingReview === 2,
);
const counts = adapter.counts();
check(
  "counts coherent",
  counts.boardDoing === board.filter((c) => c.lane === "doing").length &&
    counts.mockupsInTriage === 2 && counts.goalsActive === 0,
);

// 5. flows over live projections
// The flow writes ride the adapter's POST routes (D-4),
// so a fixture write server stands in for the shell: the
// todo route accepts, and the repo file route holds the
// compare-and-swap over the README's served sha256 — the
// CAS the checks below pin lives there now, not in the
// adapter.
const { createHash } = await import("node:crypto");
const sha256Hex = (s) => createHash("sha256").update(s).digest("hex");
const readme = repo?.files.find((f) => f.name === "README.md");
let readmeNow = { content: readme?.content ?? "", sha: readme?.sha ?? "" };
const flowRealFetch = globalThis.fetch;
globalThis.fetch = async (url, init) => {
  const u = String(url);
  if (u === "/api/projects/alpha/todos" && init?.method === "POST") {
    return Response.json({ todo: {} });
  }
  if (u === "/api/repos/delta-repo/file" && init?.method === "POST") {
    const body = JSON.parse(init.body);
    if (body.base_sha256 !== readmeNow.sha) {
      return Response.json(
        { error: "file changed on disk", current_sha256: readmeNow.sha },
        { status: 409 },
      );
    }
    readmeNow = { content: body.content, sha: sha256Hex(body.content) };
    return Response.json({ path: body.path, sha256: readmeNow.sha });
  }
  throw new Error(`fixture write server: unexpected ${init?.method ?? "GET"} ${u}`);
};
const flow = new LiveWorkbenchAdapter(structuredClone(doc));
const armedBefore = flow.armedRows().length;
const moved = await flow.writeTodo(fx.open_todo, { status: "doing" });
check(
  "doing arms at the default cadence",
  moved.armed === true && flow.armedRows().length === armedBefore + 1 &&
    flow.armedRows().find((r) => r.todo === fx.open_todo)?.cadence_minutes === 15,
);
const retired = await flow.writeTodo(fx.doing_todo, { status: "done" });
check(
  "done retires the served armed row",
  retired.armed === false &&
    !flow.armedRows().some((r) => r.todo === fx.doing_todo),
);
const saved = await flow.guardedSave("delta-repo", "README.md", "# Fixture repo\n\nedited\n", readme?.sha ?? "");
check("guarded save with the served sha", saved.ok === true);
const stale = await flow.guardedSave("delta-repo", "README.md", "stale write", readme?.sha ?? "");
check(
  "stale sha refuses, file untouched",
  stale.ok === false &&
    flow.repo("delta-repo")?.files.find((f) => f.name === "README.md")?.content === "# Fixture repo\n\nedited\n",
);
globalThis.fetch = flowRealFetch;

// Goal writer rules (W-C5): the writes ride POST
// /api/goals/{slug}/… to the goal-record store, so a
// fixture goal server stands in for the shell — it holds
// the writer rules the checks pin (uncited blocked
// refused, cited blocked stamped by the verifying party,
// terminal post clears owner-waiting and retires the
// ping, a retired ping refuses re-arm), exactly as the
// store's writer enforces them. The pipeline serves no
// goal records yet (doc.goals is empty and says why), so
// the record rides in seam shape here.
const goalDoc = structuredClone(doc);
goalDoc.goals = [
  {
    slug: "fixture-goal",
    project: "alpha",
    title: "Fixture goal",
    contract: {
      objective: "Exercise the writer rules.",
      completeWhen: "the checks pass",
      blockedOnlyWhen: "a cited owner decision is missing",
      continuation: "continue",
    },
    ping: { entryId: "goal:fixture-goal", cadenceMinutes: 30, armed: true },
    lastPost: {
      handle: "main",
      status_code: "WORKING",
      summary: "working",
      owner_waiting: { label: "fixture decision", commissioned_at: "2026-10-25T00:00:00+00:00" },
      postedAt: "2026-10-25T00:00:00+00:00",
    },
  },
];
const goalServerRecord = structuredClone(goalDoc.goals[0]);
globalThis.fetch = async (url, init) => {
  const u = String(url);
  const body = JSON.parse(init?.body ?? "{}");
  if (u === "/api/goals/fixture-goal/ping" && init?.method === "POST") {
    const rec = goalServerRecord;
    if (body.armed && (rec.lastPost?.status_code === "DONE" || rec.lastPost?.status_code === "CLOSED")) {
      return Response.json(
        { error: "this goal is closed — its ping is retired and cannot be re-armed" },
        { status: 400 },
      );
    }
    rec.ping.armed = body.armed;
    return Response.json({ goal: structuredClone(rec), ping_sync: { action: "unchanged" } });
  }
  if (u === "/api/goals/fixture-goal/status" && init?.method === "POST") {
    const rec = goalServerRecord;
    const post = body.post;
    const blocked = post.status_code === "BLOCKED-OWNER" || post.status_code === "BLOCKED-HARD";
    if (blocked && !post.basis_citation?.thread) {
      return Response.json(
        { error: "a blocked post must carry its basis citation — uncited blocked posts are refused at the writer" },
        { status: 400 },
      );
    }
    const stored = { ...post };
    if (blocked) stored.verification = stored.verification ?? { by: "main", at: new Date().toISOString() };
    if (post.status_code === "DONE" || post.status_code === "CLOSED") {
      if (stored.owner_waiting) stored.owner_waiting = null;
      rec.ping.armed = false;
    }
    rec.lastPost = { ...stored, postedAt: new Date().toISOString() };
    return Response.json({ goal: structuredClone(rec), ping_sync: { action: "unchanged" } });
  }
  throw new Error(`fixture goal server: unexpected ${init?.method ?? "GET"} ${u}`);
};
const goals = new LiveWorkbenchAdapter(goalDoc);
check("injected goal records serve", goals.allGoals().length === 1 && goals.goals("alpha").length === 1);
let refused = false;
try {
  await goals.postGoalStatus("fixture-goal", { handle: "main", status_code: "BLOCKED-OWNER", summary: "blocked" });
} catch {
  refused = true;
}
check("uncited blocked post refused at the writer", refused);
const cited = await goals.postGoalStatus("fixture-goal", {
  handle: "main",
  status_code: "BLOCKED-OWNER",
  summary: "blocked",
  basis_citation: { thread: "main", at: "2026-10-25T09:00:00+00:00" },
});
check(
  "cited blocked post stamped by the verifying party",
  cited.lastPost?.verification?.by === "main",
);
const donePost = await goals.postGoalStatus("fixture-goal", {
  handle: "main",
  status_code: "DONE",
  summary: "done",
  owner_waiting: { label: "fixture decision", commissioned_at: "2026-10-25T00:00:00+00:00" },
});
check("terminal post clears owner-waiting", donePost.lastPost?.owner_waiting === null);
check("terminal post retires the ping server-side", donePost.ping.armed === false);
await goals.postGoalStatus("fixture-goal", { handle: "main", status_code: "CLOSED", summary: "closed" });
let rearmRefused = false;
try {
  await goals.setGoalPing("fixture-goal", true);
} catch {
  rearmRefused = true;
}
check("retired ping refuses re-arm", rearmRefused);
const disarmedGoal = await goals.setGoalPing("fixture-goal", false);
check("ping disarm adopts the served record", disarmedGoal.ping.armed === false);
globalThis.fetch = flowRealFetch;
check(
  "empty pipeline goal store reads honestly",
  adapter.allGoals().length === 0 && adapter.counts().goalsActive === 0,
);

// Annotation flows (W-C5): the served annotation thread
// projects from the fixture store's anchored message;
// creates and replies ride POST /api/messages against a
// fixture message server that echoes the stored row.
const annAdapter = new LiveWorkbenchAdapter(structuredClone(doc));
const servedThreads = annAdapter.annotationsForPlan("2026-10-25-fixture-work");
check(
  "served annotation thread projects",
  servedThreads.length === 1 && servedThreads[0].messages.length === 1,
  `${servedThreads.length} thread(s)`,
);
let nextMsgId = 9001;
const annBodies = [];
globalThis.fetch = async (url, init) => {
  const u = String(url);
  if (u === "/api/messages" && init?.method === "POST") {
    const body = JSON.parse(init.body);
    annBodies.push(body);
    const id = nextMsgId++;
    return Response.json({
      message: {
        id,
        author: body.author,
        body: body.body,
        created_at: "2026-10-25T12:00:00+00:00",
        state: "sent",
        project_slug: body.project_slug ?? null,
        anchor_type: body.anchor_type ?? "none",
        anchor_ref: body.anchor_ref ?? null,
        selection: body.selection ?? null,
        parent_id: body.parent_id ?? null,
      },
    });
  }
  throw new Error(`fixture message server: unexpected ${init?.method ?? "GET"} ${u}`);
};
const ann = new LiveWorkbenchAdapter(structuredClone(doc));
const created = await ann.addAnnotation(
  "2026-10-25-fixture-work",
  "### Step 1 — Build the fixture stores",
  "Re-check this anchor after the next edit.",
);
check(
  "annotation create lands server-first and projects",
  created.id === "ann-9001" && created.status === "anchored" &&
    created.messages.length === 1 &&
    ann.annotationsForPlan("2026-10-25-fixture-work").length === 2,
);
check(
  "annotation create carries the §12 selection payload",
  annBodies[0]?.anchor_type === "text" &&
    annBodies[0]?.anchor_ref === "2026-10-25-fixture-work/plan.md" &&
    annBodies[0]?.selection?.kind === "text" &&
    annBodies[0]?.selection?.component_id === "plans/plan-reader" &&
    annBodies[0]?.selection?.quote === "### Step 1 — Build the fixture stores" &&
    annBodies[0]?.send === true,
);
const replied = await ann.replyAnnotation(created.id, "Checked — still anchored.");
check(
  "annotation reply appends through the root",
  replied.messages.length === 2 && annBodies[1]?.parent_id === 9001 && annBodies[1]?.send === true,
);
globalThis.fetch = flowRealFetch;

// 6. Entry pages (W1): the live adapter fetches the main
//    file's exact bytes over the byte route's shape — the
//    URL built from the served detail's file list — and a
//    refusal (route refusal, no main file) carries its
//    reason. fetch is stubbed: the route's construction
//    and the result mapping are what is pinned here.
const pageAdapter = new LiveWorkbenchAdapter(structuredClone(doc));
const realFetch = globalThis.fetch;
const seenUrls = [];
globalThis.fetch = async (url) => {
  seenUrls.push(String(url));
  return new Response("<html><body>fixture page</body></html>", {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
};
const tilePage = await pageAdapter.entryPage("tile-a");
check(
  "entry page fetched over the raw route shape",
  tilePage.ok === true && seenUrls[0] === "/raw/alpha/entries/tile-a/mock.html",
  seenUrls[0] ?? "no fetch made",
);
check(
  "entry page body is the served bytes, unmodified",
  tilePage.ok === true && tilePage.body === "<html><body>fixture page</body></html>",
);
globalThis.fetch = async () =>
  new Response("no such file\n", { status: 404 });
const routeRefusal = await pageAdapter.entryPage("tile-a");
check(
  "byte-route refusal carries the route's own reason",
  routeRefusal.ok === false && routeRefusal.reason === "no such file",
  routeRefusal.ok ? "served a page" : routeRefusal.reason,
);
globalThis.fetch = async () => {
  throw new Error("connection refused");
};
const downRefusal = await pageAdapter.entryPage("tile-a");
check(
  "unreachable byte route refuses with its reason",
  downRefusal.ok === false && downRefusal.reason.includes("did not answer"),
);
globalThis.fetch = realFetch;
// The fixture workspace holds no by-reference entry (every
// entry is entry-dir with a main file), so the no-main-file
// refusal is exercised over a document whose served detail
// carries an empty file list — the shape a by-reference
// entry serves (list_entry_files returns [] for one).
const byRefDoc = structuredClone(doc);
byRefDoc.projectFeeds.alpha.entryDetails["spec-doc"].files = [];
const byRefAdapter = new LiveWorkbenchAdapter(byRefDoc);
let byRefFetches = 0;
globalThis.fetch = async () => {
  byRefFetches++;
  return new Response("<html></html>", { status: 200 });
};
const byRefPage = await byRefAdapter.entryPage("spec-doc");
globalThis.fetch = realFetch;
check(
  "entry with no main file refuses, no fetch made",
  byRefPage.ok === false && byRefPage.reason.includes("held by reference") &&
    byRefFetches === 0,
  byRefPage.ok ? "served a page" : byRefPage.reason,
);

// The degraded repo document: the backend's error form
// (the projects index's code summary, SPEC §21) — a repo
// whose git probe failed serves error set with
// dirty_counts null. Code detail is no longer in the
// document (it serves on demand through the Code
// routes), so the old composition's detail-null half
// has no document face anymore. The store must project
// the honest absence, never throw on it: the step-3
// composed drive met a document whose every repo
// carried this form (all probes timed out under load)
// and the old store died in its constructor on the
// first one.
const degradedDoc = structuredClone(doc);
const degradedRow = degradedDoc.projectsIndex.projects.find((r) => r.id === "alpha");
degradedRow.code.error = "git timed out";
degradedRow.code.dirty_counts = null;
let degradedAdapter = null;
let degradedThrow = null;
try {
  degradedAdapter = new LiveWorkbenchAdapter(degradedDoc);
} catch (e) {
  degradedThrow = e;
}
check(
  "degraded repo document constructs the store",
  degradedAdapter !== null,
  degradedThrow ? String(degradedThrow) : "",
);
const degradedRepo = degradedAdapter?.repos().find((r) => r.slug === "alpha");
check(
  "degraded repo projects its absence honestly",
  degradedRepo?.sweep === "degraded" &&
    degradedRepo?.syncLabel === "Status unavailable" &&
    degradedRepo?.modifiedCount === 0,
  degradedRepo
    ? `${degradedRepo.sweep}/${degradedRepo.syncLabel}/${degradedRepo.modifiedCount}`
    : "no repo projected",
);
const healthyRepo = degradedAdapter?.repos().find((r) => r.slug !== "alpha");
check(
  "healthy repos in the same document project normally",
  healthyRepo !== undefined && healthyRepo.sweep === "swept" &&
    healthyRepo.syncLabel !== "Status unavailable",
  healthyRepo ? `${healthyRepo.slug}/${healthyRepo.syncLabel}` : "none found",
);

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
