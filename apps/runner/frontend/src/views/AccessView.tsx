import { useState, type ReactNode } from "react";
import type { AccessLogView, Snapshot } from "../venue/types";
import { AdapterError } from "../venue/types";
import { adapter } from "../venue";
import {
  Dialog,
  ErrorNotice,
  GroupLabel,
  GroupedList,
  Row,
  StatusChip,
} from "../components/ui";
import { Button } from "@workhorse/kit/components/controls/Button";
import { LogRow, type LogRowEntry } from "@workhorse/kit/components/display/LogRow";

/** The served AccessLogView is the kit LogRow's entry shape
 *  for the timeline study's scoped variant: its kind is
 *  present only where the record serves a chip, and absent
 *  kinds render no badge — in the row or anywhere else.
 *  This only drops the record-side fields the row doesn't
 *  take (id, at). */
function toEntry(a: AccessLogView): LogRowEntry {
  return {
    dateToken: a.dateToken,
    time: a.time,
    headline: a.headline,
    ...(a.meta ? { meta: a.meta } : {}),
    ...(a.kind ? { kind: a.kind } : {}),
  };
}

/** The lease-row form: the name and the trailing cluster
 *  ride line 1 — the cluster is paid for first and never
 *  shrinks — and the sub takes line 2 at the full row
 *  width. RowText's form puts the cluster on the sub's own
 *  line; beside the session rows' Unattributed chip +
 *  Release button that starved the sub to ~117px and cut
 *  its since-time tail at phone width. */
function StackRow({
  label,
  sub,
  end,
}: {
  label: ReactNode;
  sub: ReactNode;
  end: ReactNode;
}) {
  return (
    <div className="rn-stack">
      <div className="rn-stack-top">
        <span className="rn-lab rn-name">{label}</span>
        <span className="rn-stack-end">{end}</span>
      </div>
      <div className="rn-sub">{sub}</div>
    </div>
  );
}

/** Frame 7 — Access: registered callers, the live session
 *  census with its attribution, and the day's access log.
 *  Rows derive from the store, so a grant, extension, or
 *  release re-renders this view. An unattributed session —
 *  no lease record, no claim — carries the one-tap release
 *  the backend serves; an attributed session's lifecycle
 *  belongs to its lease record, so it renders without one.
 *  The access log renders through the kit's one LogRow
 *  (scoped variant), the same component Events consumes. */
export function AccessView({ snap }: { snap: Snapshot }) {
  const [releaseFor, setReleaseFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const releasing = snap.access.find((a) => a.session === releaseFor) ?? null;

  const release = async () => {
    if (!releaseFor) return;
    setError(null);
    try {
      await adapter.releaseAccess(releaseFor);
      setReleaseFor(null);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };

  return (
    <>
      <h2 className="rn-largetitle">Access</h2>
      <p className="rn-subtitle">Registered callers and their live sessions</p>
      {error ? <ErrorNotice message={error} /> : null}
      <GroupLabel>Registered callers</GroupLabel>
      <GroupedList>
        {snap.callers.map((c) => (
          <Row key={c.caller}>
            <StackRow
              label={<span className="mono">{c.caller}</span>}
              sub={c.sub}
              end={<StatusChip tone={c.stateTone} label={c.stateLabel} />}
            />
          </Row>
        ))}
      </GroupedList>
      <GroupLabel>Session access</GroupLabel>
      <GroupedList>
        {snap.access.map((a) => (
          <Row key={a.session}>
            <StackRow
              label={<span className="mono">{a.session}</span>}
              sub={a.sub}
              end={
                <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                  {a.unattributed ? (
                    <>
                      <StatusChip tone="warn" label="Unattributed" />
                      <Button variant="danger" onClick={() => setReleaseFor(a.session)}>
                        Release
                      </Button>
                    </>
                  ) : (
                    <StatusChip tone="idle" label={a.caller ?? "attributed"} />
                  )}
                </span>
              }
            />
          </Row>
        ))}
      </GroupedList>
      <GroupLabel>Access log · today</GroupLabel>
      <GroupedList>
        {snap.accessLog.map((a) => (
          <LogRow key={a.id} entry={toEntry(a)} />
        ))}
      </GroupedList>
      {releasing ? (
        <Dialog
          title="Release session"
          body={
            <>
              Release the unattributed session <b>{releasing.displayName}</b> (
              <span className="mono">{releasing.session}</span>) now? No lease record and no
              caller claim it; its venue capacity is freed and its evidence record is
              retired.
            </>
          }
          confirmLabel="Release session"
          danger
          onConfirm={release}
          onCancel={() => setReleaseFor(null)}
        />
      ) : null}
    </>
  );
}
