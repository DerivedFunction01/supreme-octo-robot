// ItemCard — the shared item card (Today's bands and the
// handler detail's Open items render the same card, as
// the original's itemCard() did). Verbs, options, and
// labels are served; the card renders them and derives
// nothing. The title itself opens the source — there is
// no Act button.
//
// Behaviour (the original's wireItems/itemVerb):
//   - plain verbs post at once; `done` without
//     clears_at_source and `mute_type` go through the
//     confirm dialog first, with the original's texts;
//   - `rule_it` arms rule mode — the next option tap
//     posts as the standing rule instead of a pick;
//   - snooze / reply / modify open the expand panel
//     (snooze times + resume note; or the one-line note
//     with Send);
//   - every write carries an idempotency key, reports
//     through the note toast, and refreshes the view.

import { useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Card } from "@workhorse/kit/components/display/Card";
import { Input } from "@workhorse/kit/components/controls/Fields";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import { day, type AttentionItem } from "./model";
import { call, idem, api } from "./transport";
import { SlotDot, useAttentionUi } from "./ui";

type ExpandMode = "snooze" | "reply" | "modify" | null;

export function ItemCard({ item, band }: { item: AttentionItem; band: string }) {
  const ui = useAttentionUi();
  const [expand, setExpand] = useState<ExpandMode>(null);
  const [ruleMode, setRuleMode] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [resumeNote, setResumeNote] = useState("");

  const owner = item.need === "owner_actionable";
  const verbs = item.verbs ?? [];
  const hint = verbs.find((v) => v.rule_hint);
  const plainVerbs = verbs.filter(
    (v) => !["pick", "snooze", "reply", "modify"].includes(v.verb),
  );
  const hasSnooze = verbs.some((v) => v.verb === "snooze");
  const needsNote = verbs.some((v) => ["reply", "modify"].includes(v.verb));
  const hasModify = verbs.some((v) => v.verb === "modify");

  async function postItemAction(payload: Record<string, unknown>) {
    try {
      await call(api.itemAction({ itemId: item.id, body: { idempotency_key: idem(), ...payload } }));
      ui.notify("Saved");
      ui.refresh();
    } catch (e) {
      ui.notify(`Failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  function onVerb(verb: string) {
    if (verb === "snooze" || verb === "reply" || verb === "modify") {
      setExpand(verb);
      return;
    }
    if (verb === "rule_it") {
      setRuleMode(true);
      return;
    }
    if (verb === "mute_type") {
      ui.confirm(
        "Mute every open item of this type from this handler?",
        () => void postItemAction({ verb }),
      );
      return;
    }
    if (verb === "done" && String(item.clears_at_source) !== "true") {
      ui.confirm(
        "Mark done here? It will not clear at the source — the source keeps its own copy.",
        () => void postItemAction({ verb }),
      );
      return;
    }
    void postItemAction({ verb });
  }

  function onPick(optionId: string) {
    const verb = ruleMode ? "rule_it" : "pick";
    setRuleMode(false);
    void postItemAction({ verb, option_id: optionId });
  }

  async function onSnooze(at: string) {
    try {
      await call(
        api.itemAction({
          itemId: item.id,
          body: {
            verb: "snooze",
            return_at: at,
            return_on_activity: true,
            resume_note: resumeNote || null,
            idempotency_key: idem(),
          },
        }),
      );
      ui.notify("Snoozed");
      ui.refresh();
    } catch (e) {
      ui.notify(`Snooze failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <Card className="mb-3">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0 text-[15px] font-semibold [overflow-wrap:anywhere]">
          {item.source_url ? (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--ui-accent)" }}
            >
              {item.title}
            </a>
          ) : (
            item.title
          )}
        </span>
        {owner && band === "breakthrough" ? (
          <StatusChip className="shrink-0" tone="fail" label="Needs you" />
        ) : owner ? (
          <StatusChip className="shrink-0" tone="warn" label={item.kind_label} />
        ) : (
          <StatusChip className="shrink-0" tone="idle" label={item.kind_label} />
        )}
      </div>

      <div className="mt-1.5 text-[13px]" style={{ color: "var(--ui-content-secondary)" }}>
        <div className="flex flex-wrap items-center gap-1.5">
          <SlotDot slot={item.handler.color_slot} />
          <Button
            variant="ghost"
            onClick={() =>
              ui.navigate(`#/attention/handlers/${encodeURIComponent(item.handler.handle)}`)
            }
          >
            {item.handler.label}
          </Button>
          <span>· waiting {item.waiting_label}</span>
        </div>
        {item.due_at ? <div>Due {day(item.due_at)}</div> : null}
        {item.resume_note ? <div>Resume: {item.resume_note}</div> : null}
        {item.provenance_label ? <div>{item.provenance_label}</div> : null}
      </div>

      {item.options && item.options.length ? (
        <div className="mt-2.5 flex flex-wrap gap-2">
          {item.options.map((o) => (
            <Button key={o.id} variant="secondary" onClick={() => onPick(o.id)}>
              {o.label}
            </Button>
          ))}
        </div>
      ) : null}

      <div className="mt-2.5 flex flex-wrap gap-2">
        {plainVerbs.map((v) => (
          <Button
            key={v.verb}
            variant={v.primary ? "primary" : "secondary"}
            onClick={() => onVerb(v.verb)}
          >
            {v.label}
          </Button>
        ))}
        {hasSnooze ? (
          <Button variant="secondary" onClick={() => onVerb("snooze")}>
            Snooze
          </Button>
        ) : null}
        {needsNote ? (
          <Button variant="secondary" onClick={() => onVerb("reply")}>
            Reply
          </Button>
        ) : null}
        {hasModify ? (
          <Button variant="secondary" onClick={() => onVerb("modify")}>
            Modify
          </Button>
        ) : null}
      </div>

      {hint ? (
        <p className="mt-2 text-[13px]" style={{ color: "var(--ui-content-secondary)" }}>
          {hint.rule_hint}
        </p>
      ) : null}

      {expand === "snooze" ? (
        <div className="mt-3">
          <p className="text-[13px]" style={{ color: "var(--ui-content-secondary)" }}>
            Snooze until — or until there is new activity on it.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(item.snooze_options?.times ?? []).map((t) => (
              <Button key={t} variant="secondary" onClick={() => void onSnooze(t)}>
                {day(t)}
              </Button>
            ))}
          </div>
          <div className="mt-2 max-w-[420px]">
            <Input
              ariaLabel="Resume note"
              placeholder="Resume note"
              value={resumeNote}
              onChange={(e) => setResumeNote(e.target.value)}
            />
          </div>
        </div>
      ) : null}

      {expand === "reply" || expand === "modify" ? (
        <div className="mt-3 flex max-w-[520px] flex-wrap items-center gap-2">
          <div className="min-w-[220px] flex-1">
            <Input
              ariaLabel="Reply note"
              placeholder="One line to the lane"
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
            />
          </div>
          <Button
            variant="primary"
            onClick={() =>
              void postItemAction({ verb: expand === "modify" ? "modify" : "reply", note: noteText })
            }
          >
            Send
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

/** A handler verb button (quick verbs on the status card,
 *  topic lanes, and the handler verbs row): posts the
 *  verb to the handler action, notes "Sent", refreshes. */
export function HandlerVerbButton({
  handle,
  verb,
  label,
}: {
  handle: string;
  verb: string;
  label: string;
}) {
  const ui = useAttentionUi();
  return (
    <Button
      variant="secondary"
      onClick={async () => {
        try {
          await call(api.handlerAction({ handle, body: { verb, idempotency_key: idem() } }));
          ui.notify("Sent");
          ui.refresh();
        } catch (e) {
          ui.notify(`Failed: ${e instanceof Error ? e.message : String(e)}`);
        }
      }}
    >
      {label}
    </Button>
  );
}
