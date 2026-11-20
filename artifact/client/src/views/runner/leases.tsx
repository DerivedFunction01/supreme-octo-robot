// Leases — the panel's home section (app.js renderLeases /
// renderGrant / renderAccess) and the storyboard's lease
// detail (frame 2), as views of the one client. Records,
// specs (labels), grant, budget (caps) and listeners are
// separate portions; each card renders from the portions
// landed so far and re-renders as the rest arrive — no
// section waits on another portion's read.

import type { ReactNode } from "react";
import { ArmConfirm } from "@workhorse/kit/components/ArmConfirm";
import { Button } from "@workhorse/kit/components/Button";
import { Card } from "@workhorse/kit/components/Card";
import { EmptyState } from "@workhorse/kit/components/EmptyState";
import {
  GroupedList,
  Row,
  StatRow,
} from "@workhorse/kit/components/GroupedList";
import { StatusChip } from "@workhorse/kit/components/StatusChip";
import { api } from "../../lib/actions";
import {
  countdownText,
  extendRefusalText,
  fmtNum,
  fmtTime,
  shortenRefusalText,
  specById,
  specLabel,
  specRateText,
  specTitle,
  type AccessEntry,
  type LeaseEntry,
  type ListenersPayload,
  type Spec,
} from "./model";
import {
  AllStaleBanner,
  DegradedCard,
  ExtendPicker,
  LeaseStatusChips,
  PartStatus,
  ShortenPicker,
  extKey,
  usePickers,
  type PickerState,
} from "./pickers";
import { callApi, callVerdict, useRunner } from "./state";

export const MONO = { fontFamily: "var(--wb-font-mono, monospace)" } as const;

function kv(label: ReactNode, children: ReactNode) {
  return (
    <p className="mt-1.5 text-sm" style={{ color: "var(--wb-content-secondary)" }}>
      {label}{" "}
      <b style={{ color: "var(--wb-content-primary)", fontWeight: 600 }}>{children}</b>
    </p>
  );
}

/* ---------------- listeners (per-session census) ---------------- */

export function ListenerLines({
  listeners,
  session,
}: {
  listeners: ListenersPayload["listeners"];
  session: string;
}) {
  // The listeners portion is keyed by session and served
  // ready (suspect derivation included); honest absence
  // (no census yet, or a census with no listeners) renders
  // no line at all.
  const census = listeners?.[session] ?? null;
  if (!census) return null;
  if (census.error) {
    return (
      <p className="mt-1.5 text-sm" style={{ color: "var(--wb-content-secondary)" }}>
        Listeners <b style={{ color: "var(--wb-content-primary)" }}>census failed</b>
      </p>
    );
  }
  return (
    <>
      {(census.listeners || []).map((l, i) => (
        <p
          key={i}
          className="mt-1.5 flex flex-wrap items-center gap-1.5 text-sm"
          style={{ color: "var(--wb-content-secondary)" }}
        >
          Port <b style={{ color: "var(--wb-content-primary)" }}>{String(l.port)}</b> ·
          pid {String(l.pid)} · <span style={MONO}>{l.cwd || "—"}</span>
          {(l.suspect || []).length ? (
            <StatusChip tone="warn" label={`suspect: ${(l.suspect || []).join(", ")}`} />
          ) : null}
        </p>
      ))}
    </>
  );
}

/* ---------------- extend / shorten reports ---------------- */

function useLeaseActions(pickers: PickerState) {
  const { act, setBusy, setNotice } = useRunner();

  const applyExtend = (kind: "lease" | "grant", key: string) => {
    const stateKey = extKey(kind, key);
    const hours = pickers.extHours[stateKey] ?? 8;
    void act(async () => {
      setBusy(stateKey, "Extending…");
      try {
        const res =
          kind === "grant"
            ? await callApi<Record<string, unknown>>(() =>
                api.extendGrant({ body: { hours } }),
              )
            : await callApi<Record<string, unknown>>(() =>
                api.extendLease({ body: { session: key, hours } }),
              );
        if (res.action === "extended") {
          pickers.closeExt(stateKey);
          setNotice(`Extended — new deadline ${fmtTime(res.new_deadline as string)}`);
        } else if (res.action === "grant-extended") {
          pickers.closeExt("grant");
          setNotice(`Grant extended — until ${fmtTime(res.new_until as string)}`);
        } else {
          // Refusals surface the core's reason — the extend
          // endpoints answer 200 with the refusal action.
          setNotice(`Extension refused: ${extendRefusalText(res)}`);
        }
      } finally {
        setBusy(stateKey, null);
      }
    });
  };

  const applyShorten = (session: string) => {
    const body: Record<string, unknown> = { session };
    const dl = pickers.shortDeadline[session];
    if (dl) {
      const when = new Date(dl);
      if (Number.isNaN(when.getTime())) {
        setNotice("Shorten refused: the chosen time is not a valid time");
        return;
      }
      body.deadline = when.toISOString();
    } else {
      body.hours = pickers.shortHours[session] ?? 8;
    }
    void act(async () => {
      const k = `shorten:${session}`;
      setBusy(k, "Shortening…");
      try {
        const res = await callVerdict(() => api.shortenLease({ body }));
        if (res.action === "shortened") {
          pickers.closeShort(session);
          pickers.setShortDeadline(session, null);
          setNotice(`Shortened — new deadline ${fmtTime(res.new_deadline as string)}`);
        } else {
          setNotice(`Shorten refused: ${shortenRefusalText(res)}`);
        }
      } finally {
        setBusy(k, null);
      }
    });
  };

  const terminate = (session: string) => {
    void act(async () => {
      await callApi(() => api.stopLease({ body: { session } }));
    });
  };

  return { applyExtend, applyShorten, terminate };
}

/* ---------------- lease card ---------------- */

function LeaseCard({
  entry,
  specs,
  listeners,
  pickers,
  actions,
  navigate,
}: {
  entry: LeaseEntry;
  specs: Spec[];
  listeners: ListenersPayload["listeners"];
  pickers: PickerState;
  actions: ReturnType<typeof useLeaseActions>;
  navigate: (hash: string) => void;
}) {
  const { now } = useRunner();
  const rec = entry.record || {};
  const session = entry.session || rec.session || "";
  const spec = specById(specs, rec.shape);
  const title = spec ? specTitle(spec) : session || "lease";
  const age = entry.keepalive_heartbeat_age_s;
  const key = extKey("lease", session);
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="min-w-0 cursor-pointer truncate text-left text-[15px] font-semibold"
          style={{ color: "var(--wb-content-primary)", minHeight: 24 }}
          onClick={() => navigate(`#/runner/leases/${encodeURIComponent(session)}`)}
        >
          {title}
        </button>
        <LeaseStatusChips entry={entry} />
      </div>
      <p
        className="mt-2 text-[26px] leading-tight font-semibold"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {countdownText(rec.deadline, now)}
      </p>
      {kv(
        "Deadline",
        <>
          {fmtTime(rec.deadline)} · session <span style={MONO}>{rec.session || "—"}</span>
          {rec.caller ? (
            <>
              {" "}
              · Caller <b>{rec.caller}</b>
            </>
          ) : null}
        </>,
      )}
      {kv(
        "Heartbeat",
        <>
          {age == null ? "unknown" : `${Math.round(age)}s ago`} · Pulse{" "}
          {rec.last_pulse_result || "—"} · Burn {spec ? specRateText(spec) : "—"}
        </>,
      )}
      {entry.sync_claim
        ? kv(
            "Sync claim",
            <>
              {entry.sync_claim.caller || "—"} · until{" "}
              {fmtTime(entry.sync_claim.expires_at)}
            </>,
          )
        : null}
      <ListenerLines listeners={listeners} session={session} />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <ArmConfirm
          label="Terminate"
          confirmLabel="Confirm terminate"
          statement={`Terminate the ${session} lease now. The lease ends immediately and its deadline stops being enforced.`}
          variant="danger"
          disarmKey={session}
          onConfirm={() => actions.terminate(session)}
        />
        <Button variant="ghost" onClick={() => pickers.toggleExt(key)}>
          Extend
        </Button>
        <Button variant="ghost" onClick={() => pickers.toggleShort(session)}>
          Shorten
        </Button>
      </div>
      {pickers.extOpen.has(key) ? (
        <ExtendPicker
          stateKey={key}
          pickers={pickers}
          onApply={() => actions.applyExtend("lease", session)}
        />
      ) : null}
      {pickers.shortOpen.has(session) ? (
        <ShortenPicker
          session={session}
          pickers={pickers}
          onApply={() => actions.applyShorten(session)}
        />
      ) : null}
    </Card>
  );
}

/* ---------------- access list ---------------- */

export function AccessList({ entries }: { entries: AccessEntry[] }) {
  const { act } = useRunner();
  if (!entries.length) return null;
  return (
    <Card title="Session access">
      <GroupedList>
        {entries.map((e, i) => (
          <Row
            key={e.session || i}
            label={<span style={MONO}>{e.session || "—"}</span>}
            sub={
              <>
                {e.shape_class || "shape unknown"} ·{" "}
                {e.caller ? (
                  <>
                    Caller <b>{e.caller}</b>
                  </>
                ) : (
                  "Unattributed"
                )}{" "}
                · since {fmtTime(e.first_seen)}
              </>
            }
            badge={
              e.caller ? undefined : <StatusChip tone="warn" label="Unattributed" />
            }
            end={
              e.unattributed ? (
                <ArmConfirm
                  label="Release"
                  confirmLabel="Confirm release"
                  statement={`Release the unattributed session ${e.session || ""} now. Its access hold is dropped.`}
                  variant="danger"
                  disarmKey={e.session || ""}
                  onConfirm={() =>
                    void act(async () => {
                      await callApi(() =>
                        api.releaseAccess({ body: { session: e.session || "" } }),
                      );
                    })
                  }
                />
              ) : undefined
            }
          />
        ))}
      </GroupedList>
    </Card>
  );
}

/* ---------------- leases view (route /) ---------------- */

export function LeasesView({ navigate }: { navigate: (hash: string) => void }) {
  const { parts, allDown, allFailed } = useRunner();
  const pickers = usePickers();
  const actions = useLeaseActions(pickers);
  if (allDown) return <DegradedCard />;
  const records = parts.records.data?.records || [];
  const specs = parts.specs.data?.specs || [];
  const listeners = parts.listeners.data?.listeners;
  const access = parts.records.data?.access || [];
  return (
    <div className="flex flex-col gap-4">
      {allFailed ? <AllStaleBanner /> : null}
      <PartStatus name="grant" part={parts.grant} />
      <GrantCardWithActions pickers={pickers} actions={actions} />
      <PartStatus name="records" part={parts.records} />
      {parts.records.data ? (
        records.length ? (
          records.map((entry, i) => (
            <LeaseCard
              key={entry.session || entry.record?.session || i}
              entry={entry}
              specs={specs}
              listeners={listeners}
              pickers={pickers}
              actions={actions}
              navigate={navigate}
            />
          ))
        ) : (
          <EmptyState message="No leases running" />
        )
      ) : null}
      <AccessList entries={access} />
    </div>
  );
}

// The grant card, sharing the list's picker state and the
// shared actions hook (its Extend apply is the grant form
// of the same verb).
function GrantCardWithActions({
  pickers,
  actions,
}: {
  pickers: PickerState;
  actions: ReturnType<typeof useLeaseActions>;
}) {
  return (
    <GrantCardInner pickers={pickers} applyExtend={actions.applyExtend} />
  );
}

function GrantCardInner({
  pickers,
  applyExtend,
}: {
  pickers: PickerState;
  applyExtend: (kind: "lease" | "grant", key: string) => void;
}) {
  const { parts, act } = useRunner();
  const grantPart = parts.grant.data;
  const grant = grantPart?.grant;
  const active = Boolean(grant && typeof grant === "object" && grant.until);
  if (!active || !grant) return null;
  const caps = parts.budget.data?.budget?.caps || {};
  const env = grantPart?.envelope ?? null;
  const envCaps = env?.caps || caps;
  const envLeases = env && Array.isArray(env.records) ? env.records : [];
  const envSpend = env?.spend || {};
  const specs = parts.specs.data?.specs || [];
  const budget = parts.budget.data?.budget;
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[15px] font-semibold">Two-tier grant</span>
        <StatusChip tone="ok" label="Active" />
      </div>
      {kv(
        "Until",
        <>
          {fmtTime(grant.until)} · Burst spec{" "}
          {specLabel(specs, (grant.scope || {}).burst_shape)}
        </>,
      )}
      {budget && budget.standing_day_spent != null
        ? kv(
            "Standing spend today",
            <>
              {fmtNum(budget.standing_day_spent)} of{" "}
              {envCaps.standing_daily == null ? "—" : fmtNum(envCaps.standing_daily)} CU
            </>,
          )
        : kv(
            "Standing cap",
            <>{envCaps.standing_daily == null ? "—" : `${fmtNum(envCaps.standing_daily)} CU/day`}</>,
          )}
      {env ? (
        <>
          {kv(
            "Envelope caps (at grant)",
            <>
              daily {envCaps.daily == null ? "—" : `${fmtNum(envCaps.daily)} CU`} ·
              monthly {envCaps.monthly == null ? "—" : `${fmtNum(envCaps.monthly)} CU`}
            </>,
          )}
          {kv(
            "Envelope spend",
            <>
              today {envSpend.day_spent == null ? "—" : `${fmtNum(envSpend.day_spent)} CU`}{" "}
              · this month{" "}
              {envSpend.month_spent == null ? "—" : `${fmtNum(envSpend.month_spent)} CU`}
            </>,
          )}
          <p
            className="mt-2.5 text-sm font-semibold"
            style={{ color: "var(--wb-content-primary)" }}
          >
            Envelope leases
          </p>
          {envLeases.length ? (
            envLeases.map((rec, i) => (
              <p
                key={i}
                className="mt-1 text-sm"
                style={{ color: "var(--wb-content-secondary)" }}
              >
                · <b style={{ color: "var(--wb-content-primary)" }}>{specLabel(specs, rec.shape)}</b>
                {rec.caller ? (
                  <>
                    {" "}
                    · caller <b style={{ color: "var(--wb-content-primary)" }}>{rec.caller}</b>
                  </>
                ) : null}{" "}
                · until{" "}
                <b style={{ color: "var(--wb-content-primary)" }}>{fmtTime(rec.deadline)}</b>
              </p>
            ))
          ) : (
            <p className="mt-1 text-sm" style={{ color: "var(--wb-content-secondary)" }}>
              No envelope leases yet.
            </p>
          )}
        </>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <ArmConfirm
          label="Revoke grant"
          confirmLabel="Confirm revoke"
          statement="Revoke the two-tier grant now. The lobby is no longer held by the standing duty."
          variant="ghost"
          disarmKey="grant"
          onConfirm={() =>
            void act(async () => {
              await callApi(() => api.ungrant({ body: {} }));
            })
          }
        />
        <Button variant="ghost" onClick={() => pickers.toggleExt("grant")}>
          Extend grant
        </Button>
      </div>
      {pickers.extOpen.has("grant") ? (
        <ExtendPicker
          stateKey="grant"
          pickers={pickers}
          onApply={() => applyExtend("grant", "")}
        />
      ) : null}
    </Card>
  );
}

/* ---------------- lease detail (route /leases/<id>) ---------------- */

export function LeaseDetailView({ session }: { session: string }) {
  const { parts, allDown, now } = useRunner();
  const pickers = usePickers();
  const actions = useLeaseActions(pickers);
  if (allDown) return <DegradedCard />;
  const records = parts.records.data?.records || [];
  const entry = records.find(
    (e) => (e.session || e.record?.session || "") === session,
  );
  const specs = parts.specs.data?.specs || [];
  return (
    <div className="flex flex-col gap-4">
      <PartStatus name="records" part={parts.records} />
      {parts.records.data && !entry ? (
        <EmptyState
          message={`No lease record for ${session}`}
          detail="The session is not in the last served records."
        />
      ) : null}
      {entry ? (
        <>
          <Card>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[15px] font-semibold">
                {(() => {
                  const spec = specById(specs, entry.record?.shape);
                  return spec ? specTitle(spec) : session;
                })()}
              </span>
              <LeaseStatusChips entry={entry} />
            </div>
            <p
              className="mt-2 text-[26px] leading-tight font-semibold"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {countdownText(entry.record?.deadline, now)}
            </p>
            <div className="mt-3">
              <GroupedList>
                <StatRow label="State">
                  {entry.record?.standing
                    ? "Standing"
                    : entry.action || "unknown"}
                </StatRow>
                <StatRow label="Shape">
                  {specLabel(specs, entry.record?.shape)}
                </StatRow>
                <StatRow label="Caller">{entry.record?.caller || "—"}</StatRow>
                <StatRow label="Session">
                  <span style={MONO}>{entry.record?.session || session}</span>
                </StatRow>
                {entry.record?.acquired_at ? (
                  <StatRow label="Acquired">{fmtTime(entry.record.acquired_at)}</StatRow>
                ) : null}
                <StatRow label="Deadline">
                  {fmtTime(entry.record?.deadline)} ·{" "}
                  {countdownText(entry.record?.deadline, now)}
                </StatRow>
                <StatRow label="Heartbeat">
                  {entry.keepalive_heartbeat_age_s == null
                    ? "unknown"
                    : `${Math.round(entry.keepalive_heartbeat_age_s)}s ago`}
                </StatRow>
                <StatRow label="Pulse">{entry.record?.last_pulse_result || "—"}</StatRow>
                <StatRow label="Burn">
                  {(() => {
                    const spec = specById(specs, entry.record?.shape);
                    return spec ? specRateText(spec) : "—";
                  })()}
                </StatRow>
                {entry.sync_claim ? (
                  <StatRow label="Sync claim">
                    {entry.sync_claim.caller || "—"} · until{" "}
                    {fmtTime(entry.sync_claim.expires_at)}
                  </StatRow>
                ) : null}
              </GroupedList>
            </div>
            <ListenerLines
              listeners={parts.listeners.data?.listeners}
              session={session}
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <ArmConfirm
                label="Terminate"
                confirmLabel="Confirm terminate"
                statement={`Terminate the ${session} lease now. The lease ends immediately and its deadline stops being enforced.`}
                variant="danger"
                disarmKey={session}
                onConfirm={() => actions.terminate(session)}
              />
              <Button
                variant="ghost"
                onClick={() => pickers.toggleExt(extKey("lease", session))}
              >
                Extend
              </Button>
              <Button variant="ghost" onClick={() => pickers.toggleShort(session)}>
                Shorten
              </Button>
            </div>
            {pickers.extOpen.has(extKey("lease", session)) ? (
              <ExtendPicker
                stateKey={extKey("lease", session)}
                pickers={pickers}
                onApply={() => actions.applyExtend("lease", session)}
              />
            ) : null}
            {pickers.shortOpen.has(session) ? (
              <ShortenPicker
                session={session}
                pickers={pickers}
                onApply={() => actions.applyShorten(session)}
              />
            ) : null}
          </Card>
        </>
      ) : null}
    </div>
  );
}
