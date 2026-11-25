import { useEffect, useRef, useState, type ReactNode } from "react";

// The formatted plan reader (W6) — a hand-rolled markdown
// render in the app's own vocabulary (the lineDiff
// precedent: no markdown library is bundled, so the reader
// parses the plan file's block structure itself). Headings
// carry anchors, task lists render as checklist bands,
// blockquotes render as ruling bands, GFM tables as real
// tables, code fences with a light token highlight, and
// mermaid fences attempt the renderer lazily — when it is
// not bundled (it is not), the framed source stands in,
// labelled as such. Selecting text surfaces the Annotate
// action (W5's entry point): the selection becomes an
// anchored annotation's quote.

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "para"; text: string }
  | { kind: "quote"; lines: string[] }
  | { kind: "code"; lang: string; lines: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "list"; items: { text: string; checked: boolean | null }[] }
  | { kind: "hr" };

function parseBlocks(raw: string): Block[] {
  const lines = raw.split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i++;
      continue;
    }
    const fence = /^```(\S*)\s*$/.exec(line);
    if (fence) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) {
        body.push(lines[i]);
        i++;
      }
      i++; // closing fence
      blocks.push({ kind: "code", lang: fence[1] ?? "", lines: body });
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      i++;
      continue;
    }
    if (/^---+\s*$/.test(line)) {
      blocks.push({ kind: "hr" });
      i++;
      continue;
    }
    if (line.startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) {
        quote.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      blocks.push({ kind: "quote", lines: quote });
      continue;
    }
    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1].trim())) {
      const splitRow = (r: string) =>
        r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const header = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    if (/^\s*(?:[-*]|\d+\.)\s+/.test(line)) {
      const items: { text: string; checked: boolean | null }[] = [];
      while (i < lines.length && /^\s*(?:[-*]|\d+\.)\s+/.test(lines[i])) {
        const m = /^\s*(?:[-*]|\d+\.)\s+(?:\[([ xX])\]\s+)?(.*)$/.exec(lines[i]);
        if (m) {
          items.push({
            text: m[2],
            checked: m[1] === undefined ? null : m[1].toLowerCase() === "x",
          });
        }
        i++;
      }
      blocks.push({ kind: "list", items });
      continue;
    }
    const para: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,4}\s|>|```)/.test(lines[i]) &&
      !/^\s*(?:[-*]|\d+\.)\s+/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    blocks.push({ kind: "para", text: para.join(" ") });
  }
  return blocks;
}

/** Inline forms: `code`, **bold**, *italic*, [text](href)
 *  (rendered as styled text — the reader never navigates). */
function renderInline(text: string, keyBase: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, i) => {
    const key = `${keyBase}-${i}`;
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={key}
          className="rounded px-1 py-px font-mono text-[0.92em]"
          style={{ backgroundColor: "var(--ui-surface-sunken)" }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      return (
        <span key={key} style={{ color: "var(--ui-accent)", textDecoration: "underline" }}>
          {link[1]}
        </span>
      );
    }
    return <span key={key}>{part}</span>;
  });
}

const KEYWORDS =
  /\b(const|let|var|function|return|if|else|for|while|import|from|export|type|interface|new|await|async|class|extends)\b/;

function highlightCodeLine(line: string, key: string): ReactNode {
  const commentAt = line.indexOf("//");
  const code = commentAt >= 0 ? line.slice(0, commentAt) : line;
  const comment = commentAt >= 0 ? line.slice(commentAt) : "";
  const tokens = code.split(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g);
  return (
    <div key={key}>
      {tokens.map((tok, i) =>
        /^["']/.test(tok) ? (
          <span key={i} style={{ color: "var(--ui-status-stale-text)" }}>
            {tok}
          </span>
        ) : (
          <span key={i}>
            {tok.split(KEYWORDS).map((piece, j) =>
              KEYWORDS.test(piece) ? (
                <span key={j} style={{ color: "var(--ui-status-canonical-text)", fontWeight: 600 }}>
                  {piece}
                </span>
              ) : (
                <span key={j}>{piece}</span>
              ),
            )}
          </span>
        ),
      )}
      {comment ? <span style={{ color: "var(--ui-content-muted)" }}>{comment}</span> : null}
      {line === "" ? " " : null}
    </div>
  );
}

function MermaidBlock({ source }: { source: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    // Lazy by design: mermaid is not a bundled dependency,
    // so the import refuses and the framed source below is
    // the standing render. If the renderer ever ships, the
    // diagram takes its place with no reader change. (The
    // specifier rides a variable so the type checker does
    // not try to resolve an unbundled module.)
    const specifier = "mermaid";
    import(/* @vite-ignore */ specifier)
      .then(async (mod) => {
        const mermaid = (mod as { default?: { initialize: (c: object) => void; render: (id: string, src: string) => Promise<{ svg: string }> } }).default;
        if (!mermaid) throw new Error("no renderer");
        mermaid.initialize({ startOnLoad: false });
        const out = await mermaid.render(`ui-diagram-${Math.abs(source.length * 31)}`, source);
        if (live) setSvg(out.svg);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [source]);
  if (svg) {
    return (
      <div
        className="my-3 overflow-x-auto p-4"
        style={{
          backgroundColor: "var(--ui-surface-2)",
          border: "1px solid var(--ui-border-default)",
          borderRadius: "var(--ui-radius-md)",
        }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  }
  return (
    <div
      className="my-3 overflow-x-auto p-4"
      style={{
        backgroundColor: "var(--ui-surface-2)",
        border: "1px dashed var(--ui-border-strong)",
        borderRadius: "var(--ui-radius-md)",
      }}
    >
      <div className="mb-2 text-xs font-bold tracking-[0.07em] uppercase" style={{ color: "var(--ui-content-secondary)" }}>
        Diagram{failed ? " · source — the mermaid renderer is not bundled" : " · rendering…"}
      </div>
      <pre className="m-0 font-mono text-xs leading-[1.7] whitespace-pre-wrap">{source}</pre>
    </div>
  );
}

export function PlanReader({
  raw,
  onAnnotate,
}: {
  raw: string;
  onAnnotate?: (quote: string) => void;
}) {
  const blocks = parseBlocks(raw);
  const rootRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState("");

  const captureSelection = () => {
    const sel = window.getSelection();
    const root = rootRef.current;
    if (!sel || !root || sel.isCollapsed) {
      setSelected("");
      return;
    }
    if (sel.anchorNode && root.contains(sel.anchorNode)) {
      setSelected(sel.toString().trim());
    }
  };

  return (
    <div>
      {onAnnotate && selected ? (
        <div
          className="mb-3 flex items-center gap-3 p-[10px_14px]"
          style={{
            backgroundColor: "var(--ui-surface-sunken)",
            border: "1px solid var(--ui-border-default)",
            borderRadius: "var(--ui-radius-md)",
          }}
        >
          <span className="min-w-0 flex-1 truncate text-[13px]" style={{ color: "var(--ui-content-secondary)" }}>
            Selected: "{selected}"
          </span>
          <button
            type="button"
            className="shrink-0 rounded-full px-3 py-1 text-xs font-semibold"
            style={{ backgroundColor: "var(--ui-accent)", color: "var(--ui-on-accent)" }}
            onClick={() => {
              onAnnotate(selected);
              setSelected("");
              window.getSelection()?.removeAllRanges();
            }}
          >
            Annotate
          </button>
        </div>
      ) : null}
      <div
        ref={rootRef}
        onMouseUp={captureSelection}
        className="p-[18px_20px] text-[14px] leading-[1.65]"
        style={{
          backgroundColor: "var(--ui-surface-2)",
          border: "1px solid var(--ui-border-default)",
          borderRadius: "var(--ui-radius-md)",
          color: "var(--ui-content-primary)",
        }}
      >
        {blocks.map((b, i) => {
          const key = `b${i}`;
          switch (b.kind) {
            case "heading": {
              const slug = b.text.toLowerCase().replace(/[^a-z0-9]+/g, "-");
              if (b.level === 1) {
                return (
                  <h3 key={key} id={`pr-${slug}`} className="mt-0 mb-3 text-[19px] font-bold">
                    {renderInline(b.text, key)}
                  </h3>
                );
              }
              if (b.level === 2) {
                return (
                  <h4
                    key={key}
                    id={`pr-${slug}`}
                    className="mt-5 mb-2 border-l-[3px] pl-2.5 text-[15.5px] font-bold first:mt-0"
                    style={{ borderColor: "var(--ui-accent)" }}
                  >
                    {renderInline(b.text, key)}
                  </h4>
                );
              }
              return (
                <h5 key={key} id={`pr-${slug}`} className="mt-4 mb-1.5 text-[14px] font-bold">
                  {renderInline(b.text, key)}
                </h5>
              );
            }
            case "para":
              return (
                <p key={key} className="my-2 [overflow-wrap:anywhere]">
                  {renderInline(b.text, key)}
                </p>
              );
            case "quote":
              return (
                <div
                  key={key}
                  className="my-3 p-[10px_14px]"
                  style={{
                    backgroundColor: "color-mix(in srgb, var(--ui-okabe-blue) 8%, transparent)",
                    borderLeft: "3px solid var(--ui-okabe-blue)",
                    borderRadius: "0 var(--ui-radius-md) var(--ui-radius-md) 0",
                  }}
                >
                  <div
                    className="mb-1 text-[11px] font-bold tracking-[0.07em] uppercase"
                    style={{ color: "var(--ui-status-canonical-text)" }}
                  >
                    Ruling
                  </div>
                  {b.lines.map((l, j) => (
                    <p key={j} className="my-1 [overflow-wrap:anywhere]">
                      {renderInline(l, `${key}-${j}`)}
                    </p>
                  ))}
                </div>
              );
            case "code":
              if (b.lang === "mermaid") {
                return <MermaidBlock key={key} source={b.lines.join("\n")} />;
              }
              return (
                <div
                  key={key}
                  className="my-3 overflow-x-auto p-3.5 font-mono text-xs leading-[1.75]"
                  style={{
                    backgroundColor: "var(--ui-surface-sunken)",
                    border: "1px solid var(--ui-border-default)",
                    borderRadius: "var(--ui-radius-md)",
                    whiteSpace: "pre",
                  }}
                >
                  {b.lang ? (
                    <div className="mb-1.5" style={{ color: "var(--ui-content-muted)" }}>
                      {b.lang}
                    </div>
                  ) : null}
                  {b.lines.map((l, j) => highlightCodeLine(l, `${key}-${j}`))}
                </div>
              );
            case "table":
              return (
                <div key={key} className="my-3 overflow-x-auto">
                  <table className="w-full border-collapse text-[13px]">
                    <thead>
                      <tr>
                        {b.header.map((h, j) => (
                          <th
                            key={j}
                            className="border-b-2 px-2.5 py-1.5 text-left font-bold"
                            style={{ borderColor: "var(--ui-border-strong)" }}
                          >
                            {renderInline(h, `${key}-h${j}`)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {b.rows.map((r, j) => (
                        <tr key={j}>
                          {b.header.map((_, k) => (
                            <td
                              key={k}
                              className="border-b px-2.5 py-1.5 align-top [overflow-wrap:anywhere]"
                              style={{ borderColor: "var(--ui-border-default)" }}
                            >
                              {renderInline(r[k] ?? "", `${key}-${j}-${k}`)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            case "list":
              return (
                <div key={key} className="my-2 flex flex-col gap-1.5">
                  {b.items.map((item, j) =>
                    item.checked !== null ? (
                      <div
                        key={j}
                        className="flex items-start gap-2.5 p-[8px_12px]"
                        style={{
                          backgroundColor: "var(--ui-surface-sunken)",
                          borderRadius: "var(--ui-radius-md)",
                          opacity: item.checked ? 0.75 : 1,
                        }}
                      >
                        <span
                          aria-hidden
                          className="mt-px flex h-[16px] w-[16px] flex-[0_0_16px] items-center justify-center rounded-[4px] text-[11px] font-bold"
                          style={{
                            border: `1.5px solid ${item.checked ? "var(--ui-okabe-bluish-green)" : "var(--ui-border-strong)"}`,
                            backgroundColor: item.checked ? "var(--ui-okabe-bluish-green)" : "transparent",
                            color: "var(--ui-on-accent)",
                          }}
                        >
                          {item.checked ? "✓" : ""}
                        </span>
                        <span className="[overflow-wrap:anywhere]">{renderInline(item.text, `${key}-${j}`)}</span>
                      </div>
                    ) : (
                      <div key={j} className="flex items-start gap-2.5 pl-1">
                        <span aria-hidden style={{ color: "var(--ui-content-muted)" }}>
                          •
                        </span>
                        <span className="[overflow-wrap:anywhere]">{renderInline(item.text, `${key}-${j}`)}</span>
                      </div>
                    ),
                  )}
                </div>
              );
            case "hr":
              return <hr key={key} className="my-4 border-0 border-t" style={{ borderColor: "var(--ui-border-default)" }} />;
          }
        })}
      </div>
    </div>
  );
}
