// Storyboard chrome components (kit sheet: GroupedList, Row,
// StatusChip, PickerChips, Dialog over Scrim, NoticeRow)
// composed app-locally on Workhorse Kit v1 tokens. The extracted
// kit v1 ships the workbench's 24 primitives + tokens; these
// named storyboard components are not among its files, so they
// are built here from kit tokens only — no local palette, type,
// or radius values. Recorded as a kit gap in the lane report.
// The kit sheet's LogRow is NOT built here: since the
// timeline-component study (2026-11-13) it ships in the kit
// itself (@workhorse/kit/components/LogRow) and Events consumes
// that one shared component.

import { useState, type ReactNode } from "react";
import { ChevronRight, TriangleAlert } from "lucide-react";
import type { Tone } from "../venue/types";
import { Button } from "@workhorse/kit/components/Button";
import { Input } from "@workhorse/kit/components/Fields";

export function GroupLabel({ children }: { children: ReactNode }) {
  return <div className="rn-glabel">{children}</div>;
}

export function GroupedList({ children }: { children: ReactNode }) {
  return <div className="rn-group">{children}</div>;
}

export function Row({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick?: () => void;
}) {
  const inner = <>{children}</>;
  if (onClick) {
    return (
      <button type="button" className="rn-row rn-row-btn" onClick={onClick}>
        {inner}
      </button>
    );
  }
  return <div className="rn-row">{inner}</div>;
}

/** RowText — the two-line stack form (the lease-row form,
 *  owner's row ruling 2026-11-13, matching the kit Row): the
 *  label gets line 1 and truncates; the sub gets line 2,
 *  truncating, with the trailing content (`end` — a status
 *  chip, an action cluster) riding that line flex-none at its
 *  right. Neither text line ever competes with the chip for
 *  width, so the row can never balloon at phone width. With
 *  no sub, `end` rides the label line. Rows that flanked the
 *  text with a sibling rn-ml-auto chip span migrate to `end`. */
export function RowText({
  label,
  sub,
  mono,
  end,
}: {
  label: ReactNode;
  sub?: ReactNode;
  mono?: boolean;
  end?: ReactNode;
}) {
  const trailing = end ? <span className="rn-stack-end">{end}</span> : null;
  return (
    <div className="rn-stack">
      <div className="rn-stack-top">
        <span className={mono ? "rn-lab rn-name mono" : "rn-lab rn-name"}>{label}</span>
        {sub ? null : trailing}
      </div>
      {sub ? (
        <div className="rn-stack-sub">
          <span className="rn-sub rn-sub-truncate">{sub}</span>
          {trailing}
        </div>
      ) : null}
    </div>
  );
}

export function RowValue({ children }: { children: ReactNode }) {
  return <span className="rn-val">{children}</span>;
}

export function Chevron() {
  return <ChevronRight size={15} className="rn-chev" aria-hidden />;
}

export function ActionRow({
  label,
  danger,
  onClick,
}: {
  label: string;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={danger ? "rn-row rn-row-btn rn-action danger" : "rn-row rn-row-btn rn-action"}
      onClick={onClick}
    >
      <span className="rn-lab">{label}</span>
    </button>
  );
}

const TONE_HUE: Record<Exclude<Tone, "idle">, string> = {
  ok: "var(--wb-okabe-bluish-green)",
  info: "var(--wb-okabe-blue)",
  warn: "var(--wb-okabe-orange)",
  fail: "var(--wb-okabe-vermilion)",
};

export function StatusChip({ tone, label }: { tone: Tone; label: string }) {
  if (tone === "idle") {
    return (
      <span
        className="rn-chip"
        style={{
          backgroundColor: "var(--wb-surface-sunken)",
          color: "var(--wb-content-secondary)",
        }}
      >
        <i style={{ backgroundColor: "var(--wb-content-muted)" }} />
        <span className="rn-chip-lab">{label}</span>
      </span>
    );
  }
  const hue = TONE_HUE[tone];
  return (
    <span
      className="rn-chip"
      style={{
        backgroundColor: `color-mix(in srgb, ${hue} 16%, transparent)`,
        color: `color-mix(in srgb, ${hue} 78%, var(--wb-content-primary))`,
      }}
    >
      <i style={{ backgroundColor: hue }} />
      <span className="rn-chip-lab">{label}</span>
    </span>
  );
}

export function PickerChips<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  ariaLabel: string;
}) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }} role="group" aria-label={ariaLabel}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            className="rn-chip rn-pick"
            onClick={() => onChange(o.value)}
            style={
              on
                ? {
                    backgroundColor: "var(--wb-accent)",
                    borderColor: "var(--wb-accent)",
                    color: "var(--wb-on-accent)",
                  }
                : {
                    backgroundColor: "var(--wb-surface-2)",
                    borderColor: "var(--wb-border-strong)",
                    color: "var(--wb-content-secondary)",
                  }
            }
          >
            <span className="rn-chip-lab">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Duration picker — the panel's shared duration set as
 *  chips (adapter-served options) plus a custom-hours input;
 *  typing a custom value supersedes the chips, and a value
 *  no chip carries renders as its own chip so the current
 *  choice is always visible. The value is hours throughout:
 *  the control is a duration, not a preset id. */
export function DurationPicker({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { hours: number; label: string }[];
  value: number;
  onChange: (hours: number) => void;
  ariaLabel: string;
}) {
  const [custom, setCustom] = useState("");
  const matched = options.some((o) => o.hours === value);
  return (
    <span
      style={{ display: "inline-flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}
    >
      <PickerChips
        ariaLabel={ariaLabel}
        value={matched ? String(value) : "__custom__"}
        onChange={(v) => {
          if (v !== "__custom__") {
            setCustom("");
            onChange(Number(v));
          }
        }}
        options={[
          ...options.map((o) => ({ value: String(o.hours), label: o.label })),
          ...(matched ? [] : [{ value: "__custom__", label: `${value}h` }]),
        ]}
      />
      <span style={{ width: 96 }}>
        <Input
          type="number"
          min="0.25"
          step="0.25"
          ariaLabel={`${ariaLabel} — custom hours`}
          placeholder="Custom h"
          value={custom}
          onChange={(e) => {
            setCustom(e.target.value);
            const v = Number(e.target.value);
            if (Number.isFinite(v) && v > 0) onChange(v);
          }}
        />
      </span>
    </span>
  );
}

export function NoticeRow({ children }: { children: ReactNode }) {
  return (
    <div className="rn-notice" role="status">
      <TriangleAlert size={18} aria-hidden style={{ flex: "0 0 18px", marginTop: 1 }} />
      <span>{children}</span>
    </div>
  );
}

export function Dialog({
  title,
  body,
  confirmLabel,
  danger,
  onConfirm,
  onCancel,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="rn-scrim" role="presentation" onClick={onCancel}>
      <div
        className="rn-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rn-dialog-title">{title}</div>
        <div className="rn-dialog-body">{body}</div>
        <div className="rn-dialog-actions">
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rn-notice rn-notice-fail" role="alert">
      <TriangleAlert size={18} aria-hidden style={{ flex: "0 0 18px", marginTop: 1 }} />
      <span>{message}</span>
    </div>
  );
}
