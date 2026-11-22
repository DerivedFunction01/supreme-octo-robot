// New lease — the panel's start controls (controls.js):
// the Normal lease / Two-tier grant mode switch, the spec
// pickers over the served catalog (no client-side fallback
// catalog: the core serves the shapes or the section shows
// its load state), the duration presets, the projected
// cost, and the two start verbs. When a grant is active
// the grant form gives way to the panel's grant-active
// note — revocation lives on the grant card (Leases view).

import { useEffect, useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Card } from "@workhorse/kit/components/display/Card";
import { GroupedList, RadioRow } from "@workhorse/kit/components/display/GroupedList";
import { SegmentedControl } from "@workhorse/kit/components/controls/SegmentedControl";
import { api } from "../../lib/actions";
import { fmtNum, fmtTime, specById, type Spec } from "./model";
import {
  CustomHoursInput,
  DegradedCard,
  DurationChips,
  PartStatus,
  specSub,
} from "./pickers";
import { callApi, useRunner } from "./state";

function SpecPicker({
  specs,
  value,
  onPick,
  ariaLabel,
}: {
  specs: Spec[];
  value: string | null;
  onPick: (id: string) => void;
  ariaLabel: string;
}) {
  if (!specs.length) {
    return (
      <p className="text-sm" style={{ color: "var(--wb-content-muted)" }}>
        Loading specs…
      </p>
    );
  }
  return (
    <div role="radiogroup" aria-label={ariaLabel}>
      <GroupedList>
        {specs.map((s) => (
          <RadioRow
            key={s.id}
            label={s.label || s.id}
            sub={specSub(s)}
            selected={s.id === value}
            onSelect={() => onPick(s.id)}
          />
        ))}
      </GroupedList>
    </div>
  );
}

export function NewLeaseView({ navigate }: { navigate: (hash: string) => void }) {
  const { parts, act, allDown } = useRunner();
  const [mode, setMode] = useState<"normal" | "grant">("normal");
  const [shape, setShape] = useState<string | null>(null);
  const [burst, setBurst] = useState<string | null>(null);
  const [normalHours, setNormalHours] = useState(8);
  const [grantHours, setGrantHours] = useState(8);
  const [starting, setStarting] = useState(false);

  const specs = parts.specs.data?.specs || [];
  // The panel's default: the first served spec, until the
  // operator picks another.
  useEffect(() => {
    if (specs.length) {
      if (!shape || !specs.some((s) => s.id === shape)) setShape(specs[0]!.id);
      if (!burst || !specs.some((s) => s.id === burst)) setBurst(specs[0]!.id);
    }
  }, [specs, shape, burst]);

  if (allDown) return <DegradedCard />;

  const budget = parts.budget.data?.budget;
  const grant = parts.grant.data?.grant;
  const grantActive = Boolean(grant && typeof grant === "object" && grant.until);
  const chosen = specById(specs, shape);
  const rate = chosen ? chosen.rate_cu_per_hour : null;

  const startLease = () => {
    if (!shape || starting) return;
    setStarting(true);
    let ok = false;
    void act(async () => {
      await callApi(() => api.startLease({ body: { shape, hours: normalHours } }));
      ok = true;
    }).then(() => {
      setStarting(false);
      if (ok) navigate("#/runner");
    });
  };

  const startGrant = () => {
    if (!burst || starting) return;
    setStarting(true);
    let ok = false;
    void act(async () => {
      await callApi(() => api.grant({ body: { hours: grantHours, burst } }));
      ok = true;
    }).then(() => {
      setStarting(false);
      if (ok) navigate("#/runner");
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <PartStatus name="specs" part={parts.specs} />
      <Card>
        {budget && budget.balance != null ? (
          <p className="mb-3 text-sm" style={{ color: "var(--wb-content-secondary)" }}>
            Balance{" "}
            <b style={{ color: "var(--wb-content-primary)" }}>
              {fmtNum(budget.balance)} CU
            </b>
          </p>
        ) : null}
        <SegmentedControl
          ariaLabel="Lease mode"
          options={[
            { value: "normal", label: "Normal lease" },
            { value: "grant", label: "Two-tier grant" },
          ]}
          value={mode}
          onChange={(v) => setMode(v)}
        />
        {mode === "normal" ? (
          <div className="mt-4 flex flex-col gap-3">
            <SpecPicker
              specs={specs}
              value={shape}
              onPick={setShape}
              ariaLabel="Lease shape"
            />
            <div className="flex flex-wrap items-center gap-2">
              <DurationChips hours={normalHours} onPick={setNormalHours} />
              <CustomHoursInput ariaLabel="Custom lease hours" onHours={setNormalHours} />
            </div>
            <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
              Projected cost{" "}
              <strong style={{ color: "var(--wb-content-primary)" }}>
                {rate == null ? "Cost unconfirmed" : `${fmtNum(rate * normalHours)} CU`}
              </strong>
            </p>
            <Button disabled={starting || !shape} onClick={startLease}>
              {starting ? "Starting…" : "Start lease"}
            </Button>
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-3">
            {grantActive ? (
              <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
                Grant active until{" "}
                <strong style={{ color: "var(--wb-content-primary)" }}>
                  {fmtTime(grant?.until)}
                </strong>
                . The lobby is held by the standing duty.
              </p>
            ) : (
              <>
                <SpecPicker
                  specs={specs}
                  value={burst}
                  onPick={setBurst}
                  ariaLabel="Burst shape"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <DurationChips hours={grantHours} onPick={setGrantHours} />
                  <CustomHoursInput ariaLabel="Custom grant hours" onHours={setGrantHours} />
                </div>
                <Button disabled={starting || !burst} onClick={startGrant}>
                  {starting ? "Starting…" : "Start grant"}
                </Button>
              </>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
