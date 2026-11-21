// Digest (storyboard frame 5): the digest windows, the
// include switches — and the digest itself. The digest is
// the owner's single approval surface, so this view renders
// what the adapter assembles for the next window: the
// owner-placed sections, the derived stalls, the staffing
// measure, the handlers grouped by topic (each lane's
// quick verbs live, steering through the same handler
// endpoint), and the parked plans. The next window is
// computed by the adapter from the enabled windows and
// the scenario clock — toggling a window re-derives the
// next window everywhere it appears. Include switches
// re-derive the preview line from the live store counts.
import { Fragment, useState } from "react";
import { useDataSource, useStoreVersion } from "../attention/useStore";
import { Toggle } from "@workhorse/kit/components/controls/Toggle";
import { Group, GroupLabel, Row, RowText, RowValue } from "../components/groups";
import { VerbButtons } from "../components/VerbButtons";
import { StaleNotice, UnreachableNotice } from "../components/SurfaceNotice";

function windowTimeLabel(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const d = new Date(Date.UTC(2026, 0, 1, h + 5, m));
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  })
    .format(d)
    .toUpperCase();
}

let keyCounter = 0;

export function DigestView() {
  useStoreVersion();
  const ds = useDataSource();
  const digest = ds.getDigest();
  const content = digest.content;
  const health = ds.getSurfaceHealth();
  // The digest is the owner's single approval surface: a
  // digest portion that has never loaded is unreachable,
  // never an empty approval queue (the original's rule).
  if (health.digest.state === "down") {
    return <UnreachableNotice what="The digest" />;
  }
  const [actionError, setActionError] = useState<string | null>(null);

  const act = (handle: string, verb: string) => {
    const result = ds.handlerAction(handle, verb, `digest-action-${++keyCounter}`);
    setActionError(result.ok ? null : result.error);
  };

  return (
    <>
      <StaleNotice health={health.digest} />
      <GroupLabel>Windows</GroupLabel>
      <Group>
        {digest.windows.map((w) => (
          <Row key={w.id}>
            <Toggle
              label={`${w.label} · ${windowTimeLabel(w.time)}`}
              checked={w.enabled}
              onChange={(checked) => ds.setDigestWindow(w.id, checked)}
            />
          </Row>
        ))}
      </Group>
      <GroupLabel>Next window</GroupLabel>
      <Group>
        <Row>
          <RowText label={digest.next_label} />
          <RowValue>{digest.next_detail}</RowValue>
        </Row>
        <Row>
          <RowText label={digest.preview_label} />
        </Row>
      </Group>

      {content.sections.map((section) => (
        // Fragment, not a div: a wrapper div makes the label
        // a :first-child, and .glabel's first-child rule
        // zeroes the 20px section margin (spacing audit,
        // 2026-11-15 — the owner's Digest instances).
        <Fragment key={section.kind}>
          <GroupLabel>{`${section.kind_label} — ${section.owner_label}`}</GroupLabel>
          <Group>
            {section.rows.map((r) => (
              <Row key={`${r.handle}-${r.title}`}>
                <RowText
                  label={r.title}
                  sub={`${r.handler_label} · ${r.provenance_label}`}
                />
                <RowValue>{r.age_label}</RowValue>
              </Row>
            ))}
          </Group>
        </Fragment>
      ))}

      {content.stalls.length > 0 ? (
        <>
          <GroupLabel>Stalled</GroupLabel>
          <Group>
            {content.stalls.map((s) => (
              <Row key={s.handle}>
                <RowText
                  label={s.summary}
                  sub={
                    s.clearing_act
                      ? `${s.handler_label} · ${s.status_label} · clears with: ${s.clearing_act}`
                      : `${s.handler_label} · ${s.status_label}`
                  }
                />
                <RowValue>{s.age_label}</RowValue>
              </Row>
            ))}
          </Group>
        </>
      ) : null}

      <GroupLabel>Staffing</GroupLabel>
      <Group>
        {!content.staffing.available ? (
          <Row>
            <RowText
              label="Staffing measure unavailable"
              sub={content.staffing.reason ?? undefined}
            />
          </Row>
        ) : (
          <>
            {content.staffing.idle_minutes_total > 0 ? (
              <Row>
                <RowText label="Fleet idle" />
                <RowValue>{`${content.staffing.idle_minutes_total} min idle`}</RowValue>
              </Row>
            ) : null}
            {content.staffing.rows.map((r) => (
              <Row key={`${r.kind}-${r.handle ?? r.topic ?? ""}`}>
                <RowText
                  label={`${r.kind_label} — ${r.handler_label}`}
                  sub={r.detail}
                />
                {r.escalation_label ? <RowValue>{r.escalation_label}</RowValue> : null}
              </Row>
            ))}
            {content.staffing.rows.length === 0 &&
            content.staffing.idle_minutes_total === 0 ? (
              <Row>
                <RowText label="Nothing flagged" sub="Every topic is staffed" />
              </Row>
            ) : null}
          </>
        )}
      </Group>

      <GroupLabel>Handlers by topic</GroupLabel>
      {content.topics.map((topic) => (
        <Fragment key={topic.topic}>
          <GroupLabel>
            {topic.topic}
            {topic.worst_label ? ` · worst: ${topic.worst_label}` : ""}
            {topic.stalls ? ` · ${topic.stalls} stalled` : ""}
          </GroupLabel>
          <Group>
            <Row>
              <RowText
                label="Open"
                sub={
                  topic.open_counts.length
                    ? topic.open_counts
                        .map((c) => `${c.count} ${c.kind_label}`)
                        .join(" · ")
                    : "Nothing open"
                }
              />
            </Row>
            {topic.lanes.map((lane) => (
              <div key={lane.handle}>
                <Row>
                  <RowText
                    label={lane.label}
                    sub={lane.status_label ?? "No status posted"}
                  />
                  {lane.stale ? <RowValue>Stalled</RowValue> : null}
                </Row>
                {lane.quick_verbs.length > 0 ? (
                  <Row padded>
                    <VerbButtons
                      verbs={lane.quick_verbs}
                      onAct={(verb) => act(lane.handle, verb)}
                    />
                  </Row>
                ) : null}
              </div>
            ))}
          </Group>
        </Fragment>
      ))}

      {actionError ? (
        <p
          className="text-sm"
          role="alert"
          style={{ color: "var(--wb-status-hard-gate-text)", margin: "8px 4px 0" }}
        >
          {actionError}
        </p>
      ) : null}

      <GroupLabel>Parked plans</GroupLabel>
      <Group>
        {!content.parked_plans.available ? (
          <Row>
            <RowText
              label="Parked plans unavailable"
              sub={content.parked_plans.reason ?? undefined}
            />
          </Row>
        ) : content.parked_plans.plans.length === 0 ? (
          <Row>
            <RowText label="No parked plans" />
          </Row>
        ) : (
          content.parked_plans.plans.map((p) => (
            <Row key={`${p.project}-${p.title}`}>
              <RowText label={p.title} sub={p.project} />
              <RowValue>{p.age_label}</RowValue>
            </Row>
          ))
        )}
      </Group>

      <GroupLabel>Include</GroupLabel>
      <Group>
        <Row>
          <Toggle
            label="Decisions waiting"
            checked={digest.include.decisions}
            onChange={(c) => ds.setDigestInclude("decisions", c)}
          />
        </Row>
        <Row>
          <Toggle
            label="Waiting on others"
            checked={digest.include.waiting}
            onChange={(c) => ds.setDigestInclude("waiting", c)}
          />
        </Row>
        <Row>
          <Toggle
            label="FYI items"
            checked={digest.include.fyi}
            onChange={(c) => ds.setDigestInclude("fyi", c)}
          />
        </Row>
      </Group>
    </>
  );
}
