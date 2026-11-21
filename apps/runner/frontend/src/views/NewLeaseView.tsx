import { useState } from "react";
import type { Snapshot, SpecView } from "../venue/types";
import { AdapterError } from "../venue/types";
import { adapter, DURATION_OPTIONS, fmtDurHours } from "../venue";
import {
  ActionRow,
  DurationPicker,
  ErrorNotice,
  GroupLabel,
  GroupedList,
  Row,
  RowValue,
} from "../components/ui";
import { SegmentedControl } from "@workhorse/kit/components/controls/SegmentedControl";
import { Select, Input } from "@workhorse/kit/components/controls/Fields";
import { Check } from "lucide-react";
import { GrantCard } from "./GrantCard";

type GrantKind = "normal" | "two-tier";
const CUSTOM = "__custom__";

/** One served-spec row: the core's label, its descriptor,
 *  and its rate — "Cost unconfirmed" when the core serves
 *  no rate. The catalog is the served specs portion; there
 *  is no client-side fallback list. */
function SpecRow({
  spec,
  selected,
  onSelect,
}: {
  spec: SpecView;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <Row onClick={onSelect}>
      <span className="rn-lab">{spec.label}</span>
      <RowValue>
        {spec.descriptor} · {spec.rateLabel}
      </RowValue>
      {selected ? (
        <Check size={17} aria-hidden style={{ color: "var(--wb-accent)", flex: "0 0 auto" }} />
      ) : null}
    </Row>
  );
}

/** Frame 3 — New lease. Every control works against the
 *  served contracts: the shape catalog is the core's specs
 *  portion (every shape it offers is startable here), the
 *  duration is the shared picker set or a custom value,
 *  the caller is registry-validated, and the acquire is
 *  priced from the served rate — an unconfirmed rate
 *  projects nothing. Two-tier mode is the grant's own
 *  surface: the start form (burst spec + grant hours)
 *  while no grant is active, the grant card while one is. */
export function NewLeaseView({
  snap,
  onAcquired,
}: {
  snap: Snapshot;
  onAcquired: (session: string) => void;
}) {
  const [kind, setKind] = useState<GrantKind>("normal");
  const [shape, setShape] = useState(() => snap.specs[0]?.id ?? "");
  const [burst, setBurst] = useState(() => snap.specs[0]?.id ?? "");
  const [callerSel, setCallerSel] = useState(adapter.registeredCallers()[0] ?? "");
  const [customCaller, setCustomCaller] = useState("");
  const [hours, setHours] = useState(2);
  const [grantHours, setGrantHours] = useState(8);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const spec = snap.specs.find((s) => s.id === shape) ?? snap.specs[0];
  const cost = spec && spec.rateCuPerHour != null ? spec.rateCuPerHour * hours : null;
  const caller = callerSel === CUSTOM ? customCaller.trim() : callerSel;
  const inScope = snap.grant != null && spec != null && snap.grant.shapes.includes(spec.id);

  const acquire = async () => {
    setError(null);
    if (!caller) {
      setError("Name a caller — a lease is granted to a registered caller.");
      return;
    }
    if (!spec) {
      setError("The venue serves no shapes to start.");
      return;
    }
    setBusy(true);
    try {
      const lease = await adapter.acquire({ shape: spec.id, caller, hours });
      onAcquired(lease.session);
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const startGrant = async () => {
    setError(null);
    if (!burst) {
      setError("The venue serves no burst spec to grant.");
      return;
    }
    setBusy(true);
    try {
      await adapter.startGrant({ hours: grantHours, burst });
    } catch (e) {
      setError(e instanceof AdapterError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2 className="rn-largetitle">New lease</h2>
      <p className="rn-subtitle">
        Balance {snap.budget.balanceCu} CU · a lease is granted to a registered caller
      </p>
      {error ? <ErrorNotice message={error} /> : null}
      <div style={{ marginBottom: 18 }}>
        <SegmentedControl
          options={[
            { value: "normal", label: "Normal lease" },
            { value: "two-tier", label: "Two-tier grant" },
          ]}
          value={kind}
          onChange={(v) => setKind(v as GrantKind)}
          ariaLabel="Grant kind"
        />
      </div>
      {kind === "two-tier" ? (
        snap.grant ? (
          <GrantCard snap={snap} />
        ) : (
          <>
            <GroupLabel>Burst spec</GroupLabel>
            <GroupedList>
              {snap.specs.map((s) => (
                <SpecRow
                  key={s.id}
                  spec={s}
                  selected={s.id === burst}
                  onSelect={() => setBurst(s.id)}
                />
              ))}
            </GroupedList>
            <GroupLabel>Grant</GroupLabel>
            <GroupedList>
              <Row>
                <span className="rn-lab rn-lab-keep">Grant hours</span>
                <span className="rn-ml-auto">
                  <DurationPicker
                    ariaLabel="Grant duration"
                    options={DURATION_OPTIONS}
                    value={grantHours}
                    onChange={setGrantHours}
                  />
                </span>
              </Row>
            </GroupedList>
            <GroupLabel>Start</GroupLabel>
            <GroupedList>
              <ActionRow
                label={busy ? "Starting…" : `Start grant · ${fmtDurHours(grantHours)}`}
                onClick={startGrant}
              />
            </GroupedList>
            <p className="rn-sub" style={{ marginTop: 10 }}>
              A grant snapshots the sanctioned shapes and the budget caps in force at grant
              time; in-scope acquires under it carry its envelope stamp and price against the
              snapshot.
            </p>
          </>
        )
      ) : (
        <>
          <GroupLabel>Shape</GroupLabel>
          <GroupedList>
            {snap.specs.map((s) => (
              <SpecRow
                key={s.id}
                spec={s}
                selected={s.id === shape}
                onSelect={() => setShape(s.id)}
              />
            ))}
          </GroupedList>
          <GroupLabel>Grant</GroupLabel>
          <GroupedList>
            <Row>
              <span className="rn-lab">Caller</span>
              <span className="rn-ml-auto" style={{ width: 240 }}>
                <Select
                  ariaLabel="Caller"
                  value={callerSel}
                  onChange={(e) => setCallerSel(e.target.value)}
                  options={[
                    ...adapter.registeredCallers().map((c) => ({ value: c, label: c })),
                    { value: CUSTOM, label: "Custom caller…" },
                  ]}
                />
              </span>
            </Row>
            {callerSel === CUSTOM ? (
              <Row>
                <span className="rn-lab">Caller name</span>
                <span className="rn-ml-auto" style={{ width: 240 }}>
                  <Input
                    ariaLabel="Custom caller name"
                    value={customCaller}
                    placeholder="thread caller id"
                    onChange={(e) => setCustomCaller(e.target.value)}
                  />
                </span>
              </Row>
            ) : null}
            <Row>
              <span className="rn-lab rn-lab-keep">Duration</span>
              <span className="rn-ml-auto">
                <DurationPicker
                  ariaLabel="Lease duration"
                  options={DURATION_OPTIONS}
                  value={hours}
                  onChange={setHours}
                />
              </span>
            </Row>
          </GroupedList>
          <GroupLabel>Acquire</GroupLabel>
          <GroupedList>
            <ActionRow
              label={
                busy
                  ? "Acquiring…"
                  : cost != null
                    ? `Acquire lease · ${cost} CU`
                    : "Acquire lease · cost unconfirmed"
              }
              onClick={acquire}
            />
          </GroupedList>
          {inScope ? (
            <p className="rn-sub" style={{ marginTop: 10 }}>
              This shape is in the active grant's scope — the acquire carries the grant's
              envelope stamp and prices against its snapshot caps.
            </p>
          ) : null}
          <p className="rn-sub" style={{ marginTop: 10 }}>
            Placement is the venue layer's: a live lease at this shape is adopted by
            latest-deadline order before a new one is created (contract 12). Venue:{" "}
            {snap.leases[0]?.venueLabel ?? "Colab"} — the only implemented adapter.
          </p>
        </>
      )}
    </>
  );
}
