// Built-in detail — the read-only form for a built-in job
// (approved mockup frame 6 + the owner's taxonomy
// refinement; contract 09 amendment).
//
// Status, last run, latest outcome, and the 24 h counts —
// every figure served by the detail view. NO Enabled
// switch, NO Run now, NO Disable: built-ins are not
// operator-run. The one operable part is the Config group,
// rendered only when the entry carries knobs. Family
// built-ins close with the Managed-by group (owning
// service + the "Open in" row, which posts the shell-
// bridge navigation intent); direct built-ins have no
// family, so the group is absent — placement in the
// Built-in group is the whole statement.

import type { SchedulerApi } from "../api";
import type { JobDetailView, OpenInTarget } from "../types";
import { ConfigGroup } from "../components/ConfigGroup";
import { LargeTitle } from "../components/ui";
import {
  FactRow,
  Group,
  GroupLabel,
  OutcomeChip,
  Row,
  jobChip,
} from "../components/ui";
import { FAMILY_LABELS, OPEN_IN_LABELS } from "../format";

export function BuiltInDetail({
  api,
  detail,
  onOpenInApp,
}: {
  api: SchedulerApi;
  detail: JobDetailView;
  onOpenInApp?: (target: OpenInTarget, jobId: string) => void;
}) {
  const chip = jobChip(detail);
  const familyLabel = detail.family ? FAMILY_LABELS[detail.family] : null;
  const subtitle = familyLabel
    ? `Built-in · ${familyLabel} · ${detail.cadence_label}`
    : `Built-in · ${detail.cadence_label}`;

  // The latest outcome in the served forms: a scripted
  // built-in's last-run prose, else the served activity
  // label (an agent built-in acts through pings). Detail's
  // ping history serves event rows, not records, so there
  // is no record summary to draw from (S8 dispositions,
  // contract 09).
  const latestOutcome =
    detail.last_run?.detail ?? detail.last_activity?.label ?? "—";

  return (
    <>
      <LargeTitle title={detail.id} subtitle={subtitle} />

      <GroupLabel>Status</GroupLabel>
      <Group>
        <FactRow label="Status">
          {detail.status === "active" ? "Active" : "Suspended"}
        </FactRow>
        <FactRow label={detail.last_activity ? "Last activity" : "Last run"}>
          <OutcomeChip tone={chip.tone} text={chip.text} />
        </FactRow>
        <div
          className="px-3.5 py-[11px]"
          style={{ borderTopColor: "var(--ui-border-default)" }}
        >
          <div
            className="text-[14.5px] font-medium"
            style={{ color: "var(--ui-content-primary)" }}
          >
            Latest outcome
          </div>
          <p
            className="mt-1 text-[12.5px] leading-relaxed whitespace-normal [overflow-wrap:anywhere]"
            style={{ color: "var(--ui-content-secondary)" }}
          >
            {latestOutcome}
          </p>
        </div>
        <FactRow label="Runs · 24 h">{detail.runs_24h}</FactRow>
        <FactRow label="Failures · 24 h">{detail.failures_24h}</FactRow>
      </Group>

      {detail.config ? (
        <ConfigGroup api={api} jobId={detail.id} config={detail.config} />
      ) : null}

      {familyLabel && detail.open_in ? (
        <>
          <GroupLabel>Managed by</GroupLabel>
          <Group>
            <FactRow label="Owning service">{familyLabel}</FactRow>
            <Row
              label={
                <span
                  className="font-semibold"
                  style={{ color: "var(--ui-accent)" }}
                >
                  Open in {OPEN_IN_LABELS[detail.open_in]}
                </span>
              }
              chevron
              onClick={() => onOpenInApp?.(detail.open_in!, detail.id)}
            />
          </Group>
        </>
      ) : null}
    </>
  );
}
