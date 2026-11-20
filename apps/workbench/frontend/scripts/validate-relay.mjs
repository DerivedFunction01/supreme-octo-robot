// validate-relay.mjs — the frame transport check
// (REBUILD STEP 3).
//
// Builds the fixture feeds document through the pipeline
// server half (scripts/fixture_feeds.py, as validate-live
// does), bundles the live adapter, and drives it over a
// RELAY channel instead of HTTP: the adapter is
// constructed with a stub WbChannel that stands in for
// the shell relay + privileged bridge — it records every
// (action, args) the adapter sends and answers with
// bridge envelopes {status, payload, error} carrying the
// fixture's semantics (the goal record adopted whole, the
// §12 annotation create, the guarded-save CAS over the
// served sha, the entry page's base64 bytes, the dataset
// engine's rows).
//
// The proof therefore exercises the adapter's transport
// translation and envelope adaptation end to end — every
// route the seam calls lands on its wbApi/wbRaw action
// with the server set's arg shapes, 2xx envelopes serve
// their payloads, refusals surface the server's text,
// a status-0 envelope refuses with the bridge's
// diagnosis, and a relay-level rejection is the seam's
// could-not-reach refusal with local state untouched
// (server-first, W-C5). It does NOT exercise the live
// shell: the artifact runtime's relay is platform's
// step-3 integration surface, and this stub is its
// faithful stand-in at the wire contract
// (workhorse:action-request/response, envelope verbatim).
//
// Run: npm run validate:relay   (exit 1 on any failure)

import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = join(here, "..");
const repoRoot = join(appRoot, "..", "..", "..");

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
delete doc._fixture;

// -- bundle the live adapter -------------------------------
const tmp = mkdtempSync(join(tmpdir(), "wb-relay-"));
const entry = join(tmp, "entry.ts");
writeFileSync(
  entry,
  `export { LiveWorkbenchAdapter } from ${JSON.stringify(join(appRoot, "src/lib/liveAdapter.ts"))};`,
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

// -- the stub channel: the shell relay + bridge, in
//    fixture form. `calls` records every action the
//    adapter sends; failMode drives the refusal classes.
const calls = [];
let failMode = null; // null | "reject" | "down"
const repoShas = new Map(); // "repoId|path" -> current sha
const stubChannel = async (action, args = {}) => {
  calls.push({ action, args });
  if (failMode === "reject") {
    throw new Error("shell did not answer within 30000ms");
  }
  if (failMode === "down") {
    return {
      status: 0,
      payload: null,
      error: "Workbench server is unreachable (connection refused).",
    };
  }
  switch (action) {
    case "getFeeds":
      return { status: 200, payload: doc, error: null };
    case "todoAction": {
      const body = args.body ?? {};
      if (body.verb === "create") {
        return {
          status: 201,
          payload: { todo: { id: "relay-created-todo" } },
          error: null,
        };
      }
      return { status: 200, payload: { todo: { id: body.id ?? "x" } }, error: null };
    }
    case "goalPing": {
      // The fixture workspace serves no goals, so the
      // stub synthesizes the served record in the store's
      // shape — the adapter adopts the response's goal
      // whole, which is the behaviour under test.
      const goal = {
        slug: args.slug,
        title: "Relay goal",
        state: "active",
        ping: { armed: args.body.armed, cadence_minutes: 15 },
        status_posts: [],
      };
      return { status: 200, payload: { goal }, error: null };
    }
    case "createMessage":
      return {
        status: 201,
        payload: {
          message: {
            id: 9001,
            author: "owner",
            body: args.body.body,
            created_at: "2026-11-15T00:00:00Z",
          },
        },
        error: null,
      };
    case "saveRepoFile": {
      const key = `${args.repoId}|${args.path}`;
      const current = repoShas.get(key);
      if (current && args.baseSha256 !== current) {
        return {
          status: 409,
          payload: { current_sha256: current },
          error: null,
        };
      }
      const sha = "f".repeat(64);
      repoShas.set(key, sha);
      return { status: 200, payload: { sha256: sha }, error: null };
    }
    case "getEntryPage": {
      const body = "<html><body>relay page bytes</body></html>";
      return {
        status: 200,
        payload: {
          contentType: "text/html; charset=utf-8",
          bodyBase64: Buffer.from(body, "utf-8").toString("base64"),
          bytes: Buffer.byteLength(body),
        },
        error: null,
      };
    }
    case "postRepoDatasetSql":
      return {
        status: 200,
        payload: { columns: ["form", "cik"], rows: [["10-K", "320193"]] },
        error: null,
      };
    case "forceRefresh":
    case "rescanProjects":
      return { status: 200, payload: {}, error: null };
    default:
      return { status: 200, payload: {}, error: null };
  }
};

const saw = (action, pred = () => true) =>
  calls.find((c) => c.action === action && pred(c.args));

// -- boot: the entry's getFeeds over the channel, then
//    the adapter over the envelope's payload --------------
const bootEnv = await stubChannel("getFeeds");
check("boot rides the relay (getFeeds)", saw("getFeeds") !== undefined);
check(
  "boot envelope serves the document",
  bootEnv.status === 200 && bootEnv.payload?.projects?.projects?.length === 2,
);
const adapter = new LiveWorkbenchAdapter(
  structuredClone(bootEnv.payload),
  "",
  () => new Date(),
  stubChannel,
);
check(
  "adapter projects the served document",
  adapter.projects().length === 2,
  adapter.projects().map((p) => p.slug).join(", "),
);

// -- a todo create rides todoAction, server-first ---------
const todoCountBefore = adapter.todos("alpha").length;
const created = await adapter.addTodo("alpha", "bundle-1", "Relay todo");
check(
  "todo create rides todoAction {slug, body}",
  saw("todoAction", (a) => a.slug === "alpha" && a.body?.verb === "create") !== undefined,
);
check(
  "created todo adopts the server's id",
  created.id === "relay-created-todo" && adapter.todos("alpha").length === todoCountBefore + 1,
);

// -- a goal ping rides goalPing and adopts the record -----
const goalSlug = "relay-goal";
const pinged = await adapter.setGoalPing(goalSlug, true);
check(
  "goal ping rides goalPing {slug, body}",
  saw("goalPing", (a) => a.slug === goalSlug && a.body?.armed === true) !== undefined,
);
check("goal record adopted whole", pinged.ping?.armed === true);

// -- an annotation create rides createMessage (§12) -------
const plan = adapter.plans("alpha")[0];
const quote = (plan.raw.match(/^[^\n]+/m) ?? [""])[0].slice(0, 40);
const thread = await adapter.addAnnotation(plan.bundle, quote, "Relay note");
check(
  "annotation create rides createMessage with the §12 payload",
  saw(
    "createMessage",
    (a) =>
      a.body?.anchor_type === "text" &&
      a.body?.selection?.quote === quote &&
      a.body?.send === true,
  ) !== undefined,
);
check(
  "annotation thread projects from the served record",
  thread.id === "ann-9001" && adapter.annotationsForPlan(plan.bundle).length >= 1,
);

// -- the guarded repo save rides saveRepoFile (CAS) -------
const readme = adapter
  .repo("delta-repo")
  ?.files.find((f) => f.name === "README.md");
check("delta README served with its sha", Boolean(readme?.sha));
const servedSha = readme.sha;
repoShas.set("delta-repo|README.md", servedSha);
const saved = await adapter.guardedSave(
  "delta-repo",
  "README.md",
  "# Delta (relay edit)\n",
  servedSha,
);
check(
  "guarded save rides saveRepoFile with the served sha as baseSha256",
  saw(
    "saveRepoFile",
    (a) => a.repoId === "delta-repo" && a.baseSha256 === servedSha,
  ) !== undefined,
);
check("guarded save accepts on the envelope's sha", saved.ok && saved.sha === "f".repeat(64));
const stale = await adapter.guardedSave(
  "delta-repo",
  "README.md",
  "# Delta (stale edit)\n",
  servedSha,
);
check(
  "stale sha refuses over the relay, file untouched",
  !stale.ok &&
    stale.reason.includes("stale sha") &&
    adapter
      .repo("delta-repo")
      ?.files.find((f) => f.name === "README.md")
      ?.content?.includes("relay edit") === true,
);

// -- the entry page rides getEntryPage, bytes decoded -----
const page = await adapter.entryPage("spec-doc");
check(
  "entry page rides getEntryPage {slug, entryId}",
  saw("getEntryPage", (a) => a.slug === "alpha" && a.entryId === "spec-doc") !== undefined,
);
check(
  "entry page decodes the envelope's base64 bytes",
  page.ok && page.body.includes("relay page bytes"),
);

// -- dataset SQL rides postRepoDatasetSql ------------------
const sql = await adapter.datasetSql(
  "delta-repo",
  "data/filings.csv",
  "select form, cik from filings",
);
check(
  "dataset SQL rides postRepoDatasetSql {repoId, path, sql}",
  saw(
    "postRepoDatasetSql",
    (a) => a.repoId === "delta-repo" && a.path === "data/filings.csv",
  ) !== undefined,
);
check(
  "dataset SQL serves the engine's rows",
  sql.ok && sql.source === "engine" && sql.table.rows[0][0] === "10-K",
);

// -- refresh rides forceRefresh ----------------------------
await adapter.refresh();
check("refresh rides forceRefresh", saw("forceRefresh") !== undefined);

// -- refusal classes ----------------------------------------
failMode = "reject";
const todosBeforeReject = adapter.todos("alpha").length;
let rejectText = "";
try {
  await adapter.addTodo("alpha", "bundle-1", "Must not land");
} catch (err) {
  rejectText = err.message;
}
check(
  "relay rejection is the could-not-reach refusal",
  rejectText.includes("could not reach the workbench server") &&
    rejectText.includes("nothing was saved"),
  rejectText,
);
check(
  "relay rejection leaves local state untouched",
  adapter.todos("alpha").length === todosBeforeReject,
);

failMode = "down";
let downText = "";
try {
  await adapter.setGoalPing(goalSlug, false);
} catch (err) {
  downText = err.message;
}
check(
  "status-0 envelope refuses with the bridge's diagnosis",
  downText.includes("unreachable"),
  downText,
);
failMode = null;

console.log(`\n${passes} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
