// Today (storyboard frame 2) plus the contract's bands the
// frame's moment did not happen to show: "Decided —
// awaiting fulfillment" (§9.6) and the fulfilled effects.
// Every group derives from the one mock store, so a decision
// in any group moves every count on the page.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useDataSource, useStoreVersion } from "../attention/useStore";
import type { ItemView } from "../attention/types";
import { Group, GroupLabel, Row, RowText, RowValue } from "../components/groups";
import { HandlerChip } from "../components/chips";
import { AwaitingRow, DecisionRow, WaitingRow } from "../components/rows";
import { DecisionSheet } from "../components/DecisionSheet";
import { LargeTitle } from "../components/LargeTitle";
import { StaleNotice, UnreachableNotice } from "../components/SurfaceNotice";

export function TodayView() {
  useStoreVersion();
  const ds = useDataSource();
  const today = ds.getToday();
  const health = ds.getSurfaceHealth();
  // The original's rule: when neither fast portion has
  // ever loaded, the surface is unreachable — the page
  // says exactly that and renders no queue at all, clear
  // or otherwise.
  const unreachable = health.today.state === "down" && health.glance.state === "down";
  // Preview furniture: ?sheet=<item-id> opens the preview
  // with that item's decision sheet up (screenshot pass).
  const [sheetItem, setSheetItem] = useState<ItemView | null>(() => {
    const id = new URLSearchParams(window.location.search).get("sheet");
    if (!id) return null;
    return (
      [...today.decisions, ...today.breakthrough, ...today.due_decidable, ...today.fyi.items].find(
        (i) => i.id === id,
      ) ?? null
    );
  });
  const [fyiOpen, setFyiOpen] = useState(false);

  // Keep the open sheet bound to the live item (it may move
  // to the awaiting band or return while the sheet is open).
  const liveSheetItem = sheetItem
    ? ([...today.decisions, ...today.breakthrough, ...today.due_decidable, ...today.fyi.items].find(
        (i) => i.id === sheetItem.id,
      ) ?? null)
    : null;

  if (unreachable) {
    return (
      <>
        <LargeTitle title="Today" subtitle={today.subtitle} />
        <UnreachableNotice what="The surface" />
      </>
    );
  }

  return (
    <>
      <LargeTitle title="Today" subtitle={today.subtitle} />

      <StaleNotice health={health.today} />

      {today.unavailable.map((u, i) => (
        <Group key={i}>
          <Row>
            <RowText
              label={u.reason}
              sub={`Showing the last good copy from ${u.last_good_label}.`}
            />
          </Row>
        </Group>
      ))}

      {today.breakthrough.length > 0 ? (
        <>
          <GroupLabel>Breakthrough</GroupLabel>
          <Group>
            {today.breakthrough.map((item) => (
              <DecisionRow key={item.id} item={item} onOpenSheet={setSheetItem} />
            ))}
          </Group>
        </>
      ) : null}

      <GroupLabel>Needs your decision · {today.decisions.length}</GroupLabel>
      {today.decisions.length > 0 ? (
        <Group>
          {today.decisions.map((item) => (
            <DecisionRow key={item.id} item={item} onOpenSheet={setSheetItem} />
          ))}
        </Group>
      ) : (
        <Group>
          <Row>
            <RowText label="Nothing waiting" sub="The queue is clear" />
          </Row>
        </Group>
      )}

      {today.awaiting.length > 0 ? (
        <>
          <GroupLabel>Decided — awaiting fulfillment</GroupLabel>
          <Group>
            {today.awaiting.map((item) => (
              <AwaitingRow key={item.id} item={item} />
            ))}
          </Group>
        </>
      ) : null}

      <GroupLabel>Due today</GroupLabel>
      <Group>
        {today.due_decidable.map((item) => (
          <DecisionRow key={item.id} item={item} onOpenSheet={setSheetItem} />
        ))}
        {today.due_today.map((row, i) => (
          <Row key={i}>
            <RowText label={row.label} sub={row.sub} />
            <RowValue>{row.value}</RowValue>
          </Row>
        ))}
      </Group>

      <GroupLabel>Waiting on others</GroupLabel>
      <Group>
        {today.waiting_on_others.map((item) => (
          <WaitingRow key={item.id} item={item} />
        ))}
        <Row onClick={() => setFyiOpen(!fyiOpen)}>
          <RowText
            label={`FYI · ${today.fyi.count} items`}
            sub={today.fyi.newest_title ? `Newest: ${today.fyi.newest_title}` : "Nothing new"}
          />
          <span style={{ marginLeft: "auto", color: "var(--wb-content-muted)" }}>
            {fyiOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
        </Row>
        {fyiOpen
          ? today.fyi.items.map((item) => (
              // An FYI row opens its sheet: the served
              // mute_type verb lives there, behind its
              // confirm — muting holds the whole type.
              <Row key={item.id} onClick={() => setSheetItem(item)}>
                <HandlerChip label={item.handler_label} severity={item.severity} />
                <RowText label={item.title} sub={item.waiting_label} />
              </Row>
            ))
          : null}
      </Group>

      <DecisionSheet item={liveSheetItem} onClose={() => setSheetItem(null)} />
    </>
  );
}
