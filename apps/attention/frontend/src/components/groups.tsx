// The iOS form-language group family (kit sheet: GroupedList,
// GroupLabel, Row, StatRow, SwitchRow, RadioRow). These are
// named kit components that are not among the 24 extracted
// viewer primitives — composed here from kit tokens at the
// storyboard's metrics, and recorded as a kit gap in the
// lane report. Interactive controls inside the rows are the
// kit's own primitives (Toggle, Button, SegmentedControl).
import { type ReactNode } from "react";
import { Check, ChevronRight } from "lucide-react";

export function GroupLabel({ children }: { children: ReactNode }) {
  return <div className="glabel">{children}</div>;
}

export function Group({ children }: { children: ReactNode }) {
  // .wb-group, not .group — see the collision note in app.css.
  return <div className="wb-group">{children}</div>;
}

export function Row({
  children,
  onClick,
  padded = false,
}: {
  children: ReactNode;
  onClick?: () => void;
  padded?: boolean;
}) {
  const style = padded ? { padding: "16px" } : undefined;
  if (onClick) {
    return (
      <button type="button" className="row row-button" style={style} onClick={onClick}>
        {children}
      </button>
    );
  }
  return (
    <div className="row" style={style}>
      {children}
    </div>
  );
}

export function RowText({
  label,
  sub,
  subTruncate = false,
}: {
  label: ReactNode;
  sub?: ReactNode;
  subTruncate?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="lab">{label}</div>
      {sub ? <div className={subTruncate ? "sub sub-trunc" : "sub"}>{sub}</div> : null}
    </div>
  );
}

export function RowValue({ children }: { children: ReactNode }) {
  return (
    <span className="val" style={{ marginLeft: "auto" }}>
      {children}
    </span>
  );
}

export function Chevron() {
  return (
    <span style={{ marginLeft: "auto", color: "var(--wb-content-muted)", flex: "0 0 auto" }}>
      <ChevronRight size={15} strokeWidth={2.2} />
    </span>
  );
}

/** RadioRow: label + sub-line, checkmark when selected. */
export function RadioRow({
  label,
  sub,
  selected,
  onSelect,
}: {
  label: string;
  sub?: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className="row row-button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
    >
      <RowText label={label} sub={sub} />
      {selected ? (
        <span style={{ marginLeft: "auto", color: "var(--wb-accent)", flex: "0 0 auto" }}>
          <Check size={18} strokeWidth={2.6} />
        </span>
      ) : null}
    </button>
  );
}
