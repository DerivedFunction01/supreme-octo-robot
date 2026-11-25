import { useState } from "react";
import type { Snapshot } from "../venue/types";
import { AdapterError } from "../venue/types";
import { adapter, DURATION_OPTIONS, fmtDurHours } from "../venue";
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

/** The two-tier grant card — the panel's grant surface: the
 *  grant's until and burst spec, the snapshot caps it was
 *  granted under with spend against them, the leases its
 *  envelope attributes, and its two lifecycle acts (extend,
 *  revoke). Renders only what the served grant projection
 *  carries; a grant with no standing spend served shows the
 *  standing cap alone, as the panel does. Mounted wherever
 *  the grant is in play (Leases, the New lease grant form). */
export function GrantCard({ snap }: { snap: Snapshot }) {
  const grant = snap.grant;
  const [extendOpen, setExtendOpen] = useState(false);
  const [extendHours, setExtendHours] = useState(8);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!grant) return null;

  const extend = async () => {
    setError(null);
    try {
      const res = await adapter.extendGrant(extendHours);
      setNote(res.note);
      setExtendOpen(false);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };
  const revoke = async () => {
    setConfirmRevoke(false);
    setError(null);
    try {
      await adapter.ungrant();
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    }
  };

  const cap = (v: number | null) => (v != null ? `${v}` : "—");

  return (
    <>
      <GroupLabel>Two-tier grant</GroupLabel>
      {error ? <ErrorNotice message={error} /> : null}
      {note ? (
        <div
          className="rn-notice"
          role="status"
          style={{
            borderColor: "var(--ui-okabe-bluish-green)",
            background:
              "color-mix(in srgb, var(--ui-okabe-bluish-green) 12%, var(--ui-surface-2))",
          }}
        >
          <span>{note}</span>
        </div>
      ) : null}
      <GroupedList>
        <Row>
          <span className="rn-lab">Until</span>
          <RowValue>{grant.untilLabel}</RowValue>
          <span className="rn-ml-auto">
            <StatusChip tone="ok" label="Active" />
          </span>
        </Row>
        <Row>
          <span className="rn-lab">Burst spec</span>
          <RowValue>{grant.burstLabel}</RowValue>
        </Row>
        <Row>
          <span className="rn-lab">Standing</span>
          <RowValue>
            {grant.standingDaySpentCu != null
              ? `Standing spend today ${grant.standingDaySpentCu} of ${cap(grant.caps.standingDaily)} CU`
              : `Standing cap ${cap(grant.caps.standingDaily)} CU/day`}
          </RowValue>
        </Row>
        <Row>
          {/* Stack form: beside the two-line label the
              single-line value ellipsized at phone width
              ("daily 250 · monthly 10…"), losing the
              monthly figure. The value takes line 2 at
              full width, as the lease details line does. */}
          <div className="rn-stack">
            <div className="rn-stack-top">
              <span className="rn-lab rn-name">Envelope caps (at grant)</span>
            </div>
            <div className="rn-sub">
              daily {cap(grant.caps.daily)} · monthly {cap(grant.caps.monthly)} CU
            </div>
          </div>
        </Row>
        <Row>
          <span className="rn-lab">Envelope spend</span>
          <RowValue>
            today {grant.spendDayCu} · this month {grant.spendMonthCu} CU
          </RowValue>
        </Row>
      </GroupedList>
      <GroupLabel>Envelope leases</GroupLabel>
      <GroupedList>
        {grant.leases.length === 0 ? (
          <Row>
            <RowText label="No envelope leases yet" sub="In-scope acquires under this grant land here." />
          </Row>
        ) : (
          grant.leases.map((l) => (
            <Row key={l.session}>
              <RowText
                label={l.displayName}
                sub={
                  <>
                    {l.shapeLabel} · <span className="mono">{l.caller ?? "unattributed"}</span>{" "}
                    · until {l.deadlineLabel}
                  </>
                }
              />
            </Row>
          ))
        )}
      </GroupedList>
      <GroupLabel>Grant actions</GroupLabel>
      <GroupedList>
        <ActionRow
          label={extendOpen ? "Close extend" : "Extend grant"}
          onClick={() => setExtendOpen((v) => !v)}
        />
        {extendOpen ? (
          <>
            <Row>
              <span className="rn-lab rn-lab-keep">Extend by</span>
              <span className="rn-ml-auto">
                <DurationPicker
                  ariaLabel="Extend grant duration"
                  options={DURATION_OPTIONS}
                  value={extendHours}
                  onChange={setExtendHours}
                />
              </span>
            </Row>
            <ActionRow
              label={`Extend grant by ${fmtDurHours(extendHours)}`}
              onClick={extend}
            />
          </>
        ) : null}
        <ActionRow label="Revoke grant" danger onClick={() => setConfirmRevoke(true)} />
      </GroupedList>
      {confirmRevoke ? (
        <Dialog
          title="Revoke grant"
          body={
            <>
              Revoke the two-tier grant now? Its envelope stops pricing new acquires; leases
              already attributed keep their envelope stamps.
            </>
          }
          confirmLabel="Revoke grant"
          danger
          onConfirm={revoke}
          onCancel={() => setConfirmRevoke(false)}
        />
      ) : null}
    </>
  );
}
