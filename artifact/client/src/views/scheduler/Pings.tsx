// V-4 · Pings — the outbox, oldest first (the original's
// pingsView()): one card per waiting ping with its due,
// its skew-corrected waiting duration, the past-ack-
// timeout marker, coalesced count, body ref, and the ack
// instruction. Below it, the storyboard frame's Recent
// group (RESTORE-NOTES X-4): the acked-pings window,
// backed by getPingsRecent — servable from the action
// layer without inventing data. Its fetch rides the same
// 30 s cadence as the poll, with its own honest
// loading / error / empty states; a failure there never
// touches the poll's failure ladder. The waiting list
// itself is the pings portion: it renders when that
// portion lands, with its waiting ages computed from
// the pings payload's own served_at skew.

import { useQuery } from "@tanstack/react-query";
import { DegradedBanner } from "@workhorse/kit/components/display/DegradedBanner";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import {
  GroupLabel,
  GroupedList,
  Row,
} from "@workhorse/kit/components/display/GroupedList";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import { api } from "../../lib/actions";
import {
  PINGS_RECENT_LIMIT,
  POLL_MS,
  SchedulerFailure,
  fmtDur,
  fmtTime,
  servedAgeSecs,
  unwrap,
  type PingPayload,
  type PingsPayload,
} from "./model";

function PingCard({ ping, skewMs, now }: { ping: PingPayload; skewMs: number; now: number }) {
  const age = servedAgeSecs(ping.created, skewMs, now);
  return (
    <section
      className="p-[13px_15px]"
      style={{
        backgroundColor: "var(--ui-card-bg)",
        border: `1px solid ${ping.overdue ? "var(--ui-status-stale)" : "var(--ui-border-default)"}`,
        borderRadius: "var(--ui-card-radius)",
        color: "var(--ui-content-primary)",
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <strong>{ping.job_id}</strong>
        <StatusChip tone="idle" label={ping.kind} />
        {ping.overdue ? <StatusChip tone="warn" label="past ack timeout" /> : null}
      </div>
      <div className="mt-1 text-sm" style={{ color: "var(--ui-content-secondary)" }}>
        due {fmtTime(ping.due)} · waiting{" "}
        <span className="num">{fmtDur(age)}</span>
      </div>
      {ping.coalesced_count > 1 ? (
        <div className="text-xs" style={{ color: "var(--ui-content-secondary)" }}>
          {ping.coalesced_count} dues coalesced
        </div>
      ) : null}
      {ping.body_ref ? (
        <div className="text-xs" style={{ color: "var(--ui-content-secondary)" }}>
          body: {ping.body_ref}
        </div>
      ) : null}
      <div className="text-xs" style={{ color: "var(--ui-content-secondary)" }}>
        Ack: <code className="mono">bin/sched ack {ping.id}</code>
      </div>
    </section>
  );
}

function failureText(error: unknown): { message: string; detail: string } {
  if (error instanceof SchedulerFailure && error.kind === "bridge") {
    return {
      message: "Recent pings could not be loaded — the bridge is unreachable.",
      detail: error.message,
    };
  }
  if (error instanceof SchedulerFailure) {
    return {
      message: "Recent pings could not be loaded — the server answered an error.",
      detail: error.message,
    };
  }
  return { message: "Recent pings could not be loaded.", detail: String(error) };
}

function RecentGroup() {
  const query = useQuery({
    queryKey: ["scheduler", "pings-recent"],
    queryFn: () =>
      unwrap<PingsPayload>(api.getPingsRecent({ limit: PINGS_RECENT_LIMIT })),
    retry: false,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
  });
  const pings = query.data?.pings ?? null;

  return (
    <div className="mt-3">
      <GroupLabel>Recent</GroupLabel>
      {query.error && pings ? (
        <div className="mb-3">
          <DegradedBanner
            message={failureText(query.error).message}
            detail="Showing the last good window."
          />
        </div>
      ) : null}
      {pings ? (
        pings.length > 0 ? (
          <GroupedList>
            {pings.map((p) => (
              <Row
                key={p.id}
                label={p.job_id}
                badge={<StatusChip tone="idle" label={p.kind} />}
                sub={
                  <>
                    acked {fmtTime(p.acked_at)} · due {fmtTime(p.due)}
                    {p.coalesced_count > 1
                      ? ` · ${p.coalesced_count} dues coalesced`
                      : ""}
                  </>
                }
              />
            ))}
          </GroupedList>
        ) : (
          <EmptyState message="No acked pings in the window." />
        )
      ) : query.error ? (
        <DegradedBanner
          message={failureText(query.error).message}
          detail={failureText(query.error).detail}
        />
      ) : (
        <EmptyState message="Loading…" />
      )}
    </div>
  );
}

export function Pings({
  pings,
  skewMs,
  now,
}: {
  pings: PingsPayload | null;
  skewMs: number;
  now: number;
}) {
  const waiting = pings?.pings;
  return (
    <div className="flex flex-col gap-2">
      <GroupLabel>Pings — oldest first</GroupLabel>
      {waiting ? (
        waiting.length > 0 ? (
          <div className="flex flex-col gap-2.5">
            {waiting.map((p) => (
              <PingCard key={p.id} ping={p} skewMs={skewMs} now={now} />
            ))}
          </div>
        ) : (
          <EmptyState message="Outbox empty — nothing waiting." />
        )
      ) : (
        <EmptyState message="Loading…" />
      )}
      <RecentGroup />
    </div>
  );
}
