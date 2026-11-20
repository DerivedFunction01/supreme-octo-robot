// Queue rows. A decision row carries its ruled actions
// inline (the storyboard's form): Open navigates to the
// handler, the verb/option buttons record the decision at
// the tap, and the row body opens the decision sheet (note,
// options, history). The kit's TriageRow cannot host these —
// its chip/badge slots are inert by contract — so the row is
// composed from kit primitives in the storyboard's form;
// recorded as a kit tension in the lane report.
import { useState } from "react";
import { useDataSource } from "../attention/useStore";
import { verbLabel } from "../attention/verb-labels";
import type { AwaitingView, ItemView } from "../attention/types";
import { Button } from "@workhorse/kit/components/Button";
import { Badge } from "@workhorse/kit/components/Badge";
import { useNav } from "../nav";
import { HandlerChip, SeverityChip } from "./chips";
import { Row, RowText } from "./groups";
import { ConfirmDialog } from "./ConfirmDialog";
import { DONE_CONFIRM, MUTE_TYPE_CONFIRM } from "./DecisionSheet";

let rowKeyCounter = 0;

export function DecisionRow({
  item,
  onOpenSheet,
}: {
  item: ItemView;
  onOpenSheet: (item: ItemView) => void;
}) {
  const ds = useDataSource();
  const { go } = useNav();
  const [confirmVerb, setConfirmVerb] = useState<string | null>(null);

  const post = (verb: string, optionId?: string) => {
    const result = ds.decide(item.id, {
      verb,
      option_id: optionId ?? null,
      idempotency_key: `row-${item.id}-${++rowKeyCounter}`,
      // A quick snooze takes the served defaults: the
      // first served return time, return-on-activity as
      // served. The sheet carries the full choice.
      ...(verb === "snooze"
        ? {
            return_at: item.snooze_options.times[0]?.at ?? null,
            return_on_activity: item.snooze_options.on_activity,
          }
        : {}),
    });
    if (!result.ok) onOpenSheet(item); // validation surfaces in the sheet
  };

  const quick = (verb: string, optionId?: string) => {
    // The same confirm gates as the sheet: muting a type
    // always confirms; done confirms when the item does
    // not clear at the source.
    if (
      optionId === undefined &&
      (verb === "mute_type" || (verb === "done" && !item.clears_at_source))
    ) {
      setConfirmVerb(verb);
      return;
    }
    post(verb, optionId);
  };

  // rule_it is a two-tap act (arm, then the option) — it
  // lives in the sheet, not on the row.
  const plainVerbs = item.verbs.filter(
    (v) => v !== "decide" && v !== "snooze" && v !== "rule_it",
  );
  const hasSnooze = item.verbs.includes("snooze");

  return (
    <>
    <Row>
      <HandlerChip label={item.handler_label} severity={item.severity} />
      {/* The title is the row's only flex-grower (basis 0), so
          line-breaking ignores it: when chip + actions happen
          to fit the line, the title is left with the few px of
          free space and crushes to a vertical column. The
          .row-title floor (app.css — it must outrank the
          blanket .row > * min-width: 0 rule) makes its
          hypothetical size count in the wrap decision, so the
          action cluster wraps first, and the title never
          renders below readable width. */}
      <button
        type="button"
        className="row-title flex-1 cursor-pointer text-left"
        onClick={() => onOpenSheet(item)}
        aria-label={`Open decision: ${item.title}`}
      >
        <RowText
          label={item.title}
          sub={item.failure ?? item.waiting_label}
          subTruncate
        />
      </button>
      {item.history.length > 0 ? (
        <span style={{ minWidth: 0, marginLeft: "auto" }}>
          <Badge kind="needs-changes" text={`${item.history.length} returned`} />
        </span>
      ) : null}
      <span className="row-actions">
        <Button variant="ghost" onClick={() => go({ name: "handler", handle: item.handle })}>
          Open
        </Button>
        {item.options
          ? // Quick option buttons only when the labels fit a
            // row; a long option label routes through the
            // sheet, where the SegmentedControl wraps it.
            item.options.every((o) => o.label.length <= 16)
            ? item.options.map((o) => (
                <Button key={o.id} variant="secondary" onClick={() => quick("decide", o.id)}>
                  {o.label}
                </Button>
              ))
            : [
                <Button key="decide" variant="secondary" onClick={() => onOpenSheet(item)}>
                  Decide
                </Button>,
              ]
          : plainVerbs.map((verb) => (
              <Button key={verb} variant="secondary" onClick={() => quick(verb)}>
                {verbLabel(verb)}
              </Button>
            ))}
        {hasSnooze ? (
          <Button variant="ghost" onClick={() => quick("snooze")}>
            Snooze
          </Button>
        ) : null}
      </span>
    </Row>
    <ConfirmDialog
      message={
        confirmVerb === "mute_type"
          ? MUTE_TYPE_CONFIRM
          : confirmVerb === "done"
            ? DONE_CONFIRM
            : null
      }
      confirmLabel={confirmVerb ? verbLabel(confirmVerb) : "Confirm"}
      onConfirm={() => {
        const verb = confirmVerb;
        setConfirmVerb(null);
        if (verb) post(verb);
      }}
      onCancel={() => setConfirmVerb(null)}
    />
    </>
  );
}

export function AwaitingRow({ item }: { item: AwaitingView }) {
  const bandSeverity =
    item.band_state === "queued" ? "info" : item.band_state === "sent" ? "warn" : "idle";
  return (
    <Row>
      <HandlerChip label={item.handler_label} severity={item.severity} />
      <RowText label={item.title} sub={item.decided_label} />
      <span style={{ marginLeft: "auto", minWidth: 0 }} className="flex items-center gap-2">
        {item.decision.send_id ? (
          <span className="mono text-xs" style={{ color: "var(--wb-content-muted)" }}>
            {item.decision.send_id}
          </span>
        ) : null}
        <SeverityChip severity={bandSeverity} label={item.band_label} />
      </span>
    </Row>
  );
}

export function WaitingRow({ item }: { item: ItemView }) {
  const { go } = useNav();
  return (
    <Row onClick={() => go({ name: "handler", handle: item.handle })}>
      <RowText label={item.title} sub={`${item.handler_label} thread · ${item.waiting_label.replace("Waiting ", "")}`} />
      <span style={{ marginLeft: "auto" }}>
        <SeverityChip severity="idle" label="Waiting" />
      </span>
    </Row>
  );
}
