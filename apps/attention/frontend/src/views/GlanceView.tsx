// Glance (storyboard frames 1 and 6): the ambient surface —
// clock type scale, the presence chip, the count, and the
// next items. Presence-filtered by the adapter (contract
// 09): active shows needs-decision counts and next-due;
// away lists only breakthroughs and withholds next-due.
// The night frame is this same surface on the night ladder
// with an away presence — the store underneath is live, so
// a decision made in Today moves the night count too.
//
// The extracted kit carries no night-ladder token scope
// (kit sheet names one; S2's tokens carry palettes x modes
// + density only) — the .night-ladder overrides in app.css
// carry the storyboard's night values pending a kit night
// scope. Recorded as a kit gap in the lane report.
import { useDataSource, useStoreVersion } from "../attention/useStore";
import { useNav } from "../nav";
import { Group, GroupLabel, Row, RowText, RowValue } from "../components/groups";
import { HandlerChip, PresenceChipView } from "../components/chips";
import { DownSourcesNotice, StaleNotice } from "../components/SurfaceNotice";
import { useIsPhone } from "@workhorse/kit/lib/responsive";

export function GlanceView({ night = false }: { night?: boolean }) {
  useStoreVersion();
  const isPhone = useIsPhone();
  const ds = useDataSource();
  const { go } = useNav();
  const glance = ds.getGlance(night);
  const health = ds.getSurfaceHealth();
  // A glance portion that has never loaded is not a clear
  // queue: the empty row below must not claim one.
  const glanceDown = health.glance.state === "down";

  const body = (
    <div className={`glance ${isPhone ? "glance-phone" : ""}`}>
      <div className="glance-left">
        <div className="glance-clock">{glance.clock_label}</div>
        <div className="glance-date">{glance.date_label}</div>
        <div style={{ marginTop: 22 }}>
          {glance.presence.mode !== "active" ? (
            <button
              type="button"
              className="presence-link"
              aria-label="Return to Active"
              title="Return to Active"
              onClick={() => ds.setPresence("active", "17:00")}
              style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}
            >
              <PresenceChipView presence={glance.presence} large />
            </button>
          ) : (
            <PresenceChipView presence={glance.presence} large />
          )}
        </div>
        <div className="glance-count">{glance.count_label}</div>
        <div className="glance-sub">{glance.sub_label}</div>
        {glance.held_label ? (
          <div className="glance-sub">{glance.held_label}</div>
        ) : null}
      </div>
      <div className="glance-right">
        <GroupLabel>Next</GroupLabel>
        <Group>
          {glance.next.map((item) => (
            <Row key={item.id} padded onClick={() => go({ name: "today" })}>
              <HandlerChip label={item.handler_label} severity={item.severity} />
              <RowText
                label={<span style={{ fontSize: 16.5 }}>{item.title}</span>}
                sub={
                  item.due_label
                    ? `${item.due_label} · ${item.handler_label}`
                    : item.waiting_label
                }
              />
            </Row>
          ))}
          {glance.next.length === 0 && !glanceDown ? (
            <Row padded>
              <RowText label="Nothing needs you" sub="The queue is clear" />
            </Row>
          ) : null}
          {glance.next.length === 0 && glanceDown ? (
            <Row padded>
              <RowText
                label="The surface is unreachable"
                sub="Nothing is being hidden; this is the whole report."
              />
            </Row>
          ) : null}
        </Group>
        <StaleNotice health={health.glance} />
        <DownSourcesNotice sources={glance.down_sources} />
        <GroupLabel>{glance.rows_label}</GroupLabel>
        <Group>
          {glance.rows.map((row, i) => (
            <Row key={i} padded>
              <RowText label={row.label} />
              <RowValue>
                <span style={{ fontSize: 15.5 }}>{row.value}</span>
              </RowValue>
            </Row>
          ))}
        </Group>
      </div>
    </div>
  );

  if (night) {
    return (
      <div className="night-ladder" data-mode="dark">
        {body}
      </div>
    );
  }
  return body;
}
