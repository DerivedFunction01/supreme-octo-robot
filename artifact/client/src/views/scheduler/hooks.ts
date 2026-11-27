// Scheduler views — hooks. The poll machine is the
// original client's poll loop (app.js) carried onto the
// one client's react-query (INTEGRATION.md §1): the four
// snapshot calls run as four independent queries, one per
// portion, so each portion renders when it lands instead
// of waiting for the slowest of the four — but the
// failure ladder is still the snapshot's: `failureCount`
// counts consecutive failed CYCLES (a cycle completes
// when every portion has settled at least once since the
// last counted cycle; a cycle with any portion failed
// counts once, a fully served cycle resets it), the
// first failure in call order names the kind, and each
// query's retained `data` is that portion's last-good.
// The ladder state is module-level in effect — the
// queries' keys are stable across route changes, exactly
// as app.js's module-level state survived them. Entering
// a job route refetches at once (the original refreshed
// on its route change to a job); other route changes
// only re-render.

import { useEffect, useRef, useState } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  POLL_MS,
  SchedulerFailure,
  fetchJobDetail,
  fetchJobs,
  fetchLedgerFeed,
  fetchOverview,
  fetchPings,
  type FailureKind,
  type JobDetailPayload,
  type JobsPayload,
  type LedgerPayload,
  type OverviewPayload,
  type PingsPayload,
  type Portion,
} from "./model";

function portionOf<T extends { served_at: string }>(
  query: UseQueryResult<T>,
): Portion<T> {
  const data = query.data ?? null;
  return {
    data,
    fetchedAt: query.dataUpdatedAt || null,
    skewMs: data
      ? new Date(data.served_at).getTime() - query.dataUpdatedAt
      : 0,
  };
}

const CYCLE_ORDER = ["overview", "jobs", "pings", "ledger"] as const;
type CycleKey = (typeof CYCLE_ORDER)[number];

export interface SchedulerPortions {
  overview: Portion<OverviewPayload>;
  jobs: Portion<JobsPayload>;
  pings: Portion<PingsPayload>;
  ledger: Portion<LedgerPayload>;
  jobDetail: JobDetailPayload | null;
  /** Consecutive failed poll cycles (the ladder). */
  failures: number;
  failureKind: FailureKind | null;
  refetchAll: () => void;
}

export function useSchedulerPortions(jobId: string | null): SchedulerPortions {
  const queryOpts = {
    retry: false,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
  } as const;
  const overviewQ = useQuery({
    ...queryOpts,
    queryKey: ["scheduler", "overview"],
    queryFn: fetchOverview,
  });
  const jobsQ = useQuery({
    ...queryOpts,
    queryKey: ["scheduler", "jobs"],
    queryFn: fetchJobs,
  });
  const pingsQ = useQuery({
    ...queryOpts,
    queryKey: ["scheduler", "pings"],
    queryFn: fetchPings,
  });
  const ledgerQ = useQuery({
    ...queryOpts,
    queryKey: ["scheduler", "ledger", "feed"],
    queryFn: fetchLedgerFeed,
  });
  const detailQ = useQuery({
    ...queryOpts,
    queryKey: ["scheduler", "job", jobId],
    queryFn: () => fetchJobDetail(jobId as string),
    enabled: jobId != null,
  });

  const refetchAllRef = useRef(() => {});
  refetchAllRef.current = () => {
    void overviewQ.refetch();
    void jobsQ.refetch();
    void pingsQ.refetch();
    void ledgerQ.refetch();
    if (jobId != null) void detailQ.refetch();
  };
  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;
  const firstRef = useRef(true);
  useEffect(() => {
    if (firstRef.current) {
      firstRef.current = false;
      return;
    }
    if (jobIdRef.current) refetchAllRef.current();
  }, [jobId]);

  /* The ladder, counted in cycles. Each portion's settle
   * stamp is its latest success/failure timestamp; when
   * every portion's stamp has advanced past the last
   * counted cycle's, the cycle is complete: it failed if
   * any portion's latest settle was a failure (the first
   * in call order names the kind), and it resets the
   * count when all four served. A portion still in flight
   * holds the cycle open — the original's refresh() also
   * waited for all four to settle before it counted. */
  const queries = { overview: overviewQ, jobs: jobsQ, pings: pingsQ, ledger: ledgerQ };
  const stamps: Record<CycleKey, number> = {
    overview: Math.max(overviewQ.dataUpdatedAt, overviewQ.errorUpdatedAt),
    jobs: Math.max(jobsQ.dataUpdatedAt, jobsQ.errorUpdatedAt),
    pings: Math.max(pingsQ.dataUpdatedAt, pingsQ.errorUpdatedAt),
    ledger: Math.max(ledgerQ.dataUpdatedAt, ledgerQ.errorUpdatedAt),
  };
  const countedRef = useRef<Record<CycleKey, number>>({
    overview: 0, jobs: 0, pings: 0, ledger: 0,
  });
  const [ladder, setLadder] = useState<{ failures: number; kind: FailureKind | null }>({
    failures: 0,
    kind: null,
  });
  useEffect(() => {
    const counted = countedRef.current;
    if (!CYCLE_ORDER.every((k) => stamps[k] > counted[k])) return;
    countedRef.current = { ...stamps };
    const firstBad = CYCLE_ORDER.find(
      (k) => queries[k].errorUpdatedAt > queries[k].dataUpdatedAt,
    );
    if (firstBad) {
      const err = queries[firstBad].error;
      setLadder((prev) => ({
        failures: prev.failures + 1,
        kind: err instanceof SchedulerFailure ? err.kind : "bridge",
      }));
    } else {
      setLadder({ failures: 0, kind: null });
    }
  });

  return {
    overview: portionOf(overviewQ),
    jobs: portionOf(jobsQ),
    pings: portionOf(pingsQ),
    ledger: portionOf(ledgerQ),
    jobDetail: detailQ.data ?? null,
    failures: ladder.failures,
    failureKind: ladder.kind,
    refetchAll: () => refetchAllRef.current(),
  };
}

/** A ticking clock for the views' age arithmetic: the
 *  original re-rendered every 5 s between polls so ages
 *  and countdowns stay honest. */
export function useNow(stepMs = 5000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), stepMs);
    return () => clearInterval(timer);
  }, [stepMs]);
  return now;
}

/** Reactive max-width match. The jobs table's compact form
 *  and the status strip's pill shedding ride the original
 *  client's own breakpoint (720px — its stylesheet's
 *  "house table breakpoint"), not the kit's phone seam:
 *  table compaction is the scheduler's behaviour of
 *  record, a data-presentation rule, not a phone variant. */
export function useMaxWidth(px: number): boolean {
  const [matches, setMatches] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia(`(max-width: ${px}px)`).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${px}px)`);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [px]);
  return matches;
}
