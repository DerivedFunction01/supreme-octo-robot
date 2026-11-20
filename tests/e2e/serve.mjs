#!/usr/bin/env node
/**
 * The rendered legs' own serve route (playwright.config.ts
 * starts it as the suite's webServer): the BUILT client
 * (artifact/client/dist — the caller's `bun run
 * build:client` output) served statically, with the action
 * transport answered by the suite itself.
 *
 * The transport contract is the client's own (artifact/
 * client/src/lib/actions.ts): POST ./actions with
 * {action, args} answers {data} carrying the common
 * envelope {status, payload, error}.
 *
 * What each action class answers, and why:
 *
 * - The two reads the shell's own sections consume OUTSIDE
 *   any error boundary — getGlance and getDigest, read by
 *   the unified Settings view's Presence and Digest
 *   sections (artifact/client/src/views/attention/
 *   settings-sections.tsx) — answer the real backend's
 *   EMPTY-STATE shapes: the field-for-field forms
 *   pipeline/attention's build_glance / build_digest
 *   return over an empty store (default windows
 *   07:30/12:30/17:30 all enabled, include flags all on,
 *   presence active with no expiry, every list empty).
 *   The canned empty payload is NOT one of those shapes:
 *   the Digest section trusts a non-null payload and reads
 *   its window fields, so a {} payload crashes the
 *   Settings render — and with no boundary above it, the
 *   whole document. A leg that cannot render the surface
 *   measures the serve, not the surface.
 * - The two writes those same sections post — postPresence
 *   and postDigestPrefs — land in the serve's in-memory
 *   seeded state and are served back by the reads above,
 *   exactly the client's own working-fake pattern
 *   (artifact/client/fake/fake-server.mjs: a write mutates
 *   the fake's state, the next read serves it). A
 *   control's effect is then measured against the state
 *   the real path would paint — a presence radio's
 *   selection, a digest switch's flip — never against a
 *   canned reply that repaints nothing and would convict
 *   working controls as dead.
 * - Every other action answers the canned success
 *   envelope with an empty payload, as before.
 *
 * The guarded-writes boundary (docs/checks.md) is
 * unchanged: no leg fires a real write at a live backend,
 * nothing here persists beyond the suite's own process,
 * and a verdict over this serve route prices the rendered
 * chrome and the surfaces as the seeded state serves
 * them — not the live write paths.
 *
 * GET /__health is the config's readiness probe.
 */
import { readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const distDir = join(here, "..", "..", "artifact", "client", "dist");
const port = Number(process.env.E2E_PORT || 3510);

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

/* ---------------- the seeded state ---------------- */

// The backend's own label table (pipeline/attention/
// services/reads/model.py, MODE_LABELS) and default
// digest windows (the same module's Settings default).
const MODE_LABELS = { active: "Active", focus: "Focus", away: "Away" };
const WINDOW_TIMES = ["07:30", "12:30", "17:30"];

// The seeded store: presence as the backend's sample
// empty state carries it (active, no expiry, no
// expectation), and digest prefs in the backend's stored
// form — a windows/include map where an absent key stands
// at its default (enabled / on), per digest_windows /
// digest_include in the reads model.
const seeded = {
  presence: { mode: "active", expectation: "", expires_at: null },
  digestWindows: {},
  digestInclude: {},
};

function presenceView() {
  return {
    mode: seeded.presence.mode,
    mode_label: MODE_LABELS[seeded.presence.mode],
    expectation: seeded.presence.expectation,
    expires_at: seeded.presence.expires_at,
  };
}

function enabledTimes() {
  return WINDOW_TIMES.filter((time) => seeded.digestWindows[time] !== false);
}

/** The next enabled window after `now` (today, else
 *  tomorrow's first), or null when none is enabled — the
 *  reads model's next_window over the enabled set. */
function nextWindowAt(now) {
  const enabled = enabledTimes();
  if (enabled.length === 0) return null;
  for (const time of enabled) {
    const [h, m] = time.split(":").map(Number);
    const at = new Date(now);
    at.setHours(h, m, 0, 0);
    if (at.getTime() > now.getTime()) return at.toISOString();
  }
  const [h, m] = enabled[0].split(":").map(Number);
  const at = new Date(now);
  at.setDate(at.getDate() + 1);
  at.setHours(h, m, 0, 0);
  return at.toISOString();
}

/** build_glance over the seeded store. */
function glancePayload() {
  const now = new Date();
  return {
    contract: "api/1",
    presence: presenceView(),
    clock: { now: now.toISOString(), next_window_at: nextWindowAt(now) },
    next_due: null,
    decision_count: 0,
    handler_dots: [],
    held_count: 0,
    breakthrough_count: 0,
    breakthrough_items: [],
    down_sources: [],
  };
}

/** build_digest over the seeded store. */
function digestPayload() {
  const now = new Date();
  return {
    contract: "api/1",
    generated_at: now.toISOString(),
    window: {
      next_at: nextWindowAt(now),
      times: [...WINDOW_TIMES],
      enabled_times: enabledTimes(),
    },
    include: {
      decisions: seeded.digestInclude.decisions !== false,
      waiting: seeded.digestInclude.waiting !== false,
      fyi: seeded.digestInclude.fyi !== false,
    },
    sections: [],
    expired: [],
    programmes: [],
    stalls: [],
    staffing: { available: false, rows: [] },
    topics: [],
    parked_plans: { available: false, plans: [] },
  };
}

/* ---------------- scheduler fixtures (env-gated) ----------------
 *
 * E2E_SCHED_FIXTURES=1 turns on the captured-payload
 * scheduler portions: getJobs / getOverview answer the
 * live payloads staged in E2E_FIXTURES_DIR (live-jobs.json
 * / live-overview.json) instead of the canned empty
 * envelope, so a drive can measure a surface against the
 * real served shapes (the jobs-overflow proof). With the
 * env absent nothing changes — the qa sweep's canned
 * behaviour above is untouched, and every other action
 * keeps its seeded or canned answer either way.
 */
const SCHED_FIXTURES = process.env.E2E_SCHED_FIXTURES === "1";
let schedFixtures = null;
if (SCHED_FIXTURES) {
  const dir = process.env.E2E_FIXTURES_DIR || "";
  schedFixtures = {
    getJobs: JSON.parse(readFileSync(join(dir, "live-jobs.json"), "utf8")),
    getOverview: JSON.parse(readFileSync(join(dir, "live-overview.json"), "utf8")),
  };
  console.log(`e2e serve: scheduler fixtures ON (${dir})`);
}

/**
 * Answer one action with its payload: the seeded reads
 * and writes above; the canned empty payload for every
 * other action (the header states the boundary).
 */
function handleAction(action, args) {
  if (schedFixtures && Object.hasOwn(schedFixtures, action)) {
    return schedFixtures[action];
  }
  const body =
    args && typeof args === "object" && args.body && typeof args.body === "object"
      ? args.body
      : {};
  switch (action) {
    case "getGlance":
      return glancePayload();
    case "getDigest":
      return digestPayload();
    case "postPresence": {
      // The client's one presence write (postPresenceMode):
      // {mode, expires_at, expectation}; the real path
      // answers the PresenceView the write leaves standing.
      if (typeof body.mode === "string" && body.mode in MODE_LABELS) {
        seeded.presence = {
          mode: body.mode,
          expectation: typeof body.expectation === "string" ? body.expectation : "",
          expires_at: typeof body.expires_at === "string" ? body.expires_at : null,
        };
      }
      return presenceView();
    }
    case "postDigestPrefs": {
      // One pref per post: {window_time, window_enabled}
      // or {include_key, include_enabled}. The client
      // discards this payload and refreshes the digest
      // read; the updated digest is the honest answer.
      if (typeof body.window_time === "string" && typeof body.window_enabled === "boolean") {
        seeded.digestWindows[body.window_time] = body.window_enabled;
      }
      if (typeof body.include_key === "string" && typeof body.include_enabled === "boolean") {
        seeded.digestInclude[body.include_key] = body.include_enabled;
      }
      return digestPayload();
    }
    default:
      return {};
  }
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");
  if (req.method === "GET" && url.pathname === "/__health") {
    res.writeHead(200, { "content-type": "text/plain" });
    res.end("ok");
    return;
  }
  if (req.method === "POST" && url.pathname === "/actions") {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", () => {
      let payload = {};
      try {
        const parsed = JSON.parse(raw);
        payload = handleAction(parsed.action, parsed.args ?? {});
      } catch {
        // An unparseable body names no action: the canned
        // empty payload is the answer, as for any action
        // the seeded state does not carry.
        payload = {};
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ data: { status: 200, payload, error: null } }));
    });
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
  console.log(`e2e serve: built client on http://127.0.0.1:${port}/`);
});
