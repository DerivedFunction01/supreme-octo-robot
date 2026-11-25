// The iOS form vocabulary the scheduler storyboard composes —
// GroupedList / GroupLabel / Row / NoticeRow / ActionRow and the
// outcome StatusChip — rendered from Workhorse Kit v1 tokens.
//
// KIT GAP (reported in the lane report): the kit sheet names
// these components, but the extracted kit's 24 primitives do not
// include them (its Chip/Badge render the ruled-status table,
// not run outcomes). They are composed here from kit tokens —
// no kit code is copied — pending the kit extension that S8 or
// a kit lane lands once, in the kit's home, for every consumer.

import type { CSSProperties, ReactNode } from "react";
import { ChevronRight, TriangleAlert } from "lucide-react";
import type { JobView, RunView } from "../types";
import { fmtTimeOfDay } from "../format";

export type Tone = "ok" | "info" | "warn" | "fail" | "idle";

const TONE_HUE: Record<Tone, string> = {
  ok: "var(--ui-status-done)",
  info: "var(--ui-status-canonical)",
  warn: "var(--ui-status-stale)",
  fail: "var(--ui-status-hard-gate)",
  idle: "var(--ui-content-muted)",
};

const TONE_TEXT: Record<Tone, string> = {
  ok: "var(--ui-status-done-text)",
  info: "var(--ui-status-canonical-text)",
  warn: "var(--ui-status-stale-text)",
  fail: "var(--ui-status-hard-gate-text)",
  idle: "var(--ui-content-secondary)",
};

/** Settings-row composition for the kit Toggle: the row
 *  carries its own visible label (a Lab or title span), so the
 *  Toggle's own label span is visually hidden — it stays in
 *  the accessibility tree as the switch's name. Passed through
 *  the Toggle's className seam; the kit is untouched. (The
 *  same composition the workbench app uses.) */
export const TOGGLE_LABEL_SR_ONLY = "[&>span:last-of-type]:sr-only";

export function OutcomeChip({
  tone,
  text,
  onPress,
}: {
  tone: Tone;
  text: string;
  onPress?: () => void;
}) {
  const style: CSSProperties = {
    backgroundColor:
      tone === "idle"
        ? "var(--ui-surface-sunken)"
        : `color-mix(in srgb, ${TONE_HUE[tone]} 14%, transparent)`,
    color: TONE_TEXT[tone],
    borderRadius: "var(--ui-chip-radius)",
  };
  const inner = (
    <>
      <span
        aria-hidden="true"
        className="inline-block h-[7px] w-[7px] shrink-0 rounded-full"
        style={{ backgroundColor: TONE_HUE[tone] }}
      />
      <span className="truncate">{text}</span>
    </>
  );
  // shrink-0: a chip never yields its width to a flex
  // sibling — inside the Pings row's label span the summary
  // text squeezed the chip until its own label ellipsized
  // ("Wake" rendered "W…", mobile critic). The
  // sibling text truncates instead; the chip stays whole.
  const classes =
    "inline-flex max-w-full shrink-0 items-center gap-1.5 overflow-hidden px-2.5 py-[2.5px] text-xs font-semibold whitespace-nowrap";
  if (onPress) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onPress();
        }}
        // The button form is a tap target: 28px tall clears
        // the 24px target bar the static chip's 21px missed.
        className={`${classes} min-h-[28px] cursor-pointer border-0 focus-visible:outline-2 focus-visible:outline-(--ui-focus-ring)`}
        style={style}
      >
        {inner}
      </button>
    );
  }
  return (
    <span className={classes} style={style}>
      {inner}
    </span>
  );
}

/** The status chip for one job row — a fixed presentation
 *  mapping over served status/label/detail, in the chip's
 *  shortest served form: outcome + time only (Ran · time /
 *  Failed · exit n / Skipped / Next · time / Disabled). A
 *  run's reason ("Skipped · venue busy") never rides the
 *  chip — it stays in the job detail and the ledger, where
 *  the served detail prose belongs. */
export function jobChip(
  job: JobView,
  withDuration = false,
): { tone: Tone; text: string } {
  if (job.status === "suspended") return { tone: "idle", text: "Disabled" };
  if (job.last_activity) {
    switch (job.last_activity.state) {
      case "pending":
        return { tone: "warn", text: "Waiting" };
      case "overdue":
        return { tone: "fail", text: job.last_activity.label };
      case "served":
        return { tone: "info", text: job.last_activity.label };
      case "served_acked":
        return { tone: "ok", text: job.last_activity.label };
    }
  }
  const run = job.last_run;
  if (!run) {
    return job.next_due
      ? { tone: "idle", text: `Next · ${fmtTimeOfDay(job.next_due, job.timezone)}` }
      : { tone: "idle", text: "No runs yet" };
  }
  return runChip(run, job.timezone, withDuration);
}

export function runChip(
  run: RunView,
  tz?: string,
  withDuration = false,
): { tone: Tone; text: string } {
  switch (run.status) {
    case "running":
      return { tone: "info", text: "Running" };
    case "skipped_overlap":
      return { tone: "warn", text: "Skipped" };
    case "ok":
      if (run.detail?.startsWith("Skipped · ")) {
        // The skip's reason is detail prose, not chip text:
        // the chip carries the bare outcome, matching the
        // skipped_overlap chip (owner ruling).
        return { tone: "warn", text: "Skipped" };
      }
      return {
        tone: "ok",
        text:
          `Ran · ${fmtTimeOfDay(run.ts, tz)}` +
          (withDuration && run.duration_label ? ` · ${run.duration_label}` : ""),
      };
    case "failed":
      return { tone: "fail", text: run.label };
    case "timeout":
      return { tone: "fail", text: "Timed out" };
    case "could_not_start":
      return { tone: "fail", text: "Could not start" };
  }
}

export function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <div
      className="mt-5 mb-2 ml-[2px] text-xs font-bold tracking-[0.07em] uppercase first:mt-0"
      style={{ color: "var(--ui-content-secondary)" }}
    >
      {children}
    </div>
  );
}

export function Group({ children }: { children: ReactNode }) {
  return (
    <div
      className="overflow-hidden [&>*+*]:border-t"
      style={{
        backgroundColor: "var(--ui-surface-2)",
        borderColor: "var(--ui-border-default)",
        borderStyle: "solid",
        borderWidth: 1,
        borderRadius: "var(--ui-radius-lg)",
        // [&>*+*] needs the colour too; border-top colour inherits
        // this element's border colour via border-color on children.
      }}
    >
      {children}
    </div>
  );
}

export function Row({
  label,
  sub,
  end,
  chevron = false,
  onClick,
}: {
  label: ReactNode;
  sub?: ReactNode;
  end?: ReactNode;
  chevron?: boolean;
  onClick?: () => void;
}) {
  // Two-line discipline (the owner's row ruling
  // — the same cure the Runner's lease rows took when the
  // "Renewal due" chip clipped against the name): the label
  // gets its own line and flexes across the full row width,
  // the chevron pinned at that line's end; the chip never
  // competes with the label for the name line's width. When
  // the row carries a details line (sub), the trailing
  // content rides THAT line — right-aligned and flex-none,
  // so the details text truncates and the chip never clips.
  // A row with no details line (the Settings sheet's select
  // rows) keeps its trailing content on the label line.
  const hasSub = !!sub;
  const trailing = end ? (
    <div className="ml-auto flex flex-none items-center gap-2">{end}</div>
  ) : null;
  const chevronEl = chevron ? (
    <ChevronRight
      size={15}
      className="flex-none"
      style={{ color: "var(--ui-content-muted)" }}
    />
  ) : null;
  const content = (
    <div className="min-w-0 flex-1">
      <div className="flex flex-nowrap items-center gap-3">
        <div
          className="min-w-0 flex-1 truncate text-[14.5px] font-medium"
          style={{ color: "var(--ui-content-primary)" }}
        >
          {label}
        </div>
        {hasSub ? null : trailing}
        {chevronEl}
      </div>
      {hasSub ? (
        <div className="flex flex-nowrap items-center gap-2">
          <div
            className="min-w-0 flex-1 truncate text-[12.5px]"
            style={{ color: "var(--ui-content-secondary)" }}
          >
            {sub}
          </div>
          {trailing}
        </div>
      ) : null}
    </div>
  );
  const classes =
    "flex min-h-[47px] w-full flex-nowrap items-center gap-3 px-3.5 py-[11px] text-left";
  const style: CSSProperties = { borderTopColor: "var(--ui-border-default)" };
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${classes} cursor-pointer border-0 bg-transparent hover:bg-(--ui-surface-1) focus-visible:outline-2 focus-visible:outline-(--ui-focus-ring)`}
        style={style}
      >
        {content}
      </button>
    );
  }
  return (
    <div className={classes} style={style}>
      {content}
    </div>
  );
}

/** The family tag on a built-in row (mockup form: 11px bold,
 *  letterspaced, secondary on sunken, 7px radius). Direct
 *  built-ins carry no tag — placement is the whole statement. */
export function ServiceTag({ label }: { label: string }) {
  return (
    <span
      className="flex-none rounded-[7px] px-[7px] py-[2px] text-[11px] font-bold tracking-[0.05em]"
      style={{
        color: "var(--ui-content-secondary)",
        backgroundColor: "var(--ui-surface-sunken)",
      }}
    >
      {label}
    </span>
  );
}

/** The compact single-line row of the Jobs Built-in group
 *  (mockup form: 36px min-height, 13.5px truncating label,
 *  the family tag at the right; no chevron glyph — the row
 *  itself is the button). */
export function CompactRow({
  label,
  tag,
  onClick,
}: {
  label: string;
  tag?: string | null;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span
        className="min-w-0 flex-1 truncate text-[13.5px] font-medium"
        style={{ color: "var(--ui-content-primary)" }}
      >
        {label}
      </span>
      {tag ? <ServiceTag label={tag} /> : null}
    </>
  );
  const classes =
    "flex min-h-[36px] w-full flex-nowrap items-center gap-3 px-3.5 py-1.5 text-left";
  const style: CSSProperties = { borderTopColor: "var(--ui-border-default)" };
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${classes} cursor-pointer border-0 bg-transparent hover:bg-(--ui-surface-1) focus-visible:outline-2 focus-visible:outline-(--ui-focus-ring)`}
        style={style}
      >
        {content}
      </button>
    );
  }
  return (
    <div className={classes} style={style}>
      {content}
    </div>
  );
}

/** Fact row: label left, value right (the detail Facts form).
 *  At phone width (the kit 480px breakpoint) the row stacks —
 *  label on its own line, value beneath it at full width,
 *  left-aligned — the same two-line principle as the Row cure:
 *  a long value (a job title, a suspend reason) then wraps as
 *  ordinary full-width prose instead of stacking into a tall
 *  narrow right-aligned column beside the shrink-0 label. */
export function FactRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div
      className="flex min-h-[47px] min-w-0 items-center gap-3 px-3.5 py-[11px] max-[480px]:flex-col max-[480px]:items-stretch max-[480px]:gap-1"
      style={{ borderTopColor: "var(--ui-border-default)" }}
    >
      <span
        className="shrink-0 text-[14.5px] font-medium"
        style={{ color: "var(--ui-content-primary)" }}
      >
        {label}
      </span>
      <span
        className="ml-auto flex min-w-0 items-center gap-2 text-right text-sm [overflow-wrap:anywhere] max-[480px]:ml-0 max-[480px]:text-left"
        style={{ color: "var(--ui-content-secondary)" }}
      >
        {children}
      </span>
    </div>
  );
}

export function NoticeRow({
  title,
  text,
}: {
  title: string;
  text: string;
}) {
  return (
    <div
      className="mb-[18px] flex items-start gap-[11px] rounded-xl px-3.5 py-3 text-sm"
      style={{
        backgroundColor:
          "color-mix(in srgb, var(--ui-okabe-orange) 20%, var(--ui-surface-2))",
        borderColor: "var(--ui-okabe-orange)",
        borderStyle: "solid",
        borderWidth: 1,
        color: "var(--ui-status-stale-text)",
      }}
      role="status"
    >
      <TriangleAlert size={18} className="mt-[1px] shrink-0" />
      <span className="min-w-0 [overflow-wrap:anywhere]">
        <b className="font-bold">{title}</b> {text}
      </span>
    </div>
  );
}

export function ActionRow({
  label,
  danger = false,
  onClick,
}: {
  label: string;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[47px] w-full cursor-pointer items-center px-3.5 py-[11px] text-left hover:bg-(--ui-surface-1) focus-visible:outline-2 focus-visible:outline-(--ui-focus-ring)"
      style={{
        borderTopColor: "var(--ui-border-default)",
        backgroundColor: "transparent",
        borderWidth: 0,
      }}
    >
      <span
        className="min-w-0 truncate text-[14.5px] font-semibold"
        style={{
          color: danger
            ? "var(--ui-status-hard-gate-text)"
            : "var(--ui-accent)",
        }}
      >
        {label}
      </span>
    </button>
  );
}

/** The views' page heading — title + served subtitle. (Moved
 *  from the retired app-local shell when the views re-pointed
 *  to the kit AppShell; it is view furniture, not chrome.) The
 *  h2 carries the sc-largetitle hook: at phone width the kit
 *  PhoneShell's navbar already carries the title, so the app
 *  CSS suppresses this one there (see index.css) and the
 *  served subtitle stays as the only line under it. */
export function LargeTitle({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <>
      <h2
        className="sc-largetitle m-0 text-[27px] font-bold tracking-[-0.015em] [overflow-wrap:anywhere]"
        style={{ color: "var(--ui-content-primary)" }}
      >
        {title}
      </h2>
      <p
        className="mt-1 mb-5 text-sm [overflow-wrap:anywhere]"
        style={{ color: "var(--ui-content-secondary)" }}
      >
        {subtitle}
      </p>
    </>
  );
}

export function ActionError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="mt-2 ml-[2px] text-[13px]"
      style={{ color: "var(--ui-status-hard-gate-text)" }}
    >
      {message}
    </p>
  );
}
