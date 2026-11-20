// FU-2 fake proof — drives the real built client (../dist)
// in a headless Chromium against the fake venue panel
// (fake-server.mjs) and asserts the per-venue/account budget
// distinction end to end:
//
//   1. each served budget renders distinctly, with its own
//      figures (two Colab accounts, one EC2 venue);
//   2. the local venue — served with budget: null — renders
//      no budget card, no figures, nothing budget-shaped;
//   3. the EC2 card's cap editor, saved with a new daily cap,
//      changes that budget alone: the fake's log shows one
//      setBudget addressed (ec2, primary), the re-served card
//      shows the new cap, and the other budgets' figures and
//      caps are unchanged.
//
// Run:  node proof.mjs        (exit 0 = every assertion held)
// Needs: ../dist built (bun run build:client) and a
// Playwright-cached Chromium under the home directory's
// .cache/ms-playwright.

import { spawn } from "node:child_process";
import { existsSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const port = Number(process.env.FAKE_PORT || 8971);
const base = `http://127.0.0.1:${port}`;
const logPath = join(here, "fake-actions.log");

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

function chromiumPath() {
  const root = join(homedir(), ".cache", "ms-playwright");
  const candidates = [];
  for (const dir of readdirSync(root).sort().reverse()) {
    candidates.push(join(root, dir, "chrome-linux", "headless_shell"));
    candidates.push(join(root, dir, "chrome-linux", "chrome"));
  }
  return candidates.find((p) => existsSync(p));
}

/* ---------------- tiny CDP client ---------------- */

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.seq = 0;
    this.pending = new Map();
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }
}

async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  return new Cdp(ws);
}

/* ---------------- main ---------------- */

rmSync(logPath, { force: true });
const server = spawn("node", [join(here, "fake-server.mjs")], {
  env: { ...process.env, FAKE_PORT: String(port) },
  stdio: ["ignore", "pipe", "pipe"],
});
const browserPath = chromiumPath();
if (!browserPath) {
  console.error("no cached Chromium found under the home .cache/ms-playwright");
  server.kill();
  process.exit(2);
}
const browser = spawn(
  browserPath,
  [
    "--remote-debugging-port=0",
    "--remote-debugging-address=127.0.0.1",
    "--no-sandbox",
    "--disable-gpu",
    `--user-data-dir=${join(here, ".proof-profile")}`,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"] },
);

const wsUrl = await new Promise((resolve, reject) => {
  let buf = "";
  browser.stderr.on("data", (c) => {
    buf += c;
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) resolve(m[1]);
  });
  setTimeout(() => reject(new Error("browser DevTools URL never appeared")), 20000);
});

let exitCode = 0;
try {
  // Wait for the fake server to answer.
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`${base}/__state`);
      if (r.ok) break;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250));
  }

  const cdp = await connect(wsUrl);
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  await cdp.send("Page.enable", {}, sessionId);
  await cdp.send("Runtime.enable", {}, sessionId);

  const evaluate = async (expression) => {
    const out = await cdp.send(
      "Runtime.evaluate",
      { expression, returnByValue: true, awaitPromise: true },
      sessionId,
    );
    if (out.exceptionDetails) {
      const desc =
        out.exceptionDetails.exception?.description ||
        out.exceptionDetails.text ||
        "evaluate failed";
      throw new Error(desc);
    }
    return out.result.value;
  };

  const waitFor = async (expression, seconds = 30) => {
    const deadline = Date.now() + seconds * 1000;
    for (;;) {
      try {
        if (await evaluate(expression)) return true;
      } catch { /* page still loading — keep polling */ }
      if (Date.now() > deadline) return false;
      await new Promise((r) => setTimeout(r, 400));
    }
  };

  await cdp.send("Page.navigate", { url: `${base}/#/runner/budget` }, sessionId);

  const text = () => evaluate(`document.body.innerText`);
  check(
    "budget view renders against the fake",
    await waitFor(`document.body.innerText.includes("Colab Primary")`),
  );
  const body = await text();

  // 1 — distinct budgets, own figures.
  check("Colab Primary card with its figures",
    body.includes("Colab Primary") && body.includes("500 CU") &&
    body.includes("12.5 of 40 CU") && body.includes("120 of 300 CU"));
  check("Colab Backup card, distinct from Primary",
    body.includes("Colab Backup") && body.includes("3.25 of 25 CU") &&
    body.includes("30 of 150 CU"));
  check("EC2 Main card with its own figures",
    body.includes("EC2 Main") && body.includes("220.5 CU") &&
    body.includes("8 of 20 CU") && body.includes("64 of 200 CU"));

  // 2 — the local venue: no card, no editor, nothing.
  const editButtons = await evaluate(
    `[...document.querySelectorAll("button")].filter(b => b.textContent.trim() === "Edit caps").length`,
  );
  check("exactly three cap editors (one per budgeted entry)", editButtons === 3,
    `found ${editButtons}`);
  check("no budget UI for the local venue",
    !/local/i.test(body) && !body.includes("This machine"));

  // 3 — edit the EC2 card's daily cap: 20 → 99.
  const opened = await evaluate(`(() => {
    const btns = [...document.querySelectorAll("button")]
      .filter(b => b.textContent.trim() === "Edit caps");
    const btn = btns.find(b => {
      let n = b;
      while (n && !n.textContent.includes("EC2 Main")) n = n.parentElement;
      return n && !n.textContent.includes("Colab");
    });
    if (!btn) return false;
    btn.click();
    return true;
  })()`);
  check("EC2 card editor opens", opened === true);
  const edited = await waitFor(`(() => {
    const btns = [...document.querySelectorAll("button")]
      .filter(b => b.textContent.trim() === "Save caps");
    if (!btns.length) return false;
    const btn = btns[0];
    let card = btn;
    while (card && !card.textContent.includes("EC2 Main")) card = card.parentElement;
    if (!card) return false;
    const input = card.querySelector('input[type="number"]');
    if (!input) return false;
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    setter.call(input, "99");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    btn.click();
    return true;
  })()`, 10);
  check("EC2 daily cap edited and saved", edited === true);
  check("notice names the addressed budget",
    await waitFor(`document.body.innerText.includes("Budget caps updated for EC2 Main (ec2/primary)")`, 20));
  const after = await text();
  check("EC2 card re-serves with the new cap", after.includes("8 of 99 CU"));
  check("Colab budgets unchanged in the UI",
    after.includes("12.5 of 40 CU") && after.includes("3.25 of 25 CU"));

  // Server-side: exactly one addressed write; only EC2 moved.
  const state = await (await fetch(`${base}/__state`)).json();
  const byKey = Object.fromEntries(
    state.filter((e) => e.budget).map((e) => [`${e.venue}/${e.account}`, e.budget.caps]),
  );
  check("fake state: EC2 daily cap is 99", byKey["ec2/primary"]?.daily === 99);
  check("fake state: Colab caps untouched",
    byKey["colab/primary"]?.daily === 40 && byKey["colab/backup"]?.daily === 25);
  const log = existsSync(logPath) ? readFileSync(logPath, "utf8").trim().split("\n").filter(Boolean) : [];
  const writes = log.map((l) => JSON.parse(l)).filter((l) => l.action === "setBudget");
  check("exactly one setBudget call reached the fake", writes.length === 1,
    `${writes.length} calls`);
  check("the write was addressed to (ec2, primary) with the full cap set",
    writes.length === 1 && writes[0].body.venue === "ec2" &&
    writes[0].body.account === "primary" && writes[0].body.daily_cu_budget === 99 &&
    writes[0].body.monthly_cu_budget === 200 && writes[0].body.standing_daily_cu_cap === null);
} catch (e) {
  console.error("proof driver error:", e);
  exitCode = 2;
} finally {
  browser.kill();
  server.kill();
  rmSync(join(here, ".proof-profile"), { recursive: true, force: true });
}

const failed = results.filter((r) => !r.ok);
console.log(
  failed.length === 0 && exitCode === 0
    ? `\nFAKE PROOF: PASS (${results.length} assertions)`
    : `\nFAKE PROOF: FAIL (${failed.length}/${results.length} assertions failed)`,
);
process.exit(exitCode || (failed.length ? 1 : 0));
