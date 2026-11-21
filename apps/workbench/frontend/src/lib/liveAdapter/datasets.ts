// Live adapter datasets + project diff + worktrees:
// the dataset SQL engine route (with the served-
// snapshot fallback), the served/computed project
// diff, and worktree detail.

import { runDatasetSql } from "../datasetSql";
import {
  computeDiff,
  flattenRepoFiles,
  normalizeServedDiff,
} from "../diffModel";
import type { DatasetSqlResult } from "../seam";
import type { DiffMode, ProjectDiff, WorktreeDetail } from "../types";
import type { LiveHost } from "./host";
import { findFileInTree } from "./shared";


export async function datasetSql(h: LiveHost, repoSlug: string, path: string, sql: string): Promise<DatasetSqlResult> {
  // The engine route first (POST /api/projects/code/{slug}/
  // dataset/sql — the repos POST dispatch runs
  // run_dataset_sql server-side); a refused or
  // unreachable route falls back to the same engine
  // over the served snapshot, labelled as such. In the
  // frame form the postRepoDatasetSql action carries
  // the same call over the relay, with the same
  // fallback on refusal or unreachability.
  type SqlPayload = {
    columns?: string[];
    rows?: unknown[][];
    error?: string;
  };
  try {
    let payload: SqlPayload | null = null;
    if (h.channel) {
      const env = await h.channel("postRepoDatasetSql", {
        repoId: repoSlug,
        path,
        sql,
      });
      if (env.status >= 200 && env.status < 300) {
        payload = env.payload as SqlPayload;
      }
    } else {
      const res = await fetch(h.url(`/api/projects/code/${encodeURIComponent(repoSlug)}/dataset/sql`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, sql }),
      });
      if (res.ok) {
        payload = (await res.json()) as SqlPayload;
      }
    }
    if (payload) {
      if (payload.error) return { ok: false, reason: payload.error };
      if (Array.isArray(payload.columns) && Array.isArray(payload.rows)) {
        return {
          ok: true,
          table: {
            name: "sql",
            columns: payload.columns,
            rows: payload.rows.map((r) => r.map((c) => String(c ?? ""))),
          },
          source: "engine",
        };
      }
    }
  } catch {
    // fall through to the snapshot engine
  }
  const repo = h.s.repoList.find((r) => r.slug === repoSlug);
  const file = repo ? findFileInTree(repo.files, path) : undefined;
  if (!file?.dataset) return { ok: false, reason: `No dataset is served for ${path}.` };
  const out = runDatasetSql(file.dataset.tables, sql);
  if (!out.ok) return out;
  return { ok: true, table: out.table, source: "snapshot" };
}

export function projectDiff(h: LiveHost, repoSlug: string, mode: DiffMode): ProjectDiff {
  const feed = h.doc.projectFeeds[repoSlug];
  const served = feed ? normalizeServedDiff(feed.diff, mode) : null;
  const repo = h.s.repoList.find((r) => r.slug === repoSlug);
  if (!repo) {
    return served ?? { mode, label: mode, files: [], note: `Unknown repo: ${repoSlug}` };
  }
  if (mode === "working" && served) return served;
  const computed = computeDiff(repo.files, mode);
  if (mode === "uncommitted" && served && !computed.staged?.length && !computed.unstaged?.length) {
    return {
      ...served,
      note: "The snapshot carries the working diff; the staged / unstaged split rides the /diff route at the serving shell.",
    };
  }
  return computed;
}

export function worktreeDetail(h: LiveHost, repoSlug: string, path: string): WorktreeDetail | undefined {
  const repo = h.s.repoList.find((r) => r.slug === repoSlug);
  const w = repo?.worktrees.find((x) => x.path === path);
  if (!repo || !w) return undefined;
  const changedFiles = flattenRepoFiles(repo.files)
    .filter(({ file }) => file.classification === "untracked" || file.headContent !== undefined)
    .map(({ path: p }) => p);
  const feed = h.doc.projectFeeds[repoSlug];
  const served = (feed?.worktrees?.worktrees ?? []).find(
    (x) => (x as { path?: string }).path === path,
  ) as { active?: { title?: string } | string } | undefined;
  const activePlan =
    typeof served?.active === "string"
      ? served.active
      : served?.active?.title;
  return {
    label: w.label,
    path: w.path,
    branch: w.branch,
    dirty: w.dirty,
    activePlan,
    changedFiles: w.branch === repo.branch ? changedFiles : [],
  };
}
