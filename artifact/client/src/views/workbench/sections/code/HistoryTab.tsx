// The History tab (absorption plan, step 8): the HEAD
// timeline and the change records from the history feed,
// with the dirty / ahead streaks the feed derives. The
// streaks also ride the repo view's header (same feed,
// same values — the header mounts its own query so the
// two never disagree by construction of the query key).

import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useCheckout } from "./checkoutContext";
import type { RepoHistoryPayload } from "../../lib/api-types-code";
import { formatDateTime, formatRelative, formatShortHash } from "../../lib/format";
import { exposureLabel, publicationLabel } from "../../lib/labels";
import { EmptyWell, ErrorWell, metaStyle, SkeletonWell } from "../shared";

export function HistoryTab({ projectId }: { projectId: string }) {
  const query = useQuery({
    queryKey: ["code-history", projectId],
    queryFn: () => api.getCodeHistory({ projectId }),
  });
  const payload = query.data?.payload as unknown as RepoHistoryPayload | null;

  if (query.isPending) return <SkeletonWell label="the repo history" />;
  if (query.isError || !payload) {
    return (
      <ErrorWell
        section="History"
        message={query.data?.error ?? "the history could not be loaded."}
      />
    );
  }
  const records = [...payload.records].reverse();
  return (
    <div data-anchor="repos/history">
      <p style={{ color: "var(--ui-content-secondary)", fontSize: "var(--ui-font-size-sm)" }}>
        {payload.dirty_since ? (
          <>
            Working tree dirty since {formatDateTime(payload.dirty_since)} (
            {formatRelative(payload.dirty_since)}).{" "}
          </>
        ) : (
          <>The working tree is clean in the recorded history. </>
        )}
        {payload.ahead_since ? (
          <>
            Ahead of the upstream since {formatDateTime(payload.ahead_since)} (
            {formatRelative(payload.ahead_since)}).
          </>
        ) : (
          <>Not ahead of the upstream in the recorded history.</>
        )}
      </p>

      <h3
        style={{
          fontSize: "var(--ui-font-size-base)",
          fontWeight: 600,
          margin: "var(--ui-space-24) 0 var(--ui-space-8)",
        }}
      >
        HEAD timeline
      </h3>
      {payload.timeline.length === 0 ? (
        <EmptyWell>No HEAD movements recorded yet.</EmptyWell>
      ) : (
        <ol
          style={{
            listStyle: "none",
            margin: 0,
            padding: "0 0 0 var(--ui-space-16)",
            borderLeft: "1px solid var(--ui-border-default)",
          }}
        >
          {[...payload.timeline].reverse().map((point) => (
            <li
              key={`${point.ts}:${point.head}`}
              style={{ padding: "var(--ui-space-4) 0 var(--ui-space-4) var(--ui-space-8)" }}
            >
              <span className="mono" style={{ fontSize: "var(--ui-font-size-sm)" }}>
                {formatShortHash(point.head)}
              </span>{" "}
              <span style={metaStyle}>
                {point.branch ?? "detached"} · {formatDateTime(point.ts)} (
                {formatRelative(point.ts)})
              </span>
            </li>
          ))}
        </ol>
      )}

      <h3
        style={{
          fontSize: "var(--ui-font-size-base)",
          fontWeight: 600,
          margin: "var(--ui-space-24) 0 var(--ui-space-8)",
        }}
      >
        Change records — <span className="num">{records.length}</span>
      </h3>
      {records.length === 0 ? (
        <EmptyWell>
          No changes recorded yet.
        </EmptyWell>
      ) : (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            borderTop: "1px solid var(--ui-border-default)",
          }}
        >
          {records.map((record) => (
            <li
              key={`${record.at}:${record.head}`}
              style={{
                display: "flex",
                gap: "var(--ui-space-12)",
                flexWrap: "wrap",
                alignItems: "baseline",
                padding: "var(--ui-space-4) var(--ui-space-8)",
                borderBottom: "1px solid var(--ui-border-default)",
                fontSize: "var(--ui-font-size-sm)",
              }}
            >
              <span style={metaStyle}>{formatDateTime(record.at)}</span>
              <span className="mono" style={metaStyle}>
                {formatShortHash(record.head)}
              </span>
              <span style={{ minWidth: 0, overflowWrap: "anywhere", flex: 1 }}>
                {record.head_subject ?? "—"}
              </span>
              <span style={metaStyle}>
                {record.branch ?? "detached"} ·{" "}
                {record.dirty_total > 0 ? `${record.dirty_total} dirty` : "clean"} ·{" "}
                {publicationLabel(record.publication)} · {exposureLabel(record.exposure_level)}
                {record.exposed_commits != null && record.exposed_commits > 0
                  ? ` (${record.exposed_commits} commits)`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
