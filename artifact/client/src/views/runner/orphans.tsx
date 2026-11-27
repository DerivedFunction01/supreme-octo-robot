// Orphans — the panel's orphaned-sessions section
// (orphans.js): live runtimes with no lease record. The
// card renders only what the portion serves — the derived
// deadline with its evidence source, the conflicts the
// derivation found, the evidenced shape or the candidate
// list — and Adopt posts to the core's adopt verb through
// the verdict channel (409 answers carry the refusal's
// reason). The shape pick and the jobs-expander state
// live outside the poll-driven render, keyed by session.

import { useState, type ReactNode } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Card } from "@workhorse/kit/components/display/Card";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import { GroupedList, RadioRow } from "@workhorse/kit/components/display/GroupedList";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import { api } from "../../lib/actions";
import {
  adoptRefusalText,
  countdownText,
  fmtAge,
  fmtTime,
  specById,
  specLabel,
  type Orphan,
} from "./model";
import { DegradedCard, PartStatus, specSub } from "./pickers";
import { callVerdict, useRunner } from "./state";

function line(children: ReactNode) {
  return (
    <p className="mt-1.5 text-sm" style={{ color: "var(--ui-content-secondary)" }}>
      {children}
    </p>
  );
}

function b(children: ReactNode) {
  return <b style={{ color: "var(--ui-content-primary)", fontWeight: 600 }}>{children}</b>;
}

function conflictValue(v: unknown): string {
  const s = String(v ?? "—");
  return /^\d{4}-\d{2}-\d{2}T/.test(s) ? fmtTime(s) : s;
}

function OrphanCard({
  orphan,
  shapePick,
  onPickShape,
  jobsOpen,
  onToggleJobs,
}: {
  orphan: Orphan;
  shapePick: Record<string, string>;
  onPickShape: (session: string, id: string) => void;
  jobsOpen: Record<string, boolean>;
  onToggleJobs: (session: string, open: boolean) => void;
}) {
  const { parts, act, setNotice, now } = useRunner();
  const o = orphan;
  const specs = parts.specs.data?.specs || [];
  const dl = o.derived_deadline;
  const past = dl ? new Date(dl).getTime() <= now : false;
  const jobsCount = o.jobs_in_flight ?? 0;
  const candidates = Array.isArray(o.shape_candidates) ? o.shape_candidates : [];
  const pick =
    shapePick[o.session || ""] ||
    (candidates.length === 1 ? candidates[0] : null);

  const adopt = () => {
    const session = o.session || "";
    const body: Record<string, unknown> = { session };
    if (!o.shape_evidenced) {
      if (!pick) {
        setNotice(
          "Adoption refused: the shape class matches several catalog shapes",
        );
        return;
      }
      body.shape = pick;
    }
    void act(async () => {
      const res = await callVerdict(() => api.adoptOrphan({ body }));
      if (res.action === "adopted") {
        const record = (res.record ?? {}) as Record<string, unknown>;
        const deadline = (record.deadline as string) || o.derived_deadline;
        setNotice(
          `Adopted — ${session} is a lease again${deadline ? `, deadline ${fmtTime(deadline)}` : ""}`,
        );
      } else {
        setNotice(`Adoption refused: ${adoptRefusalText(res)}`);
      }
    });
  };

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[15px] font-semibold">{o.session || "session"}</span>
        <StatusChip tone="warn" label="Orphaned" />
      </div>
      {!dl ? null : past ? (
        <p
          className="mt-2 flex flex-wrap items-center gap-2 text-[26px] leading-tight font-semibold"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {fmtTime(dl)}
          <StatusChip tone="warn" label="past deadline" />
        </p>
      ) : (
        <p
          className="mt-2 text-[26px] leading-tight font-semibold"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {countdownText(dl, now)}
        </p>
      )}
      {line(
        <>
          First seen {b(fmtTime(o.first_seen))}
          {o.acquired_at ? <> · Acquired {b(fmtTime(o.acquired_at))}</> : null}
          {jobsCount === 0 ? <> · In-flight jobs {b(0)}</> : null}
          {o.kit_installed ? <> · Renewal kit {b("installed")}</> : null}
        </>,
      )}
      {jobsCount > 0 ? (
        <details
          className="mt-2"
          open={Boolean(jobsOpen[o.session || ""])}
          onToggle={(e) =>
            onToggleJobs(o.session || "", (e.target as HTMLDetailsElement).open)
          }
        >
          <summary className="cursor-pointer text-sm">
            In-flight jobs {b(jobsCount)}
          </summary>
          <div className="mt-1.5">
            {(o.jobs_in_flight_entries || []).map((e) => (
              <p
                key={e.id}
                className="text-sm"
                style={{ color: "var(--ui-content-secondary)" }}
              >
                <span style={{ fontFamily: "var(--ui-font-mono, monospace)" }}>
                  {e.id}
                </span>{" "}
                · {e.kind} · {e.state} · {fmtAge(e.started_at, now)}
              </p>
            ))}
          </div>
        </details>
      ) : null}
      {o.shape_evidenced ? (
        line(<>Shape {b(specLabel(specs, o.shape))} · evidenced</>)
      ) : (
        <>
          {line(
            <>
              Shape class {b(o.shape_class || "unknown")} — not evidenced
            </>,
          )}
          {candidates.length ? (
            <div role="radiogroup" aria-label="Shape candidates" className="mt-2">
              <GroupedList>
                {candidates.map((id) => {
                  const spec = specById(specs, id);
                  return (
                    <RadioRow
                      key={id}
                      label={specLabel(specs, id)}
                      sub={spec ? specSub(spec) : undefined}
                      selected={id === pick}
                      onSelect={() => onPickShape(o.session || "", id)}
                    />
                  );
                })}
              </GroupedList>
            </div>
          ) : (
            line("No catalog candidates for this class.")
          )}
        </>
      )}
      {line(
        <>
          Creator caller {b(o.creator_caller || "—")}
          {o.first_claim && o.first_claim !== o.creator_caller ? (
            <> · first claim {b(o.first_claim)}</>
          ) : null}
        </>,
      )}
      {o.derived_deadline
        ? line(
            <>
              Derived deadline {b(fmtTime(o.derived_deadline))} · from{" "}
              {b(o.deadline_source || "—")}
              {o.deadline_stale_possible ? (
                <>
                  {" "}
                  <StatusChip tone="warn" label="possibly stale" />
                </>
              ) : null}
            </>,
          )
        : line(<>Derived deadline {b("none")}</>)}
      {(Array.isArray(o.conflicts) ? o.conflicts : []).map((c, i) => (
        <p
          key={i}
          className="mt-1.5 text-sm"
          style={{ color: "var(--ui-content-secondary)" }}
        >
          Conflict — {c.field}:{" "}
          {(Array.isArray(c.values) ? c.values : [])
            .map((v) => `${v.source} says ${conflictValue(v.value)}`)
            .join(" · ")}
        </p>
      ))}
      {o.handover_pending
        ? line(<StatusChip tone="warn" label="Handover pending" />)
        : null}
      <div className="mt-3">
        <Button disabled={Boolean(o.handover_pending)} onClick={adopt}>
          Adopt
        </Button>
      </div>
    </Card>
  );
}

export function OrphansView() {
  const { parts, allDown } = useRunner();
  const [shapePick, setShapePick] = useState<Record<string, string>>({});
  const [jobsOpen, setJobsOpen] = useState<Record<string, boolean>>({});
  if (allDown) return <DegradedCard />;
  const orphans = parts.orphans.data?.orphans || [];
  return (
    <div className="flex flex-col gap-4">
      <PartStatus name="orphans" part={parts.orphans} />
      {parts.orphans.data ? (
        orphans.length ? (
          orphans.map((o, i) => (
            <OrphanCard
              key={o.session || i}
              orphan={o}
              shapePick={shapePick}
              onPickShape={(session, id) =>
                setShapePick((prev) => ({ ...prev, [session]: id }))
              }
              jobsOpen={jobsOpen}
              onToggleJobs={(session, open) =>
                setJobsOpen((prev) => ({ ...prev, [session]: open }))
              }
            />
          ))
        ) : (
          <EmptyState message="No orphaned sessions" />
        )
      ) : null}
    </div>
  );
}
