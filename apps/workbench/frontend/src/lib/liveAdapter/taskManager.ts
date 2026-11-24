// Live adapter Task Manager read: the load monitor's
// snapshot as served by GET /api/task-manager. The
// backend serves the shape ready (fresh rows, or honest
// absence — stamp, stale: true, empty lists — when the
// snapshot is stale); this client only fetches and
// hands the served shape on, in the documents.ts form.
// No channel action exists for this route, so the fetch
// form is the only form.

import type { LiveHost } from "./host";

export interface TaskManagerProcess {
  pid: number;
  ppid: number;
  cpu_pct: number;
  mem_pct: number;
  elapsed_s: number;
  argv: string[];
  cwd: string;
  repo: string | null;
  thread: string | null;
}

export interface TaskManagerMem {
  total_kb: number;
  available_kb: number;
  used_kb: number;
}

export interface TaskManagerVenue {
  kind: string;
  name: string;
  live: boolean;
  in_flight: number | null;
}

export interface TaskManagerJob {
  id: string;
  title: string;
  state: string;
}

export interface TaskManagerSnapshot {
  stamp: string | null;
  stale: boolean;
  load: [number, number, number] | null;
  cpus: number | null;
  mem: TaskManagerMem | null;
  processes: TaskManagerProcess[];
  venues: TaskManagerVenue[];
  jobs: TaskManagerJob[];
}

export type TaskManagerResult =
  | { ok: true; snapshot: TaskManagerSnapshot }
  | { ok: false; reason: string };

export async function taskManager(h: LiveHost): Promise<TaskManagerResult> {
  let res: Response;
  try {
    res = await fetch(h.url("/api/task-manager"));
  } catch {
    return {
      ok: false,
      reason:
        "The snapshot could not be fetched — the Task Manager feed did not answer. Nothing was rendered.",
    };
  }
  if (!res.ok) {
    let reason = "";
    try {
      const payload = (await res.json()) as { error?: string };
      reason = payload.error ?? "";
    } catch {
      reason = "";
    }
    return {
      ok: false,
      reason: reason || `The Task Manager feed refused this snapshot (status ${res.status}).`,
    };
  }
  const snapshot = (await res.json()) as TaskManagerSnapshot;
  return { ok: true, snapshot };
}
