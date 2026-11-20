/**
 * The jobs-overflow after-proof (clean-room lane 2,
 * 2026-11-20): measures the Scheduler Jobs surface
 * against the CAPTURED live payloads — serve.mjs with
 * E2E_SCHED_FIXTURES=1 answers getJobs / getOverview
 * from the staged live-jobs.json / live-overview.json —
 * at the owner's phone frame (390×844) and the desktop
 * control (1280×800), and RECORDS the geometry in
 * measurements-after.json plus a screenshot per
 * viewport. The before-proof (run
 * workhorse-jobs-overflow-before-20261120T170019Z) is
 * the comparison record: same targets, same measures.
 *
 * This spec asserts nothing about geometry — a wait
 * only proves the surface rendered. The verdict is
 * read off the record: phone table width vs the card
 * content box, scroller scrollWidth vs clientWidth,
 * each target label's completeness (span scrollWidth
 * vs clientWidth, chip right edge vs the viewport),
 * the banner's rect at scroll-top, and the desktop
 * control unchanged (six columns, zero overflow).
 */
import { test, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const OUT_DIR = process.env.E2E_OUT_DIR ?? ".";

const TARGET_IDS = [
  "bridge-drain",
  "card-watch",
  "colab-liveness-oak-reef-65-r1795149559-r1795190959",
  "colab-liveness-oak-reef-65-r1795149958",
  "memory-index-watchdog",
];

/** The whole measurement, taken in the page so the
 *  record carries the same fields as the before-proof. */
function measureJobsPage(targetIds: string[]) {
  const rect = (el: Element) => {
    const r = el.getBoundingClientRect();
    return {
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      right: r.right,
      bottom: r.bottom,
    };
  };
  const doc = document.documentElement;
  const table = document.querySelector('table[aria-label="Jobs"]');
  if (!table) return { error: "jobs table not rendered" };

  // The scroller: the nearest scrollable ancestor of
  // the table (the shell's content region).
  let scroller: Element | null = null;
  let up: Element | null = table;
  while (up && up !== doc) {
    up = up.parentElement;
    if (!up) break;
    const cs = getComputedStyle(up);
    if (
      (cs.overflowY === "auto" || cs.overflowY === "scroll") &&
      up.scrollHeight >= up.clientHeight
    ) {
      scroller = up;
      break;
    }
  }

  const card = table.closest("section");
  const headers = [...table.querySelectorAll("thead th")];
  const outcomeIdx = headers.findIndex(
    (th) => (th.textContent || "").trim() === "Last outcome",
  );

  // The aged-pings banner: the deepest element carrying
  // its text (its own bar, not an ancestor's textContent).
  let banner: Element | null = null;
  for (const cand of document.querySelectorAll("body *")) {
    if ((cand.textContent || "").includes("ping(s) waiting past the ack timeout")) {
      if (!banner || banner.contains(cand)) banner = cand;
    }
  }
  const search = [...document.querySelectorAll("input")].find((i) =>
    (i.getAttribute("placeholder") || "").toLowerCase().includes("search"),
  );

  const rows: unknown[] = [];
  const chips: unknown[] = [];
  for (const id of targetIds) {
    const tr = table.querySelector(`tr[aria-label="Open job ${id}"]`);
    if (!tr) {
      rows.push({ id, missing: true });
      continue;
    }
    rows.push({
      id,
      rowRect: rect(tr),
      cells: [...tr.children].map((td) => ({
        rect: rect(td),
        clientWidth: (td as HTMLElement).clientWidth,
        scrollWidth: td.scrollWidth,
      })),
    });
    const cell = outcomeIdx >= 0 ? tr.children[outcomeIdx] : undefined;
    const chip = cell?.querySelector('[class*="inline-flex"]');
    if (chip) {
      const labelEl = [...chip.querySelectorAll("span")].find(
        (s) =>
          s.getAttribute("aria-hidden") !== "true" &&
          (s.textContent || "").trim().length > 0,
      );
      const chipRect = rect(chip);
      chips.push({
        label: (chip.textContent || "").trim(),
        chipRect,
        chipClientWidth: (chip as HTMLElement).clientWidth,
        chipScrollWidth: chip.scrollWidth,
        labelClientWidth: labelEl ? (labelEl as HTMLElement).clientWidth : null,
        labelScrollWidth: labelEl ? labelEl.scrollWidth : null,
        labelComplete:
          !!labelEl &&
          labelEl.scrollWidth <= (labelEl as HTMLElement).clientWidth &&
          chipRect.right <= window.innerWidth,
      });
    }
  }

  const bannerRect = banner ? rect(banner) : null;
  const searchRect = search ? rect(search) : null;
  return {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    docClientWidth: doc.clientWidth,
    docScrollWidth: doc.scrollWidth,
    horizontalOverflow: doc.scrollWidth > doc.clientWidth,
    tableRect: rect(table),
    tableLayout: getComputedStyle(table).tableLayout,
    cardRect: card ? rect(card) : null,
    columns: headers.map((th) => ({
      text: (th.textContent || "").trim(),
      rect: rect(th),
    })),
    scroller: scroller
      ? {
          rect: rect(scroller),
          scrollTop: (scroller as HTMLElement).scrollTop,
          clientWidth: (scroller as HTMLElement).clientWidth,
          scrollWidth: scroller.scrollWidth,
        }
      : null,
    chips,
    rows,
    banner: banner
      ? { rect: bannerRect, offsetHeight: (banner as HTMLElement).offsetHeight }
      : null,
    searchRect,
    bannerOverlapsSearch:
      !!bannerRect &&
      !!searchRect &&
      bannerRect.x < searchRect.right &&
      searchRect.x < bannerRect.right &&
      bannerRect.y < searchRect.bottom &&
      searchRect.y < bannerRect.bottom,
    suspects: [...document.querySelectorAll("body *")]
      .filter((e) => e.scrollWidth > e.clientWidth + 1)
      .slice(0, 8)
      .map((e) => ({
        tag: e.tagName.toLowerCase(),
        cls: typeof e.className === "string" ? e.className : "",
        text: (e.textContent || "").trim().slice(0, 48),
        clientWidth: (e as HTMLElement).clientWidth,
        scrollWidth: e.scrollWidth,
      })),
  };
}

const measurements: Record<string, unknown> = { phase: "after" };

async function drive(page: Page): Promise<Record<string, unknown>> {
  await page.goto("/#/scheduler/jobs");
  await page.waitForSelector('table[aria-label="Jobs"] tbody tr', {
    timeout: 30_000,
  });
  await page.waitForSelector('tr[aria-label="Open job bridge-drain"]', {
    timeout: 30_000,
  });
  await page
    .waitForSelector("text=/ping\\(s\\) waiting past the ack timeout/", {
      timeout: 30_000,
    })
    .catch(() => null);
  await page.waitForTimeout(400);
  return page.evaluate(measureJobsPage, TARGET_IDS);
}

test.describe("jobs overflow after-proof — phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  test("390x844 measurements + screenshot", async ({ page }) => {
    measurements.phone = await drive(page);
    await page.screenshot({ path: join(OUT_DIR, "after-phone.png") });
  });
});

test.describe("jobs overflow after-proof — desktop", () => {
  test.use({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
  test("1280x800 measurements + screenshot", async ({ page }) => {
    measurements.desktop = await drive(page);
    await page.screenshot({ path: join(OUT_DIR, "after-desktop.png") });
  });
});

test.afterAll(() => {
  writeFileSync(
    join(OUT_DIR, "measurements-after.json"),
    JSON.stringify(measurements, null, 2) + "\n",
  );
});
