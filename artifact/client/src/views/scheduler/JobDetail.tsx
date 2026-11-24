// V-3 · Job detail — the original's jobDetailView(): the
// facts card (the list entry's fields over the getJob
// detail payload), then the kind's history — scripted:
// Recent runs + the latest run's stdout/stderr tails;
// agent: Recent activity (recent dues + ping history).
// States are the original's: unknown id → "No such
// job."; detail not yet landed (or landed for another
// job) → "Loading detail…"; empty history → "No runs
// yet." / "No dues yet."
//
// Standing exclusion (RESTORE-NOTES X-3): NO Enabled
// switch and NO Run now / Disable controls — no backing
// server verb exists and the original client is
// read-only by design.

import type { ReactNode } from "react";
import { Card } from "@workhorse/kit/components/display/Card";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import {
  fmtDur,
  fmtTime,
  outcomeTone,
  type JobDetailPayload,
  type JobsPayload,
} from "./model";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      className="flex items-baseline justify-between gap-4 py-[5px] text-sm"
      style={{ borderBottom: "1px solid var(--wb-border-default)" }}
    >
      <span style={{ color: "var(--wb-content-secondary)" }}>{label}</span>
      <span className="min-w-0 text-right [overflow-wrap:anywhere]">{children}</span>
    </div>
  );
}

/** The long-text facts (Command, State paths,
 * Classification), spanning the facts grid in the
 * codebase's definition-list form (the workbench worktree
 * dl): a fixed 120px label column, the value left-aligned
 * in the full remaining width. On the stat row above,
 * these values wrap inside the row's leftover space as a
 * narrow right-aligned column — faithful text, hard to
 * scan (scheduler critic confirmation) — and
 * a long value squeezes its label into a sliver. */
function WideFact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      className="grid py-[5px] text-sm"
      style={{
        gridColumn: "1 / -1",
        gridTemplateColumns: "120px 1fr",
        columnGap: "var(--wb-space-16)",
        borderBottom: "1px solid var(--wb-border-default)",
      }}
    >
      <span style={{ color: "var(--wb-content-secondary)" }}>{label}</span>
      <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
    </div>
  );
}

function HistoryRow({
  first,
  children,
}: {
  first?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className="flex flex-wrap items-center gap-2.5 py-[5px] text-sm"
      style={first ? undefined : { borderTop: "1px solid var(--wb-border-default)" }}
    >
      {children}
    </div>
  );
}

function RowTime({ ts }: { ts: string }) {
  return (
    <span className="mono num text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
      {fmtTime(ts)}
    </span>
  );
}

function Dim({ children }: { children: ReactNode }) {
  return <span style={{ color: "var(--wb-content-secondary)" }}>{children}</span>;
}

export function JobDetail({
  jobs,
  jobDetail,
  jobId,
  navigate,
}: {
  jobs: JobsPayload | null;
  jobDetail: JobDetailPayload | null;
  jobId: string;
  navigate: (hash: string) => void;
}) {
  if (!jobs) {
    return <EmptyState message="Loading…" />;
  }
  const j = jobs.jobs.find((x) => x.id === jobId);
  if (!j) {
    return <EmptyState message="No such job." />;
  }
  const d = jobDetail;
  if (!d || d.id !== jobId) {
    return <EmptyState message="Loading detail…" />;
  }
  const det = d.detail;

  const facts: { label: string; value: ReactNode; wide?: boolean }[] = [
    {
      label: "Kind / status",
      value: `${j.kind} · ${j.status}${j.suspend_reason ? ` (${j.suspend_reason})` : ""}`,
    },
    { label: "Cadence", value: `${j.cadence_label} · ${j.timezone}` },
    {
      label: "Next due",
      value: j.next_due
        ? `${fmtTime(j.next_due)} (in ${fmtDur(j.next_due_in_secs)})`
        : "—",
    },
    { label: "Timeout", value: `${det.timeout_secs}s` },
    { label: "OK exit codes", value: (det.ok_exit_codes || []).join(", ") },
    { label: "Report", value: det.report?.when ?? "—" },
    { label: "Command", value: det.run?.argv ? det.run.argv.join(" ") : "—", wide: true },
    {
      label: "State paths",
      value: (det.state_paths || []).join(" · ") || "—",
      wide: true,
    },
    { label: "Classification", value: det.classification || "—", wide: true },
  ];

  const isAgent = j.kind === "agent";
  const latest = d.recent_runs[0];
  const hasHistory = isAgent
    ? d.recent_dues.length > 0 || d.ping_history.length > 0
    : d.recent_runs.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <p>
        <a
          href="#/scheduler/jobs"
          onClick={(e) => {
            e.preventDefault();
            navigate("#/scheduler/jobs");
          }}
          className="inline-block py-[2px]"
          style={{ color: "var(--wb-accent)" }}
        >
          ← all jobs
        </a>
      </p>

      <Card title={d.id}>
        <div className="grid gap-x-7 [grid-template-columns:repeat(auto-fit,minmax(290px,1fr))]">
          {facts.map((fact) =>
            fact.wide ? (
              <WideFact key={fact.label} label={fact.label}>
                {fact.value}
              </WideFact>
            ) : (
              <Fact key={fact.label} label={fact.label}>
                {fact.value}
              </Fact>
            ),
          )}
        </div>
      </Card>

      <Card title={isAgent ? "Recent activity" : "Recent runs"}>
        {!hasHistory ? (
          <EmptyState message={isAgent ? "No dues yet." : "No runs yet."} />
        ) : isAgent ? (
          <div>
            {d.recent_dues.slice(0, 15).map((r, i) => (
              <HistoryRow key={`due-${r.ts}-${i}`} first={i === 0}>
                <RowTime ts={r.ts} />
                <span>agent due</span>
                {r.collapsed != null && r.collapsed > 1 ? (
                  <Dim>{r.collapsed} collapsed</Dim>
                ) : null}
              </HistoryRow>
            ))}
            {d.ping_history.map((p, i) => (
              <HistoryRow
                key={`ping-${p.ts}-${i}`}
                first={d.recent_dues.length === 0 && i === 0}
              >
                <RowTime ts={p.ts} />
                <Dim>{p.detail}</Dim>
              </HistoryRow>
            ))}
          </div>
        ) : (
          <div>
            {d.recent_runs.map((r, i) => (
              <HistoryRow key={`run-${r.ts}-${i}`} first={i === 0}>
                <RowTime ts={r.ts} />
                <StatusChip tone={outcomeTone(r.label)} label={r.label} />
                {r.matched_pattern ? <Dim>matched {r.matched_pattern}</Dim> : null}
                {r.collapsed != null && r.collapsed > 1 ? (
                  <Dim>{r.collapsed} collapsed</Dim>
                ) : null}
              </HistoryRow>
            ))}
          </div>
        )}

        {!isAgent && latest && (latest.stdout_tail || latest.stderr_tail) ? (
          <>
            <h4 className="mt-4 mb-1 text-[13.5px] font-semibold">
              Latest run output (tails)
            </h4>
            {latest.stdout_tail ? (
              <pre
                tabIndex={0}
                className="mono my-1.5 max-h-[180px] overflow-auto rounded-[7px] p-2.5 text-xs whitespace-pre-wrap [word-break:break-word] focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-(--wb-focus-ring)"
                style={{
                  backgroundColor: "var(--wb-surface-sunken)",
                  border: "1px solid var(--wb-border-default)",
                }}
              >
                {latest.stdout_tail}
              </pre>
            ) : null}
            {latest.stderr_tail ? (
              <pre
                tabIndex={0}
                className="mono my-1.5 max-h-[180px] overflow-auto rounded-[7px] p-2.5 text-xs whitespace-pre-wrap [word-break:break-word] focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-(--wb-focus-ring)"
                style={{
                  backgroundColor: "var(--wb-surface-sunken)",
                  border: "1px solid var(--wb-border-default)",
                }}
              >
                {latest.stderr_tail}
              </pre>
            ) : null}
          </>
        ) : null}
      </Card>
    </div>
  );
}
