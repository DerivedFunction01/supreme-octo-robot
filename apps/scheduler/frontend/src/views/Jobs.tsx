// The Jobs list, grouped (approved mockup frames 1–3 +
// the owner's taxonomy refinement, 2026-11-13; contract 09
// amendment). The split is the SERVED classification, never
// derived here: operator jobs are full rows in the "Yours"
// group exactly as before; built-ins are compact single-
// line rows in the Built-in group — family built-ins carry
// their family tag, direct built-ins carry none (placement
// is the whole statement). Search and the status segment
// filter BOTH groups; a group with no matches hides, and
// the no-match state stays the honest empty state.
//
// Composition: at phone width the Built-in group opens
// with its header row (count + running summary, a working
// disclosure); on desktop the group label carries the
// summary and the rows split across two columns (frame 3).

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { SegmentedControl } from "@workhorse/kit/components/controls/SegmentedControl";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { useIsPhone } from "@workhorse/kit/lib/responsive";
import type { SchedulerApi } from "../api";
import type { JobView } from "../types";
import { LargeTitle } from "../components/ui";
import {
  CompactRow,
  Group,
  GroupLabel,
  OutcomeChip,
  Row,
  jobChip,
} from "../components/ui";
import { FAMILY_LABELS, cadenceKindWord } from "../format";

type Filter = "all" | "enabled" | "disabled";

export function Jobs({
  api,
  search,
  onOpenJob,
}: {
  api: SchedulerApi;
  search: string;
  onOpenJob: (jobId: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [builtinsOpen, setBuiltinsOpen] = useState(true);
  const isPhone = useIsPhone();
  const jobs = api.listJobs();
  const operators = jobs.filter((j) => j.audience === "operator");
  const builtins = jobs.filter((j) => j.audience === "builtin");
  const runningBuiltins = builtins.filter((j) => j.status === "active").length;

  const needle = search.trim().toLowerCase();
  const matches = (job: JobView) => {
    if (filter === "enabled" && job.status !== "active") return false;
    if (filter === "disabled" && job.status !== "suspended") return false;
    if (
      needle &&
      !job.id.toLowerCase().includes(needle) &&
      !job.owner.toLowerCase().includes(needle)
    ) {
      return false;
    }
    return true;
  };
  const visibleOperators = operators.filter(matches);
  const visibleBuiltins = builtins.filter(matches);

  const builtinRow = (job: JobView) => (
    <CompactRow
      key={job.id}
      label={job.id}
      tag={job.family ? FAMILY_LABELS[job.family] : null}
      onClick={() => onOpenJob(job.id)}
    />
  );

  return (
    <>
      <LargeTitle
        title="Jobs"
        subtitle={`${jobs.length} entries · ${operators.length} yours · ${builtins.length} built-in`}
      />
      <div className="mb-[18px]">
        <SegmentedControl
          ariaLabel="Filter jobs by status"
          options={[
            { value: "all", label: "All" },
            { value: "enabled", label: "Enabled" },
            { value: "disabled", label: "Disabled" },
          ]}
          value={filter}
          onChange={setFilter}
        />
      </div>

      {visibleOperators.length === 0 && visibleBuiltins.length === 0 ? (
        <EmptyState message="No jobs match this filter" />
      ) : (
        <>
          {visibleOperators.length > 0 ? (
            <>
              <GroupLabel>Yours</GroupLabel>
              <Group>
                {visibleOperators.map((job) => {
                  const chip = jobChip(job);
                  return (
                    <Row
                      key={job.id}
                      label={job.id}
                      sub={`${cadenceKindWord(job.cadence)} · ${job.cadence_label}`}
                      end={<OutcomeChip tone={chip.tone} text={chip.text} />}
                      chevron
                      onClick={() => onOpenJob(job.id)}
                    />
                  );
                })}
              </Group>
            </>
          ) : null}

          {visibleBuiltins.length > 0 ? (
            <>
              <GroupLabel>
                {isPhone
                  ? "Built-in"
                  : `Built-in · ${runningBuiltins} running`}
              </GroupLabel>
              {isPhone ? (
                <Group>
                  <button
                    type="button"
                    aria-expanded={builtinsOpen}
                    onClick={() => setBuiltinsOpen((open) => !open)}
                    className="flex min-h-[47px] w-full cursor-pointer flex-nowrap items-center gap-3 border-0 px-3.5 py-[11px] text-left focus-visible:outline-2 focus-visible:outline-(--wb-focus-ring)"
                    style={{
                      backgroundColor: "var(--wb-surface-1)",
                      borderTopColor: "var(--wb-border-default)",
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div
                        className="truncate text-[14.5px] font-medium"
                        style={{ color: "var(--wb-content-primary)" }}
                      >
                        Built-in services
                      </div>
                      <div
                        className="truncate text-[12.5px]"
                        style={{ color: "var(--wb-content-secondary)" }}
                      >
                        Internal pipeline loops
                      </div>
                    </div>
                    <div className="ml-auto flex max-w-[60%] flex-none items-center gap-2">
                      <OutcomeChip
                        tone={runningBuiltins === builtins.length ? "ok" : "warn"}
                        text={`${runningBuiltins} running`}
                      />
                    </div>
                    {builtinsOpen ? (
                      <ChevronDown
                        size={15}
                        className="flex-none"
                        style={{ color: "var(--wb-content-muted)" }}
                      />
                    ) : (
                      <ChevronRight
                        size={15}
                        className="flex-none"
                        style={{ color: "var(--wb-content-muted)" }}
                      />
                    )}
                  </button>
                  {builtinsOpen ? visibleBuiltins.map(builtinRow) : null}
                </Group>
              ) : (
                (() => {
                  const half = Math.ceil(visibleBuiltins.length / 2);
                  const columns = [
                    visibleBuiltins.slice(0, half),
                    visibleBuiltins.slice(half),
                  ].filter((col) => col.length > 0);
                  return (
                    <div className="flex items-start gap-[18px]">
                      {columns.map((col, i) => (
                        <div key={i} className="min-w-0 flex-1">
                          <Group>{col.map(builtinRow)}</Group>
                        </div>
                      ))}
                    </div>
                  );
                })()
              )}
            </>
          ) : null}
        </>
      )}
    </>
  );
}
