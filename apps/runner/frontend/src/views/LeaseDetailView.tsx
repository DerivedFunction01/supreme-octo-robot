import { useState } from "react";
import type { Snapshot } from "../venue/types";
import { AdapterError } from "../venue/types";
import { adapter, DURATION_OPTIONS, fmtDurHours, fmtTime } from "../venue";
import {
  ActionRow,
  Dialog,
  DurationPicker,
  ErrorNotice,
  GroupLabel,
  GroupedList,
  Row,
  RowText,
  RowValue,
  StatusChip,
} from "../components/ui";
import { Input } from "@workhorse/kit/components/controls/Fields";

/** Frame 2 — Lease detail, with working Extend / Shorten /
 *  Release and a Run-a-job group that exercises the adapter's
 *  exec verb. Extend and Shorten are the panel's pair: both
 *  take the shared duration set (or a custom value), Shorten
 *  also takes an absolute end time, and the last input
 *  touched wins between the two. */
export function LeaseDetailView({
  snap,
  session,
  onBack,
}: {
  snap: Snapshot;
  session: string;
  onBack: () => void;
}) {
  const lease = snap.leases.find((l) => l.session === session);
  const [confirmRelease, setConfirmRelease] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState("gate · check");
  const [extendOpen, setExtendOpen] = useState(false);
  const [extendHours, setExtendHours] = useState(8);
  const [shortenOpen, setShortenOpen] = useState(false);
  const [shortenHours, setShortenHours] = useState(2);
  const [shortenDeadline, setShortenDeadline] = useState("");

  if (!lease) {
    return (
      <>
        <h2 className="rn-largetitle">Lease closed</h2>
        <p className="rn-subtitle">This lease is no longer live.</p>
        <GroupedList>
          <ActionRow label="Back to Leases" onClick={onBack} />
        </GroupedList>
      </>
    );
  }
  const runs = snap.runsBySession[session] ?? [];

  const extend = async () => {
    setError(null);
    try {
      const res = await adapter.extend(session, extendHours);
      setNote(res.note);
      setExtendOpen(false);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };
  const shorten = async () => {
    setError(null);
    try {
      const res = shortenDeadline
        ? await adapter.shorten(session, {
            deadline: new Date(shortenDeadline).toISOString(),
          })
        : await adapter.shorten(session, { hours: shortenHours });
      setNote(res.note);
      setShortenOpen(false);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };
  const release = async () => {
    setConfirmRelease(false);
    setError(null);
    try {
      await adapter.release(session);
      onBack();
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };
  const exec = async () => {
    setError(null);
    setNote(null);
    try {
      await adapter.exec(session, job.trim() || "gate · check", lease.caller ?? "unattributed");
      setNote(`Run started on ${lease.displayName} — watch it land in Runs and Events.`);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };

  return (
    <>
      <h2 className="rn-largetitle">{lease.displayName}</h2>
      <p className="rn-subtitle">
        {lease.venueLabel} venue · session {session.match(/(\d+)$/)?.[1] ?? session}
      </p>
      {error ? <ErrorNotice message={error} /> : null}
      {note ? (
        <div className="rn-notice" role="status" style={{ borderColor: "var(--ui-okabe-bluish-green)", background: "color-mix(in srgb, var(--ui-okabe-bluish-green) 12%, var(--ui-surface-2))" }}>
          <span>{note}</span>
        </div>
      ) : null}
      <GroupLabel>Lease</GroupLabel>
      <GroupedList>
        <Row>
          <span className="rn-lab">State</span>
          <span className="rn-ml-auto">
            <StatusChip tone={lease.stateTone} label={lease.stateLabel} />
          </span>
        </Row>
        <Row>
          <span className="rn-lab">Shape</span>
          <RowValue>{lease.shapeLabel}</RowValue>
        </Row>
        <Row>
          <span className="rn-lab">Venue</span>
          <RowValue>{lease.venueLabel}</RowValue>
        </Row>
        <Row>
          <span className="rn-lab">Caller</span>
          <RowValue>
            <span className="mono">{lease.caller ?? "unattributed"}</span>
          </RowValue>
        </Row>
        {lease.acquiredLabel ? (
          <Row>
            <span className="rn-lab">Acquired</span>
            <RowValue>{lease.acquiredLabel}</RowValue>
          </Row>
        ) : null}
        <Row>
          <span className="rn-lab">Deadline</span>
          <RowValue>{lease.remainingLabel}</RowValue>
        </Row>
        {lease.envelopeId ? (
          <Row>
            <span className="rn-lab">Envelope</span>
            <RowValue>
              <span className="mono">{lease.envelopeId}</span>
            </RowValue>
          </Row>
        ) : null}
      </GroupedList>
      {lease.diagnostics ? (
        <>
          <GroupLabel>Diagnostics</GroupLabel>
          <GroupedList>
            <Row>
              <span className="rn-lab">Heartbeat</span>
              <RowValue>{lease.diagnostics.heartbeatLabel}</RowValue>
            </Row>
            {lease.diagnostics.pulseLabel ? (
              <Row>
                <span className="rn-lab">Pulse</span>
                <RowValue>{lease.diagnostics.pulseLabel}</RowValue>
              </Row>
            ) : null}
            <Row>
              <span className="rn-lab">Burn</span>
              <RowValue>{lease.diagnostics.burnLabel}</RowValue>
            </Row>
            {lease.diagnostics.syncClaim ? (
              <Row>
                <span className="rn-lab">Sync claim</span>
                <RowValue>
                  <span className="mono">{lease.diagnostics.syncClaim.caller}</span> · until{" "}
                  {lease.diagnostics.syncClaim.untilLabel}
                </RowValue>
              </Row>
            ) : null}
            {lease.diagnostics.listeners.map((l) => (
              <Row key={l.port}>
                <span className="rn-lab">Port {l.port}</span>
                <span
                  className="rn-ml-auto"
                  style={{ display: "inline-flex", gap: 8, alignItems: "center" }}
                >
                  <RowValue>
                    pid {l.pid} · <span className="mono">{l.cwd ?? "—"}</span>
                  </RowValue>
                  {l.suspect.length > 0 ? (
                    <StatusChip tone="warn" label={`suspect: ${l.suspect.join(", ")}`} />
                  ) : null}
                </span>
              </Row>
            ))}
          </GroupedList>
        </>
      ) : null}
      <GroupLabel>Runs on this lease</GroupLabel>
      <GroupedList>
        {runs.length === 0 ? (
          <Row>
            <RowText label="No runs yet" sub="Runs launched on this lease land here." />
          </Row>
        ) : (
          runs.map((r) => (
            <Row key={r.runId}>
              <RowText
                label={r.job}
                mono
                sub={
                  <>
                    Started {fmtTime(r.startedAt)} · {r.durationLabel}
                  </>
                }
                end={<StatusChip tone={r.stateTone} label={r.stateLabel} />}
              />
            </Row>
          ))
        )}
      </GroupedList>
      <GroupLabel>Run a job</GroupLabel>
      <GroupedList>
        <Row>
          <span className="rn-lab">Job</span>
          <span className="rn-ml-auto" style={{ width: 260 }}>
            <Input
              ariaLabel="Job label"
              value={job}
              onChange={(e) => setJob(e.target.value)}
            />
          </span>
        </Row>
        <ActionRow label={`Run job on this lease · ${lease.venueLabel}`} onClick={exec} />
      </GroupedList>
      <GroupLabel>Actions</GroupLabel>
      {/* Capability disabling (Step 4): the served
          capability set alone decides enablement — a
          not-applicable verb's rows render disabled
          with the served reason on the control, never
          removed; layout does not change with it. */}
      <GroupedList>
        <ActionRow
          label={extendOpen ? "Close extend" : "Extend lease"}
          disabled={!lease.capabilities.extend.applicable}
          disabledReason={lease.capabilities.extend.reason}
          onClick={() => setExtendOpen((v) => !v)}
        />
        {extendOpen ? (
          <>
            <Row>
              <span className="rn-lab rn-lab-keep">Extend by</span>
              <span className="rn-ml-auto">
                <DurationPicker
                  ariaLabel="Extend duration"
                  options={DURATION_OPTIONS}
                  value={extendHours}
                  onChange={setExtendHours}
                />
              </span>
            </Row>
            <ActionRow
              label={`Extend by ${fmtDurHours(extendHours)}`}
              disabled={!lease.capabilities.extend.applicable}
              disabledReason={lease.capabilities.extend.reason}
              onClick={extend}
            />
          </>
        ) : null}
        <ActionRow
          label={shortenOpen ? "Close shorten" : "Shorten lease"}
          disabled={!lease.capabilities.shorten.applicable}
          disabledReason={lease.capabilities.shorten.reason}
          onClick={() => setShortenOpen((v) => !v)}
        />
        {shortenOpen ? (
          <>
            <Row>
              <span className="rn-lab rn-lab-keep">Shorten by</span>
              <span className="rn-ml-auto">
                <DurationPicker
                  ariaLabel="Shorten duration"
                  options={DURATION_OPTIONS}
                  value={shortenHours}
                  onChange={(h) => {
                    setShortenHours(h);
                    setShortenDeadline("");
                  }}
                />
              </span>
            </Row>
            <Row>
              <span className="rn-lab">Or end at</span>
              <span className="rn-ml-auto" style={{ width: 240 }}>
                <Input
                  type="datetime-local"
                  ariaLabel="Shorten to deadline"
                  value={shortenDeadline}
                  onChange={(e) => setShortenDeadline(e.target.value)}
                />
              </span>
            </Row>
            <ActionRow
              label={
                shortenDeadline
                  ? "Shorten to the chosen time"
                  : `Shorten by ${fmtDurHours(shortenHours)}`
              }
              disabled={!lease.capabilities.shorten.applicable}
              disabledReason={lease.capabilities.shorten.reason}
              onClick={shorten}
            />
          </>
        ) : null}
        <ActionRow
          label="Release lease"
          danger
          disabled={!lease.capabilities.release.applicable}
          disabledReason={lease.capabilities.release.reason}
          onClick={() => setConfirmRelease(true)}
        />
      </GroupedList>
      {confirmRelease ? (
        <Dialog
          title="Release lease"
          body={
            <>
              Release <b>{lease.displayName}</b> ({lease.venueLabel} venue,{" "}
              <span className="mono">{lease.caller ?? "unattributed"}</span>)? The session
              closes, its running segment is journaled as spend, and any run still going is
              orphaned.
            </>
          }
          confirmLabel="Release lease"
          danger
          onConfirm={release}
          onCancel={() => setConfirmRelease(false)}
        />
      ) : null}
    </>
  );
}
