#!/usr/bin/env tsx
// Adapter-contract tests for the LIVE adapter (S8 deliverable
// 4): the adapter is driven against the pipeline-served
// payloads captured by tools/live/dump_served.py from the
// real moved server over the S1-capture fixture store
// (tools/live/payloads-pipeline.json — the same capture the
// served-payload diff verdict rests on). A stub fetch serves
// those payloads at the /api/v1 routes; every assertion is
// about the adapter's projections: schema conformance of the
// mapped job views, the vocabulary translations, the
// activity join, the served classification axis, the served
// detail projections + config blocks, the G5 acked window,
// the config save's POST round trip and refusal matrix, and
// the G8 verb refusals. Exit 1 on any failure.
//
// Provenance discipline: the adapter must read the axis,
// the config blocks, and the acked window FROM the payloads
// — so the classification assertions first edit one served
// axis in the payload (the adapter has no table to fall
// back on; what it renders is what the payload says), and
// the storage-watch config block exists ONLY in the stub's
// served detail (the pipeline's backfilled block, as the
// landed registry serves it — the fixture capture's entries
// carry no blocks and serve null, asserted as such for the
// other 25).

import { readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { LiveSchedulerApi } from "../src/live/live-adapter";

const CONTRACTS = new URL("../../../../contracts/", import.meta.url);
const readJson = (rel: string) =>
  JSON.parse(readFileSync(new URL(rel, CONTRACTS), "utf8"));
const payloads = JSON.parse(
  readFileSync(new URL("./live/payloads-pipeline.json", import.meta.url), "utf8"),
);

let failures = 0;
let checks = 0;
function verdict(ok: boolean, label: string, detail?: string) {
  checks++;
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
}

/** Canonical deep-equal (object key order normalized). */
function canon(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canon).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([k, v]) => `${JSON.stringify(k)}:${canon(v)}`);
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}
const deepEqual = (a: unknown, b: unknown) => canon(a) === canon(b);

const ajv = new Ajv2020({ strict: false });
addFormats(ajv);
ajv.addSchema(readJson("schemas/job-view.schema.json"));
const validateJobView = ajv.getSchema("job-view.schema.json")!;

// --- the stub bridge: the captured payloads at their routes ----
// storage-watch's served detail is augmented with the config
// block the pipeline's landed registry serves for it
// (pipeline/scheduling/jobs/storage-watch.yaml, version 1) —
// the fixture capture's entries carry no blocks, so without
// this the block would exist nowhere in the stubbed world
// and the adapter's config path would have nothing served
// to read.
const SW_CONFIG_BLOCK = {
  version: 1,
  knobs: [
    {
      key: "home_low_free_gb",
      label: "Low tier — home free space below",
      type: "integer",
      unit: "GB",
      value: 50,
      min: 1,
      max: 500,
    },
    {
      key: "home_critical_free_gb",
      label: "Critical tier — home free space below",
      type: "integer",
      unit: "GB",
      value: 45,
      min: 1,
      max: 500,
    },
  ],
  constraints: [
    {
      kind: "lt",
      left: "home_critical_free_gb",
      right: "home_low_free_gb",
      message: "The critical tier must sit below the low tier.",
    },
  ],
};
const swDetailServed = JSON.parse(
  JSON.stringify(payloads.details["storage-watch"]),
);
swDetailServed.detail.config = SW_CONFIG_BLOCK;

// Provenance probe: edit bridge-drain's SERVED axis (list +
// detail) to operator/null/null. If the adapter carried its
// own classification table it would keep rendering the
// table's venue/dispatch answer; reading the payload is the
// only way it can render this one.
for (const job of payloads.jobs.jobs as Array<Record<string, any>>) {
  if (job.id === "bridge-drain") {
    job.audience = "operator";
    job.family = null;
    job.open_in = null;
  }
}
const bdDetailServed = payloads.details["bridge-drain"] as Record<string, any>;
bdDetailServed.audience = "operator";
bdDetailServed.family = null;
bdDetailServed.open_in = null;

const routes: Record<string, unknown> = {
  "/api/v1/overview": payloads.overview,
  "/api/v1/jobs": payloads.jobs,
  "/api/v1/pings": payloads.pings,
  "/api/v1/pings/recent": payloads.recent_pings,
  "/api/v1/ledger?limit=500": payloads.ledger,
};
for (const [id, detail] of Object.entries(payloads.details)) {
  routes[`/api/v1/jobs/${id}`] = detail;
}
routes["/api/v1/jobs/storage-watch"] = swDetailServed;

// The stub's config writer: the server's guarded save
// (pipeline configblocks.py) emulated at its route — the
// refusal names and details are the server's own forms.
const stubConfig = {
  version: 1,
  values: { home_low_free_gb: 50, home_critical_free_gb: 45 } as Record<
    string,
    number
  >,
};
function stubConfigView() {
  return {
    version: stubConfig.version,
    knobs: SW_CONFIG_BLOCK.knobs.map((knob) => ({
      ...knob,
      value: stubConfig.values[knob.key]!,
    })),
    constraints: SW_CONFIG_BLOCK.constraints,
  };
}
function postConfig(url: string, body: string) {
  const reply = (status: number, payload: unknown) => ({
    ok: status < 300,
    status,
    json: async () => payload,
  });
  const match = /^\/api\/v1\/jobs\/([^/]+)\/config$/.exec(url);
  const jobId = match ? decodeURIComponent(match[1]!) : "";
  if (jobId !== "storage-watch" && jobId !== "flap-watch") {
    return reply(404, {
      ok: false,
      error: "not_found",
      detail: `no such job: ${jobId}`,
    });
  }
  if (jobId === "flap-watch") {
    return reply(400, {
      ok: false,
      error: "bad_request",
      detail: "flap-watch carries no editable config.",
    });
  }
  const req = JSON.parse(body) as {
    version: number;
    values: Record<string, number>;
  };
  if (req.version !== stubConfig.version) {
    return reply(409, {
      ok: false,
      error: "no_match",
      detail:
        `storage-watch config changed since it was loaded ` +
        `(now version ${stubConfig.version}) — reload and re-apply.`,
    });
  }
  const merged = { ...stubConfig.values };
  for (const [key, value] of Object.entries(req.values)) {
    const knob = SW_CONFIG_BLOCK.knobs.find((k) => k.key === key);
    if (!knob) {
      return reply(400, {
        ok: false,
        error: "bad_request",
        detail: `Unknown knob ${key}.`,
      });
    }
    if (value < knob.min || value > knob.max) {
      return reply(400, {
        ok: false,
        error: "bad_request",
        detail: `${knob.label} must be between ${knob.min} and ${knob.max} ${knob.unit}.`,
      });
    }
    merged[key] = value;
  }
  if (!(merged.home_critical_free_gb! < merged.home_low_free_gb!)) {
    return reply(400, {
      ok: false,
      error: "bad_request",
      detail: "The critical tier must sit below the low tier.",
    });
  }
  stubConfig.values = merged;
  stubConfig.version += 1;
  return reply(200, { ok: true, version: stubConfig.version, config: stubConfigView() });
}

const fetchFn = async (
  url: string,
  init?: { method?: string; body?: string },
) => {
  if (init?.method === "POST") return postConfig(url, init.body ?? "{}");
  const body = routes[url];
  if (body === undefined) {
    return { ok: false, status: 404, json: async () => ({}) };
  }
  return { ok: true, status: 200, json: async () => body };
};

const api = new LiveSchedulerApi({ fetchFn, pollMs: 60_000 });
await api.ready();
verdict(api.lastError === null, "live adapter: first refresh succeeds", api.lastError ?? undefined);

// --- job views ---------------------------------------------------
const jobs = api.listJobs();
const servedJobs = payloads.jobs.jobs as Array<Record<string, any>>;
verdict(jobs.length === 26, "live jobs: 26 served", `${jobs.length}`);
verdict(
  deepEqual(jobs.map((j) => j.id), servedJobs.map((j) => j.id)),
  "live jobs: order matches the served order",
);
for (const job of jobs) {
  verdict(
    validateJobView(job) === true,
    `job view ${job.id} validates against job-view.schema.json`,
    validateJobView.errors?.map((e) => e.message).join("; ") || undefined,
  );
}
const JOB_KEYS = [
  "audience", "cadence", "cadence_label", "expected_wakes_per_day",
  "failures_24h", "family", "failure_streak", "id", "kind",
  "last_activity", "last_run", "next_due", "next_due_in_secs",
  "open_in", "owner", "report_mode", "runs_24h", "status",
  "suspend_reason", "timezone",
];
verdict(
  jobs.every((j) => deepEqual(Object.keys(j).sort(), [...JOB_KEYS].sort())),
  "live job views carry exactly the app key set (no migrated, no activity_24h)",
);

const byId = new Map(jobs.map((j) => [j.id, j]));
const servedById = new Map(servedJobs.map((j) => [j.id, j]));
const storageWatch = byId.get("storage-watch")!;
const servedSw = servedById.get("storage-watch")!;
verdict(
  storageWatch.runs_24h === servedSw.runs_24h.total &&
    storageWatch.failures_24h === servedSw.runs_24h.failed &&
    storageWatch.failure_streak === 2 &&
    storageWatch.report_mode === servedSw.report_when &&
    storageWatch.expected_wakes_per_day === servedSw.expected_wake_per_day,
  "storage-watch: 24h totals, streak, report mode, wakes join from the served fields",
);
verdict(
  jobs.every(
    (j) =>
      j.runs_24h === servedById.get(j.id)!.runs_24h.total &&
      j.failures_24h === servedById.get(j.id)!.runs_24h.failed &&
      j.report_mode === servedById.get(j.id)!.report_when,
  ),
  "every job: totals + report mode track the served payload",
);

// --- run vocabulary + labels verbatim ----------------------------
const flapWatch = byId.get("flap-watch")!;
verdict(
  flapWatch.last_run?.status === "ok" &&
    flapWatch.last_run?.exit_code === 3 &&
    flapWatch.last_run?.label === "Exit 3 · normal",
  "flap-watch last run: accepted-nonzero stays ok, label verbatim",
);
verdict(
  storageWatch.last_run?.status === "failed" &&
    storageWatch.last_run?.label === "Failed · exit 1",
  "storage-watch last run: server failure → app failed, label verbatim",
);
const flapDetail = api.getJob("flap-watch")!;
verdict(
  flapDetail.recent_runs.some((r) => r.status === "could_not_start"),
  "spawn_error translates to could_not_start",
);
verdict(
  flapDetail.recent_runs.some((r) => r.status === "timeout"),
  "timeout passes through untranslated",
);
const swDetail = api.getJob("storage-watch")!;
const allRuns = [
  ...jobs.map((j) => j.last_run).filter((r) => r !== null),
  ...servedJobs.flatMap((j) => {
    const d = api.getJob(j.id);
    return d ? d.recent_runs : [];
  }),
];
verdict(
  allRuns.every((r) => r.duration_label === null && r.detail === null),
  "G1/G2: live runs serve duration_label/detail as null (dropped on the live surface)",
  `${allRuns.length} runs`,
);

// --- activity (G7) -----------------------------------------------
const bridgeDrain = byId.get("bridge-drain")!;
const servedBd = servedById.get("bridge-drain")!;
verdict(
  bridgeDrain.last_activity?.state === "pending" &&
    bridgeDrain.last_activity?.label === "Ping pending" &&
    bridgeDrain.last_activity?.ping_id === "f10000000001" &&
    bridgeDrain.last_activity?.since === servedBd.last_activity.ts,
  "bridge-drain activity: served state + label, ping_id joined from pending pings, since = served ts",
);
verdict(
  jobs.filter((j) => j.kind === "scripted").every((j) => j.last_activity === null),
  "scripted jobs serve no activity (the pinned behavior)",
);

// --- classification (the served axis — no local table) -----------
verdict(
  jobs.every((j) => {
    const served = servedById.get(j.id)!;
    return (
      j.audience === served.audience &&
      j.family === served.family &&
      j.open_in === served.open_in
    );
  }),
  "classification: every job's axis is the served payload's axis, verbatim",
);
verdict(
  byId.get("bridge-drain")!.audience === "operator" &&
    byId.get("bridge-drain")!.family === null &&
    byId.get("bridge-drain")!.open_in === null,
  "provenance probe: bridge-drain renders the payload's edited axis (operator), not any local table",
);
const counts = {
  operator: jobs.filter((j) => j.audience === "operator").length,
  builtin: jobs.filter((j) => j.audience === "builtin").length,
  family: jobs.filter((j) => j.family !== null).length,
  direct: jobs.filter((j) => j.audience === "builtin" && j.family === null).length,
};
verdict(
  counts.operator === 7 && counts.builtin === 19 && counts.family === 12 && counts.direct === 7,
  "classification counts follow the served payloads (6+probe operator / 19 built-in / 12 family / 7 direct)",
  JSON.stringify(counts),
);
verdict(
  storageWatch.audience === "builtin" && storageWatch.family === null && storageWatch.open_in === null,
  "storage-watch is the amendment's direct built-in (as served)",
);

// --- overview -----------------------------------------------------
const overview = api.getOverview();
verdict(
  overview.server_status === payloads.overview.status &&
    deepEqual(overview.totals_by_kind, { scripted: 25, agent: 1 }) &&
    deepEqual(overview.totals_by_status, { active: 25, suspended: 1 }) &&
    overview.outbox_aged === payloads.overview.outbox.aged &&
    deepEqual(overview.totals_24h, payloads.overview.totals_24h) &&
    overview.expected_wakes_per_day === payloads.overview.expected_wake_per_day,
  "overview: status, registry/outbox joins, 24h totals track the served payload",
);
verdict(
  deepEqual(overview.storage, payloads.overview.storage) &&
    deepEqual(overview.config, payloads.overview.config),
  "overview: storage + config blocks pass through in the served form",
);
verdict(overview.notice === null, "G3: live overview notice is null (not frozen, not served)");

// --- details -------------------------------------------------------
const details = servedJobs.map((j) => api.getJob(j.id));
verdict(details.every((d) => d !== null), "all 26 job details served after ready()");
const servedDetailOf = (id: string) =>
  id === "storage-watch"
    ? swDetailServed
    : (payloads.details[id] as Record<string, any>);
verdict(
  details.every((d) => deepEqual(d!.config, servedDetailOf(d!.id).detail.config)),
  "config on every live detail is the served block (storage-watch's backfilled block; null as served for the other 25)",
);
verdict(
  details.every((d) => {
    const served = servedDetailOf(d!.id).detail;
    return (
      deepEqual(d!.catalog, served.catalog) &&
      d!.suspended_on === served.suspended_on &&
      d!.self_removal === served.self_removal
    );
  }),
  "detail projections pass through as served (catalog axis / suspended_on / self_removal — flap-watch's catalog included)",
);
const bdDetail = api.getJob("bridge-drain")!;
verdict(
  deepEqual(bdDetail.ping_history, payloads.details["bridge-drain"].ping_history),
  "bridge-drain ping history: the served event rows pass through verbatim",
  `${bdDetail.ping_history.length} rows`,
);
verdict(
  deepEqual(bdDetail.recent_dues.map((d) => d.outcome), ["pending", "collapsed", "collapsed"]) &&
    deepEqual(bdDetail.recent_dues.map((d) => d.collapsed), [0, 2, 1]) &&
    bdDetail.recent_dues[0]!.due === servedBd.next_due,
  "bridge-drain recent dues: pending row from next_due, then the served due records under the app's projection (collapsed > 0 reads collapsed)",
);
verdict(
  swDetail.title === payloads.details["storage-watch"].detail.title &&
    deepEqual(swDetail.report, payloads.details["storage-watch"].detail.report) &&
    swDetail.classification === payloads.details["storage-watch"].detail.classification,
  "detail block: title, report, classification project from the served block",
);

// --- pings ----------------------------------------------------------
const pings = api.listPings();
verdict(
  deepEqual(pings.map((p) => p.id), ["f10000000003", "f10000000001", "f10000000004"]),
  "pending pings: oldest first, as served",
);
verdict(
  pings[0]!.overdue === true && pings[0]!.job_id === "storage-watch",
  "the aged escalation reads overdue",
);
verdict(
  pings.find((p) => p.id === "f10000000001")?.summary === "bridge-drain — drain episode open" &&
    pings.find((p) => p.id === "f10000000003")?.summary === "storage-watch",
  "ping summary: detail.summary when written, job_id fallback otherwise",
);
// --- G5: the acked window (GET /api/v1/pings/recent) --------------
const recent = api.listRecentPings();
const servedRecent = payloads.recent_pings.pings as Array<Record<string, any>>;
verdict(
  deepEqual(
    recent.map((p) => p.id),
    servedRecent.map((p) => p.id),
  ),
  "G5: listRecentPings serves the acked window from the route (newest ack first, as served)",
  recent.map((p) => p.id).join(", "),
);
verdict(
  recent.every(
    (p) => p.state === "acked" && p.overdue === false && p.acked_at !== undefined,
  ) &&
    recent.find((p) => p.id === "f10000000008")?.summary ===
      "bridge-drain — drain episode open" &&
    recent.find((p) => p.id === "f10000000006")?.summary === "flap-watch",
  "G5 window rows: acked records, never overdue, summary from detail.summary with job_id fallback",
);
verdict(
  recent.every((p) => {
    const served = servedRecent.find((s) => s.id === p.id)!;
    const expected = Math.max(
      0,
      Math.floor(
        (Date.parse(payloads.overview.server_now) -
          Date.parse(served.created)) /
          1000,
      ),
    );
    return p.age_secs === expected;
  }),
  "G5 window ages: arithmetic over the served created vs the served server_now",
);

// --- ledger -----------------------------------------------------------
const ledger = api.getLedger(500);
verdict(
  ledger.served_at === payloads.ledger.served_at &&
    deepEqual(ledger.events, payloads.ledger.events),
  "ledger feed passes through verbatim (36 seeded events, detail strings included)",
  `${ledger.events.length} events`,
);
verdict(api.getLedger(2).events.length === 2, "getLedger slices to the requested limit");

// --- G8: the verb dispositions ---------------------------------------
const runNow = api.runNow("storage-watch");
const enable = api.setJobEnabled("storage-watch", false);
const ack = api.ackPing("f10000000001", "operator");
verdict(
  !runNow.ok && runNow.error === "outside_scope",
  "G8: runNow refuses on the live adapter (outside_scope — the read-only rule stands)",
);
verdict(
  !enable.ok && enable.error === "outside_scope",
  "G8: setJobEnabled refuses on the live adapter (outside_scope)",
);
verdict(
  !ack.ok && ack.error === "outside_scope",
  "G8: ackPing refuses on the live adapter (outside_scope)",
);
// --- the config save: POST /api/v1/jobs/<id>/config ----------------
const saved = await api.saveConfig("storage-watch", 1, {
  home_low_free_gb: 40,
  home_critical_free_gb: 30,
});
verdict(saved.ok === true, "saveConfig: the POST round trip accepts a valid save");
const swAfterSave = api.getJob("storage-watch")!;
verdict(
  swAfterSave.config?.version === 2 &&
    swAfterSave.config.knobs.find((k) => k.key === "home_low_free_gb")?.value ===
      40 &&
    swAfterSave.config.knobs.find((k) => k.key === "home_critical_free_gb")
      ?.value === 30,
  "saveConfig: the cached detail carries the served response config (version 2, new values) when the save resolves",
);
const staleSave = await api.saveConfig("storage-watch", 1, {
  home_low_free_gb: 35,
  home_critical_free_gb: 30,
});
verdict(
  !staleSave.ok &&
    staleSave.error === "no_match" &&
    staleSave.detail.includes("changed since it was loaded (now version 2)"),
  "saveConfig: stale-stamp refusal surfaces whole (no_match, the server's detail verbatim)",
);
verdict(
  api.getJob("storage-watch")!.config?.version === 2,
  "saveConfig: the stale refusal applied nothing (cached config unmoved)",
);
const oorSave = await api.saveConfig("storage-watch", 2, {
  home_low_free_gb: 9999,
  home_critical_free_gb: 25,
});
verdict(
  !oorSave.ok &&
    oorSave.error === "bad_request" &&
    oorSave.detail.includes("must be between 1 and 500 GB"),
  "saveConfig: out-of-range refusal surfaces whole (bad_request, the server's range detail)",
);
const constraintSave = await api.saveConfig("storage-watch", 2, {
  home_low_free_gb: 40,
  home_critical_free_gb: 40,
});
verdict(
  !constraintSave.ok &&
    constraintSave.error === "bad_request" &&
    constraintSave.detail === "The critical tier must sit below the low tier.",
  "saveConfig: constraint refusal surfaces whole (bad_request, the constraint's own message)",
);
const knoblessSave = await api.saveConfig("flap-watch", 1, { anything: 1 });
verdict(
  !knoblessSave.ok &&
    knoblessSave.error === "bad_request" &&
    knoblessSave.detail.includes("carries no editable config"),
  "saveConfig: a knobless entry refuses bad_request (no fabricated form)",
);
const unknownSave = await api.saveConfig("no-such-job", 1, { anything: 1 });
verdict(
  !unknownSave.ok && unknownSave.error === "not_found",
  "saveConfig: an unknown job refuses not_found",
);

// --- bridge-down: last-good / empty snapshot --------------------------
const down = new LiveSchedulerApi({
  fetchFn: async () => {
    throw new Error("bridge down");
  },
});
await down.ready();
verdict(
  down.listJobs().length === 0 &&
    down.getOverview().server_status === "unreachable" &&
    down.lastError !== null,
  "bridge-down before first load: empty snapshot reads unreachable, error recorded, ready still resolves",
);

console.log(`\n${checks} checks, ${failures} failures`);
process.exit(failures > 0 ? 1 : 0);
