import { useState } from "react";
import type { OrphanView, Snapshot } from "../venue/types";
import { AdapterError } from "../venue/types";
import { adapter } from "../venue";
import {
  Dialog,
  ErrorNotice,
  GroupLabel,
  GroupedList,
  NoticeRow,
  PickerChips,
  Row,
  RowText,
  StatusChip,
} from "../components/ui";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Select } from "@workhorse/kit/components/controls/Fields";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";

/** Frame 4 — Orphans: sessions with evidence but no live lease
 *  record. Adopt (under a registered caller) and Release work.
 *  E4 forms (ruled 2026-11-14): a past-deadline orphan's
 *  headline carries the served deadline time plus a
 *  past-deadline chip, and the Jobs control opens the orphan's
 *  in-flight jobs in the kit Sheet drawer.
 *  V6: the card carries the census's evidence lines — first
 *  seen / acquired / renewal kit, the evidenced shape or its
 *  class, the creator caller and first claim, the derived
 *  deadline with its source and stale flag, and the
 *  derivation's conflicts. A class-ambiguous orphan's adopt
 *  dialog carries the candidate picker (the pick posts as
 *  the adopt's shape); a handover-pending orphan's Adopt is
 *  disabled — its parent record takes it over by swap.
 *  A nameless row (an assignment that lost its name
 *  server-side; the census keys it by endpoint) renders
 *  its endpoint and prior name as evidence, and adopts
 *  and releases through the endpoint forms — adoption
 *  mints a fresh name, release unassigns by endpoint. */
/** A row's identity: its session name, or — on a
 *  nameless row, whose name is lost server-side — its
 *  endpoint, the key the census itself serves it under. */
const keyOf = (o: OrphanView): string => o.session ?? o.endpoint ?? "";

export function OrphansView({ snap }: { snap: Snapshot }) {
  const [adoptFor, setAdoptFor] = useState<string | null>(null);
  const [releaseFor, setReleaseFor] = useState<string | null>(null);
  const [jobsFor, setJobsFor] = useState<string | null>(null);
  const jobsOrphan = snap.orphans.find((o) => keyOf(o) === jobsFor) ?? null;
  const adoptOrphan = snap.orphans.find((o) => keyOf(o) === adoptFor) ?? null;
  const [caller, setCaller] = useState(adapter.registeredCallers()[0] ?? "");
  const [shapePick, setShapePick] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const openAdopt = (key: string) => {
    const orphan = snap.orphans.find((o) => keyOf(o) === key);
    setShapePick(
      orphan && !orphan.shapeEvidenced && orphan.shapeCandidates.length === 1
        ? orphan.shapeCandidates[0].id
        : null,
    );
    setAdoptFor(key);
  };

  const adopt = async () => {
    if (!adoptFor || !adoptOrphan) return;
    setError(null);
    try {
      const shape =
        !adoptOrphan.shapeEvidenced ? (shapePick ?? undefined) : undefined;
      if (adoptOrphan.nameless && adoptOrphan.endpoint) {
        // The endpoint form: a fresh name is minted and
        // bound, and the record restores under it.
        await adapter.adoptNamelessOrphan(adoptOrphan.endpoint, caller, shape);
      } else if (adoptOrphan.session) {
        await adapter.adoptOrphan(adoptOrphan.session, caller, shape);
      }
      setAdoptFor(null);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };
  const release = async () => {
    if (!releaseFor) return;
    const row = snap.orphans.find((o) => keyOf(o) === releaseFor);
    setError(null);
    try {
      if (row?.nameless && row.endpoint) {
        // The endpoint form: the endpoint is the
        // unassign key.
        await adapter.releaseNamelessOrphan(row.endpoint);
      } else if (row?.session) {
        await adapter.releaseOrphan(row.session);
      }
      setReleaseFor(null);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };

  return (
    <>
      <h2 className="rn-largetitle">Orphans</h2>
      <p className="rn-subtitle">Sessions with no live lease record</p>
      {error ? <ErrorNotice message={error} /> : null}
      {snap.orphans.length > 0 ? (
        <NoticeRow>
          <b>
            {snap.orphans.length} orphan session{snap.orphans.length > 1 ? "s" : ""}.
          </b>{" "}
          It holds venue capacity but no caller owns it; adopt it under a lease or release
          it.
        </NoticeRow>
      ) : null}
      {snap.orphans.length === 0 ? (
        <EmptyState
          message="No orphan sessions"
          detail="Every live session carries a lease record and a caller."
        />
      ) : (
        <GroupedList>
          {snap.orphans.map((o) => (
            <Row key={keyOf(o)}>
              <div className="rn-stack">
                <div className="rn-stack-top rn-orphan-top">
                  <span className="rn-lab rn-name">{o.displayName}</span>
                  {o.deadlinePast ? (
                    <span className="rn-orphan-past">
                      <span className="rn-orphan-past-time">{o.deadlineLabel}</span>
                      <StatusChip tone={o.deadlineTone} label="past deadline" />
                    </span>
                  ) : null}
                  <span className="rn-orphan-actions">
                    {o.jobs.length > 0 ? (
                      <Button variant="secondary" onClick={() => setJobsFor(keyOf(o))}>
                        Jobs
                      </Button>
                    ) : null}
                    <Button
                      variant="secondary"
                      disabled={o.handoverPending}
                      onClick={() => openAdopt(keyOf(o))}
                    >
                      Adopt
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => setReleaseFor(keyOf(o))}
                    >
                      Release
                    </Button>
                  </span>
                </div>
                <div className="rn-sub">{o.sub}</div>
                {o.nameless ? (
                  <div className="rn-sub">
                    Name <b>lost</b> · endpoint <b>{o.endpoint}</b>
                    {o.priorSession ? (
                      <>
                        {" "}
                        · previously <b>{o.priorSession}</b>
                      </>
                    ) : null}{" "}
                    · adopt and release both ride the endpoint — adoption mints a
                    fresh name, release unassigns it
                  </div>
                ) : null}
                <div className="rn-sub">
                  First seen <b>{o.firstSeenLabel}</b>
                  {o.acquiredLabel ? (
                    <>
                      {" "}
                      · Acquired <b>{o.acquiredLabel}</b>
                    </>
                  ) : null}
                  {o.kitInstalled ? (
                    <>
                      {" "}
                      · Renewal kit <b>installed</b>
                    </>
                  ) : null}
                </div>
                {o.shapeEvidenced ? (
                  <div className="rn-sub">
                    Shape <b>{o.shapeLabel}</b> · evidenced
                  </div>
                ) : (
                  <div className="rn-sub">
                    Shape class <b>{o.shapeClassLabel ?? "unknown"}</b> — not evidenced
                    {o.shapeCandidates.length > 0
                      ? "; pick the shape to adopt"
                      : "; no catalog candidates for this class"}
                  </div>
                )}
                <div className="rn-sub">
                  Creator caller <b>{o.creatorCaller ?? "—"}</b>
                  {o.firstClaim && o.firstClaim !== o.creatorCaller ? (
                    <>
                      {" "}
                      · first claim <b>{o.firstClaim}</b>
                    </>
                  ) : null}
                </div>
                {o.deadline ? (
                  <div className="rn-sub">
                    Derived deadline <b>{o.deadlineLabel}</b> · from{" "}
                    <b>{o.deadlineSource ?? "—"}</b>
                    {o.deadlineStalePossible ? (
                      <>
                        {" "}
                        <StatusChip tone="warn" label="possibly stale" />
                      </>
                    ) : null}
                  </div>
                ) : (
                  <div className="rn-sub">
                    Derived deadline <b>none</b> — no source carries one for this session
                  </div>
                )}
                {o.conflicts.map((c) => (
                  <div className="rn-sub" key={c.field}>
                    Conflict — {c.field}: {c.text}
                  </div>
                ))}
                {o.handoverPending ? (
                  <div className="rn-sub">
                    <StatusChip tone="warn" label="Handover pending" /> its parent record
                    takes it over by swap — adoption is refused.
                  </div>
                ) : null}
              </div>
            </Row>
          ))}
        </GroupedList>
      )}
      <GroupLabel>Resolved this week</GroupLabel>
      <GroupedList>
        {snap.resolvedOrphans.map((r) => (
          <Row key={r.session}>
            <RowText
              label={r.displayName}
              sub={r.sub}
              end={<StatusChip tone={r.tone} label={r.label} />}
            />
          </Row>
        ))}
      </GroupedList>
      {adoptFor ? (
        <Dialog
          title="Adopt orphan session"
          body={
            <>
              <p style={{ marginTop: 0 }}>
                Adopt <b>{adoptOrphan?.displayName}</b> under a lease for a registered
                caller. The lease record is written from the session's evidence; the
                deadline stands as evidenced.
              </p>
              {adoptOrphan?.deadline ? (
                <p>
                  Derived deadline <b>{adoptOrphan.deadlineLabel}</b> · from{" "}
                  <b>{adoptOrphan.deadlineSource ?? "—"}</b>
                </p>
              ) : null}
              <Select
                ariaLabel="Adopting caller"
                value={caller}
                onChange={(e) => setCaller(e.target.value)}
                options={adapter.registeredCallers().map((c) => ({ value: c, label: c }))}
              />
              {adoptOrphan && !adoptOrphan.shapeEvidenced ? (
                adoptOrphan.shapeCandidates.length > 0 ? (
                  <>
                    <p style={{ marginBottom: 8 }}>
                      Shape class <b>{adoptOrphan.shapeClassLabel ?? "unknown"}</b> — not
                      evidenced; pick the shape to adopt:
                    </p>
                    <PickerChips
                      ariaLabel="Adopting shape"
                      value={shapePick ?? ""}
                      onChange={(v) => setShapePick(v)}
                      options={adoptOrphan.shapeCandidates.map((c) => ({
                        value: c.id,
                        label: `${c.label} · ${c.rateLabel}`,
                      }))}
                    />
                  </>
                ) : (
                  <p>
                    Shape class <b>{adoptOrphan.shapeClassLabel ?? "unknown"}</b> — no
                    catalog candidates for this class; adoption needs the CLI.
                  </p>
                )
              ) : null}
            </>
          }
          confirmLabel="Adopt session"
          onConfirm={adopt}
          onCancel={() => setAdoptFor(null)}
        />
      ) : null}
      {releaseFor ? (
        <Dialog
          title="Release orphan session"
          body={
            <>
              Release{" "}
              <b>{snap.orphans.find((o) => keyOf(o) === releaseFor)?.displayName}</b>? The
              session's venue capacity is freed and its evidence record is retired. No
              caller owns it, so no spend is journaled.
            </>
          }
          confirmLabel="Release session"
          danger
          onConfirm={release}
          onCancel={() => setReleaseFor(null)}
        />
      ) : null}
      <Sheet
        open={jobsOrphan !== null}
        title={jobsOrphan ? `Jobs · ${jobsOrphan.displayName}` : "Jobs"}
        onClose={() => setJobsFor(null)}
        footer={
          <Button variant="secondary" onClick={() => setJobsFor(null)}>
            Close
          </Button>
        }
      >
        {jobsOrphan ? (
          <div className="rn-drawer-scroll">
            <GroupedList>
              {jobsOrphan.jobs.map((j) => (
                <Row key={j.id}>
                  <RowText
                    label={j.label}
                    sub={j.sub}
                    end={<StatusChip tone={j.tone} label={j.stateLabel} />}
                  />
                </Row>
              ))}
            </GroupedList>
          </div>
        ) : null}
      </Sheet>
    </>
  );
}
