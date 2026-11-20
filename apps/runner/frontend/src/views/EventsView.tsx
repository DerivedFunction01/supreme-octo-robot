import { Fragment, useState } from "react";
import { Zap } from "lucide-react";
import type { EventKind, EventView, Snapshot } from "../venue/types";
import { GroupLabel, GroupedList, PickerChips } from "../components/ui";
import { EmptyState } from "@workhorse/kit/components/EmptyState";
import {
  LogRow,
  LogRowDrawer,
  type LogRowEntry,
} from "@workhorse/kit/components/LogRow";

type Filter = "all" | EventKind;

/** The served EventView is already the kit LogRow's entry
 *  shape; this only re-keys the entity for the component
 *  (the session id stays view-side for routing). */
function toEntry(e: EventView): LogRowEntry {
  return {
    dateToken: e.dateToken,
    time: e.time,
    headline: e.headline,
    kind: { label: e.kindLabel, tone: e.tone },
    meta: e.meta,
    detail: {
      message: e.detail.message,
      facts: e.detail.facts,
      ...(e.detail.entity
        ? {
            entity: {
              groupLabel: e.detail.entity.groupLabel,
              title: e.detail.entity.title,
              sub: e.detail.entity.sub,
            },
          }
        : {}),
    },
  };
}

/** Frame 5 — Events: kind filter chips + the TopBar text filter
 *  both work against the store's event stream. Rows are the
 *  kit's one LogRow (timeline-component study, Variant B);
 *  a row opens its drawer: full message, served facts, and
 *  the routing row for the lease the message names.
 *  V8 (logs depth): the Budget filter chip rides the served
 *  category (the panel's logCategory over the outbox
 *  vocabulary — budget events are their own category, not a
 *  kind), the timeline groups by the served day, and each
 *  entry carries a raw-record expansion: the record's JSON,
 *  served pretty-printed, rendered verbatim. */
export function EventsView({
  snap,
  query,
  onOpenSession,
}: {
  snap: Snapshot;
  query: string;
  onOpenSession?: (session: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [rawId, setRawId] = useState<string | null>(null);
  const q = query.trim().toLowerCase();
  const events = snap.events.filter(
    (e) =>
      (filter === "all" ||
        (filter === "budget" ? e.category === "budget" : e.kind === filter)) &&
      (!q ||
        e.message.toLowerCase().includes(q) ||
        e.headline.toLowerCase().includes(q)),
  );
  // Day groups over the served day key, in stream order.
  const groups: { key: string; label: string; events: EventView[] }[] = [];
  for (const e of events) {
    const g = groups.find((g) => g.key === e.dayKey);
    if (g) g.events.push(e);
    else groups.push({ key: e.dayKey, label: e.dayLabel, events: [e] });
  }
  const open = snap.events.find((e) => e.id === openId) ?? null;
  return (
    <>
      <h2 className="rn-largetitle">Events</h2>
      <p className="rn-subtitle">Lease and run events · live</p>
      <div style={{ marginBottom: 16 }}>
        <PickerChips
          ariaLabel="Event kind filter"
          value={filter}
          onChange={(v) => setFilter(v as Filter)}
          options={[
            { value: "all", label: "All" },
            { value: "lease", label: "Leases" },
            { value: "run", label: "Runs" },
            { value: "grant", label: "Grants" },
            { value: "budget", label: "Budget" },
            { value: "error", label: "Errors" },
          ]}
        />
      </div>
      {events.length === 0 ? (
        <EmptyState message="No events match" detail="The venue's lease and run events stream here." />
      ) : (
        groups.map((g) => (
          // Fragment, not a div: a wrapper div makes the
          // day label a :first-child and .rn-glabel's
          // first-child rule zeroes its 20px section
          // margin (spacing audit, 2026-11-15).
          <Fragment key={g.key}>
            <GroupLabel>
              {g.label} · {g.events.length} event{g.events.length === 1 ? "" : "s"}
            </GroupLabel>
            <GroupedList>
              {g.events.map((e) => (
                <div key={e.id}>
                  <LogRow entry={toEntry(e)} onOpen={() => setOpenId(e.id)} />
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-end",
                      padding: "0 14px 8px",
                    }}
                  >
                    <button
                      type="button"
                      className="rn-chip"
                      aria-expanded={rawId === e.id}
                      onClick={() => setRawId(rawId === e.id ? null : e.id)}
                      style={{
                        backgroundColor: "var(--wb-surface-sunken)",
                        color: "var(--wb-content-secondary)",
                        cursor: "pointer",
                      }}
                    >
                      <span className="rn-chip-lab">{rawId === e.id ? "Hide raw" : "Raw record"}</span>
                    </button>
                  </div>
                  {rawId === e.id ? (
                    <pre
                      className="mono"
                      style={{
                        margin: "0 14px 12px",
                        padding: "10px 12px",
                        borderRadius: 8,
                        backgroundColor: "var(--wb-surface-sunken)",
                        color: "var(--wb-content-secondary)",
                        fontSize: 12,
                        lineHeight: 1.5,
                        overflowX: "auto",
                        whiteSpace: "pre",
                      }}
                    >
                      {e.raw}
                    </pre>
                  ) : null}
                </div>
              ))}
            </GroupedList>
          </Fragment>
        ))
      )}
      <LogRowDrawer
        entry={open ? toEntry(open) : null}
        onClose={() => setOpenId(null)}
        onEntityOpen={
          open?.detail.entity && onOpenSession
            ? () => {
                const session = open.detail.entity!.session;
                setOpenId(null);
                onOpenSession(session);
              }
            : undefined
        }
        entityLeading={
          <span
            aria-hidden="true"
            className="flex items-center justify-center"
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              flex: "0 0 30px",
              color: "#fff",
              background:
                "linear-gradient(135deg, var(--wb-okabe-sky-blue), var(--wb-okabe-blue))",
            }}
          >
            <Zap size={16} />
          </span>
        }
      />
    </>
  );
}
