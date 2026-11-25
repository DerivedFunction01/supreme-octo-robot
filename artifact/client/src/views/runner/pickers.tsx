// Shared runner components: the per-portion status line,
// the notice, the degraded card, the lease status chips,
// and the extend / shorten pickers. Picker selection and
// open state live outside the poll-driven render (the
// panel's rule) — here, in a hook's state, so a portion
// landing never loses a pick or collapses a picker.

import { useState, type ReactNode } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Card } from "@workhorse/kit/components/display/Card";
import { DegradedBanner } from "@workhorse/kit/components/display/DegradedBanner";
import { Input } from "@workhorse/kit/components/controls/Fields";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import {
  EXT_DURATIONS,
  fmtAgeAgo,
  fmtDur,
  type LeaseEntry,
  type Spec,
  specDescriptor,
  specRateText,
} from "./model";
import { useRunner, type PartName, type PartState } from "./state";

/* ---------------- portion status ---------------- */

export function PartStatus({
  name,
  part,
}: {
  name: PartName;
  part: PartState<unknown>;
}) {
  const { refetchPart, now } = useRunner();
  if (part.loadedAt == null && !part.failed) {
    return (
      <p className="text-xs" style={{ color: "var(--ui-content-muted)" }}>
        Loading…
      </p>
    );
  }
  if (part.loadedAt == null && part.failed) {
    return (
      <p
        className="flex items-center gap-2 text-xs"
        style={{ color: "var(--ui-status-hard-gate-text)" }}
      >
        Couldn't load.
        <Button variant="ghost" onClick={() => refetchPart(name)}>
          Retry
        </Button>
      </p>
    );
  }
  if (part.failed) {
    return (
      <p className="text-xs" style={{ color: "var(--ui-status-stale-text)" }}>
        Update failed — last updated{" "}
        {fmtAgeAgo(new Date(part.loadedAt as number).toISOString(), now)}
      </p>
    );
  }
  return null;
}

/* ---------------- notice ---------------- */

export function NoticeBar() {
  const { notice } = useRunner();
  if (!notice) return null;
  return (
    <p role="status" className="text-sm" style={{ color: "var(--ui-content-primary)" }}>
      {notice}
    </p>
  );
}

/* ---------------- degraded (storyboard frame 8) ---------------- */

export function DegradedCard() {
  const { refetchAll, restartServer, busy } = useRunner();
  return (
    <Card>
      <p className="text-base font-semibold">Lease server unreachable</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => refetchAll()}>Try again</Button>
        <Button
          variant="ghost"
          disabled={Boolean(busy.restart)}
          onClick={() => void restartServer()}
        >
          {busy.restart || "Restart lease server"}
        </Button>
      </div>
    </Card>
  );
}

export function AllStaleBanner() {
  return (
    <DegradedBanner
      message="Lease server unreachable — showing the last served state."
    />
  );
}

/* ---------------- lease status chips ---------------- */

export function LeaseStatusChips({ entry }: { entry: LeaseEntry }) {
  const rec = entry.record || {};
  const chips: ReactNode[] = [];
  if (rec.standing) {
    chips.push(<StatusChip key="standing" tone="ok" label="Standing" />);
  } else if (entry.action === "active") {
    chips.push(<StatusChip key="state" tone="ok" label="Active" />);
  } else if (entry.action === "recorded-but-dead") {
    chips.push(<StatusChip key="state" tone="fail" label="Recorded · dead" />);
  } else {
    chips.push(
      <StatusChip key="state" tone="warn" label={entry.action || "unknown"} />,
    );
  }
  // A live-looking record whose work channel the census
  // keeps failing to reach is named beside its state, never
  // instead of it.
  if (entry.channel && entry.channel.verdict === "suspect") {
    chips.push(<StatusChip key="channel" tone="warn" label="Channel suspect" />);
  }
  return <span className="flex flex-none flex-wrap items-center gap-1.5">{chips}</span>;
}

/* ---------------- duration chips ---------------- */

export function DurationChips({
  hours,
  onPick,
  disabled,
}: {
  hours: number;
  onPick: (hours: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {EXT_DURATIONS.map((h) => (
        <Button
          key={h}
          variant={h === hours ? "primary" : "secondary"}
          disabled={disabled}
          onClick={() => onPick(h)}
        >
          {h === 24 ? "24h" : fmtDur(h)}
        </Button>
      ))}
    </div>
  );
}

export function CustomHoursInput({
  onHours,
  ariaLabel,
}: {
  onHours: (hours: number) => void;
  ariaLabel: string;
}) {
  const [text, setText] = useState("");
  return (
    <Input
      type="number"
      min="0.25"
      step="0.25"
      placeholder="Custom (hours)"
      ariaLabel={ariaLabel}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const v = parseFloat(e.target.value);
        if (v > 0) onHours(v);
      }}
      style={{ maxWidth: 180 }}
    />
  );
}

/* ---------------- picker state ---------------- */

export interface PickerState {
  extOpen: Set<string>;
  toggleExt: (key: string) => void;
  closeExt: (key: string) => void;
  extHours: Record<string, number>;
  setExtHours: (key: string, hours: number) => void;
  shortOpen: Set<string>;
  toggleShort: (session: string) => void;
  closeShort: (session: string) => void;
  shortHours: Record<string, number>;
  setShortHours: (session: string, hours: number) => void;
  shortDeadline: Record<string, string>;
  setShortDeadline: (session: string, value: string | null) => void;
}

export function extKey(kind: "lease" | "grant", key: string): string {
  return kind === "grant" ? "grant" : `lease:${key}`;
}

export function usePickers(): PickerState {
  const [extOpen, setExtOpen] = useState<Set<string>>(new Set());
  const [extHoursMap, setExtHoursMap] = useState<Record<string, number>>({});
  const [shortOpen, setShortOpen] = useState<Set<string>>(new Set());
  const [shortHoursMap, setShortHoursMap] = useState<Record<string, number>>({});
  const [shortDeadlineMap, setShortDeadlineMap] = useState<Record<string, string>>({});

  const toggleIn =
    (set: React.Dispatch<React.SetStateAction<Set<string>>>) => (key: string) =>
      set((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });

  const closeIn =
    (set: React.Dispatch<React.SetStateAction<Set<string>>>) => (key: string) =>
      set((prev) => {
        if (!prev.has(key)) return prev;
        const next = new Set(prev);
        next.delete(key);
        return next;
      });

  return {
    extOpen,
    toggleExt: toggleIn(setExtOpen),
    closeExt: closeIn(setExtOpen),
    extHours: extHoursMap,
    setExtHours: (key, hours) =>
      setExtHoursMap((prev) => ({ ...prev, [key]: hours })),
    shortOpen,
    toggleShort: toggleIn(setShortOpen),
    closeShort: closeIn(setShortOpen),
    shortHours: shortHoursMap,
    setShortHours: (session, hours) =>
      setShortHoursMap((prev) => ({ ...prev, [session]: hours })),
    shortDeadline: shortDeadlineMap,
    setShortDeadline: (session, value) =>
      setShortDeadlineMap((prev) => {
        const next = { ...prev };
        if (value == null) delete next[session];
        else next[session] = value;
        return next;
      }),
  };
}

/* ---------------- extend picker ---------------- */

export function ExtendPicker({
  stateKey,
  pickers,
  onApply,
}: {
  stateKey: string;
  pickers: PickerState;
  onApply: () => void;
}) {
  const { busy } = useRunner();
  const hours = pickers.extHours[stateKey] ?? 8;
  const busyLabel = busy[stateKey];
  return (
    <div
      className="mt-3"
      style={{
        borderTop: "1px solid var(--ui-border-default)",
        paddingTop: "var(--ui-space-12, 12px)",
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <DurationChips
          hours={hours}
          disabled={Boolean(busyLabel)}
          onPick={(h) => pickers.setExtHours(stateKey, h)}
        />
        <CustomHoursInput
          ariaLabel="Custom extend hours"
          onHours={(h) => pickers.setExtHours(stateKey, h)}
        />
      </div>
      <Button
        className="mt-2.5 w-full"
        disabled={Boolean(busyLabel)}
        onClick={onApply}
      >
        {busyLabel || `Extend by ${fmtDur(hours)}`}
      </Button>
    </div>
  );
}

/* ---------------- shorten picker ---------------- */

export function ShortenPicker({
  session,
  pickers,
  onApply,
}: {
  session: string;
  pickers: PickerState;
  onApply: () => void;
}) {
  const { busy } = useRunner();
  const hours = pickers.shortHours[session] ?? 8;
  const deadline = pickers.shortDeadline[session] || "";
  const busyLabel = busy[`shorten:${session}`];
  return (
    <div
      className="mt-3"
      style={{
        borderTop: "1px solid var(--ui-border-default)",
        paddingTop: "var(--ui-space-12, 12px)",
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <DurationChips
          hours={deadline ? -1 : hours}
          disabled={Boolean(busyLabel)}
          onPick={(h) => {
            pickers.setShortHours(session, h);
            pickers.setShortDeadline(session, null);
          }}
        />
        <CustomHoursInput
          ariaLabel="Custom shorten hours"
          onHours={(h) => {
            pickers.setShortHours(session, h);
            pickers.setShortDeadline(session, null);
          }}
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-sm" style={{ color: "var(--ui-content-secondary)" }}>
          or end at
        </span>
        <Input
          type="datetime-local"
          ariaLabel="Shorten to deadline"
          value={deadline}
          onChange={(e) =>
            pickers.setShortDeadline(session, e.target.value || null)
          }
          style={{ maxWidth: 240 }}
        />
      </div>
      <Button
        className="mt-2.5 w-full"
        disabled={Boolean(busyLabel)}
        onClick={onApply}
      >
        {busyLabel ||
          (deadline ? "Shorten to the chosen time" : `Shorten by ${fmtDur(hours)}`)}
      </Button>
    </div>
  );
}

/* ---------------- spec row label ---------------- */

export function specSub(spec: Spec): string {
  return `${specDescriptor(spec)} · ${specRateText(spec)}`;
}
