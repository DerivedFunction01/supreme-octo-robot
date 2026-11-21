import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { GroupedList } from "@workhorse/kit/components/display/GroupedList";
import {
  LogRow,
  type LogRowEntry,
  type LogRowTone,
} from "@workhorse/kit/components/display/LogRow";
import type { SchedulerApi } from "../api";
import { LargeTitle } from "../components/ui";
import { fmtDateToken, fmtTimeOfDay } from "../format";

// The ledger is a timeline surface: its rows are the kit's
// one LogRow (timeline-component study, Variant B — the
// mockup drew this frame unchanged from Events: kind badge
// whole at the right, the detail as the headline, the time
// on the meta line). The kind mapping is the app's served-
// kind → badge presentation, as before.
function kindChip(kind: string, detail: string): { tone: LogRowTone; text: string } {
  switch (kind) {
    case "op":
      return { tone: "info", text: "Op" };
    case "run":
      return / failed ·| timed out| could not start/.test(detail)
        ? { tone: "fail", text: "Run" }
        : { tone: "ok", text: "Run" };
    case "ping_acked":
      return { tone: "ok", text: "Ack" };
    case "ping_created":
    case "ping_coalesced":
      return { tone: "info", text: "Ping" };
    case "agent_due":
      return { tone: "warn", text: "Due" };
    case "skipped_overlap":
      return { tone: "warn", text: "Skip" };
    case "catchup":
      return { tone: "warn", text: "Catchup" };
    case "entry_removed":
      return { tone: "idle", text: "Removed" };
    case "registry_error":
    case "state_error":
      return { tone: "fail", text: "Error" };
    default:
      return { tone: "idle", text: kind };
  }
}

export function Ledger({
  api,
  search,
}: {
  api: SchedulerApi;
  search: string;
}) {
  const ledger = api.getLedger(200);
  const needle = search.trim().toLowerCase();
  const visible = ledger.events.filter(
    (event) =>
      !needle ||
      event.detail.toLowerCase().includes(needle) ||
      (event.job_id ?? "").toLowerCase().includes(needle) ||
      event.kind.includes(needle),
  );

  return (
    <>
      <LargeTitle
        title="Ledger"
        subtitle="Every op, run, and acknowledgement · today"
      />
      {visible.length === 0 ? (
        <EmptyState message="No ledger events match" />
      ) : (
        <GroupedList>
          {visible.map((event, i) => {
            const chip = kindChip(event.kind, event.detail);
            const entry: LogRowEntry = {
              dateToken: fmtDateToken(event.ts),
              time: fmtTimeOfDay(event.ts),
              headline: event.detail,
              kind: { label: chip.text, tone: chip.tone },
            };
            return <LogRow key={`${event.ts}-${i}`} entry={entry} />;
          })}
        </GroupedList>
      )}
    </>
  );
}
