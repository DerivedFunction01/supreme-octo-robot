// Entry projection: a served feed entry row (+ its
// detail) in the seam's Entry shape — review state
// derived from the served review payloads, the log
// rendered with display labels.

import type { FeedEntryDetail, FeedEntryRow } from "../feeds";
import type { Entry, ReviewState, RuledStatus } from "../types";
import { dateLabel } from "./shared";


/** Registry kinds are exhibit kinds; the seam's EntryKind
 *  is the storyboard's grouping — storyboards read as
 *  docs, every other exhibit kind as a mockup. */
function entryKind(kind: string): Entry["kind"] {
  if (kind === "storyboard") return "doc";
  if (kind === "plan" || kind === "doc") return kind;
  return "mockup";
}

function reviewOf(
  row: FeedEntryRow,
  detail: FeedEntryDetail | undefined,
): { review: ReviewState | null; reviewCount?: number } {
  const latest = detail?.latest_review;
  if (latest?.verb === "review" && latest.new) {
    try {
      const parsed = JSON.parse(latest.new) as { disposition?: string };
      if (parsed.disposition === "approve") return { review: "approved" };
      if (parsed.disposition === "stale") return { review: "stale" };
      if (parsed.disposition === "needs-changes") {
        const count = (detail?.history ?? []).filter((h) => {
          if (h.verb !== "review" || !h.new) return false;
          try {
            return (JSON.parse(h.new) as { disposition?: string }).disposition === "needs-changes";
          } catch {
            return false;
          }
        }).length;
        return { review: "needs-changes", reviewCount: Math.max(1, count) };
      }
    } catch {
      // a review payload that does not parse carries no state
    }
  }
  // The served review queue's own rule: an unexplored
  // entry awaits a ruling; a ruled status (canonical and
  // its kin) has been dispositioned, verified or not.
  if (row.status === "unexplored") {
    return { review: "in-triage" };
  }
  return { review: null };
}

export function projectEntry(
  row: FeedEntryRow,
  detail: FeedEntryDetail | undefined,
  project: string,
): Entry {
  const { review, reviewCount } = reviewOf(row, detail);
  const history = detail?.history ?? [];
  const reviewLog = [...history].reverse().map((h) => {
    let label = h.verb;
    if (h.verb === "review" && h.new) {
      try {
        const parsed = JSON.parse(h.new) as { disposition?: string; comment?: string };
        label = parsed.disposition ?? h.verb;
        if (parsed.comment) label += ` · ${parsed.comment}`;
      } catch {
        label = h.verb;
      }
    } else if (h.note) {
      label += ` · ${h.note}`;
    }
    return { label, when: dateLabel(h.ts), actor: h.actor };
  });
  const approvedBy =
    row.approval?.approved && detail?.latest_review?.verb === "review"
      ? detail.latest_review.actor
      : undefined;
  return {
    id: row.id,
    project,
    kind: entryKind(row.kind),
    title: row.title,
    status: row.status as RuledStatus,
    review,
    reviewCount,
    version: row.version,
    registeredLabel: dateLabel(row.created_at),
    stateHash: row.approval?.current_state_sha256 ?? undefined,
    approvedBy,
    staleNote: row.derived?.stale ? "Stale · served derivation" : undefined,
    reviewLog,
    archived: row.archived,
    files: (detail?.files ?? []).map((f) => ({
      path: f.path,
      isMain: f.is_main,
      sizeLabel: `${f.size_bytes.toLocaleString()} bytes`,
    })),
  };
}
