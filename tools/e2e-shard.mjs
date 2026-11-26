#!/usr/bin/env node
/**
 * The shard entry for the rendered legs (tests/e2e/) — the
 * one committed invocation a gate lane calls instead of
 * hand-rolling the Playwright leg in shell:
 *
 *   node tools/e2e-shard.mjs <qa|app> [options]
 *
 *   --sha <sha>       assert HEAD equals this commit and the
 *                     tracked tree is clean before running
 *                     (the same-tree assertion: a leg's
 *                     verdict names the tree it measured)
 *   --port <n>        E2E_PORT (defaults: qa 3510, app 3520
 *                     — a shard per session by default; when
 *                     shards share one machine, pass
 *                     distinct ports)
 *   --workers <n>     Playwright workers (default 1, the
 *                     config's own form; a venue lane passes
 *                     its measured count)
 *   --only <substr>   run only family files whose name
 *                     contains the substring (smoke runs)
 *
 * The shard owns: the family partition below, a per-shard
 * E2E_PORT + scratch dir, the browser-binary ensure, a
 * port-free check before the run (a busy port aborts —
 * another suite owns it) and after it (the final leg: the
 * port must be free again within a bounded grace;
 * Playwright stops its webServer on exit, but the release
 * is asynchronous — a single instantaneous probe races a
 * healthy shutdown and reads a mid-release port as a leak.
 * A port still bound when the grace expires is a teardown
 * failure, and the failure line names the
 * occupant where the platform can read it). Its verdict
 * rides the unified exit vocabulary: 0 when Playwright
 * passes and the port frees, 1 on any operational failure
 * (partition, tree assertion, busy port, missing install,
 * or failing specs), 2 on a usage refusal, and the
 * declared teardown verdict 3 when the specs pass but
 * the port stays bound.
 *
 * The partition is a PARTITION: every tests/e2e/*.spec.ts
 * on disk belongs to exactly one family, and this script
 * fails before running anything if a spec is unassigned,
 * double-assigned, or claimed but absent — a new spec
 * forces an explicit family decision here, never a silent
 * drop from the gate. Families: `qa` carries the rendered
 * legs (the standing practices in docs/checks.md); `app`
 * carries the project's own surface specs, and starts
 * empty — running an empty family is a clean no-op that
 * says so, because the seed ships no app specs yet.
 *
 * Seeding state: the qa family carries the legs this repo
 * has seeded — today the dead-click sweep alone (S-4). The
 * app family carries the project's own surface specs —
 * today the jobs-overflow after-proof, a measurement leg
 * whose staged-payload prerequisites are the caller's, as
 * its header names. A leg joins the partition in the same
 * change that seeds its spec; a leg the project has not
 * seeded is unexercised, never passed (docs/checks.md).
 * (jobs-overflow2 sat unassigned from the repo remake
 * until its seeding landed — the partition check refused every run
 * in that window, which is the check working as designed
 * against a seeding change that skipped its half.)
 *
 * Toolchain: this repo carries no root package-manager
 * workspace — the legs' one dependency (@playwright/test,
 * the root package.json) installs with the caller's
 * `npm install` at the repo root, and the shard invokes
 * the installed Playwright CLI binary directly.
 *
 * Prerequisites the shard does NOT own: the root
 * `npm install` and the client build (`bun run
 * build:client` in artifact/), run before this script, and
 * the composed check (`python3 check.py`), which a gate
 * runs beside this invocation — not inside it.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseOnly, USAGE_EXIT } from "./argv.mjs";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

const FAMILIES = {
  qa: ["qa-dead-click.spec.ts"],
  app: ["jobs-overflow2.spec.ts"],
};

const DEFAULT_PORTS = { qa: "3510", app: "3520" };

function fail(message, code) {
  console.error(`e2e-shard: ${message}`);
  process.exit(code);
}

// The declared surface, parsed by the unified argv
// adapter (tools/argv.mjs): both value forms are one
// flag, unknown flags and surplus positionals refuse at
// exit 2, and help is generated from this declaration.
const DECL = {
  name: "e2e-shard",
  summary: "the shard entry for the rendered legs (tests/e2e/)",
  positionals: [
    { name: "family", required: true,
      help: "the shard family (qa|app)" },
  ],
  flags: {
    sha: { takes_value: true,
           help: "assert HEAD equals this commit and the tracked tree is clean before running" },
    port: { takes_value: true,
            help: "E2E_PORT (defaults: qa 3510, app 3520)" },
    workers: { takes_value: true, default: "1",
               help: "Playwright workers (default 1)" },
    only: { takes_value: true,
            help: "run only family files whose name contains the substring" },
  },
  verdict_codes: { "teardown-failure": 3 },
};
const TEARDOWN_EXIT = DECL.verdict_codes["teardown-failure"];

const outcome = parseOnly(DECL, process.argv.slice(2));
if (!outcome.ok) {
  console.error(outcome.error);
  console.error(outcome.usage);
  process.exit(USAGE_EXIT);
}
if ("help" in outcome) {
  console.log(outcome.help);
  process.exit(0);
}
const shard = outcome.result.positionals.family;
if (!Object.hasOwn(FAMILIES, shard)) {
  fail(`unknown family ${JSON.stringify(shard)} (qa|app)`, USAGE_EXIT);
}
const sha = outcome.result.flags.sha;
const port = outcome.result.flags.port ?? DEFAULT_PORTS[shard];
const workers = outcome.result.flags.workers;
const only = outcome.result.flags.only;

// The partition check: the families' claim over the suite
// on disk must be exact — nothing unassigned, nothing
// double-assigned, nothing named that does not exist.
const onDisk = readdirSync(join(repoRoot, "tests", "e2e"))
  .filter((name) => name.endsWith(".spec.ts"))
  .sort();
const claimed = new Map();
for (const [family, files] of Object.entries(FAMILIES)) {
  for (const file of files) {
    if (claimed.has(file)) {
      fail(
        `partition: ${file} is claimed by both ${claimed.get(file)} and ${family}`,
        1,
      );
    }
    claimed.set(file, family);
  }
}
for (const file of onDisk) {
  if (!claimed.has(file)) {
    fail(
      `partition: ${file} is in no shard family — assign it in tools/e2e-shard.mjs`,
      1,
    );
  }
}
for (const file of claimed.keys()) {
  if (!onDisk.includes(file)) {
    fail(`partition: ${file} is claimed by ${claimed.get(file)} but not on disk`, 1);
  }
}

let specs = FAMILIES[shard].map((file) => join("tests", "e2e", file));
if (only !== null) {
  specs = specs.filter((path) => path.includes(only));
  if (specs.length === 0) fail(`--only ${only} matches no file in shard ${shard}`, USAGE_EXIT);
}
if (specs.length === 0) {
  console.log(`e2e-shard ${shard}: family carries no specs yet — nothing to run`);
  process.exit(0);
}

// The same-tree assertion, when the caller names the tree.
if (sha !== null) {
  const head = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  const dirty = spawnSync("git", ["status", "--porcelain", "--untracked-files=no"], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  const actual = (head.stdout ?? "").trim();
  if (head.status !== 0 || actual !== sha) {
    fail(`tree assertion: HEAD is ${actual || "(unreadable)"}, expected ${sha}`, 1);
  }
  if ((dirty.stdout ?? "").trim() !== "") {
    fail("tree assertion: tracked tree is dirty", 1);
  }
  console.log(`e2e-shard ${shard}: tree asserted at ${sha} (tracked clean)`);
}

function portFree(candidate) {
  return new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.listen(Number(candidate), "127.0.0.1", () => {
      server.close(() => resolve(true));
    });
  });
}

// The teardown grace: the webServer's release is
// asynchronous (Playwright signals it as the CLI exits;
// the socket frees some hundreds of milliseconds later),
// so the final leg re-probes over a bounded window rather
// than judging one instant. Free at any probe inside the
// window is a clean teardown; bound at every probe to the
// window's end is a leak.
const TEARDOWN_GRACE_MS = 20_000;
const TEARDOWN_PROBE_MS = 250;

async function portFreeWithin(candidate, graceMs) {
  const deadline = Date.now() + graceMs;
  for (;;) {
    if (await portFree(candidate)) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, TEARDOWN_PROBE_MS));
  }
}

// Who holds the port, for the teardown failure line: a
// verdict that names its evidence. Best-effort — an
// unnamed occupant still fails the leg.
function portOccupant(candidate) {
  const ss = spawnSync("ss", ["-ltnp", `sport = :${candidate}`], {
    encoding: "utf8",
  });
  const line = (ss.stdout ?? "")
    .split("\n")
    .find((entry) => entry.includes(`:${candidate}`));
  return line ? line.trim().replace(/\s+/g, " ") : "occupant unreadable";
}

if (!(await portFree(port))) {
  fail(`port ${port} is busy before the run — another suite owns it; pass --port`, 1);
}

// The Playwright CLI, from the root install the caller ran.
const playwrightBin = join(repoRoot, "node_modules", ".bin", "playwright");
if (!existsSync(playwrightBin)) {
  fail(
    "playwright is not installed at the repo root — run `npm install` there first (the shard does not own the install)",
    1,
  );
}

// The browser binary, ensured the canonical way (idempotent).
const install = spawnSync(playwrightBin, ["install", "chromium"], {
  cwd: repoRoot,
  stdio: "inherit",
});
if (install.status !== 0) {
  fail("playwright install chromium failed", 1);
}

const scratch = mkdtempSync(join(tmpdir(), `workhorse-e2e-shard-${shard}-`));
console.log(
  `e2e-shard ${shard}: ${specs.length} spec file(s), port ${port}, workers ${workers}, scratch ${scratch}`,
);
const child = spawn(playwrightBin, ["test", ...specs, "--workers", workers], {
  cwd: repoRoot,
  stdio: "inherit",
  env: { ...process.env, E2E_PORT: port, E2E_SCRATCH: scratch },
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    child.kill(signal);
  });
}
const status = await new Promise((resolve) => {
  child.on("close", (code) => resolve(code ?? 1));
});

// The final leg: the port must be free again within the
// teardown grace (see portFreeWithin — one instantaneous
// probe races the webServer's asynchronous release and
// fires on clean runs).
if (!(await portFreeWithin(port, TEARDOWN_GRACE_MS))) {
  console.error(
    `e2e-shard ${shard}: TEARDOWN_FAIL — port ${port} still bound ${TEARDOWN_GRACE_MS}ms after the run (${portOccupant(port)})`,
  );
  process.exit(status === 0 ? TEARDOWN_EXIT : 1);
}
console.log(`e2e-shard ${shard}: port ${port} free after the run`);
process.exit(status === 0 ? 0 : 1);
