// Handler detail (storyboard frame 3): the handler's latest
// status post with its quick verbs, the steering verbs the
// backend serves for a handler, the owner's action ledger,
// the handler's open items with the same decision rows as
// Today, its served stats as stat rows, and its muted types
// as switches. Unmuting a type surfaces that handler's
// muted FYI items in Today's rollup — the switch moves
// another surface. Steering acts record through the store
// and dispatch through the send ledger; a refused act (a
// second ping inside the digest window) surfaces its error
// here and records nothing.
import { useState } from "react";
import { useDataSource, useStoreVersion } from "../attention/useStore";
import type { ItemView } from "../attention/types";
import { Toggle } from "@workhorse/kit/components/controls/Toggle";
import { Group, GroupLabel, Row, RowText, RowValue } from "../components/groups";
import { AwaitingRow, DecisionRow } from "../components/rows";
import { DecisionSheet } from "../components/DecisionSheet";
import { VerbButtons } from "../components/VerbButtons";
import { LargeTitle } from "../components/LargeTitle";

let keyCounter = 0;

const timeFmt = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
});

export function HandlerDetailView({ handle }: { handle: string }) {
  useStoreVersion();
  const ds = useDataSource();
  const [sheetItem, setSheetItem] = useState<ItemView | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const detail = ds.getHandlerDetail(handle);
  if (!detail) {
    return <LargeTitle title="Handler" subtitle="Unknown handler" />;
  }
  const liveSheetItem = sheetItem
    ? (detail.open_items.find((i) => i.id === sheetItem.id) ?? null)
    : null;
  const status = detail.status;

  const act = (verb: string) => {
    const result = ds.handlerAction(handle, verb, `handler-action-${++keyCounter}`);
    setActionError(result.ok ? null : result.error);
  };

  return (
    <>
      <LargeTitle title={detail.handler.label} subtitle={detail.subtitle} />

      {status ? (
        <>
          <GroupLabel>Status</GroupLabel>
          <Group>
            <Row>
              <RowText label={status.status_label} sub={status.summary} />
              <RowValue>{status.at_label}</RowValue>
            </Row>
            {status.done?.map((line) => (
              <Row key={`done-${line}`}>
                <RowText label="Done" sub={line} />
              </Row>
            ))}
            {status.ongoing?.map((line) => (
              <Row key={`ongoing-${line}`}>
                <RowText label="Ongoing" sub={line} />
              </Row>
            ))}
            {status.tail?.map((t) => (
              <Row key={`tail-${t.title}`}>
                <RowText label={t.title} sub={t.kind_label} />
                <RowValue>{t.owner_label}</RowValue>
              </Row>
            ))}
            {status.blockers?.map((b) => (
              <Row key={`blocker-${b.summary}`}>
                <RowText label={b.summary} sub={b.clearing_act ?? undefined} />
                <RowValue>{b.whose_label}</RowValue>
              </Row>
            ))}
            {status.quick_verbs.length > 0 ? (
              <Row padded>
                <VerbButtons verbs={status.quick_verbs} onAct={act} />
              </Row>
            ) : null}
            {status.derived && status.derived.label ? (
              <Row>
                <RowText label={status.derived.label} />
              </Row>
            ) : null}
            {status.derived?.conflicts.map((message) => (
              <Row key={`conflict-${message}`}>
                <RowText label="Conflict" sub={message} />
              </Row>
            ))}
          </Group>
        </>
      ) : null}

      {detail.handler_verbs.length > 0 ? (
        <>
          <GroupLabel>Steering</GroupLabel>
          <Group>
            <Row padded>
              <VerbButtons verbs={detail.handler_verbs} onAct={act} />
            </Row>
          </Group>
        </>
      ) : null}

      {actionError ? (
        <p
          className="text-sm"
          role="alert"
          style={{ color: "var(--ui-status-hard-gate-text)", margin: "8px 4px 0" }}
        >
          {actionError}
        </p>
      ) : null}

      <GroupLabel>Open items</GroupLabel>
      {detail.open_items.length > 0 ? (
        <Group>
          {detail.open_items.map((item) => (
            <DecisionRow key={item.id} item={item} onOpenSheet={setSheetItem} />
          ))}
        </Group>
      ) : (
        <Group>
          <Row>
            <RowText label="Nothing waiting" sub="No open items for this handler" />
          </Row>
        </Group>
      )}

      {detail.awaiting.length > 0 ? (
        <>
          <GroupLabel>Decided — awaiting fulfillment</GroupLabel>
          <Group>
            {detail.awaiting.map((item) => (
              <AwaitingRow key={item.id} item={item} />
            ))}
          </Group>
        </>
      ) : null}

      <GroupLabel>Handler</GroupLabel>
      <Group>
        <Row>
          <RowText label="Agent-clearable now" />
          <RowValue>{detail.agent_clearable_label}</RowValue>
        </Row>
        <Row>
          <RowText label="Breakthrough hit rate" />
          <RowValue>{detail.breakthrough_hit_rate}</RowValue>
        </Row>
      </Group>

      {detail.owner_actions.length > 0 ? (
        <>
          <GroupLabel>Your actions</GroupLabel>
          <Group>
            {detail.owner_actions.map((a) => (
              <Row key={a.id}>
                <RowText
                  label={a.verb_label}
                  sub={`${a.actor_label}${a.shadow ? " · shadow" : ""}${a.note ? ` · ${a.note}` : ""}`}
                />
                <RowValue>{a.at_label}</RowValue>
              </Row>
            ))}
          </Group>
        </>
      ) : null}

      {detail.muted_types.length > 0 ? (
        <>
          <GroupLabel>Muted types</GroupLabel>
          <Group>
            {detail.muted_types.map((m) => (
              <Row key={m.type}>
                <Toggle
                  label={m.type}
                  checked={m.muted}
                  onChange={(checked) => ds.setMutedType(handle, m.type, checked)}
                />
              </Row>
            ))}
          </Group>
        </>
      ) : null}

      {detail.sends.length > 0 ? (
        <>
          <GroupLabel>Sends</GroupLabel>
          <Group>
            {detail.sends.map((s) => (
              <Row key={s.id}>
                <RowText
                  label={s.template}
                  sub={
                    s.mode === "shadow"
                      ? "Shadow — recorded, never dispatched"
                      : s.dispatch.delivered_at
                        ? `Delivered${s.dispatch.delivery_ref ? ` · ${s.dispatch.delivery_ref}` : ""}`
                        : s.dispatch.suppress_reason
                          ? `Suppressed — ${s.dispatch.suppress_reason}`
                          : s.dispatch.consumer
                            ? "Claimed — awaiting delivery"
                            : s.outcome || "Queued"
                  }
                />
                <RowValue>{timeFmt.format(new Date(s.at))}</RowValue>
              </Row>
            ))}
          </Group>
        </>
      ) : null}

      {detail.auto_applied.length > 0 ? (
        <>
          <GroupLabel>Auto-applied</GroupLabel>
          <Group>
            {detail.auto_applied.map((a, i) => (
              <Row key={`${a.at}-${i}`}>
                <RowText
                  label={a.wait_class}
                  sub={`${a.decision_label}${a.rule_id ? ` · rule ${a.rule_id}` : ""}${a.shadow ? " · shadow" : ""}`}
                />
                <RowValue>{timeFmt.format(new Date(a.at))}</RowValue>
              </Row>
            ))}
          </Group>
        </>
      ) : null}

      <DecisionSheet item={liveSheetItem} onClose={() => setSheetItem(null)} />
    </>
  );
}
