// Handlers (storyboard frame 7) + the programme registry
// rendered as cards beneath the list. The registry is
// contract 01 data; the lane commission names programme
// cards as a surface that must move with the same store —
// open-decision and awaiting counts on each card are live
// derivations over the programme's handles.
import { useDataSource, useStoreVersion } from "../attention/useStore";
import { useNav } from "../nav";
import { Card } from "@workhorse/kit/components/display/Card";
import { Group, GroupLabel, Row, RowText } from "../components/groups";
import { HandlerChip, HandlerDot, SeverityChip } from "../components/chips";
import { LargeTitle } from "../components/LargeTitle";

export function HandlersView() {
  useStoreVersion();
  const ds = useDataSource();
  const { go } = useNav();
  const handlers = ds.getHandlers();
  const programmes = ds.getProgrammes();

  return (
    <>
      <LargeTitle title="Handlers" subtitle={handlers.subtitle} />
      <Group>
        {handlers.rows.map((row) => (
          <Row key={row.handle} onClick={() => go({ name: "handler", handle: row.handle })}>
            <HandlerChip label={row.label} severity={row.severity} />
            <RowText label={`${row.label} chat`} sub={row.sub_label} />
            {row.trailing ? (
              <span style={{ marginLeft: "auto" }} className="flex items-center gap-2">
                <SeverityChip severity={row.trailing.severity} label={row.trailing.label} />
              </span>
            ) : null}
          </Row>
        ))}
      </Group>

      <GroupLabel>Programmes</GroupLabel>
      <div className="programme-grid">
        {programmes.map((p) => (
          <Card key={p.slug} title={p.label}>
            <div className="flex flex-col gap-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                {p.handles.map((h) => (
                  <span
                    key={h.handle}
                    className="flex min-w-0 items-center gap-1.5"
                    style={{ overflowWrap: "anywhere" }}
                  >
                    <HandlerDot colorSlot={h.color_slot} />
                    {h.label}
                  </span>
                ))}
              </div>
              <div style={{ color: "var(--ui-content-secondary)" }}>
                {p.cadence_label} · {p.band_label} · {p.escalation_label} · {p.venue_label}
              </div>
              <div>
                {p.open_decisions} decision{p.open_decisions === 1 ? "" : "s"} waiting
                {p.awaiting > 0 ? ` · ${p.awaiting} awaiting fulfillment` : ""}
              </div>
              <p className="text-xs" style={{ color: "var(--ui-content-muted)" }}>
                {p.rule_text}
              </p>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
