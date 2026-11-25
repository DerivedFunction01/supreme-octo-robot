import { useState } from "react";
import { Toggle } from "@workhorse/kit/components/controls/Toggle";
import { Button } from "@workhorse/kit/components/controls/Button";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { GroupedList } from "@workhorse/kit/components/display/GroupedList";
import {
  LogRow,
  type LogRowEntry,
  type LogRowTone,
} from "@workhorse/kit/components/display/LogRow";
import type { SchedulerApi } from "../api";
import type { OpenInTarget, RunView } from "../types";
import { ConfigGroup } from "../components/ConfigGroup";
import { BuiltInDetail } from "./BuiltInDetail";
import { LargeTitle } from "../components/ui";
import {
  ActionError,
  ActionRow,
  FactRow,
  Group,
  GroupLabel,
  OutcomeChip,
  Row,
  TOGGLE_LABEL_SR_ONLY,
  jobChip,
} from "../components/ui";
import {
  capitalize,
  fmtCountdown,
  fmtDateToken,
  fmtDayTime,
  fmtTimeOfDay,
  isToday,
} from "../format";

/** The LogRow badge form of a run outcome (the timeline
 *  study's scoped variant: outcome = badge, detail prose =
 *  headline, time = meta). The tone mapping is runChip's,
 *  exactly; the label is the outcome word — where runChip's
 *  text form appends the run's time ("Ran · 3:04 PM"), the
 *  badge omits it, because the time rides the row's own
 *  meta line. */
function runBadge(run: RunView): { tone: LogRowTone; text: string } {
  switch (run.status) {
    case "running":
      return { tone: "info", text: "Running" };
    case "skipped_overlap":
      return { tone: "warn", text: "Skipped" };
    case "ok":
      return run.detail?.startsWith("Skipped · ")
        ? { tone: "warn", text: "Skipped" }
        : { tone: "ok", text: "Ran" };
    case "failed":
      return { tone: "fail", text: run.label };
    case "timeout":
      return { tone: "fail", text: "Timed out" };
    case "could_not_start":
      return { tone: "fail", text: "Could not start" };
  }
}

export function JobDetail({
  api,
  jobId,
  onBack,
  onOpenInApp,
}: {
  api: SchedulerApi;
  jobId: string;
  onBack: () => void;
  onOpenInApp?: (target: OpenInTarget, jobId: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const detail = api.getJob(jobId);

  if (detail && detail.audience === "builtin") {
    // Built-ins render their own read-only form (no run /
    // enable controls anywhere on it).
    return (
      <BuiltInDetail api={api} detail={detail} onOpenInApp={onOpenInApp} />
    );
  }

  if (!detail) {
    return (
      <>
        <LargeTitle title={jobId} subtitle="Not in the registry" />
        <EmptyState
          message="This job is not in the registry"
          action={
            <Button variant="secondary" onClick={onBack}>
              Back to jobs
            </Button>
          }
        />
      </>
    );
  }

  const act = (result: { ok: boolean; detail?: string }) => {
    setError(result.ok ? null : (result.detail ?? "Action failed"));
  };

  const enabled = detail.status === "active";
  const lastChip = jobChip(detail, true);
  const kindWord =
    detail.cadence.type === "interval" ? "Interval" : "Cron";

  return (
    <>
      <LargeTitle
        title={detail.id}
        subtitle={`${kindWord} job · owned by ${detail.owner === "none" ? "the scheduler registry" : detail.owner}`}
      />

      <GroupLabel>Facts</GroupLabel>
      <Group>
        <FactRow label="Enabled">
          <Toggle
            label="Enabled"
            checked={enabled}
            onChange={(checked) => act(api.setJobEnabled(detail.id, checked))}
            className={TOGGLE_LABEL_SR_ONLY}
          />
        </FactRow>
        <FactRow label="Schedule">{capitalize(detail.cadence_label)}</FactRow>
        <FactRow label="Owner">
          <span className="mono">{detail.owner}</span>
        </FactRow>
        {detail.last_activity ? (
          <FactRow label="Last activity">
            <OutcomeChip tone={lastChip.tone} text={lastChip.text} />
          </FactRow>
        ) : (
          <FactRow label="Last run">
            {detail.last_run ? (
              <OutcomeChip tone={lastChip.tone} text={lastChip.text} />
            ) : (
              "—"
            )}
          </FactRow>
        )}
        <FactRow label="Next run">
          {detail.next_due
            ? `${fmtTimeOfDay(detail.next_due, detail.timezone)} · ${fmtCountdown(detail.next_due_in_secs)}`
            : "—"}
        </FactRow>
        {!enabled && detail.suspend_reason ? (
          <FactRow label="Suspended">
            {detail.suspend_reason}
            {detail.suspended_on ? ` · since ${detail.suspended_on}` : ""}
          </FactRow>
        ) : null}
      </Group>
      <ActionError message={error} />

      {detail.config ? (
        <ConfigGroup api={api} jobId={detail.id} config={detail.config} />
      ) : null}

      <GroupLabel>Run history</GroupLabel>
      <GroupedList>
        {detail.recent_runs.length === 0 ? (
          <Row label="No runs yet" sub="Agent jobs serve activity through pings instead" />
        ) : (
          detail.recent_runs.slice(0, 12).map((run, i) => {
            const badge = runBadge(run);
            const entry: LogRowEntry = {
              dateToken: fmtDateToken(run.ts, detail.timezone),
              time: fmtTimeOfDay(run.ts, detail.timezone),
              headline:
                (run.detail ?? run.label) +
                (run.collapsed > 0 ? ` · ${run.collapsed} collapsed` : ""),
              kind: { label: badge.text, tone: badge.tone },
            };
            return <LogRow key={`${run.ts}-${i}`} entry={entry} />;
          })
        )}
      </GroupedList>

      <GroupLabel>Registry</GroupLabel>
      <Group>
        <FactRow label="Title">
          <span className="max-w-[430px] whitespace-normal">{detail.title}</span>
        </FactRow>
        <FactRow label="Kind">
          {detail.kind === "agent" ? "Agent" : "Scripted"}
        </FactRow>
        {detail.body ? (
          <FactRow label="Body">
            <span className="mono">{detail.body}</span>
          </FactRow>
        ) : null}
        {detail.run ? (
          <FactRow label="Run">
            <span className="mono max-w-[430px] [overflow-wrap:anywhere]">
              {detail.run.argv.join(" ")}
            </span>
          </FactRow>
        ) : null}
        <FactRow label="Timezone">{detail.timezone}</FactRow>
        <FactRow label="Timeout">
          {detail.timeout_secs !== null ? `${detail.timeout_secs} s` : "—"}
        </FactRow>
        <FactRow label="Report">{detail.report_mode}</FactRow>
        <FactRow label="OK exit codes">
          <span className="mono">{detail.ok_exit_codes.join(", ")}</span>
        </FactRow>
        <FactRow label="Runs · 24 h">
          {detail.runs_24h} runs · {detail.failures_24h} failures · streak{" "}
          {detail.failure_streak}
        </FactRow>
        <FactRow label="Expected wakes/day">{detail.expected_wakes_per_day}</FactRow>
        <FactRow label="Lifetime">{detail.lifetime}</FactRow>
        {detail.catalog ? (
          <FactRow label="Catalog">
            {detail.catalog.origin} · {detail.catalog.generality} ·{" "}
            {detail.catalog.use_case}
          </FactRow>
        ) : null}
        <div
          className="px-3.5 py-[11px]"
          style={{ borderTopColor: "var(--ui-border-default)" }}
        >
          <div
            className="text-[14.5px] font-medium"
            style={{ color: "var(--ui-content-primary)" }}
          >
            Classification
          </div>
          <p
            className="mt-1 text-[12.5px] leading-relaxed whitespace-normal [overflow-wrap:anywhere]"
            style={{ color: "var(--ui-content-secondary)" }}
          >
            {detail.classification}
          </p>
        </div>
        {detail.state_paths.length > 0 ? (
          <div
            className="px-3.5 py-[11px]"
            style={{ borderTopColor: "var(--ui-border-default)" }}
          >
            <div
              className="text-[14.5px] font-medium"
              style={{ color: "var(--ui-content-primary)" }}
            >
              State paths
            </div>
            {detail.state_paths.map((path) => (
              <div key={path} className="mono mt-1 text-[12px] break-all" style={{ color: "var(--ui-content-secondary)" }}>
                {path}
              </div>
            ))}
          </div>
        ) : null}
      </Group>

      <GroupLabel>Recent dues</GroupLabel>
      <Group>
        {detail.recent_dues.slice(0, 8).map((due, i) => (
          <Row
            key={`${due.due}-${i}`}
            label={
              isToday(due.due, detail.timezone)
                ? fmtTimeOfDay(due.due, detail.timezone)
                : fmtDayTime(due.due, detail.timezone)
            }
            sub={
              due.outcome === "pending"
                ? "Pending"
                : due.outcome === "collapsed"
                  ? `Collapsed · ${due.collapsed} points into one run`
                  : due.outcome === "skipped_overlap"
                    ? "Skipped · previous run still active"
                    : "Fired"
            }
            end={
              <OutcomeChip
                tone={
                  due.outcome === "pending"
                    ? "idle"
                    : due.outcome === "fired"
                      ? "ok"
                      : "warn"
                }
                text={
                  due.outcome === "pending"
                    ? "Pending"
                    : due.outcome === "fired"
                      ? "Fired"
                      : due.outcome === "collapsed"
                        ? "Collapsed"
                        : "Skipped"
                }
              />
            }
          />
        ))}
      </Group>

      {detail.ping_history.length > 0 ? (
        <>
          <GroupLabel>Ping history</GroupLabel>
          <GroupedList>
            {detail.ping_history.map((row, i) => {
              // The window serves the server's event rows (S8):
              // the headline is the served detail string; the
              // badge reads the event kind — acked, voided, or
              // still waiting (created / woken / coalesced).
              const entry: LogRowEntry = {
                dateToken: fmtDateToken(row.ts, detail.timezone),
                time: fmtTimeOfDay(row.ts, detail.timezone),
                headline: row.detail,
                kind:
                  row.kind === "ping_acked"
                    ? { label: "Acked", tone: "ok" }
                    : row.kind === "ping_voided"
                      ? { label: "Void", tone: "idle" }
                      : { label: "Waiting", tone: "warn" },
                meta: row.ping_kind ?? row.kind,
              };
              return <LogRow key={`${row.ts}-${i}`} entry={entry} />;
            })}
          </GroupedList>
        </>
      ) : null}

      <GroupLabel>Actions</GroupLabel>
      <Group>
        <ActionRow label="Run now" onClick={() => act(api.runNow(detail.id))} />
        {enabled ? (
          <ActionRow
            label="Disable job"
            danger
            onClick={() => act(api.setJobEnabled(detail.id, false))}
          />
        ) : (
          <ActionRow
            label="Enable job"
            onClick={() => act(api.setJobEnabled(detail.id, true))}
          />
        )}
      </Group>
    </>
  );
}
