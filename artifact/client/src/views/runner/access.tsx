// Access — the panel's session access list (app.js
// renderAccess) as its own route (storyboard frame 7):
// every live session with its caller, or flagged
// unattributed; unattributed entries carry the one release
// verb, attributed ones render without it — their
// lifecycle belongs to their lease record or their owning
// thread. The same list also closes the Leases view, as it
// closed the panel's leases section.

import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { AccessList } from "./leases";
import { DegradedCard, PartStatus } from "./pickers";
import { useRunner } from "./state";

export function AccessView() {
  const { parts, allDown } = useRunner();
  if (allDown) return <DegradedCard />;
  const access = parts.records.data?.access || [];
  return (
    <div className="flex flex-col gap-4">
      <PartStatus name="records" part={parts.records} />
      {parts.records.data ? (
        access.length ? (
          <AccessList entries={access} />
        ) : (
          <EmptyState message="No live sessions" />
        )
      ) : null}
    </div>
  );
}
