import { useState, type ReactNode } from "react";
import type { Snapshot } from "../venue/types";
import { fmtTime } from "../venue/adapter";
import {
  ActionRow,
  Chevron,
  GroupLabel,
  GroupedList,
  NoticeRow,
  Row,
  RowText,
  StatusChip,
} from "../components/ui";
import { EmptyState } from "@workhorse/kit/components/EmptyState";
import { GrantCard } from "./GrantCard";

/** Frame 1 — Leases. Also renders frame 8 (Degraded) when the
 *  adapter reports the lease server unreachable. */
export function LeasesView({
  snap,
  query,
  onOpenLease,
  onTryAgain,
  onRestart,
  busy,
}: {
  snap: Snapshot;
  query: string;
  onOpenLease: (session: string) => void;
  onTryAgain: () => void;
  onRestart: () => void;
  busy: boolean;
}) {
  if (snap.degraded) {
    return <DegradedLeases snap={snap} onTryAgain={onTryAgain} onRestart={onRestart} busy={busy} />;
  }
  const q = query.trim().toLowerCase();
  const leases = snap.leases.filter(
    (l) =>
      !q ||
      l.displayName.toLowerCase().includes(q) ||
      (l.caller ?? "").toLowerCase().includes(q) ||
      l.session.includes(q),
  );
  return (
    <>
      <h2 className="rn-largetitle">Leases</h2>
      <p className="rn-subtitle">
        Balance {snap.budget.balanceCu} CU · {snap.runningCount} sessions running
      </p>
      {snap.grant ? <GrantCard snap={snap} /> : null}
      <GroupLabel>Running</GroupLabel>
      {leases.length === 0 ? (
        <EmptyState message="No sessions match this search" detail="Live leases are listed here as the venue serves them." />
      ) : (
        <GroupedList>
          {leases.map((l) => (
            <LeaseRow
              key={l.session}
              name={l.displayName}
              details={
                <>
                  {l.shapeLabel} · <span className="mono">{l.caller ?? "unattributed"}</span> ·{" "}
                  {l.endsLabel}
                </>
              }
              chip={<StatusChip tone={l.stateTone} label={l.stateLabel} />}
              chevron
              onClick={() => onOpenLease(l.session)}
            />
          ))}
        </GroupedList>
      )}
      <GroupLabel>Recent runs</GroupLabel>
      <GroupedList>
        {snap.recentRuns.map((r) => (
          <Row key={r.runId}>
            <RowText
              label={r.job}
              mono
              sub={
                <>
                  {r.sessionName} · {r.durationLabel}
                </>
              }
              end={<StatusChip tone={r.stateTone} label={r.stateLabel} />}
            />
          </Row>
        ))}
      </GroupedList>
    </>
  );
}

/** Lease row — the owner's form (ruled 2026-11-13 from his phone
 *  screenshot, where the old row's "Renewal due" chip clipped to
 *  "Renewal du" against the wrapped details block): line 1 is the
 *  lease name + status badge + chevron, line 2 the details at
 *  full row width — the same form the Recent Runs rows use. The
 *  badge slot is flex-none so a badge can never be clipped; the
 *  name is the only element that gives, truncating with an
 *  ellipsis. */
function LeaseRow({
  name,
  details,
  chip,
  chevron,
  onClick,
}: {
  name: string;
  details: ReactNode;
  chip: ReactNode;
  chevron?: boolean;
  onClick?: () => void;
}) {
  return (
    <Row onClick={onClick}>
      <div className="rn-stack">
        <div className="rn-stack-top">
          <span className="rn-lab rn-name">{name}</span>
          <span className="rn-stack-end">
            {chip}
            {chevron ? <Chevron /> : null}
          </span>
        </div>
        <div className="rn-sub">{details}</div>
      </div>
    </Row>
  );
}

/** Frame 8 — Degraded: lease server unreachable. */
function DegradedLeases({
  snap,
  onTryAgain,
  onRestart,
  busy,
}: {
  snap: Snapshot;
  onTryAgain: () => void;
  onRestart: () => void;
  busy: boolean;
}) {
  return (
    <>
      <h2 className="rn-largetitle">Leases</h2>
      <p className="rn-subtitle">
        Showing the last served state · {snap.lastServedAt ? fmtTime(snap.lastServedAt) : "—"}
      </p>
      <NoticeRow>
        <b>Lease server unreachable.</b> {snap.leases.length} sessions were live at the last
        check; their state is frozen until the server answers.
      </NoticeRow>
      <GroupLabel>Last known</GroupLabel>
      <GroupedList>
        {snap.leases.map((l) => (
          <LeaseRow
            key={l.session}
            name={l.displayName}
            details={
              <>
                {l.shapeLabel} · <span className="mono">{l.caller ?? "unattributed"}</span> · ends{" "}
                {fmtTime(l.deadline)}
              </>
            }
            chip={<StatusChip tone="idle" label="Last known" />}
          />
        ))}
      </GroupedList>
      <GroupLabel>Recovery</GroupLabel>
      <GroupedList>
        <ActionRow label={busy ? "Probing…" : "Try again"} onClick={onTryAgain} />
        <ActionRow label="Restart lease server" danger onClick={onRestart} />
      </GroupedList>
    </>
  );
}

export function useBusy(): [boolean, (fn: () => Promise<unknown>) => Promise<void>] {
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };
  return [busy, run];
}
