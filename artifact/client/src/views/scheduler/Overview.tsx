// V-1 · Overview — the whole poll at a glance (the
// original's overviewView()): four stat cards over the
// served totals, the Failing-now panel when any job's
// failure streak is live, and the Recent activity feed
// (the ledger portion's window, in the kit's one log-row
// form). Each section renders when its own portion lands
// — the stat cards on the overview portion, Failing now
// on the jobs portion, Recent activity on the ledger
// portion. Composition: kit Card + LogRow; the original's
// field set is the inventory — the storyboard frame is a
// composition sketch, not a data inventory (RESTORE-
// NOTES X-1).

import type { ReactNode } from "react";
import { Card } from "@workhorse/kit/components/Card";
import { EmptyState } from "@workhorse/kit/components/EmptyState";
import { GroupedList } from "@workhorse/kit/components/GroupedList";
import { LogRow } from "@workhorse/kit/components/LogRow";
import { StatusChip } from "@workhorse/kit/components/StatusChip";
import {
  fmtBytes,
  fmtTime,
  ledgerLogEntry,
  outcomeTone,
  type JobsPayload,
  type LedgerPayload,
  type OverviewPayload,
} from "./model";

function StatLine({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[2.5px] text-sm">
      <span style={{ color: "var(--wb-content-secondary)" }}>{label}</span>
      <span className="num text-right">{children}</span>
    </div>
  );
}

function BigLine({ children }: { children: ReactNode }) {
  return <div className="num mb-1 text-[21px] font-semibold">{children}</div>;
}

export function Overview({
  overview,
  jobs,
  ledger,
  navigate,
}: {
  overview: OverviewPayload | null;
  jobs: JobsPayload | null;
  ledger: LedgerPayload | null;
  navigate: (hash: string) => void;
}) {
  const o = overview;
  const t = o?.totals_24h;
  const st = o?.storage;
  const failing = jobs ? jobs.jobs.filter((j) => j.failure_streak > 0) : [];
  const events = ledger?.events;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(215px,1fr))]">
        <Card title="Last 24 hours">
          {o && t ? (
            <>
              <BigLine>{t.runs} runs</BigLine>
              <StatLine label="failures">{t.failures}</StatLine>
              <StatLine label="wake-ups served">{t.wakeups_served}</StatLine>
              <StatLine label="pings created">{t.pings_created}</StatLine>
            </>
          ) : (
            <EmptyState message="Loading…" />
          )}
        </Card>
        <Card title="Registry">
          {o ? (
            <>
              <BigLine>{o.registry.total} jobs</BigLine>
              <StatLine label="scripted">{o.registry.by_kind.scripted || 0}</StatLine>
              <StatLine label="agent">{o.registry.by_kind.agent || 0}</StatLine>
              <StatLine label="migrated">
                {typeof o.registry.migrated === "number" ? o.registry.migrated : "—"}
              </StatLine>
            </>
          ) : (
            <EmptyState message="Loading…" />
          )}
        </Card>
        <Card title="Outbox">
          {o ? (
            <>
              <BigLine>{o.outbox.depth} pending</BigLine>
              <StatLine label="past ack timeout">{o.outbox.aged}</StatLine>
              <StatLine label="running now">{o.running.join(", ") || "—"}</StatLine>
            </>
          ) : (
            <EmptyState message="Loading…" />
          )}
        </Card>
        <Card title="Log store">
          {o && st ? (
            <>
              <BigLine>
                {st.kind} · {fmtBytes(st.db_bytes)}
              </BigLine>
              <StatLine label="events">{st.events}</StatLine>
              <StatLine label="retention">{st.retention_days} days</StatLine>
              <StatLine label="last prune">
                {st.last_prune
                  ? `${fmtTime(st.last_prune.ts)} · ${st.last_prune.dropped} dropped`
                  : "none yet"}
              </StatLine>
              <StatLine label="lifecycle">
                <a
                  href="#/scheduler/ledger"
                  onClick={(e) => {
                    e.preventDefault();
                    navigate("#/scheduler/ledger");
                  }}
                  className="mono text-xs"
                  style={{ color: "var(--wb-accent)" }}
                >
                  sched logs …
                </a>
              </StatLine>
            </>
          ) : (
            <EmptyState message="Loading…" />
          )}
        </Card>
      </div>

      {failing.length > 0 ? (
        <Card title="Failing now">
          <div className="flex flex-col">
            {failing.map((j, i) => (
              <div
                key={j.id}
                className="flex flex-wrap items-center gap-2.5 py-[5px]"
                style={
                  i > 0
                    ? { borderTop: "1px solid var(--wb-border-default)" }
                    : undefined
                }
              >
                <StatusChip
                  tone={outcomeTone(j.last_run?.label)}
                  label={j.last_run?.label ?? "—"}
                />
                <a
                  href={`#/scheduler/jobs/${encodeURIComponent(j.id)}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(`#/scheduler/jobs/${encodeURIComponent(j.id)}`);
                  }}
                  className="font-medium"
                  style={{ color: "var(--wb-accent)" }}
                >
                  {j.id}
                </a>
                <span
                  className="num text-sm"
                  style={{ color: "var(--wb-content-secondary)" }}
                >
                  streak ×{j.failure_streak}
                </span>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Card title="Recent activity">
        {events ? (
          events.length > 0 ? (
            <GroupedList>
              {events.map((event, i) => (
                <LogRow key={`${event.ts}-${i}`} entry={ledgerLogEntry(event)} />
              ))}
            </GroupedList>
          ) : (
            <EmptyState message="No events yet." />
          )
        ) : (
          <EmptyState message="Loading…" />
        )}
      </Card>
    </div>
  );
}
