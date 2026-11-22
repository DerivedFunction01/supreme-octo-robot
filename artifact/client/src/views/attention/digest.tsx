// Digest — the original's renderDigest(): sections by
// kind, Stalled, Staffing (with escalated-to-Main rows),
// Handlers by topic, and Parked plans, over the digest
// portion. The window line leads; an unreachable digest
// says so plainly.

import { useState, type ReactNode } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Card } from "@workhorse/kit/components/display/Card";
import { DegradedBanner } from "@workhorse/kit/components/display/DegradedBanner";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import { HandlerVerbButton } from "./item-card";
import { day, type DigestPayload } from "./model";
import { api, call, staleText, usePortion } from "./transport";
import { BandHead, PageColumn, ScopeLine, useAttentionUi } from "./ui";

export function DigestView() {
  const ui = useAttentionUi();
  const portion = usePortion<DigestPayload>("digest", () => call(api.getDigest({})), ui.refreshKey);
  // Topic disclosures are controlled: a closed topic's
  // card is not rendered at all (the ReposTrackingPanel's
  // mount-on-demand form). Content left in the DOM under
  // a closed <details> is not painted, but geometry tools
  // still measure its boxes piled over the neighbouring
  // topics — the critic's N-2 overlap pairs at 768.
  const [openTopics, setOpenTopics] = useState<ReadonlySet<string>>(new Set());

  if (!portion.data) {
    return (
      <PageColumn>
        {portion.loading ? (
          <ScopeLine>Loading…</ScopeLine>
        ) : (
          <EmptyState message="The digest is unreachable — nothing is being hidden; this is the whole report." />
        )}
      </PageColumn>
    );
  }

  const d = portion.data;
  const staffing = d.staffing ?? { available: false, reason: "Staffing measure unavailable.", rows: [] };
  const pp = d.parked_plans;
  // The original's `any`: a section present, stalls,
  // staffing rows, or parked plans — else the empty line.
  const any =
    d.sections.length > 0 ||
    d.stalls.length > 0 ||
    staffing.rows.length > 0 ||
    (pp.available && pp.plans.length > 0);

  const handlerLink = (handle: string, label: string) => (
    <Button
      variant="ghost"
      onClick={() => ui.navigate(`#/attention/handlers/${encodeURIComponent(handle)}`)}
    >
      {label}
    </Button>
  );

  return (
    <PageColumn>
      <ScopeLine>
        Next window {d.window.next_at ? day(d.window.next_at) : "—"}
        {staleText(portion.stale)}
      </ScopeLine>

      {d.sections.map((s) => (
        <section key={s.kind_label}>
          <BandHead label={s.kind_label} count={s.rows.length} />
          <ScopeLine>{s.owner_label}</ScopeLine>
          {s.rows.map((row, i) => (
            <Card key={`${row.handle}-${i}`} className="mb-3">
              <div className="text-[15px] font-semibold [overflow-wrap:anywhere]">{row.title}</div>
              <div
                className="mt-1 flex flex-wrap items-center gap-1.5 text-[13px]"
                style={{ color: "var(--wb-content-secondary)" }}
              >
                {handlerLink(row.handle, row.handler_label)}
                <span>
                  · {row.provenance_label} · {day(row.at)}
                </span>
              </div>
            </Card>
          ))}
        </section>
      ))}

      {d.stalls.length ? (
        <section>
          <BandHead label="Stalled" count={d.stalls.length} />
          {d.stalls.map((s, i) => (
            <Card key={`${s.handle}-${i}`} className="mb-3">
              <div className="flex items-start justify-between gap-3">
                <span className="min-w-0 text-[15px] font-semibold [overflow-wrap:anywhere]">
                  {s.summary}
                </span>
                <StatusChip tone="warn" label={s.status_label} />
              </div>
              <div
                className="mt-1 flex flex-wrap items-center gap-1.5 text-[13px]"
                style={{ color: "var(--wb-content-secondary)" }}
              >
                {handlerLink(s.handle, s.handler_label)}
                <span>· no status for {s.age_hours}h</span>
              </div>
            </Card>
          ))}
        </section>
      ) : null}

      <section>
        <BandHead label="Staffing" count={staffing.rows.length} />
        {!staffing.available ? (
          <>
            <DegradedBanner
              message={staffing.reason || "Capacity snapshot unavailable."}
              className="mb-3"
            />
            <StaffingCards rows={staffing.rows} handlerLink={handlerLink} />
          </>
        ) : !staffing.rows.length ? (
          <ScopeLine>No programme is measured understaffed against the live fleet.</ScopeLine>
        ) : (
          <>
            {staffing.idle_minutes_total ? (
              <ScopeLine>
                Idle capacity: {staffing.idle_minutes_total} session-minutes unused.
              </ScopeLine>
            ) : null}
            <StaffingCards rows={staffing.rows} handlerLink={handlerLink} />
          </>
        )}
      </section>

      {d.topics.length ? (
        <section>
          <BandHead label="Handlers by topic" />
          {d.topics.map((t) => (
            <details
              key={t.topic}
              className="mb-3"
              open={openTopics.has(t.topic)}
              onToggle={(e) => {
                const isOpen = e.currentTarget.open;
                setOpenTopics((prev) => {
                  const next = new Set(prev);
                  if (isOpen) next.add(t.topic);
                  else next.delete(t.topic);
                  return next;
                });
              }}
            >
              <summary className="cursor-pointer text-[15px]">
                <b>{t.topic}</b>
                {t.worst_label ? ` · worst: ${t.worst_label}` : ""}
                {t.stalls ? ` · ${t.stalls} stalled` : ""}
                {t.open_counts.length
                  ? " · " + t.open_counts.map((c) => `${c.count} ${c.kind_label}`).join(" · ")
                  : ""}
              </summary>
              {openTopics.has(t.topic) ? (
                <Card className="mt-2">
                {t.lanes.map((l) => (
                  <div key={l.handle} className="flex flex-wrap items-center gap-2 py-1">
                    {handlerLink(l.handle, l.label)}
                    {l.status_label ? (
                      <StatusChip tone="info" label={l.status_label} />
                    ) : (
                      <span style={{ color: "var(--wb-content-muted)" }}>no status</span>
                    )}
                    {l.stale ? <StatusChip tone="warn" label="Stalled" /> : null}
                    {(l.quick_verbs ?? []).map((v) => (
                      <HandlerVerbButton
                        key={v.verb}
                        handle={l.handle}
                        verb={v.verb}
                        label={v.label}
                      />
                    ))}
                  </div>
                ))}
                </Card>
              ) : null}
            </details>
          ))}
        </section>
      ) : null}

      <section>
        <BandHead label="Parked plans" count={pp.plans.length} />
        {!pp.available ? (
          <DegradedBanner
            message={`${pp.reason || "Workbench unreachable right now."} Parked plans can't be listed until it is back.`}
          />
        ) : !pp.plans.length ? (
          <ScopeLine>No approved plan is waiting for the implement word.</ScopeLine>
        ) : (
          <>
            {pp.plans.map((p, i) => (
              <Card key={`${p.path}-${i}`} className="mb-3">
                <div className="text-[15px] font-semibold [overflow-wrap:anywhere]">
                  {p.title || p.path}
                </div>
                <div className="mt-1 text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
                  {p.project}
                  {p.age_days === null
                    ? ""
                    : ` · waiting ${p.age_days} day${p.age_days === 1 ? "" : "s"}`}
                </div>
              </Card>
            ))}
          </>
        )}
      </section>

      {!any && !d.topics.length ? (
        <EmptyState message="Nothing in the digest — no status-kind rows, no stalls, no parked plans." />
      ) : null}
    </PageColumn>
  );
}

function StaffingCards({
  rows,
  handlerLink,
}: {
  rows: DigestPayload["staffing"]["rows"];
  handlerLink: (handle: string, label: string) => ReactNode;
}) {
  return (
    <>
      {rows.map((s, i) => (
        <Card key={i} className="mb-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <span className="min-w-0 text-[15px] font-semibold [overflow-wrap:anywhere]">
              {s.handler_label || s.kind_label}
            </span>
            <span className="flex gap-2">
              <StatusChip tone="warn" label={s.kind_label} />
              {s.escalation === "main" ? <StatusChip tone="fail" label="Escalated to Main" /> : null}
            </span>
          </div>
          <div
            className="mt-1 flex flex-wrap items-center gap-1.5 text-[13px]"
            style={{ color: "var(--wb-content-secondary)" }}
          >
            {s.handle ? handlerLink(s.handle, s.topic) : null}
            <span>{s.detail}</span>
          </div>
        </Card>
      ))}
    </>
  );
}
