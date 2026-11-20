// Runner state — the panel's portion-poll machinery
// (poll.js) in the one client: every state portion loads,
// fails and retries on its own cadence; a section renders
// the moment its portion lands; a failed refresh after a
// successful load keeps the last data, labeled with its age
// (never stale-as-live); a portion that has never loaded
// shows its own error with a retry. The degraded state is
// only the everything-down state.
//
// react-query carries the panel semantics: a query whose
// fetcher throws keeps its previous data and records the
// error (last-good at read time, INTEGRATION.md §3), and
// refetchInterval is the portion's cadence. The panel's
// fetchers throw on any non-2xx answer and on the bridge's
// status-0 transport shape alike, so a query error is
// exactly "this portion is not answering" — status 0 is
// never rendered as data.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/actions";
import {
  PART_CADENCE,
  type BudgetPayload,
  type GrantPayload,
  type ListenersPayload,
  type OrphansPayload,
  type OutboxPayload,
  type RawEnvelope,
  type RecordsPayload,
  type SpecsPayload,
} from "./model";

export interface PartState<T> {
  data: T | null;
  /** When the portion last landed (ms epoch); null = never. */
  loadedAt: number | null;
  /** The latest poll of this portion failed. */
  failed: boolean;
}

export type PartName =
  | "records"
  | "specs"
  | "budget"
  | "grant"
  | "orphans"
  | "listeners"
  | "logs";

export interface RunnerParts {
  records: PartState<RecordsPayload>;
  specs: PartState<SpecsPayload>;
  budget: PartState<BudgetPayload>;
  grant: PartState<GrantPayload>;
  orphans: PartState<OrphansPayload>;
  listeners: PartState<ListenersPayload>;
  logs: PartState<OutboxPayload>;
}

export interface RunnerContextValue {
  parts: RunnerParts;
  /** Every portion failed and none has ever loaded. */
  allDown: boolean;
  /** Every portion's latest poll failed (last-good may exist). */
  allFailed: boolean;
  /** A 15s tick for countdown / age text (the panel's text
   *  is minute-granular; its 1s ticker changes no word). */
  now: number;
  notice: string | null;
  setNotice: (msg: string | null) => void;
  /** The panel's act(): clear the notice, run, surface any
   *  error as the notice, then force-poll everything. */
  act: (fn: () => Promise<void>) => Promise<void>;
  /** In-flight action labels by key (the panel's actBusy). */
  busy: Record<string, string>;
  setBusy: (key: string, label: string | null) => void;
  refetchPart: (name: PartName) => void;
  refetchAll: () => void;
  restartServer: () => Promise<void>;
}

const RunnerContext = createContext<RunnerContextValue | null>(null);

export function useRunner(): RunnerContextValue {
  const ctx = useContext(RunnerContext);
  if (!ctx) throw new Error("useRunner outside RunnerProvider");
  return ctx;
}

function errorText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

/** The panel's api() semantics over the action envelope:
 *  2xx answers the payload verbatim; anything else throws
 *  with the server's error text (the bridge diagnosis on
 *  status 0). */
export async function callApi<T>(
  fn: () => Promise<RawEnvelope>,
): Promise<T> {
  let env: RawEnvelope;
  try {
    env = await fn();
  } catch (e) {
    throw new Error(errorText(e));
  }
  if (env.status >= 200 && env.status < 300) return env.payload as T;
  throw new Error(env.error || `HTTP ${env.status}`);
}

/** The panel's apiResult() semantics: adopt and shorten
 *  answer a core refusal as 409 with the verdict JSON in
 *  the body — the parsed body returns on 200 and 409
 *  alike; only a request error or an unreachable core
 *  throws, with the server's error text. */
export async function callVerdict(
  fn: () => Promise<RawEnvelope>,
): Promise<Record<string, unknown>> {
  let env: RawEnvelope;
  try {
    env = await fn();
  } catch (e) {
    throw new Error(errorText(e));
  }
  if (env.status === 200 || env.status === 409) {
    return (env.payload ?? {}) as Record<string, unknown>;
  }
  throw new Error(env.error || `HTTP ${env.status}`);
}

function partOf<T>(
  query: { data: T | undefined; dataUpdatedAt: number; isError: boolean },
): PartState<T> {
  return {
    data: query.data ?? null,
    loadedAt: query.dataUpdatedAt > 0 ? query.dataUpdatedAt : null,
    failed: query.isError,
  };
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function RunnerProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusyState] = useState<Record<string, string>>({});
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(id);
  }, []);

  const queryOpts = { retry: false as const };
  const recordsQ = useQuery({
    ...queryOpts,
    queryKey: ["runner", "records"],
    queryFn: () =>
      callApi<RecordsPayload>(() => api.getStatePart({ part: "records" })),
    refetchInterval: PART_CADENCE.records,
  });
  const specsQ = useQuery({
    ...queryOpts,
    queryKey: ["runner", "specs"],
    queryFn: () => callApi<SpecsPayload>(() => api.getStatePart({ part: "specs" })),
    refetchInterval: PART_CADENCE.specs,
  });
  const budgetQ = useQuery({
    ...queryOpts,
    queryKey: ["runner", "budget"],
    queryFn: () =>
      callApi<BudgetPayload>(() => api.getStatePart({ part: "budget" })),
    refetchInterval: PART_CADENCE.budget,
  });
  const grantQ = useQuery({
    ...queryOpts,
    queryKey: ["runner", "grant"],
    queryFn: () => callApi<GrantPayload>(() => api.getStatePart({ part: "grant" })),
    refetchInterval: PART_CADENCE.grant,
  });
  const orphansQ = useQuery({
    ...queryOpts,
    queryKey: ["runner", "orphans"],
    queryFn: () =>
      callApi<OrphansPayload>(() => api.getStatePart({ part: "orphans" })),
    refetchInterval: PART_CADENCE.orphans,
  });
  const listenersQ = useQuery({
    ...queryOpts,
    queryKey: ["runner", "listeners"],
    queryFn: () =>
      callApi<ListenersPayload>(() => api.getStatePart({ part: "listeners" })),
    refetchInterval: PART_CADENCE.listeners,
  });
  const logsQ = useQuery({
    ...queryOpts,
    queryKey: ["runner", "logs"],
    queryFn: () => callApi<OutboxPayload>(() => api.getLeaseOutbox({ after: 0 })),
    refetchInterval: PART_CADENCE.logs,
  });

  const parts: RunnerParts = useMemo(
    () => ({
      records: partOf(recordsQ),
      specs: partOf(specsQ),
      budget: partOf(budgetQ),
      grant: partOf(grantQ),
      orphans: partOf(orphansQ),
      listeners: partOf(listenersQ),
      logs: partOf(logsQ),
    }),
    [
      recordsQ.data,
      recordsQ.dataUpdatedAt,
      recordsQ.isError,
      specsQ.data,
      specsQ.dataUpdatedAt,
      specsQ.isError,
      budgetQ.data,
      budgetQ.dataUpdatedAt,
      budgetQ.isError,
      grantQ.data,
      grantQ.dataUpdatedAt,
      grantQ.isError,
      orphansQ.data,
      orphansQ.dataUpdatedAt,
      orphansQ.isError,
      listenersQ.data,
      listenersQ.dataUpdatedAt,
      listenersQ.isError,
      logsQ.data,
      logsQ.dataUpdatedAt,
      logsQ.isError,
    ],
  );

  const allDown = useMemo(() => {
    const all = Object.values(parts);
    return all.every((p) => p.failed) && all.every((p) => p.loadedAt == null);
  }, [parts]);

  const allFailed = useMemo(
    () => Object.values(parts).every((p) => p.failed),
    [parts],
  );

  const refetchPart = useCallback(
    (name: PartName) => {
      void queryClient.refetchQueries({ queryKey: ["runner", name] });
    },
    [queryClient],
  );

  const refetchAll = useCallback(() => {
    void queryClient.refetchQueries({ queryKey: ["runner"] });
  }, [queryClient]);

  const act = useCallback(
    async (fn: () => Promise<void>) => {
      setNotice(null);
      try {
        await fn();
      } catch (e) {
        setNotice(errorText(e));
      } finally {
        await queryClient.refetchQueries({ queryKey: ["runner"] });
      }
    },
    [queryClient],
  );

  const setBusy = useCallback((key: string, label: string | null) => {
    setBusyState((prev) => {
      if (label == null) {
        if (!(key in prev)) return prev;
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: label };
    });
  }, []);

  // Restart stops the very server answering, so a failed
  // POST is not fatal: what matters is the server coming
  // back. Poll until a portion answers (panel: 20 × 1.5s).
  const restartInFlight = useRef(false);
  const restartServer = useCallback(async () => {
    if (restartInFlight.current) return;
    restartInFlight.current = true;
    setBusy("restart", "Restarting…");
    try {
      await callApi(() => api.restartServer({})).catch(() => {});
      for (let i = 0; i < 20; i++) {
        await sleep(1500);
        try {
          // A portion answering is the server being back.
          await callApi(() => api.getStatePart({ part: "records" }));
          break;
        } catch {
          /* not back yet */
        }
      }
      void queryClient.refetchQueries({ queryKey: ["runner"] });
    } finally {
      restartInFlight.current = false;
      setBusy("restart", null);
    }
  }, [queryClient, setBusy]);

  const value: RunnerContextValue = {
    parts,
    allDown,
    allFailed,
    now,
    notice,
    setNotice,
    act,
    busy,
    setBusy,
    refetchPart,
    refetchAll,
    restartServer,
  };

  return <RunnerContext.Provider value={value}>{children}</RunnerContext.Provider>;
}
