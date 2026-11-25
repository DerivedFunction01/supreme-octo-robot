import type { CSSProperties, ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Badge } from "@kit/components/display/Badge";
import { Chip, type RuledStatus } from "@kit/components/controls/Chip";
import type { ReviewState, TodoStatus } from "../lib/types";

// The iOS form vocabulary (kit sheet): GroupedList, GroupLabel,
// Row, ActionRow, StatRow — composed here over kit tokens, the
// way every storyboard frame composes them.

export function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <div
      className="mt-5 mb-2 ml-1 text-xs font-bold tracking-[0.07em] uppercase [overflow-wrap:anywhere] first:mt-0"
      style={{ color: "var(--ui-content-secondary)" }}
    >
      {children}
    </div>
  );
}

export function Group({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      className="overflow-hidden"
      style={{
        backgroundColor: "var(--ui-surface-2)",
        borderColor: "var(--ui-border-default)",
        borderStyle: "solid",
        borderWidth: 1,
        borderRadius: "var(--ui-radius-lg)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function Row({
  children,
  onClick,
  selected,
  last,
}: {
  children: ReactNode;
  onClick?: () => void;
  selected?: boolean;
  last?: boolean;
}) {
  const style: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "11px 14px",
    minHeight: 47,
    width: "100%",
    textAlign: "left",
    backgroundColor: selected ? "var(--ui-highlight-selection-fill)" : undefined,
    borderBottom: last ? undefined : "1px solid var(--ui-border-default)",
    cursor: onClick ? "pointer" : undefined,
    color: "var(--ui-content-primary)",
  };
  if (onClick) {
    return (
      <button type="button" onClick={onClick} style={style}>
        {children}
      </button>
    );
  }
  return <div style={style}>{children}</div>;
}

// Long-text posture (stage-gate rule): single-line labels
// truncate with ellipsis inside a min-w-0 box; wrapping text
// breaks anywhere rather than overflowing; a row value may
// take at most 60% of the row before it ellipsizes, so the
// label always keeps a presence.
export function Lab({ children }: { children: ReactNode }) {
  return <span className="block min-w-0 truncate text-[14.5px] font-medium">{children}</span>;
}

export function Sub({ children, truncate = false }: { children: ReactNode; truncate?: boolean }) {
  // Two-line row form (the kit's sanctioned row): the sub
  // truncates on one line. Card/prose subs keep the default
  // wrap-anywhere behavior.
  if (truncate) {
    return (
      <div className="truncate text-[12.5px]" style={{ color: "var(--ui-content-secondary)" }}>
        {children}
      </div>
    );
  }
  return (
    <div className="text-[12.5px] [overflow-wrap:anywhere]" style={{ color: "var(--ui-content-secondary)" }}>
      {children}
    </div>
  );
}

export function Val({ children, mono }: { children: ReactNode; mono?: boolean }) {
  return (
    <span
      className={`ml-auto max-w-[60%] min-w-0 truncate text-sm ${mono ? "font-mono" : ""}`}
      style={{ color: "var(--ui-content-secondary)" }}
    >
      {children}
    </span>
  );
}

export function Chev() {
  return <ChevronRight size={15} style={{ color: "var(--ui-content-muted)", flex: "0 0 auto" }} />;
}

export function ActionRow({
  label,
  danger,
  onClick,
  last,
}: {
  label: string;
  danger?: boolean;
  onClick: () => void;
  last?: boolean;
}) {
  return (
    <Row onClick={onClick} last={last}>
      <span
        className="min-w-0 truncate text-[14.5px] font-semibold"
        style={{ color: danger ? "var(--ui-danger)" : "var(--ui-accent)" }}
      >
        {label}
      </span>
    </Row>
  );
}

export function LargeTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="ui-largetitle m-0 mb-1 text-[27px] font-bold tracking-[-0.015em] [overflow-wrap:anywhere]">{children}</h2>
  );
}

export function Subtitle({ children }: { children: ReactNode }) {
  return (
    <p className="m-0 mb-5 text-sm [overflow-wrap:anywhere]" style={{ color: "var(--ui-content-secondary)" }}>
      {children}
    </p>
  );
}

/** Settings-row composition for the kit Toggle: the row
 *  carries its own visible label (a Lab or title span), so the
 *  Toggle's own label span is visually hidden — it stays in
 *  the accessibility tree as the switch's name. Passed through
 *  the Toggle's className seam; the kit is untouched. */
export const TOGGLE_LABEL_SR_ONLY = "[&>span:last-of-type]:sr-only";

/** Ruled status → kit Chip (the ONE rendering, SPEC §5.1). */
export function RuledChip({ status, gate }: { status: RuledStatus; gate?: string }) {
  return <Chip status={status} gate={gate} />;
}

/** Review/derived state → kit Badge (outline, never a Chip). */
export function ReviewBadge({
  kind,
  text,
  stateHash,
}: {
  kind: ReviewState;
  text: string;
  stateHash?: string;
}) {
  return <Badge kind={kind} text={text} stateHash={stateHash} />;
}

const TODO_PILL: Record<TodoStatus, { word: string; dot: string; bg: string; fg: string }> = {
  done: {
    word: "Done",
    dot: "var(--ui-okabe-bluish-green)",
    bg: "color-mix(in srgb, var(--ui-okabe-bluish-green) 14%, transparent)",
    fg: "var(--ui-status-implemented-text)",
  },
  doing: {
    word: "Doing",
    dot: "var(--ui-okabe-blue)",
    bg: "color-mix(in srgb, var(--ui-okabe-blue) 12%, transparent)",
    fg: "var(--ui-status-canonical-text)",
  },
  todo: {
    word: "To do",
    dot: "var(--ui-content-muted)",
    bg: "var(--ui-surface-sunken)",
    fg: "var(--ui-content-secondary)",
  },
  blocked: {
    word: "Blocked",
    dot: "var(--ui-okabe-vermilion)",
    bg: "color-mix(in srgb, var(--ui-okabe-vermilion) 12%, transparent)",
    fg: "var(--ui-status-hard-gate-text)",
  },
};

/** Work-status pill for file todos (todo|doing|blocked|done —
 *  the work record's own states, distinct from the ruled
 *  entry vocabulary the kit Chip renders). */
export function TodoPill({ status }: { status: TodoStatus }) {
  const p = TODO_PILL[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold whitespace-nowrap"
      style={{ backgroundColor: p.bg, color: p.fg }}
    >
      <span className="block h-[7px] w-[7px] rounded-full" style={{ backgroundColor: p.dot }} />
      {p.word}
    </span>
  );
}

export function relTime(iso: string, now: Date = new Date()): string {
  const ms = now.getTime() - new Date(iso).getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

/** Simple line diff (context / add / del) between HEAD and
 *  the working tree — the peek's Diff tab renders this.
 *  The implementation lives in lib/lineDiff (the adapters'
 *  diff model shares it, and the validate harness bundles
 *  seam code headlessly); re-exported here so existing
 *  imports keep their path. */
export { lineDiff } from "../lib/lineDiff";
