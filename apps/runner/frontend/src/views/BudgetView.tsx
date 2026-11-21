import { useEffect, useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Input } from "@workhorse/kit/components/controls/Fields";
import type { BudgetCaps, Snapshot } from "../venue/types";
import { adapter } from "../venue";
import {
  ErrorNotice,
  GroupLabel,
  GroupedList,
  PickerChips,
  Row,
  RowValue,
  StatusChip,
} from "../components/ui";

/** Frame 6 — Budget: every figure is folded by the adapter from
 *  the store's lease segments and live reservations. The caps
 *  editor (venue rework) writes through the adapter seam to the
 *  core's budget-caps path: each adapter carries its own
 *  budgets, and each account of an adapter is edited on its
 *  own — a cap is a non-negative number of compute units, or
 *  empty for no cap. */

const CAP_FIELDS = [
  { key: "daily", label: "Daily cap", hint: "CU per day" },
  { key: "monthly", label: "Monthly cap", hint: "CU per month" },
  { key: "standingDaily", label: "Standing daily cap", hint: "CU per day, standing caller" },
] as const;

type CapKey = (typeof CAP_FIELDS)[number]["key"];

function fmtCap(v: number | null): string {
  return v == null ? "No cap" : `${v} CU`;
}

function credentialChip(a: Snapshot["budget"]["accounts"][number]) {
  switch (a.credential) {
    case "live":
      return <StatusChip tone="ok" label="Live" />;
    case "credential-present":
      return <StatusChip tone="info" label="Credential present" />;
    default:
      return <StatusChip tone="idle" label="Not brought in" />;
  }
}

export function BudgetView({ snap }: { snap: Snapshot }) {
  const b = snap.budget;
  const [selected, setSelected] = useState<string>(b.accounts[0]?.account ?? "primary");
  const account = b.accounts.find((a) => a.account === selected) ?? b.accounts[0];
  const [fields, setFields] = useState<Record<CapKey, string>>({ daily: "", monthly: "", standingDaily: "" });
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // The form follows the selected account's served caps —
  // switching accounts (or a write landing) re-reads them.
  useEffect(() => {
    if (!account) return;
    setFields({
      daily: account.caps.daily == null ? "" : String(account.caps.daily),
      monthly: account.caps.monthly == null ? "" : String(account.caps.monthly),
      standingDaily: account.caps.standingDaily == null ? "" : String(account.caps.standingDaily),
    });
    setError(null);
    setNote(null);
  }, [account?.account, account?.caps.daily, account?.caps.monthly, account?.caps.standingDaily]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    if (!account) return;
    const caps = {} as BudgetCaps;
    for (const { key, label } of CAP_FIELDS) {
      const raw = fields[key].trim();
      if (raw === "") {
        caps[key] = null;
        continue;
      }
      const v = Number(raw);
      if (!Number.isFinite(v) || v < 0) {
        setError(`${label} must be a non-negative number, or empty for no cap.`);
        return;
      }
      caps[key] = v;
    }
    setSaving(true);
    setError(null);
    try {
      await adapter.setBudgetCaps({ venue: account.venue, account: account.account, caps });
      setNote(`Caps updated for ${account.label} (${account.account}).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <h2 className="rn-largetitle">Budget</h2>
      <p className="rn-subtitle">Compute units · this cycle</p>
      <GroupLabel>Balance</GroupLabel>
      <GroupedList>
        <Row>
          <span className="rn-lab">Balance</span>
          <RowValue>{b.balanceCu} CU</RowValue>
        </Row>
        <Row>
          <span className="rn-lab">Used today</span>
          <RowValue>{b.usedTodayCu} CU</RowValue>
        </Row>
        <Row>
          <span className="rn-lab">Reserved by live leases</span>
          <RowValue>{b.reservedCu} CU</RowValue>
        </Row>
        <Row>
          <span className="rn-lab">Projected runway</span>
          <RowValue>{b.runwayLabel}</RowValue>
        </Row>
      </GroupedList>
      <GroupLabel>Use by caller · today</GroupLabel>
      <GroupedList>
        {b.byCaller.map((c) => (
          <Row key={c.caller}>
            <span className="rn-lab mono">{c.caller}</span>
            <RowValue>{c.cu} CU</RowValue>
          </Row>
        ))}
      </GroupedList>
      <GroupLabel>Accounts · Colab</GroupLabel>
      <GroupedList>
        {b.accounts.map((a) => (
          <Row key={`${a.venue}:${a.account}`}>
            {/* Two-line stack form (the lease-row form): the
                account name + credential chip ride line 1 and
                the balance takes line 2 at full width. On one
                line the three competed — the name wrapped
                mid-word, the chip label ellipsized ("Not
                brought…") and the balance ellipsized ("Not
                dial…") at phone width. */}
            <div className="rn-stack">
              <div className="rn-stack-top">
                <span className="rn-lab rn-name">
                  {a.label} <span className="mono">({a.account})</span>
                </span>
                <span className="rn-stack-end">{credentialChip(a)}</span>
              </div>
              <div className="rn-sub">
                {a.balanceCu == null ? "Not dialed" : `Balance ${a.balanceCu} CU`}
              </div>
            </div>
          </Row>
        ))}
      </GroupedList>
      <GroupLabel>Budget caps</GroupLabel>
      <div style={{ marginBottom: 10 }}>
        <PickerChips
          ariaLabel="Account to edit"
          options={b.accounts.map((a) => ({ value: a.account, label: a.label }))}
          value={account?.account ?? ""}
          onChange={setSelected}
        />
      </div>
      {account ? (
        <>
          <GroupedList>
            {CAP_FIELDS.map(({ key, label }) => (
              <Row key={key}>
                <span className="rn-lab">{label}</span>
                <RowValue>{fmtCap(account.caps[key])}</RowValue>
              </Row>
            ))}
          </GroupedList>
          <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
            {CAP_FIELDS.map(({ key, label, hint }) => (
              <label key={key} className="rn-capfield">
                <span className="rn-lab rn-capfield-lab">
                  {label} <span className="rn-capfield-hint">· {hint}</span>
                </span>
                <span className="rn-capfield-in">
                  <Input
                    type="number"
                    min="0"
                    step="1"
                    ariaLabel={`${label} for ${account.label}`}
                    placeholder="No cap"
                    value={fields[key]}
                    onChange={(e) => setFields((f) => ({ ...f, [key]: e.target.value }))}
                  />
                </span>
              </label>
            ))}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {/* The button is paid for first: when the saved
                  note appears beside it, the note wraps in the
                  remaining width instead of squeezing the
                  button's label into an ellipsis. */}
              <span style={{ flex: "0 0 auto" }}>
                <Button variant="primary" onClick={save} disabled={saving}>
                  {saving ? "Saving…" : "Save caps"}
                </Button>
              </span>
              {note ? (
                <span style={{ color: "var(--wb-content-secondary)", minWidth: 0 }}>{note}</span>
              ) : null}
            </div>
            {error ? <ErrorNotice message={error} /> : null}
          </div>
        </>
      ) : null}
    </>
  );
}
