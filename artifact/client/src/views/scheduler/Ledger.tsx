// V-5 · Ledger — the storyboard's full ledger view
// (RESTORE-NOTES X-5): the original client serves ledger
// data only inside the Overview's Recent activity feed;
// the storyboard promotes it to a view over the SAME
// getLedger call at a view-level limit (200 here, the
// feed's is 50; the action's schema allows 500). Rows
// are the kit's LogRow, the kind chips presentation over
// the kind the ledger itself serves (model.ts) — no
// served field is invented. The fetch rides the
// snapshot's 30 s cadence with its own honest states,
// independent of the snapshot's failure ladder.

import { useQuery } from "@tanstack/react-query";
import { DegradedBanner } from "@workhorse/kit/components/display/DegradedBanner";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import {
  GroupLabel,
  GroupedList,
} from "@workhorse/kit/components/display/GroupedList";
import { LogRow } from "@workhorse/kit/components/display/LogRow";
import { api } from "../../lib/actions";
import {
  LEDGER_VIEW_LIMIT,
  POLL_MS,
  SchedulerFailure,
  ledgerLogEntry,
  unwrap,
  type LedgerPayload,
} from "./model";

function failureMessage(error: unknown): string {
  if (error instanceof SchedulerFailure && error.kind === "bridge") {
    return "The ledger could not be loaded — the bridge is unreachable.";
  }
  if (error instanceof SchedulerFailure) {
    return "The ledger could not be loaded — the server answered an error.";
  }
  return "The ledger could not be loaded.";
}

export function Ledger() {
  const query = useQuery({
    queryKey: ["scheduler", "ledger", LEDGER_VIEW_LIMIT],
    queryFn: () =>
      unwrap<LedgerPayload>(api.getLedger({ limit: LEDGER_VIEW_LIMIT })),
    retry: false,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
  });
  const events = query.data?.events ?? null;

  return (
    <div>
      <GroupLabel>Ledger — latest {LEDGER_VIEW_LIMIT} events</GroupLabel>
      {query.error && events ? (
        <div className="mb-3">
          <DegradedBanner
            message={failureMessage(query.error)}
            detail="Showing the last good window."
          />
        </div>
      ) : null}
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
      ) : query.error ? (
        <DegradedBanner
          message={failureMessage(query.error)}
          detail={
            query.error instanceof SchedulerFailure
              ? query.error.message
              : String(query.error)
          }
        />
      ) : (
        <EmptyState message="Loading…" />
      )}
    </div>
  );
}
