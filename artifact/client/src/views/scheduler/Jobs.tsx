// V-2 · Jobs — the job table (the original's jobsView() +
// jobRow()): kind filter chips (all / scripted / agent —
// the original's filter dimension, the behaviour of
// record over the storyboard's status segments, RESTORE-
// NOTES X-2), the original's six columns, row → detail.
//
// The table is view-local markup on kit tokens, not the
// kit DataTable: DataTable's contract is one-line rows
// (fixed row height, truncating cells), and the job
// row's cells are two-line by the behaviour of record
// (outcome label over its time, cadence over timezone,
// next due over its in-duration). Extending the kit is
// the coordinator's call, not this lane's; the markup
// here follows DataTable's own styling conventions
// (header treatment, hairlines, hover surface).
//
// ≤720px (the original stylesheet's house table
// breakpoint) the wide columns drop and the Job cell
// gains its compact line — the table compacts instead
// of scrolling, exactly the original's form.
//
// Overflow cure (2026-11-20): the table is auto
// layout, so columns size at their cells' min-content
// floors. Unbreakable Job-cell text — long hyphenated
// ids in the <strong>, single-token owners in Sub —
// set a 237px Job floor; with Last outcome at its chip
// floor (153px) the table took 390px inside a 320px
// card content box and the outcome pills rendered past
// the screen edge (before-proof:
// workhorse-jobs-overflow-before-20261120T170019Z).
// The label treatment the rest of the client uses —
// [overflow-wrap:anywhere] on the id and on Sub,
// min-w-0 on the id's flex wrapper — collapses those
// floors so the compact table fits its card. No column
// drops, no label truncates. The wrap rides
// wrap={compact} — scoped to compact mode, where the
// pressure is: wide mode was never broken (ids wrap
// at hyphens on their own and the Cadence timezone
// sits on one line), and the unconditional form also
// lowered the Cadence Sub's floor on desktop —
// Cadence measured 133→107.8px with the timezone
// wrapping mid-token (after-proof:
// workhorse-jobs-overflow-after2-20261120T171051Z) —
// so desktop keeps its untreated sizing.

import { useState, type ReactNode } from "react";
import { Card } from "@workhorse/kit/components/Card";
import { EmptyState } from "@workhorse/kit/components/EmptyState";
import { SegmentedControl } from "@workhorse/kit/components/SegmentedControl";
import { StatusChip } from "@workhorse/kit/components/StatusChip";
import {
  fmtDur,
  fmtTime,
  outcomeTone,
  type JobPayload,
  type JobsPayload,
} from "./model";

type KindFilter = "all" | "scripted" | "agent";

const SECONDARY = { color: "var(--wb-content-secondary)" } as const;

function Sub({ children, wrap }: { children: ReactNode; wrap?: boolean }) {
  return (
    <div
      className={wrap ? "text-xs [overflow-wrap:anywhere]" : "text-xs"}
      style={SECONDARY}
    >
      {children}
    </div>
  );
}

function LastOutcome({ job, compact }: { job: JobPayload; compact: boolean }) {
  if (job.kind === "agent") {
    const act = job.last_activity;
    if (!act) {
      return <span style={SECONDARY}>— no dues yet</span>;
    }
    return (
      <>
        <StatusChip
          tone={
            act.tone === "ok" || act.tone === "warn" || act.tone === "fail"
              ? act.tone
              : "idle"
          }
          label={act.label}
        />
        <Sub wrap={compact}>due {fmtTime(act.ts)}</Sub>
      </>
    );
  }
  const lr = job.last_run;
  if (!lr) {
    return <span style={SECONDARY}>— no runs yet</span>;
  }
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={outcomeTone(lr.label)} label={lr.label} />
        {job.failure_streak > 0 ? (
          <StatusChip tone="fail" label={`streak ×${job.failure_streak}`} />
        ) : null}
      </div>
      <Sub wrap={compact}>{fmtTime(lr.ts)}</Sub>
    </>
  );
}

function DaySummary({ job }: { job: JobPayload }) {
  if (job.kind === "agent") {
    const a = job.activity_24h;
    if (!a || !a.dues) return <>—</>;
    return (
      <>
        {a.dues} dues · {a.acked} acked
        {a.overdue ? (
          <>
            {" · "}
            <span style={{ color: "var(--wb-status-hard-gate-text)" }}>overdue</span>
          </>
        ) : null}
      </>
    );
  }
  return <>{job.runs_24h.total ? `${job.runs_24h.ok} ok · ${job.runs_24h.failed} failed` : "—"}</>;
}

const TH_CLASS =
  "px-3 text-left text-xs font-semibold tracking-[0.06em] uppercase";
const TH_STYLE = {
  color: "var(--wb-content-secondary)",
  borderBottom: "1px solid var(--wb-border-strong)",
} as const;
const TD_STYLE = {
  color: "var(--wb-content-primary)",
  borderBottom: "1px solid var(--wb-border-default)",
} as const;

export function Jobs({
  jobs,
  navigate,
  compact,
  searchText,
}: {
  jobs: JobsPayload | null;
  navigate: (hash: string) => void;
  compact: boolean;
  /** The TopBar search text (ViewProps, shell-owned).
   *  No served search exists, so the faithful form is
   *  client-side filtering over the served list — by job
   *  id and owner, the list's identifying text. */
  searchText: string;
}) {
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  if (!jobs) {
    return (
      <Card title="Jobs">
        <EmptyState message="Loading…" />
      </Card>
    );
  }
  const all = jobs.jobs;
  const query = searchText.trim().toLowerCase();
  const filtered = all.filter(
    (j) =>
      (kindFilter === "all" || j.kind === kindFilter) &&
      (query === "" ||
        j.id.toLowerCase().includes(query) ||
        (j.owner ?? "").toLowerCase().includes(query)),
  );

  const open = (id: string) => navigate(`#/scheduler/jobs/${encodeURIComponent(id)}`);

  return (
    <Card title="Jobs">
      <div className="mb-2">
        <SegmentedControl<KindFilter>
          ariaLabel="Filter jobs by kind"
          options={[
            { value: "all", label: "All" },
            { value: "scripted", label: "Scripted" },
            { value: "agent", label: "Agent" },
          ]}
          value={kindFilter}
          onChange={setKindFilter}
        />
      </div>
      <table className="w-full border-collapse text-sm" aria-label="Jobs">
        <thead>
          <tr>
            <th scope="col" className={TH_CLASS} style={TH_STYLE}>
              Job
            </th>
            {!compact ? (
              <>
                <th scope="col" className={TH_CLASS} style={TH_STYLE}>
                  Kind
                </th>
                <th scope="col" className={TH_CLASS} style={TH_STYLE}>
                  Cadence
                </th>
              </>
            ) : null}
            <th scope="col" className={TH_CLASS} style={TH_STYLE}>
              Last outcome
            </th>
            {!compact ? (
              <>
                <th scope="col" className={TH_CLASS} style={TH_STYLE}>
                  24h
                </th>
                <th scope="col" className={TH_CLASS} style={TH_STYLE}>
                  Next due
                </th>
              </>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {filtered.map((j) => (
            <tr
              key={j.id}
              role="link"
              aria-label={`Open job ${j.id}`}
              onClick={() => open(j.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  open(j.id);
                }
              }}
              tabIndex={0}
              className="cursor-pointer hover:bg-(--wb-surface-1) focus-visible:outline-2 focus-visible:outline-(--wb-focus-ring)"
            >
              <td className="px-3 py-2 align-top" style={TD_STYLE}>
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <strong
                    className={compact ? "[overflow-wrap:anywhere]" : undefined}
                  >
                    {j.id}
                  </strong>
                  {j.status === "suspended" ? (
                    <StatusChip tone="idle" label="suspended" />
                  ) : null}
                </div>
                {j.owner && j.owner.toLowerCase() !== "none" ? (
                  <Sub wrap={compact}>{j.owner}</Sub>
                ) : null}
                {compact ? (
                  <Sub wrap={compact}>
                    {j.cadence_label} · next {j.next_due ? fmtTime(j.next_due) : "—"}
                  </Sub>
                ) : null}
              </td>
              {!compact ? (
                <>
                  <td className="px-3 py-2 align-top" style={TD_STYLE}>
                    <StatusChip
                      tone={j.kind === "agent" ? "info" : "idle"}
                      label={j.kind}
                    />
                  </td>
                  <td className="num px-3 py-2 align-top" style={TD_STYLE}>
                    {j.cadence_label}
                    <Sub>{j.timezone}</Sub>
                  </td>
                </>
              ) : null}
              <td className="px-3 py-2 align-top" style={TD_STYLE}>
                <LastOutcome job={j} compact={compact} />
              </td>
              {!compact ? (
                <>
                  <td className="num px-3 py-2 align-top" style={TD_STYLE}>
                    <DaySummary job={j} />
                  </td>
                  <td className="num px-3 py-2 align-top" style={TD_STYLE}>
                    {j.next_due ? (
                      <>
                        {fmtTime(j.next_due)}
                        <Sub>in {fmtDur(j.next_due_in_secs)}</Sub>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                </>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
      {filtered.length === 0 ? (
        <div className="mt-3">
          <EmptyState
            message={
              query !== "" ? "No jobs match the search." : "No jobs of this kind."
            }
          />
        </div>
      ) : null}
    </Card>
  );
}
