// Mock adapter datasets + project diff + worktrees
// over the seeded store: the SQL engine over the
// served snapshot, the computed diff, worktree
// detail, board done-lane paging, and registry
// tracking updates.

import { runDatasetSql } from "../datasetSql";
import {
  computeDiff,
  flattenRepoFiles,
} from "../diffModel";
import type { BoardCard, DatasetSqlResult } from "../seam";
import type {
  DiffMode,
  ProjectDiff,
  Repo,
  WorktreeDetail,
} from "../types";
import { findFile } from "./helpers";
import type { MockHost } from "./host";


export async function datasetSql(h: MockHost, repoSlug: string, path: string, sql: string): Promise<DatasetSqlResult> {
  const repo = h.repo(repoSlug);
  const file = repo ? findFile(repo.files, path) : undefined;
  if (!repo || !file?.dataset) {
    return { ok: false, reason: `No dataset is served for ${path}.` };
  }
  const out = runDatasetSql(file.dataset.tables, sql);
  if (!out.ok) return out;
  return { ok: true, table: out.table, source: "engine" };
}

export function projectDiff(h: MockHost, repoSlug: string, mode: DiffMode): ProjectDiff {
  const repo = h.repo(repoSlug);
  if (!repo) return { mode, label: mode, files: [], note: `Unknown repo: ${repoSlug}` };
  return computeDiff(repo.files, mode);
}

export function worktreeDetail(h: MockHost, repoSlug: string, path: string): WorktreeDetail | undefined {
  const repo = h.repo(repoSlug);
  const w = repo?.worktrees.find((x) => x.path === path);
  if (!repo || !w) return undefined;
  const changedFiles = flattenRepoFiles(repo.files)
    .filter(
      ({ file }) =>
        (file.headContent !== undefined && file.headContent !== (file.content ?? "")) ||
        file.classification === "untracked",
    )
    .map(({ path: p }) => p);
  const active = h.s.db.plans.find(
    (p) => p.project === repoSlug && p.state === "in-progress" && !p.archived,
  );
  return {
    label: w.label,
    path: w.path,
    branch: w.branch,
    dirty: w.dirty,
    activePlan: w.branch === repo.branch ? active?.title : undefined,
    changedFiles: w.branch === repo.branch ? changedFiles : [],
  };
}

export function boardDone(h: MockHost, offset: number, limit: number): { cards: BoardCard[]; total: number } {
  const done = h.board().filter((c) => c.lane === "done");
  return { cards: done.slice(offset, offset + limit), total: done.length };
}

export async function updateRepoTracking(h: MockHost, slug: string,
    patch: Partial<NonNullable<Repo["tracking"]>> & { name?: string },): Promise<Repo> {
  const r = h.repo(slug);
  if (!r) throw new Error(`unknown repo ${slug}`);
  if (patch.name !== undefined && patch.name.trim()) r.name = patch.name.trim();
  const { name: _name, ...tracking } = patch;
  r.tracking = {
    expected: r.tracking?.expected ?? "",
    pinned: r.tracking?.pinned ?? false,
    ignored: r.tracking?.ignored ?? false,
    notes: r.tracking?.notes ?? "",
    ...tracking,
  };
  h.emit();
  return r;
}
