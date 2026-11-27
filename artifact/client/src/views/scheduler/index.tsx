// Scheduler view mount — the shell's contract surface for
// the Scheduler app (INTEGRATION.md §2). Subroutes, from
// the restored original's inventory (client/pages/
// scheduler/RESTORE-NOTES.md, V-1…V-5):
//
//   /              Overview (stat cards, Failing now,
//                  Recent activity)
//   /jobs          Jobs (kind filter, outcome table)
//   /jobs/<id>     Job detail (facts, runs / activity)
//   /pings         Pings (waiting cards, oldest first)
//   /ledger        Ledger (the storyboard's full view over
//                  the same getLedger call)
//
// The component carries V-0, the original's persistent
// semantics, around whichever view the subroute names:
// the 30 s snapshot poll with its failure ladder (bridge
// down distinct from server down, down only after 2
// consecutive failures, last-good rendered dimmed with
// its age stated), the status/freshness/count pills the
// ribbon carried (the shell contract gives views no
// chrome slot for them, so they surface here, at the top
// of the view), and the nav badges (Jobs = registry
// total; Pings hot = waiting count).
//
// Standing exclusion (RESTORE-NOTES X-3): NO Enabled
// switch and NO Run now / Disable controls anywhere in
// these views — the storyboard shows them, but no backing
// server verb exists; the original client is read-only by
// design and saveJobConfig is not wired in on the
// client's own initiative.

import { useEffect, type ReactNode } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { NoticeRow } from "@workhorse/kit/components/display/GroupedList";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import type { AppViewModule, ViewProps } from "../../lib/view-contract";
import { JobDetail } from "./JobDetail";
import { Jobs } from "./Jobs";
import { Ledger } from "./Ledger";
import { Overview } from "./Overview";
import { Pings } from "./Pings";
import { useMaxWidth, useNow, useSchedulerPortions } from "./hooks";
import {
  DOWN_AFTER,
  STALE_MS,
  fmtDur,
  type FailureKind,
  type OverviewPayload,
} from "./model";
import { schedulerMeta } from "./meta";

type SchedRoute =
  | { name: "overview" }
  | { name: "jobs" }
  | { name: "job"; id: string }
  | { name: "pings" }
  | { name: "ledger" };

function parseSubroute(subroute: string): SchedRoute {
  if (subroute === "/jobs") return { name: "jobs" };
  if (subroute.startsWith("/jobs/")) {
    const id = decodeURIComponent(subroute.slice("/jobs/".length));
    return id ? { name: "job", id } : { name: "jobs" };
  }
  if (subroute === "/pings") return { name: "pings" };
  if (subroute === "/ledger") return { name: "ledger" };
  return { name: "overview" };
}

/* ---------------- V-0 · the status strip ----------------
 * The ribbon's pills (app.js renderRibbon()), surfaced at
 * the top of the view: status, freshness, counts — and
 * the ribbon's Refresh. At ≤720px the wake-ups and pid
 * pills shed, as the original's compact ribbon did. */

function StatusStrip({
  overview,
  fetchedAt,
  failures,
  now,
  compact,
  onRefresh,
}: {
  overview: OverviewPayload | null;
  fetchedAt: number | null;
  failures: number;
  now: number;
  compact: boolean;
  onRefresh: () => void;
}) {
  const down = failures >= DOWN_AFTER;
  const o = overview;
  const ageSecs = fetchedAt ? Math.round((now - fetchedAt) / 1000) : null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {!o ? (
        <StatusChip tone="idle" label="connecting…" />
      ) : down ? (
        <StatusChip tone="fail" label="UNREACHABLE" />
      ) : o && o.status === "ok" ? (
        <StatusChip tone="ok" label="server OK" />
      ) : o ? (
        <StatusChip tone="warn" label={o.status} />
      ) : null}

      {o && ageSecs != null ? (
        <StatusChip
          tone={ageSecs * 1000 > STALE_MS ? "warn" : "idle"}
          label={ageSecs < 5 ? "data just now" : `data ${fmtDur(ageSecs)} old`}
        />
      ) : null}

      {o ? (
        <>
          <span className="num text-sm" style={{ color: "var(--ui-content-secondary)" }}>
            {o.registry.total} jobs · {o.outbox.depth} pending pings
          </span>
          {!compact ? (
            <>
              <span
                className="num text-sm"
                style={{ color: "var(--ui-content-secondary)" }}
              >
                ≈{o.expected_wake_per_day} wake-ups/day
              </span>
              <span
                className="num text-sm"
                style={{ color: "var(--ui-content-muted)" }}
              >
                pid {o.pid} · up {fmtDur(o.uptime_secs)}
              </span>
            </>
          ) : null}
        </>
      ) : null}

      <span className="ml-auto">
        <Button variant="secondary" onClick={onRefresh}>
          Refresh
        </Button>
      </span>
    </div>
  );
}

/* ---------------- V-0 · the banner ladder ----------------
 * app.js banners(), in its order: the down banners (only
 * after DOWN_AFTER consecutive failures), the one-failure
 * amber, then — never while down — registry-degraded and
 * aged-pings. The kit form is the GroupedList family's
 * NoticeRow ("kit-first from the scheduler storyboard"). */

function Banners({
  overview,
  lastGoodAt,
  failures,
  failureKind,
  now,
}: {
  overview: OverviewPayload | null;
  lastGoodAt: number | null;
  failures: number;
  failureKind: FailureKind | null;
  now: number;
}) {
  const out: ReactNode[] = [];
  const down = failures >= DOWN_AFTER;
  const lastGood = lastGoodAt
    ? ` Showing the last good data, ${fmtDur(Math.round((now - lastGoodAt) / 1000))} old.`
    : "";

  if (down && failureKind === "bridge") {
    out.push(
      <NoticeRow key="bridge" tone="fail" title="Bridge unreachable.">
        {lastGood}
      </NoticeRow>,
    );
  } else if (down) {
    out.push(
      <NoticeRow key="server" tone="fail" title="Scheduler server unreachable">
        after {failures} failed checks.{lastGood}
      </NoticeRow>,
    );
  } else if (lastGoodAt && failures === 1) {
    out.push(
      <NoticeRow key="watching">
        One check just failed — watching.
      </NoticeRow>,
    );
  }

  const o = overview;
  if (o && !down) {
    if (o.registry_errors?.length) {
      out.push(
        <NoticeRow key="registry" title="Registry degraded:">
          {o.registry_errors.length} entr
          {o.registry_errors.length === 1 ? "y" : "ies"} failed to parse; the
          last-good registry keeps running.
        </NoticeRow>,
      );
    }
    if (o.outbox.aged > 0) {
      out.push(
        <NoticeRow key="aged" title={`${o.outbox.aged} ping(s)`}>
          waiting past the ack timeout.
        </NoticeRow>,
      );
    }
  }

  return out.length > 0 ? <div>{out}</div> : null;
}

/* ---------------- the mount ---------------- */

function Component({ subroute, navigate, onBadges, searchText }: ViewProps) {
  const route = parseSubroute(subroute);
  const jobId = route.name === "job" ? route.id : null;
  const portions = useSchedulerPortions(jobId);
  const now = useNow(5000);
  const compact = useMaxWidth(720);

  const { overview, jobs, pings, ledger } = portions;
  const failures = portions.failures;
  const failureKind = portions.failureKind;
  const down = failures >= DOWN_AFTER;
  const anyData = overview.data ?? jobs.data ?? pings.data ?? ledger.data;
  const lastGoodAt =
    Math.max(
      overview.fetchedAt ?? 0,
      jobs.fetchedAt ?? 0,
      pings.fetchedAt ?? 0,
      ledger.fetchedAt ?? 0,
    ) || null;

  useEffect(() => {
    const o = overview.data;
    if (o) {
      onBadges({
        jobs: { count: o.registry.total },
        pings: { count: o.outbox.depth, hot: o.outbox.depth > 0 },
      });
    }
  }, [overview.data, onBadges]);

  let body: ReactNode;
  if (!anyData) {
    body = down ? (
      <EmptyState
        message="The scheduler server has not answered yet."
      />
    ) : (
      <EmptyState message="Loading…" />
    );
  } else {
    const view =
      route.name === "jobs" ? (
        <Jobs
          jobs={jobs.data}
          navigate={navigate}
          compact={compact}
          searchText={searchText}
        />
      ) : route.name === "job" ? (
        <JobDetail
          jobs={jobs.data}
          jobDetail={portions.jobDetail}
          jobId={route.id}
        />
      ) : route.name === "pings" ? (
        <Pings pings={pings.data} skewMs={pings.skewMs} now={now} />
      ) : route.name === "ledger" ? (
        <Ledger />
      ) : (
        <Overview
          overview={overview.data}
          jobs={jobs.data}
          ledger={ledger.data}
        />
      );
    const ageMs = lastGoodAt ? now - lastGoodAt : 0;
    body = down ? (
      <div style={{ opacity: ageMs > 3_600_000 ? 0.25 : 0.45 }}>{view}</div>
    ) : (
      view
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <StatusStrip
        overview={overview.data}
        fetchedAt={overview.fetchedAt}
        failures={failures}
        now={now}
        compact={compact}
        onRefresh={portions.refetchAll}
      />
      <Banners
        overview={overview.data}
        lastGoodAt={lastGoodAt}
        failures={failures}
        failureKind={failureKind}
        now={now}
      />
      {body}
    </div>
  );
}

// The mount assembles from ./meta (the shell-facing
// half — nav, active key, search declaration, crumb —
// which the shell imports statically for its chrome)
// and this module's Component. The shell loads this
// module lazily, as the scheduler chunk of the one
// bundle (per-view split; src/App.tsx holds the seam).
export const schedulerView: AppViewModule = {
  ...schedulerMeta,
  Component,
};
