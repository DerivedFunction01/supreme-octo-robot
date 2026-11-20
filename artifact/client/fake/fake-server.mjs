// FU-2 fake — a working fake of the venue panel backend for
// the integrated client's Budget view: a fake served state
// (this file's in-memory entries) behind the real action
// transport (POST ./actions, the SDK's {action, args} →
// {data} seam), with the real built client (../dist) served
// statically in front of it. Every control the view offers
// works against the fake: setBudget mutates the addressed
// (venue, account) entry's caps and the next getStatePart
// serves them back — no other entry moves.
//
// The fake served set is the FU-2 shape of record: two Colab
// accounts with different balances/caps/spend, an EC2 venue
// with its own budget, and a local venue whose entry carries
// budget: null (no budget at all).
//
// Run:  node fake-server.mjs            (port FAKE_PORT|8971)
//       GET /__state  → the fake entries as currently served
//       every setBudget call is appended to fake-actions.log

import { appendFileSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const distDir = join(here, "..", "dist");
const logPath = join(here, "fake-actions.log");
const port = Number(process.env.FAKE_PORT || 8971);

// The mutable fake state: caps writes land here and are
// served back on the next read, exactly as the real core's
// config writes are.
const entries = [
  {
    venue: "colab",
    account: "primary",
    label: "Colab Primary",
    credential: "live",
    budget: {
      balance: 500,
      day_spent: 12.5,
      month_spent: 120,
      standing_day_spent: 1.5,
      caps: { daily: 40, monthly: 300, standing_daily: 4 },
    },
  },
  {
    venue: "colab",
    account: "backup",
    label: "Colab Backup",
    credential: "not-brought-in",
    budget: {
      balance: null,
      day_spent: 3.25,
      month_spent: 30,
      standing_day_spent: null,
      caps: { daily: 25, monthly: 150, standing_daily: null },
    },
  },
  {
    venue: "ec2",
    account: "primary",
    label: "EC2 Main",
    credential: null,
    budget: {
      balance: 220.5,
      day_spent: 8,
      month_spent: 64,
      standing_day_spent: null,
      caps: { daily: 20, monthly: 200, standing_daily: null },
    },
  },
  { venue: "local", budget: null },
];

function budgetPart() {
  const home = entries.filter((e) => e.venue === "colab" && e.budget);
  const primary = home.find((e) => e.account === "primary");
  return {
    venue: "colab",
    budget: {
      ...primary.budget,
      accounts: home.map((e) => ({
        venue: e.venue,
        account: e.account,
        label: e.label,
        credential: e.credential,
        balance: e.budget.balance,
        day_spent: e.budget.day_spent,
        month_spent: e.budget.month_spent,
        standing_day_spent: e.budget.standing_day_spent,
        caps: e.budget.caps,
      })),
    },
    budgets: entries,
  };
}

const PARTS = {
  records: { records: [], access: [] },
  specs: { specs: [] },
  grant: { grant: null, envelope: null },
  orphans: { orphans: [] },
  listeners: { listeners: {} },
};

function envelope(payload) {
  return { status: 200, payload, error: null };
}

function handleAction(action, args) {
  if (action === "getStatePart") {
    const part = args?.part;
    if (part === "budget") return envelope(budgetPart());
    return envelope(PARTS[part] ?? {});
  }
  if (action === "getLeaseOutbox") return envelope({ events: [] });
  if (action === "setBudget") {
    const body = args?.body ?? {};
    appendFileSync(logPath, JSON.stringify({ action, body }) + "\n");
    const entry = entries.find(
      (e) => e.venue === body.venue && e.account === body.account && e.budget,
    );
    if (!entry) {
      return { status: 400, payload: null, error: "no such budget entry" };
    }
    const caps = entry.budget.caps;
    if ("daily_cu_budget" in body) caps.daily = body.daily_cu_budget;
    if ("monthly_cu_budget" in body) caps.monthly = body.monthly_cu_budget;
    if ("standing_daily_cu_cap" in body) caps.standing_daily = body.standing_daily_cu_cap;
    return envelope({
      action: "caps-updated",
      venue: entry.venue,
      account: entry.account,
      caps: { ...caps },
    });
  }
  // Any other action the shell or sibling views call gets a
  // benign empty envelope; the Budget view's own surface is
  // fully served above.
  return envelope({});
}

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

const server = createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (req.method === "POST" && url.pathname === "/actions") {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      let data;
      try {
        const { action, args } = JSON.parse(raw);
        data = handleAction(action, args ?? {});
      } catch (e) {
        data = { status: 500, payload: null, error: String(e) };
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ data }));
    });
    return;
  }
  if (req.method === "GET" && url.pathname === "/__state") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(entries));
    return;
  }
  const rel = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const path = normalize(join(distDir, rel));
  if (!path.startsWith(distDir)) {
    res.writeHead(403).end();
    return;
  }
  try {
    const body = readFileSync(path);
    res.writeHead(200, {
      "content-type": MIME[extname(path)] || "application/octet-stream",
      "content-length": statSync(path).size,
    });
    res.end(body);
  } catch {
    res.writeHead(404).end("not found");
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`fake venue panel on http://127.0.0.1:${port}/`);
});
