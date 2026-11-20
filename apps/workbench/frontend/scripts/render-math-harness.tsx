// The math adoption proof harness: server-renders the
// segment renderer twice — once from the MOCK adapter's
// entrySegments (the demo's fixture segments), once from
// the LIVE-shaped payload (contracts/fixtures/
// entry-segments.json, the backend segmenter's own
// output) — and checks the typeset-math markers in both.
// Driven by scripts/render-math-proof.mjs.

import { renderToString } from "react-dom/server";
import { MockWorkbenchAdapter } from "../src/lib/mockAdapter";
import { SegmentBlocks } from "../src/sections/SegmentBlocks";
import type { FeedSegmentBlock } from "../src/lib/feeds";
// @ts-expect-error JSON fixture, bundled by esbuild.
import liveFixture from "../../../../contracts/fixtures/entry-segments.json";

interface ProofResult {
  name: string;
  ok: boolean;
  missing: string[];
}

const MARKERS: { label: string; needle: string }[] = [
  { label: "KaTeX typeset output", needle: 'class="katex"' },
  { label: "math role", needle: 'role="math"' },
  {
    label: "display source as accessible name",
    needle: "aria-label=\"R^2 = 1 -",
  },
  { label: "equation number slot", needle: "wb-math-eqno" },
  { label: "equation number content", needle: "(1)" },
  { label: "inline malformed fallback", needle: "wb-math-broken\"" },
  { label: "inline malformed raw source", needle: "\\frac{1}{2" },
  { label: "display malformed fallback", needle: "wb-math-broken-block" },
  { label: "protected code span literal", needle: "$\\alpha$" },
  { label: "prices kept literal", needle: "$5 and $10" },
];

function check(name: string, html: string): ProofResult {
  const missing = MARKERS.filter((m) => !html.includes(m.needle)).map(
    (m) => m.label,
  );
  if (html.includes("katex-error")) missing.push("no katex-error");
  return { name, ok: missing.length === 0, missing };
}

export async function run(): Promise<ProofResult[]> {
  const results: ProofResult[] = [];

  const mock = new MockWorkbenchAdapter();
  const seg = await mock.entrySegments("e-field-note");
  if (!seg.ok) {
    results.push({
      name: "mock adapter segments",
      ok: false,
      missing: [`entrySegments refused: ${seg.reason}`],
    });
  } else {
    results.push(
      check(
        "mock adapter segments",
        renderToString(<SegmentBlocks blocks={seg.blocks} />),
      ),
    );
  }

  const blocks = (liveFixture as { blocks: FeedSegmentBlock[] }).blocks;
  results.push(
    check(
      "live-shaped fixture payload",
      renderToString(<SegmentBlocks blocks={blocks} />),
    ),
  );

  return results;
}
