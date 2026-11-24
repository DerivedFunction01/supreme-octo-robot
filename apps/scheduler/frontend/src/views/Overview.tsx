import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import type { SchedulerApi } from "../api";
import { LargeTitle } from "../components/ui";
import {
  FactRow,
  Group,
  GroupLabel,
  NoticeRow,
  OutcomeChip,
  Row,
  jobChip,
} from "../components/ui";
import { cadenceKindWord, fmtTimeOfDay } from "../format";

export function Overview({
  api,
  search,
  onOpenJob,
  onOpenJobs,
}: {
  api: SchedulerApi;
  search: string;
  onOpenJob: (jobId: string) => void;
  onOpenJobs: () => void;
}) {
  const overview = api.getOverview();
  const jobs = api.listJobs();

  // The counts split (contract 09, amendment):
  // the Status group counts the OPERATOR's jobs from the
  // served classification; built-ins summarize on their own
  // row. Last outcome and Next wake stay fleet-wide — the
  // frame shows the fleet's next wake (bridge-wake, a
  // built-in) by name.
  const operators = jobs.filter((j) => j.audience === "operator");
  const builtins = jobs.filter((j) => j.audience === "builtin");
  const operatorEnabled = operators.filter((j) => j.status === "active").length;
  const builtinsRunning = builtins.filter((j) => j.status === "active").length;

  const lastOutcome = jobs
    .map((j) => j.last_run)
    .filter((r) => r !== null)
    .sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))[0];

  const nextWake = jobs
    .filter((j) => j.next_due !== null && j.next_due_in_secs !== null)
    .sort((a, b) => (a.next_due_in_secs ?? 0) - (b.next_due_in_secs ?? 0))[0];

  // Recent jobs are the operator's, actively running ones —
  // a suspended entry has no recent runs to show.
  const recent = [...operators]
    .filter((j) => j.status === "active" && j.last_run !== null)
    .sort(
      (a, b) =>
        Date.parse(b.last_run!.ts) - Date.parse(a.last_run!.ts),
    )
    .slice(0, 3);

  // The shell's one search string filters this view's job rows
  // with the same predicate the Jobs view applies to its rows
  // (id or owner contains the needle, trimmed, case-insensitive).
  const needle = search.trim().toLowerCase();
  const visibleRecent = recent.filter(
    (job) =>
      !needle ||
      job.id.toLowerCase().includes(needle) ||
      job.owner.toLowerCase().includes(needle),
  );

  const pendingCount = Object.values(overview.outbox_by_kind).reduce(
    (a, b) => a + b,
    0,
  );

  return (
    <>
      <LargeTitle
        title="Overview"
        subtitle={`Server ${overview.server_status} · last tick ${fmtTimeOfDay(overview.last_tick)}${overview.last_tick !== "" ? " · served just now" : ""}`}
      />
      {overview.notice ? (
        <NoticeRow title={overview.notice.title} text={overview.notice.text} />
      ) : null}

      <GroupLabel>Status</GroupLabel>
      <Group>
        <FactRow label="Jobs enabled">
          {operatorEnabled} of {operators.length}
        </FactRow>
        <FactRow label="Pings waiting">
          <OutcomeChip
            tone={pendingCount > 0 ? "warn" : "idle"}
            text={`${pendingCount} waiting`}
          />
        </FactRow>
        <FactRow label="Last outcome">
          {lastOutcome ? (
            <OutcomeChip
              tone={
                lastOutcome.status === "ok"
                  ? "ok"
                  : lastOutcome.status === "running"
                    ? "info"
                    : "fail"
              }
              text={`${lastOutcome.status === "ok" ? "Ran" : lastOutcome.label} · ${fmtTimeOfDay(lastOutcome.ts)}`}
            />
          ) : (
            "—"
          )}
        </FactRow>
        <FactRow label="Next wake">
          {nextWake?.next_due
            ? `${fmtTimeOfDay(nextWake.next_due, nextWake.timezone)} · ${nextWake.id}`
            : "—"}
        </FactRow>
      </Group>

      <GroupLabel>Built-ins</GroupLabel>
      <Group>
        <Row
          label="Built-ins"
          sub="Internal pipeline loops"
          end={
            <OutcomeChip
              tone={builtinsRunning === builtins.length ? "ok" : "warn"}
              text={`${builtinsRunning} running`}
            />
          }
          chevron
          onClick={onOpenJobs}
        />
      </Group>

      <GroupLabel>Jobs</GroupLabel>
      {needle && visibleRecent.length === 0 ? (
        <EmptyState message="No jobs match this filter" />
      ) : (
        <Group>
          {visibleRecent.map((job) => {
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
      )}
    </>
  );
}
