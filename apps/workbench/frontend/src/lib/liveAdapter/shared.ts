// Shared helpers for the live adapter's projections
// and state builder: display labels for served stamps
// and the repo file-tree walk.

import type { RepoFile } from "../types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];


/** An ISO timestamp -> its "Oct 25"-style display label,
 *  year included. Labels are projections of served stamps. */
export function dateLabel(iso: string | null | undefined): string {
  if (!iso) return "No activity";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

export function findFileInTree(files: RepoFile[], path: string): RepoFile | undefined {
  const parts = path.split("/").filter(Boolean);
  let level = files;
  let found: RepoFile | undefined;
  for (const part of parts) {
    found = level.find((f) => f.name === part);
    if (!found) return undefined;
    level = found.children ?? [];
  }
  return found;
}
