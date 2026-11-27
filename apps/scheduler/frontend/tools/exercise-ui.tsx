#!/usr/bin/env tsx
// Control exercise — renders the real app (Preview → App → the
// mock adapter) in jsdom and drives every storyboarded control
// once, asserting the served state actually changed. This is the
// done-evidence that the buttons work in the mock sense: state
// changes, flows, and validation, end-to-end through the UI.

// Split for size: the jsdom harness and DOM driver
// helpers live in ./exercise-harness, and the phone
// phase in ./exercise-phone; this entry keeps the
// desktop frames and the final tally.
import {
  Preview,
  React,
  act,
  bodyText,
  buttons,
  check,
  click,
  clickRadio,
  createRoot,
  inputValueByLabel,
  mockApi,
  results,
  setInputByLabel,
  setSearch,
  sleep,
  waitFor,
  window,
} from "./exercise-harness";
import { runPhonePhase } from "./exercise-phone";

// ---------------------------------------------------------------
const root = createRoot(window.document.getElementById("root")!);
await act(async () => {
  root.render(
    React.createElement(React.StrictMode, null, React.createElement(Preview)),
  );
});
await sleep(300);

// --- Frame 1 · Overview ----------------------------------------
check("overview renders", bodyText().includes("Overview"));
check(
  "flap NoticeRow renders (storyboard text)",
  bodyText().includes("Write-denial flap active.") &&
    bodyText().includes("shell-class writes route through the ops bin"),
);
// The counts split (contract 09 amendment): Status counts the
// OPERATOR's jobs (5 of 6 — the lane watchdog is suspended);
// built-ins summarize on their own row and never inflate it.
check("overview jobs-enabled counts operator jobs only", bodyText().includes("5 of 6"));
check(
  "overview built-ins summary row (20 running)",
  bodyText().includes("Built-ins") &&
    bodyText().includes("Internal pipeline loops") &&
    bodyText().includes("20 running"),
);
check(
  "overview recent jobs are operator-only (storage-watch is a built-in now)",
  !buttons().some((b) => (b.textContent ?? "").includes("storage-watch")),
);
check("overview next wake row", bodyText().includes("Next wake"));
check("overview last outcome row", bodyText().includes("Last outcome"));
check(
  "sidebar at the kit shell's 224px width, counts (jobs badge / pings hot)",
  window.document.querySelector('[class*="w-[224px]"]') !== null &&
    bodyText().includes("Jobs") &&
    bodyText().includes("Pings"),
);
check(
  "sidebar Jobs badge counts operator jobs only (6)",
  buttons().some(
    (b) => (b.textContent ?? "").replace(/\s+/g, "") === "Jobs6",
  ),
);
// The shell's one search string filters Overview's own job
// rows (the recent operator jobs), with the Jobs view's
// predicate. Expectations derive from the store, not from
// assumed seed order.
const expectedRecent = mockApi
  .listJobs()
  .filter((j) => j.audience === "operator" && j.status === "active" && j.last_run)
  .sort((a, b) => Date.parse(b.last_run!.ts) - Date.parse(a.last_run!.ts))
  .slice(0, 3)
  .map((j) => j.id);
check(
  "overview recent-3 render (store-derived)",
  expectedRecent.length === 3 &&
    expectedRecent.every((id) => bodyText().includes(id)),
  expectedRecent.join(", "),
);
await setSearch(expectedRecent[0]!);
await sleep(200);
check(
  "overview search filters its job rows",
  bodyText().includes(expectedRecent[0]!) &&
    !bodyText().includes(expectedRecent[1]!) &&
    !bodyText().includes(expectedRecent[2]!),
);
await setSearch("zzz-no-such-job");
await sleep(200);
check(
  "overview search no-match state is honest",
  bodyText().includes("No jobs match this filter") &&
    !bodyText().includes(expectedRecent[0]!),
);
await setSearch("");
await sleep(150);
check(
  "overview search clear restores all its rows",
  expectedRecent.every((id) => bodyText().includes(id)),
);

// --- Frame 2 · Jobs ---------------------------------------------
// Arrive via the Overview's Built-ins summary row — it routes
// to the Jobs view where the Built-in group lives.
check("overview built-ins row navigates to Jobs", await click("Built-ins"));
await sleep(200);
check(
  "jobs subtitle counts the split (derived)",
  bodyText().includes("26 entries · 6 yours · 20 built-in"),
);
check(
  "jobs groups render (Yours + Built-in with the running summary)",
  bodyText().includes("Yours") && bodyText().includes("Built-in · 20 running"),
);
check("job row: bridge-wake listed", bodyText().includes("bridge-wake"));
check(
  "job chip: suspended renders Disabled",
  bodyText().includes("paywatch-lane-watchdog") && bodyText().includes("Disabled"),
);
check(
  "job sub: cadence kind + label served",
  bodyText().includes("Interval · hourly"),
);
{
  const drainRow = buttons().find((b) =>
    (b.textContent ?? "").includes("bridge-drain"),
  );
  const flapRow = buttons().find((b) =>
    (b.textContent ?? "").includes("flap-watch"),
  );
  check(
    "family built-in row carries its family tag (Dispatch)",
    !!drainRow && (drainRow.textContent ?? "").includes("Dispatch"),
  );
  check(
    "direct built-in row carries NO family tag (placement is the statement)",
    !!flapRow && (flapRow.textContent ?? "").trim() === "flap-watch",
  );
}

check("filter: Disabled segment", await clickRadio("disabled"));
await sleep(150);
check(
  "filter Disabled shows only the suspended job (built-in group hides)",
  bodyText().includes("paywatch-lane-watchdog") &&
    !bodyText().includes("bridge-wake"),
);
check("filter: All segment", await clickRadio("all"));
await sleep(150);
await setSearch("gmail");
await sleep(200);
check(
  "search filters jobs",
  bodyText().includes("weekly-gmail-otp-cleanup") &&
    !bodyText().includes("bridge-wake"),
);
await setSearch("");
await sleep(150);
// Search filters BOTH groups; a group with no matches hides.
await setSearch("storage-watch");
await sleep(200);
check(
  "search reaches the built-in group (yours hides)",
  bodyText().includes("storage-watch") &&
    !bodyText().includes("weekly-gmail-otp-cleanup") &&
    !bodyText().includes("Yours"),
);
await setSearch("colab");
await sleep(200);
check(
  "search by family prefix filters within the built-in group",
  bodyText().includes("venue-extend-guard") &&
    !bodyText().includes("storage-watch"),
);
await setSearch("");
await sleep(150);

// --- Frame 3 · Job detail (operator: memory-index-watchdog) -----
check("open job detail from row", await click("memory-index-watchdog"));
await sleep(200);
check(
  "detail subtitle (storyboard form)",
  bodyText().includes("Interval job · owned by goal:memory-md-index-watchdog"),
);
check("detail facts: schedule served", bodyText().includes("Hourly"));
check(
  "detail run history specimen",
  bodyText().includes("Completed · index fresh"),
);
check(
  "detail actions present",
  bodyText().includes("Run now") && bodyText().includes("Disable job"),
);

// run-now: the run starts, walks the engine states, completes.
check("run now (1st)", await click("Run now", { exact: true }));
await sleep(300);
check(
  "run is running (state walked to running)",
  mockApi.getJob("memory-index-watchdog")?.last_run?.status === "running",
);
// run-now during a run: contract 13 — the point skips, ledgered.
check("run now during run (2nd)", await click("Run now", { exact: true }));
await sleep(200);
check(
  "overlap skip recorded in run history",
  bodyText().includes("Skipped · previous run still active") &&
    mockApi
      .getLedger(50)
      .events.some((e) => e.kind === "skipped_overlap" && e.job_id === "memory-index-watchdog"),
);
const completed = await waitFor("memory-index-watchdog run completion", () => {
  const job = mockApi.getJob("memory-index-watchdog");
  return job?.last_run?.status === "ok";
});
check("run completes with served outcome label", completed);
check(
  "run completion ledgered with duration",
  mockApi
    .getLedger(50)
    .events.some((e) => e.detail.startsWith("memory-index-watchdog completed ·")),
);
// bridge-wake's wake minting is a built-in's behavior now — its
// detail carries no Run now, so the mint is driven adapter-side:
// the seeded plan cycle's first run is "queue empty" (no mint);
// the next cycle entry mints wakes.
mockApi.runNow("bridge-wake");
const bwRan = await waitFor("bridge-wake adapter run completion", () => {
  const job = mockApi.getJob("bridge-wake");
  return job?.last_run?.status === "ok";
});
check("bridge-wake adapter run completed", bwRan);
mockApi.runNow("bridge-wake");
const minted = await waitFor("bridge-wake wake mint", () =>
  mockApi.listPings().some((p) => p.job_id === "bridge-wake"),
);
check("bridge-wake run minted a real outbox wake ping", minted);

// pause / resume through the Enabled switch and the action rows.
let switchEl: HTMLButtonElement | null = null;
await act(async () => {
  switchEl = window.document.querySelector(
    'button[role="switch"]',
  ) as HTMLButtonElement | null;
  switchEl?.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
});
await sleep(200);
check(
  "Enabled switch suspends the job",
  mockApi.getJob("memory-index-watchdog")?.status === "suspended" &&
    bodyText().includes("Enable job"),
);
await act(async () => {
  switchEl?.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
});
await sleep(200);
check(
  "Enabled switch resumes the job",
  mockApi.getJob("memory-index-watchdog")?.status === "active",
);
check("disable via danger action row", await click("Disable job", { exact: true }));
await sleep(200);
check(
  "danger row suspended + suspend reason served",
  mockApi.getJob("memory-index-watchdog")?.status === "suspended" &&
    bodyText().includes("Suspended from the scheduler app (mock)"),
);
check("enable via action row", await click("Enable job", { exact: true }));
await sleep(200);
check(
  "action row resumed the job",
  mockApi.getJob("memory-index-watchdog")?.status === "active",
);

// --- Config on an operator detail (memory-index-watchdog) --------
// The Config group renders the SERVED form (labels, ranges,
// values from the adapter) and saves through the writer path.
check(
  "config group renders the served knobs on the operator detail",
  bodyText().includes("Config") &&
    inputValueByLabel("Topic file cap") === "40960" &&
    inputValueByLabel("Topic set register — per-topic allowance") === "12800",
);
await setInputByLabel("Topic file cap", "32768");
check("config save", await click("Save config", { exact: true }));
await sleep(200);
check(
  "config save round-trips through the store",
  mockApi
    .getJob("memory-index-watchdog")
    ?.config?.knobs.find((k) => k.key === "topic_file_max_bytes")?.value ===
    32768,
);
check(
  "config save ledgered (entry, knob, old → new)",
  mockApi
    .getLedger(200)
    .events.some((e) =>
      e.detail.includes(
        "memory-index-watchdog config · Topic file cap 40960 → 32768 bytes",
      ),
    ),
);
check(
  "config saved note shows",
  bodyText().includes("Saved — ledgered, and the engine reads it at the next fire."),
);

// --- validation: run-now on a suspended job is refused ----------
check("back to jobs", await click("Jobs", { exact: true }));
await sleep(200);
check("open suspended job", await click("paywatch-lane-watchdog"));
await sleep(200);
check("run now on suspended job", await click("Run now", { exact: true }));
await sleep(200);
check(
  "validation error served, no run created",
  bodyText().includes("is suspended — resume it before a manual run.") &&
    mockApi.getJob("paywatch-lane-watchdog")?.status === "suspended",
);
check("resume suspended job", await click("Enable job", { exact: true }));
await sleep(150);
check("run now after resume", await click("Run now", { exact: true }));
const laneDone = await waitFor("paywatch-lane-watchdog run completion", () => {
  const job = mockApi.getJob("paywatch-lane-watchdog");
  return job?.last_run?.status === "ok";
});
check("resumed job runs to completion", laneDone);
check("re-suspend to restore seed state", await click("Disable job", { exact: true }));
await sleep(150);
check(
  "seed state restored (25 of 26 enabled)",
  mockApi.getOverview().totals_by_status.active === 25,
);

// --- Built-in detail: family Arming (wb-progress) -----------------
check("back to jobs (2)", await click("Jobs", { exact: true }));
await sleep(150);
check(
  "open wb-progress job",
  await click("wb-progress-programme-b-t-01k8r0000000000000000000b2"),
);
await sleep(200);
check(
  "built-in detail subtitle carries family + cadence",
  bodyText().includes("Built-in · Arming · every 15 minutes"),
);
check(
  "built-in detail: Managed-by group with Open in Workbench",
  bodyText().includes("Managed by") &&
    bodyText().includes("Owning service") &&
    bodyText().includes("Open in Workbench"),
);
check(
  "built-in detail exposes ZERO run/enable controls",
  !bodyText().includes("Run now") &&
    !bodyText().includes("Disable job") &&
    window.document.querySelector('button[role="switch"]') === null,
);

// --- Built-in detail: family Venue (venue-extend-guard) -----------
check("back to jobs (3)", await click("Jobs", { exact: true }));
await sleep(150);
check("open venue-extend-guard", await click("venue-extend-guard"));
await sleep(200);
check(
  "venue detail subtitle (mockup frame 6 form)",
  bodyText().includes("Built-in · Venue · every 30 minutes"),
);
check(
  "venue detail: latest outcome is the served run prose",
  bodyText().includes("Latest outcome") &&
    bodyText().includes("Extended 2 leases · 1 deliberately skipped"),
);
check(
  "venue detail: 24 h counts served",
  bodyText().includes("Runs · 24 h") && bodyText().includes("Failures · 24 h"),
);
check(
  "venue detail: knobless built-in renders NO config form",
  !bodyText().includes("Save config"),
);
check("open in Runner row", await click("Open in Runner"));
await sleep(150);
check(
  "Open in Runner posts the shell-bridge intent (harness surfaces it)",
  bodyText().includes("workhorse:open → runner (venue-extend-guard)"),
);

// --- Built-in detail: family Workbench (the doctor) ---------------
check("back to jobs (4)", await click("Jobs", { exact: true }));
await sleep(150);
check("open workbench-viewer-doctor", await click("workbench-viewer-doctor"));
await sleep(200);
check(
  "doctor detail: last-run chip carries the served failure label",
  bodyText().includes("Built-in · Workbench · every 15 minutes") &&
    bodyText().includes("Failed · exit 1"),
);

// --- Built-in detail: direct (flap-watch) --------------------------
check("back to jobs (5)", await click("Jobs", { exact: true }));
await sleep(150);
check("open flap-watch", await click("flap-watch"));
await sleep(200);
check(
  "direct built-in detail: no family in the subtitle",
  bodyText().includes("Built-in · every 5 minutes"),
);
check(
  "direct built-in detail: NO Managed-by group, NO Open-in row, NO config",
  !bodyText().includes("Managed by") &&
    !bodyText().includes("Open in") &&
    !bodyText().includes("Save config"),
);

// --- Config on a built-in detail (storage-watch) -------------------
// Config is the one operable part of a built-in. Round-trip,
// fire-time read, and the three writer refusals, end-to-end.
check("back to jobs (6)", await click("Jobs", { exact: true }));
await sleep(150);
check("open storage-watch", await click("storage-watch"));
await sleep(200);
check(
  "storage-watch detail renders its served tier knobs",
  inputValueByLabel("Low tier — home free space below") === "50" &&
    inputValueByLabel("Critical tier — home free space below") === "45",
);
await setInputByLabel("Low tier — home free space below", "40");
await setInputByLabel("Critical tier — home free space below", "30");
check("storage config save (1st)", await click("Save config", { exact: true }));
await sleep(200);
const swConfig1 = mockApi.getJob("storage-watch")?.config;
check(
  "storage config round-trips (values + version)",
  swConfig1?.version === 2 &&
    swConfig1.knobs.find((k) => k.key === "home_low_free_gb")?.value === 40 &&
    swConfig1.knobs.find((k) => k.key === "home_critical_free_gb")?.value === 30,
);
check(
  "storage config save ledgered per knob (old → new)",
  mockApi
    .getLedger(200)
    .events.some((e) =>
      e.detail.includes(
        "storage-watch config · Low tier — home free space below 50 → 40 GB",
      ),
    ) &&
    mockApi
      .getLedger(200)
      .events.some((e) =>
        e.detail.includes(
          "storage-watch config · Critical tier — home free space below 45 → 30 GB",
        ),
      ),
);
// Fire-time read: raise the low tier above the served free
// figure (62G) and the next run's verdict must speak it.
await setInputByLabel("Low tier — home free space below", "70");
await setInputByLabel("Critical tier — home free space below", "45");
check("storage config save (2nd)", await click("Save config", { exact: true }));
await sleep(200);
mockApi.runNow("storage-watch");
const tierSpoken = await waitFor("storage-watch fire-time tier read", () => {
  const job = mockApi.getJob("storage-watch");
  return (job?.last_run?.detail ?? "").includes("LOW tier · 62G free");
});
check("engine reads saved config at fire time (LOW tier spoken)", tierSpoken);
// Out-of-range: refused whole — the valid knob in the same
// save must NOT be applied either.
await setInputByLabel("Low tier — home free space below", "9999");
await setInputByLabel("Critical tier — home free space below", "25");
check("storage config save (out-of-range)", await click("Save config", { exact: true }));
await sleep(200);
const swConfig2 = mockApi.getJob("storage-watch")?.config;
check(
  "out-of-range save refused whole (nothing applied, version unmoved)",
  bodyText().includes("must be between 1 and 500 GB") &&
    swConfig2?.version === 3 &&
    swConfig2.knobs.find((k) => k.key === "home_low_free_gb")?.value === 70 &&
    swConfig2.knobs.find((k) => k.key === "home_critical_free_gb")?.value === 45,
);
// Declared constraint: critical must sit below low.
await setInputByLabel("Low tier — home free space below", "70");
await setInputByLabel("Critical tier — home free space below", "70");
check("storage config save (constraint)", await click("Save config", { exact: true }));
await sleep(200);
check(
  "constraint-violating save refused whole",
  bodyText().includes("The critical tier must sit below the low tier.") &&
    mockApi.getJob("storage-watch")?.config?.version === 3,
);
// Stale: another writer saves first (version moves), then the
// form's save — still holding the old version — is refused.
const swVersionNow = mockApi.getJob("storage-watch")?.config?.version ?? 0;
const otherWriter = await mockApi.saveConfig("storage-watch", swVersionNow, {
  home_low_free_gb: 65,
  home_critical_free_gb: 45,
});
check("other writer's save lands (version moves)", otherWriter.ok === true);
check("storage config save (stale)", await click("Save config", { exact: true }));
await sleep(200);
check(
  "stale save refused, store keeps the other writer's values",
  bodyText().includes("changed since it was loaded") &&
    mockApi
      .getJob("storage-watch")
      ?.config?.knobs.find((k) => k.key === "home_low_free_gb")?.value === 65,
);

// --- Frame 4 · Pings ----------------------------------------------
check("navigate to Pings", await click("Pings"));
await sleep(200);
check(
  "pings subtitle counts waiting",
  /\d+ waiting · wakes and status posts land here/.test(bodyText()),
);
check(
  "waiting order is oldest first (contract 09)",
  bodyText().indexOf("programme-a-main — gate result posted") <
    bodyText().indexOf("programme-c — progress check due"),
  "programme-a (11 min) before programme-c (6 min)",
);
check(
  "waiting row sub carries job id + age",
  bodyText().includes("wb-progress-programme-a") && bodyText().includes("min old"),
);
// acknowledge the programme-a ping through its row's chip-button
let ackClicked = false;
await act(async () => {
  for (const btn of buttons()) {
    if ((btn.textContent ?? "").trim() !== "Acknowledge") continue;
    let node: Element | null = btn;
    for (let i = 0; i < 4 && node; i++) node = node.parentElement;
    if (node?.textContent?.includes("programme-a-main")) {
      btn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
      ackClicked = true;
      break;
    }
  }
});
await sleep(200);
check("acknowledge chip-button clicked", ackClicked);
check(
  "acked ping left Waiting and landed in Recent",
  mockApi.listRecentPings().some((p) => p.id === "7f3a9c1e52b8") &&
    bodyText().includes("Acknowledged by owner"),
);
check(
  "ack ledgered (ping_acked)",
  mockApi
    .getLedger(50)
    .events.some(
      (e) => e.kind === "ping_acked" && e.detail.includes("programme-a-main"),
    ),
);

// --- Frame 5 · Ledger ----------------------------------------------
check("navigate to Ledger", await click("Ledger"));
await sleep(200);
check(
  "ledger shows the run from this session",
  bodyText().includes("bridge-wake completed ·"),
);
check(
  "ledger shows the seeded doctor failure",
  bodyText().includes("workbench-viewer-doctor failed · exit 1"),
);
check(
  "ledger shows the seeded op",
  bodyText().includes("write · programme-c/docs/rule-layers.md"),
);
check(
  "ledger shows the config saves (op events, old → new)",
  bodyText().includes(
    "storage-watch config · Low tier — home free space below 50 → 40 GB",
  ) &&
    bodyText().includes(
      "memory-index-watchdog config · Topic file cap 40960 → 32768 bytes",
    ),
);
check(
  "ledger shows the seeded catchup collapse (contract 13 surface)",
  bodyText().includes("catchup · 3 points collapsed"),
);
await setSearch("flap-watch");
await sleep(200);
check(
  "ledger search filters",
  bodyText().includes("flap-watch") &&
    !bodyText().includes("bridge-wake completed"),
);
await setSearch("");
await sleep(150);

// --- Appearance: owned by the unified shell Settings --------
// Consolidation ruling: the app carries no
// settings surface — no Settings destination, no in-app
// appearance controls. Appearance arrives as root attributes
// from the host; in this standalone render the preview
// harness plays the host, and its palette/mode controls
// re-theme the app frame exactly as the shell's unified
// Settings drives the embedded app.
check(
  "app carries no Settings surface",
  !buttons().some((b) => (b.textContent ?? "").trim() === "Settings") &&
    !bodyText().includes("Appearance"),
);
check("harness palette → Teal", await clickRadio("teal"));
await sleep(150);
check(
  "palette switch re-themes via kit tokens",
  window.document.querySelector("[data-palette]")?.getAttribute("data-palette") === "teal",
);
check("harness mode → Dark", await clickRadio("dark"));
await sleep(150);
check(
  "mode switch applies dark tokens",
  window.document.querySelector("[data-mode]")?.getAttribute("data-mode") === "dark",
);

// --- Overview reflects everything ----------------------------------
check("back to Overview", await click("Overview"));
await sleep(200);
check(
  "overview pings-waiting matches the store",
  bodyText().includes(`${mockApi.listPings().length} waiting`),
);

await act(async () => {
  root.unmount();
});

await runPhonePhase();

const { checks, failures } = results();
console.log(`\n${checks} checks, ${failures} failures`);
process.exit(failures > 0 ? 1 : 0);
