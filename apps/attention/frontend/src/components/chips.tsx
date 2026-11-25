// App-local presentation chips, styled entirely from kit
// token variables. The kit sheet names StatusChip and
// HandlerChip as kit components, but they are not among the
// 24 extracted viewer primitives (the kit's Chip renders the
// VOC1 ruled statuses only) — recorded as a kit gap in the
// lane report. Severity tones map onto the token status
// table (contract 06): ok -> implemented, info -> canonical,
// warn -> stale, fail -> hard-gate, idle -> sunken/secondary.
import type { CSSProperties } from "react";
import type { PresenceView, Severity } from "../attention/types";

const HUE_VAR: Record<Severity, string> = {
  ok: "var(--ui-status-implemented)",
  info: "var(--ui-status-canonical)",
  warn: "var(--ui-status-stale)",
  fail: "var(--ui-status-hard-gate)",
  idle: "var(--ui-content-muted)",
};
const TEXT_VAR: Record<Severity, string> = {
  ok: "var(--ui-status-implemented-text)",
  info: "var(--ui-status-canonical-text)",
  warn: "var(--ui-status-stale-text)",
  fail: "var(--ui-status-hard-gate-text)",
  idle: "var(--ui-content-secondary)",
};

function chipStyle(severity: Severity): CSSProperties {
  if (severity === "idle") {
    return {
      backgroundColor: "var(--ui-surface-sunken)",
      color: TEXT_VAR.idle,
      borderRadius: "var(--ui-radius-pill)",
    };
  }
  return {
    backgroundColor: `color-mix(in srgb, ${HUE_VAR[severity]} 14%, transparent)`,
    color: TEXT_VAR[severity],
    borderRadius: "var(--ui-radius-pill)",
  };
}

const CHIP_CLASSES =
  "inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold whitespace-nowrap";
const CHIP_CLASSES_LARGE =
  "inline-flex items-center gap-1.5 px-3.5 py-1.5 text-sm font-semibold whitespace-nowrap";

export function SeverityChip({
  severity,
  label,
  large = false,
}: {
  severity: Severity;
  label: string;
  large?: boolean;
}) {
  return (
    <span
      className={`${large ? CHIP_CLASSES_LARGE : CHIP_CLASSES} min-w-0`}
      style={{ ...chipStyle(severity), maxWidth: "100%" }}
    >
      <span
        aria-hidden="true"
        className="inline-block h-[7px] w-[7px] shrink-0 rounded-full"
        style={{ backgroundColor: HUE_VAR[severity] }}
      />
      <span className="truncate">{label}</span>
    </span>
  );
}

/** The per-handler chip: handler name in the tint of the
 * handler's most urgent open item (storyboard form). */
export function HandlerChip({ label, severity }: { label: string; severity: Severity }) {
  return <SeverityChip severity={severity} label={label} />;
}

export function PresenceChipView({
  presence,
  large = false,
}: {
  presence: PresenceView;
  large?: boolean;
}) {
  return (
    <SeverityChip severity={presence.chip_severity} label={presence.chip_label} large={large} />
  );
}

/** Identity dot in the handler's registry color_slot
 * (the token chart series, --ui-chart-1..7). */
export function HandlerDot({ colorSlot, size = 9 }: { colorSlot: number; size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block shrink-0 rounded-full"
      style={{
        width: size,
        height: size,
        backgroundColor: `var(--ui-chart-${((colorSlot - 1) % 7) + 1})`,
      }}
    />
  );
}
