// Events — the panel's logs surface (logs.js) on the
// kit's LogRow: the closed eight-kind vocabulary, the
// category filters, the day-grouped timeline (the shipped
// form: timeline, grouped by day, relative time shown,
// compact density — the pick is the form's constants, not
// a user-facing toggle). The form model is pure (model.ts):
// level, category, shape, session and detail text derive
// from the served fields only. A row opens the kit drawer
// with the event's facts; the panel's raw-JSON expander
// becomes the drawer's fact list.

import { useMemo, useState } from "react";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import {
  GroupLabel,
  GroupedList,
} from "@workhorse/kit/components/display/GroupedList";
import {
  LogRow,
  LogRowDrawer,
  type LogRowEntry,
  type LogRowFact,
  type LogRowTone,
} from "@workhorse/kit/components/display/LogRow";
import { SegmentedControl } from "@workhorse/kit/components/controls/SegmentedControl";
import {
  LOG_KINDS,
  fmtAgeAgo,
  fmtClock,
  groupByDay,
  logCaller,
  logCategory,
  logDetailText,
  logLevel,
  logSession,
  logShape,
  specLabel,
  specTitle,
  specById,
  type LogEvent,
  type LogFilter,
  type Spec,
} from "./model";
import { DegradedCard, PartStatus } from "./pickers";
import { useRunner } from "./state";

const FILTER_KEY = "lease-ui-logs-filter";

function loadFilter(): LogFilter {
  try {
    const v = localStorage.getItem(FILTER_KEY);
    if (v === "leases" || v === "grants" || v === "budget" || v === "errors") {
      return v;
    }
  } catch {
    /* defaults */
  }
  return "all";
}

/** The panel's level vocabulary onto the kit LogRow's
 *  tones (error → fail). */
function logTone(ev: LogEvent): LogRowTone {
  const level = logLevel(ev);
  return level === "error" ? "fail" : level;
}

const LEVEL_DOT: Record<string, string> = {
  ok: "var(--wb-okabe-bluish-green)",
  info: "var(--wb-okabe-blue)",
  warn: "var(--wb-okabe-orange)",
  error: "var(--wb-okabe-vermilion)",
};

export function EventsView({ navigate }: { navigate: (hash: string) => void }) {
  const { parts, allDown, now } = useRunner();
  const [filter, setFilter] = useState<LogFilter>(loadFilter);
  const [openSeq, setOpenSeq] = useState<number | null>(null);

  const specs: Spec[] = parts.specs.data?.specs || [];
  const records = parts.records.data?.records || [];
  const allEvents = useMemo(
    () => (parts.logs.data?.events || []).filter((ev) => LOG_KINDS.has(ev.kind)),
    [parts.logs.data],
  );
  const shown = useMemo(
    () =>
      allEvents.filter(
        (ev) =>
          filter === "all" ||
          logCategory(ev) === filter ||
          (filter === "errors" && logLevel(ev) === "error"),
      ),
    [allEvents, filter],
  );
  const groups = useMemo(() => groupByDay(shown, now), [shown, now]);

  const entryFor = (ev: LogEvent): LogRowEntry => {
    const detailText = logDetailText(ev, specs);
    const shape = logShape(ev);
    const session = logSession(ev);
    const caller = logCaller(ev);
    const meta = [
      shape ? specLabel(specs, shape) : null,
      session,
      caller ? `caller ${caller}` : null,
      fmtAgeAgo(ev.ts, now),
    ]
      .filter(Boolean)
      .join(" · ");
    const facts: LogRowFact[] = [
      { label: "Seq", value: String(ev.seq), mono: true },
      { label: "Time", value: fmtClock(ev.ts), mono: true },
      { label: "Kind", value: ev.kind },
    ];
    if (shape) facts.push({ label: "Shape", value: specLabel(specs, shape) });
    if (session) facts.push({ label: "Session", value: session, mono: true });
    if (caller) facts.push({ label: "Caller", value: caller });
    const record = session
      ? records.find((e) => (e.session || e.record?.session || "") === session)
      : undefined;
    return {
      dateToken: new Date(ev.ts).toLocaleDateString([], {
        month: "short",
        day: "numeric",
      }),
      time: fmtClock(ev.ts),
      headline: detailText || ev.kind,
      kind: { label: ev.kind, tone: logTone(ev) },
      meta: meta || undefined,
      detail: {
        message: detailText || ev.kind,
        facts,
        entity:
          session && record
            ? {
                groupLabel: "Session",
                title: (() => {
                  const spec = specById(specs, record.record?.shape);
                  return spec ? specTitle(spec) : session;
                })(),
                sub: session,
              }
            : undefined,
      },
    };
  };

  const openEvent = openSeq == null ? null : shown.find((ev) => ev.seq === openSeq) || null;

  if (allDown) return <DegradedCard />;

  return (
    <div className="flex flex-col gap-4">
      <PartStatus name="logs" part={parts.logs} />
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          ariaLabel="Filter events"
          options={[
            { value: "all", label: "All" },
            { value: "leases", label: "Leases" },
            { value: "grants", label: "Grants" },
            { value: "budget", label: "Budget" },
            { value: "errors", label: "Errors" },
          ]}
          value={filter}
          onChange={(v) => {
            setFilter(v);
            try {
              localStorage.setItem(FILTER_KEY, v);
            } catch {
              /* session only */
            }
          }}
        />
        <span
          className="flex items-center gap-2.5 text-xs"
          style={{ color: "var(--wb-content-secondary)" }}
        >
          {(["ok", "info", "warn", "error"] as const).map((l) => (
            <span key={l} className="flex items-center gap-1">
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: LEVEL_DOT[l] }}
              />
              {l}
            </span>
          ))}
        </span>
      </div>
      {parts.logs.data ? (
        !allEvents.length ? (
          <EmptyState message="No events yet." />
        ) : !shown.length ? (
          <EmptyState message="No events in this filter." />
        ) : (
          <>
            {groups.map((g) => (
              <div key={g.key}>
                <GroupLabel>
                  {g.label} · {g.events.length} event{g.events.length === 1 ? "" : "s"}
                </GroupLabel>
                <GroupedList>
                  {g.events.map((ev) => (
                    <LogRow
                      key={ev.seq}
                      entry={entryFor(ev)}
                      onOpen={() => setOpenSeq(ev.seq)}
                    />
                  ))}
                </GroupedList>
              </div>
            ))}
            <p className="text-xs" style={{ color: "var(--wb-content-muted)" }}>
              Showing {shown.length} of {allEvents.length}
            </p>
          </>
        )
      ) : null}
      <LogRowDrawer
        entry={openEvent ? entryFor(openEvent) : null}
        onClose={() => setOpenSeq(null)}
        onEntityOpen={() => {
          const session = openEvent ? logSession(openEvent) : null;
          if (session) {
            setOpenSeq(null);
            navigate(`#/runner/leases/${encodeURIComponent(session)}`);
          }
        }}
      />
    </div>
  );
}
