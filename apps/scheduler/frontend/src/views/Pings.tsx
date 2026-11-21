import { useState } from "react";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { GroupedList } from "@workhorse/kit/components/display/GroupedList";
import { LogRow, type LogRowEntry } from "@workhorse/kit/components/display/LogRow";
import type { SchedulerApi } from "../api";
import type { PingView } from "../types";
import { LargeTitle } from "../components/ui";
import {
  ActionError,
  Group,
  GroupLabel,
  OutcomeChip,
  Row,
  type Tone,
} from "../components/ui";
import { fmtAge, fmtDateToken, fmtTimeOfDay } from "../format";

function kindChip(ping: PingView): { tone: Tone; text: string } {
  if (ping.overdue) return { tone: "fail", text: "Overdue" };
  switch (ping.kind) {
    case "agent-due":
      return { tone: "warn", text: "Wake" };
    case "escalation":
      return { tone: "warn", text: "Escalation" };
    case "report":
      return { tone: "info", text: "Report" };
  }
}

export function Pings({
  api,
  search,
}: {
  api: SchedulerApi;
  search: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const pending = api.listPings();
  const recent = api.listRecentPings();

  const needle = search.trim().toLowerCase();
  const matches = (ping: PingView) =>
    !needle ||
    ping.summary.toLowerCase().includes(needle) ||
    ping.job_id.toLowerCase().includes(needle);
  const visiblePending = pending.filter(matches);
  const visibleRecent = recent.filter(matches);

  return (
    <>
      <LargeTitle
        title="Pings"
        subtitle={`${pending.length} waiting · wakes and status posts land here`}
      />

      <GroupLabel>Waiting</GroupLabel>
      {visiblePending.length === 0 ? (
        <EmptyState message="No pings waiting" />
      ) : (
        <Group>
          {visiblePending.map((ping) => {
            const chip = kindChip(ping);
            const note =
              typeof ping.detail.note === "string" ? ping.detail.note : null;
            return (
              <Row
                key={ping.id}
                label={
                  <span className="flex min-w-0 items-center gap-2.5">
                    <OutcomeChip tone={chip.tone} text={chip.text} />
                    <span className="truncate">{ping.summary}</span>
                  </span>
                }
                sub={`${note ? `${note} · ` : ""}${ping.job_id} · ${fmtAge(ping.age_secs)}`}
                end={
                  <OutcomeChip
                    tone="info"
                    text="Acknowledge"
                    onPress={() => {
                      const result = api.ackPing(ping.id, "owner");
                      setError(result.ok ? null : result.detail);
                    }}
                  />
                }
              />
            );
          })}
        </Group>
      )}
      <ActionError message={error} />

      <GroupLabel>Recent</GroupLabel>
      {visibleRecent.length === 0 ? (
        <EmptyState message="Nothing acknowledged yet" />
      ) : (
        <GroupedList>
          {visibleRecent.map((ping) => {
            const ackedBy =
              typeof ping.detail.acked_by === "string"
                ? ping.detail.acked_by
                : "—";
            // The Recent group is a timeline surface: the
            // kit's LogRow (Variant B) — the summary as the
            // headline, Acked as the kind badge, the ack
            // instant in the date/time slots, the actor on
            // the meta line.
            const at = ping.acked_at ?? ping.created;
            const entry: LogRowEntry = {
              dateToken: fmtDateToken(at),
              time: fmtTimeOfDay(at),
              headline: ping.summary,
              kind: { label: "Acked", tone: "ok" },
              meta: `Acknowledged by ${ackedBy}`,
            };
            return <LogRow key={ping.id} entry={entry} />;
          })}
        </GroupedList>
      )}
    </>
  );
}
