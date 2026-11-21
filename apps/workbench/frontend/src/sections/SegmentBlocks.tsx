import { Math } from "@kit/components/shell/Math";
import type { FeedSegmentBlock, FeedSegmentRun } from "../lib/feeds";

// The served-segments renderer (the segment feed, math
// adoption): blocks arrive display-ready from behind the
// seam — text runs, code runs, and math nodes carrying
// {source, display, valid} — and render as prose, with
// each math node typeset by the kit's Math component.
// Nothing is parsed here: segmentation and the validity
// state are the backend's work, served.

function Runs({ runs }: { runs: FeedSegmentRun[] }) {
  return (
    <>
      {runs.map((run, i) => {
        if (run.type === "text") return <span key={i}>{run.text}</span>;
        if (run.type === "code") {
          return (
            <code
              key={i}
              className="rounded px-1 py-[1px] font-mono text-[0.92em]"
              style={{
                backgroundColor: "var(--wb-surface-sunken)",
                color: "var(--wb-content-primary)",
              }}
            >
              {run.text}
            </code>
          );
        }
        return (
          <Math key={i} source={run.source} display={run.display} valid={run.valid} />
        );
      })}
    </>
  );
}

export function SegmentBlocks({ blocks }: { blocks: FeedSegmentBlock[] }) {
  return (
    <div className="text-[14.5px] leading-[1.65]" style={{ color: "var(--wb-content-primary)" }}>
      {blocks.map((block, i) => {
        switch (block.kind) {
          case "heading": {
            const size =
              block.level <= 1 ? "text-[19px]" : block.level === 2 ? "text-[16px]" : "text-[14.5px]";
            return (
              <div key={i} className={`mt-4 mb-2 font-bold first:mt-0 ${size}`}>
                <Runs runs={block.runs} />
              </div>
            );
          }
          case "paragraph":
            return (
              <div key={i} className="my-2">
                <Runs runs={block.runs} />
              </div>
            );
          case "math":
            return (
              <Math key={i} source={block.source} display valid={block.valid}>
                {block.number}
              </Math>
            );
          case "code":
            return (
              <pre
                key={i}
                className="my-3 overflow-x-auto rounded-md p-3 font-mono text-[12.5px] leading-[1.6]"
                style={{
                  backgroundColor: "var(--wb-surface-sunken)",
                  color: "var(--wb-content-primary)",
                }}
              >
                {block.text}
              </pre>
            );
          case "list": {
            const cls = block.ordered ? "list-decimal" : "list-disc";
            const items = block.items.map((runs, j) => (
              <li key={j}>
                <Runs runs={runs} />
              </li>
            ));
            return block.ordered ? (
              <ol key={i} className={`my-2 pl-6 ${cls}`}>
                {items}
              </ol>
            ) : (
              <ul key={i} className={`my-2 pl-6 ${cls}`}>
                {items}
              </ul>
            );
          }
        }
      })}
    </div>
  );
}
