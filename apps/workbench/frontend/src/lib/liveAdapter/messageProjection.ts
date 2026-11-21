// Message projection: a served feed message row in
// the seam's InboxMessage shape — kind and target
// derived from the row's anchor, disposition from its
// lifecycle state.

import type { FeedMessageRow } from "../feeds";
import type { InboxMessage } from "../types";
import { dateLabel } from "./shared";


export function projectMessage(
  row: FeedMessageRow,
  disposition: InboxMessage["disposition"] | undefined,
): InboxMessage {
  const ref = row.anchor_ref ?? "";
  const bundle = ref.split("/")[0];
  let kind: InboxMessage["kind"] = "doctor";
  let target: InboxMessage["target"] = { section: "overview" };
  if (row.anchor_type === "text" || row.anchor_type === "component") {
    if (ref.endsWith("plan.md") || row.anchor_context?.step != null) {
      kind = "plan";
      target = { section: "plans", bundle };
    } else if (row.showcase || row.anchor_type === "component") {
      kind = "mockup";
      target = { section: "mockups", entryId: ref };
    }
  }
  const served =
    row.state === "sent"
      ? null
      : row.state === "acknowledged"
        ? "opened"
        : "filed";
  return {
    id: String(row.id),
    kind,
    title: row.body.split("\n")[0].slice(0, 90) || row.anchor_context?.quote || "(no body)",
    project: row.project_slug ?? "",
    arrivedLabel: dateLabel(row.created_at),
    disposition: disposition !== undefined ? disposition : (served as InboxMessage["disposition"]),
    target,
  };
}
