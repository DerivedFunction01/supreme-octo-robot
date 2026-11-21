// Phone phase — the SAME app through the kit's one responsive
// seam (useIsPhone, <= 480px). The kit PhoneShell presentation
// REPLACES the desktop shell, never flex-shrinks it (the Runner
// shell's shipped defect): the phone opens on the app index and
// a destination row pushes its section. Pixel screenshots are
// the parent's Playwright integration gate; here the phone form
// is rendered and driven for every view.
//
// Split from exercise-ui.tsx: this phase runs as
// runPhonePhase() over the shared harness
// (./exercise-harness) after the desktop frames.
import type { JobView } from "../src/types";
import {
  React,
  Row,
  OutcomeChip,
  jobChip,
  Preview,
  act,
  bodyText,
  buttons,
  check,
  click,
  createRoot,
  mockApi,
  sleep,
  window,
} from "./exercise-harness";

export async function runPhonePhase(): Promise<void> {
  window.matchMedia = (query: string) =>
    ({
      matches: query.includes("480px"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    }) as MediaQueryList;

  window.document.body.innerHTML = '<div id="root"></div>';
  const phoneRoot = createRoot(window.document.getElementById("root")!);
  await act(async () => {
    phoneRoot.render(
      React.createElement(React.StrictMode, null, React.createElement(Preview)),
    );
  });
  await sleep(300);

  check(
    "phone: kit PhoneShell engaged via useIsPhone (desktop sidebar absent)",
    window.document.querySelector('[class*="text-[32px]"]') !== null &&
      window.document.querySelector('[class*="w-[224px]"]') === null,
  );
  check(
    "phone: nav is the grouped-list index, not the sidebar (no Settings row — the unified shell Settings owns appearance)",
    window.document.querySelector('nav[aria-label="Scheduler"]') !== null &&
      bodyText().includes("Overview") &&
      bodyText().includes("Ledger") &&
      !bodyText().includes("Settings"),
  );
  await click("Overview", { exact: true });
  await sleep(200);
  check(
    "phone: overview renders incl. the flap banner state",
    bodyText().includes("Write-denial flap active.") &&
      bodyText().includes("Jobs enabled"),
  );
  await click("Scheduler", { exact: true });
  await sleep(200);
  check("phone: navigate to Jobs from the index", await click("Jobs"));
  await sleep(200);
  check(
    "phone: jobs list renders with the long-id job",
    bodyText().includes("wb-progress-programme-b-t-01k8r0000000000000000000b2"),
  );
  check(
    "phone: built-in group opens with its header row (count + running summary)",
    bodyText().includes("Built-in services") && bodyText().includes("20 running"),
  );
  // long-text construction: the compact row's label chain
  // truncates (min-w-0 flex child + truncate) instead of
  // overflowing, and the family tag rides the same line.
  {
    const rowBtn = buttons().find((b) =>
      (b.textContent ?? "").includes("wb-progress-programme-b"),
    );
    const spans = rowBtn ? [...rowBtn.querySelectorAll("span")] : [];
    check(
      "long-text: compact row label chain is min-w-0 + truncate",
      spans.some((s) => (s.className ?? "").includes("min-w-0")) &&
        spans.some((s) => (s.className ?? "").includes("truncate")),
    );
    check(
      "long-text: compact row carries its family tag on the line",
      (rowBtn?.textContent ?? "").includes("Arming"),
    );
  }
  // The header row is a working disclosure, not a glyph.
  check("phone: built-in header collapses the group", await click("Built-in services"));
  await sleep(150);
  check(
    "phone: collapsed group hides its rows",
    !buttons().some((b) => (b.textContent ?? "").includes("wb-progress-programme-b")),
  );
  check("phone: built-in header re-expands the group", await click("Built-in services"));
  await sleep(150);
  check(
    "phone: re-expanded group restores its rows",
    bodyText().includes("wb-progress-programme-b-t-01k8r0000000000000000000b2"),
  );
  // chip-length construction (owner ruling, 2026-11-13): the row
  // chip carries outcome + time only — a run's reason never rides
  // it. Row structure (the owner's two-line ruling, 2026-11-13):
  // the name line carries the name + chevron only — the chip
  // never competes with the name for width — and the chip rides
  // the details line with the cadence. Rendered
  // detached from the real Row/jobChip composition with the
  // worst cases: the longest real job name (the 50-char
  // wb-progress id) paired first with the skip-reason run (the
  // owner's screenshot: "Skipped · venue busy"), then with the
  // longest chip the composition can still emit.
  {
    const nowIso = new Date().toISOString();
    const longJob = mockApi
      .listJobs()
      .find((j) => j.id === "wb-progress-programme-b-t-01k8r0000000000000000000b2")!;
    const skipJob: JobView = {
      ...longJob,
      status: "active" as const,
      last_activity: null,
      last_run: {
        ts: nowIso,
        due: nowIso,
        status: "ok" as const,
        exit_code: 0,
        label: "OK",
        matched_pattern: null,
        collapsed: 0,
        error: null,
        stdout_tail: null,
        stderr_tail: null,
        duration_label: "3.9 s",
        detail: "Skipped · venue busy",
      },
    };
    const overdueJob: JobView = {
      ...longJob,
      status: "active" as const,
      last_run: null,
      last_activity: {
        state: "overdue" as const,
        label: "Overdue past ack timeout",
        ping_id: "p-probe",
        since: nowIso,
      },
    };
    const host = window.document.createElement("div");
    window.document.body.appendChild(host);
    const caseRoot = createRoot(host);
    const renderRow = (job: JobView) => {
      const chip = jobChip(job);
      return React.createElement(Row, {
        label: job.id,
        sub: "Every 15 minutes",
        chevron: true,
        onClick: () => {},
        end: React.createElement(OutcomeChip, {
          tone: chip.tone,
          text: chip.text,
        }),
      });
    };
    await act(async () => {
      caseRoot.render(
        React.createElement(
          React.Fragment,
          null,
          renderRow(skipJob),
          renderRow(overdueJob),
        ),
      );
    });
    await sleep(100);
    const rows = [...host.querySelectorAll("button")];
    const skipRow = rows[0];
    check(
      "chip fix: skip reason does not ride the row chip (bare 'Skipped')",
      !!skipRow &&
        !(skipRow.textContent ?? "").includes("venue busy") &&
        [...skipRow.querySelectorAll("span")].some(
          (s) => (s.textContent ?? "").trim() === "Skipped",
        ),
    );
    // The two-line row structure: the row's content stack has
    // exactly two lines — line 1 is the name element + the
    // chevron svg and nothing else (no chip text), line 2 is
    // the details text with the chip riding it.
    const assertTwoLine = (
      rowBtn: HTMLButtonElement | undefined,
      chipText: string,
    ): { name: boolean; details: boolean } => {
      if (!rowBtn) return { name: false, details: false };
      const stack = rowBtn.firstElementChild;
      if (!stack || stack.children.length !== 2)
        return { name: false, details: false };
      const nameLine = stack.children[0];
      const detailsLine = stack.children[1];
      if (!nameLine || !detailsLine) return { name: false, details: false };
      const nameKids = [...nameLine.children];
      const name =
        nameKids.length === 2 &&
        nameKids.some((k) => k.tagName === "svg") &&
        (nameLine.textContent ?? "").includes(longJob.id) &&
        !(nameLine.textContent ?? "").includes(chipText);
      const details =
        (detailsLine.textContent ?? "").includes("Every 15 minutes") &&
        (detailsLine.textContent ?? "").includes(chipText);
      return { name, details };
    };
    check(
      "row structure: name line carries the name + chevron only (skip row)",
      assertTwoLine(skipRow, "Skipped").name,
    );
    check(
      "row structure: chip rides the details line with the cadence (skip row)",
      assertTwoLine(skipRow, "Skipped").details,
    );
    check(
      "row structure: longest remaining chip ('Overdue past ack timeout') rides the details line, name line clean",
      (() => {
        const r = assertTwoLine(rows[1], "Overdue past ack timeout");
        return r.name && r.details;
      })(),
    );
    await act(async () => {
      caseRoot.unmount();
    });
    host.remove();
  }
  check(
    "phone: open the long-id job detail",
    await click("wb-progress-programme-b-t-01k8r0000000000000000000b2"),
  );
  await sleep(200);
  {
    const h2 = window.document.querySelector("h2");
    check(
      "phone: built-in detail title wraps anywhere (60-char unbroken id)",
      (h2?.className ?? "").includes("[overflow-wrap:anywhere]") &&
        bodyText().includes("Managed by") &&
        bodyText().includes("Open in Workbench") &&
        !bodyText().includes("Run now"),
    );
  }
  check("phone: back row returns to Jobs", await click("Jobs", { exact: true }));
  await sleep(200);
  await click("Scheduler", { exact: true });
  await sleep(200);
  check("phone: navigate to Pings from the index", await click("Pings"));
  await sleep(200);
  check(
    "phone: pings render",
    bodyText().includes("waiting · wakes and status posts land here"),
  );
  await click("Scheduler", { exact: true });
  await sleep(200);
  check("phone: navigate to Ledger from the index", await click("Ledger"));
  await sleep(200);
  check(
    "phone: ledger renders",
    bodyText().includes("Every op, run, and acknowledgement · today"),
  );
  await click("Scheduler", { exact: true });
  await sleep(200);
  check(
    "phone: index carries no Settings destination (unified shell Settings owns appearance)",
    !bodyText().includes("Settings"),
  );

  await act(async () => {
    phoneRoot.unmount();
  });
}
