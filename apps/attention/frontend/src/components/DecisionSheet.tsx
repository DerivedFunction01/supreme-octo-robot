// The decision sheet: the item's face — its served verb set,
// its options, an optional note, and its decision history.
// Confirming records the verdict at the tap (contract 05,
// ATT2): the store validates the verb against the served
// set, mints the send through record_send, and moves the
// item into the awaiting band. Validation failures surface
// here, in the sheet, and record nothing.
import { useMemo, useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";
import { SegmentedControl } from "@workhorse/kit/components/controls/SegmentedControl";
import { Field, Input } from "@workhorse/kit/components/controls/Fields";
import { GroupedList } from "@workhorse/kit/components/display/GroupedList";
import { Toggle } from "@workhorse/kit/components/controls/Toggle";
import { LabeledCheckbox } from "@workhorse/kit/components/controls/Checkbox";
import {
  LogRow,
  LogRowDrawer,
  type LogRowEntry,
  type LogRowTone,
} from "@workhorse/kit/components/display/LogRow";
import { useDataSource } from "../attention/useStore";
import { verbLabel } from "../attention/verb-labels";
import type { DecisionHistoryEntry, ItemView } from "../attention/types";
import { HandlerChip } from "./chips";
import { Group, GroupLabel, RadioRow } from "./groups";
import { ConfirmDialog } from "./ConfirmDialog";

/** The confirm texts (the original frontend's, verbatim):
 *  a type mute reaches every open item of the type, and a
 *  done that does not clear at the source leaves the
 *  source's copy standing. */
export const MUTE_TYPE_CONFIRM =
  "Mute every open item of this type from this handler? They stay hidden until you unmute the type on the handler's page.";
export const DONE_CONFIRM =
  "Mark done here? It will not clear at the source — the source keeps its own copy.";

/** The verdict verbs a make_rule flag may ride (the
 *  backend promotes verdict taps; bookmarks and the
 *  promotion verbs themselves never carry it). */
const PROMOTABLE = new Set([
  "decide",
  "approve",
  "deny",
  "push",
  "continue",
  "accept",
  "reject",
  "close_on_verify",
  "accept_review",
  "reject_incomplete",
  "go",
]);

const OUTCOME_TONE: Record<DecisionHistoryEntry["outcome"], LogRowTone> = {
  fulfilled: "ok",
  failed: "fail",
  stalled: "warn",
  queued: "info",
  sent: "warn",
  recorded: "idle",
};

/** One decision-history entry as the kit LogRow's entry
 *  shape (timeline-component study: the outcome is the
 *  badge, the decision is the headline, the send reference
 *  rides the meta line; the full failure text and the
 *  delivery record open in the drawer). A pure projection
 *  of the served entry — every string below is a served
 *  field, formatted. */
function historyEntry(h: DecisionHistoryEntry): LogRowEntry {
  const at = new Date(h.at);
  const dateToken = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(at);
  const time = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(at);
  const decision = h.option_id ?? verbLabel(h.verb);
  const outcomeWord = h.outcome.charAt(0).toUpperCase() + h.outcome.slice(1);
  const meta: string[] = [];
  if (h.send_id) meta.push(`ref ${h.send_id}`);
  if (h.note) meta.push(h.note);
  const hasDetail = Boolean(h.failure || h.send_id || h.note);
  return {
    dateToken,
    time,
    headline: decision,
    kind: { label: outcomeWord, tone: OUTCOME_TONE[h.outcome] },
    meta: meta.length > 0 ? meta.join(" · ") : undefined,
    detail: hasDetail
      ? {
          message: h.failure ?? decision,
          factsLabel: "Decision record",
          facts: [
            { label: "Outcome", value: outcomeWord },
            { label: "Verb", value: verbLabel(h.verb) },
            ...(h.option_id ? [{ label: "Option", value: h.option_id }] : []),
            ...(h.send_id
              ? [{ label: "Send ref", value: h.send_id, mono: true }]
              : []),
            ...(h.note ? [{ label: "Note", value: h.note }] : []),
          ],
        }
      : undefined,
  };
}

let keyCounter = 0;

export function DecisionSheet({
  item,
  onClose,
}: {
  item: ItemView | null;
  onClose: () => void;
}) {
  const ds = useDataSource();
  const [option, setOption] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [openHistory, setOpenHistory] = useState<number | null>(null);
  // The snooze panel's choices: the served return time,
  // return-on-activity, and the note it resumes with.
  const [snoozeAt, setSnoozeAt] = useState<string | null>(null);
  const [snoozeActivity, setSnoozeActivity] = useState(true);
  const [resumeNote, setResumeNote] = useState("");
  // The promotion controls: rule_it arms, then the option
  // tap rules it standing; the checkbox rides the next
  // verdict tap as the deliberate make_rule flag.
  const [ruleArmed, setRuleArmed] = useState(false);
  const [makeRule, setMakeRule] = useState(false);
  const [confirmVerb, setConfirmVerb] = useState<string | null>(null);
  const idempotencyKey = useMemo(() => `sheet-${item?.id ?? "none"}-${++keyCounter}`, [item?.id]);

  // A fresh item opens with a fresh form: the snooze
  // panel starts on the first served time and the served
  // activity default.
  const [formFor, setFormFor] = useState<string | null>(null);
  if (item && formFor !== item.id) {
    setFormFor(item.id);
    setOption(null);
    setNote("");
    setError(null);
    setSnoozeAt(item.snooze_options.times[0]?.at ?? null);
    setSnoozeActivity(item.snooze_options.on_activity);
    setResumeNote("");
    setRuleArmed(false);
    setMakeRule(false);
    setConfirmVerb(null);
  }

  if (!item) return null;

  const plainVerbs = item.verbs.filter(
    (v) => v !== "decide" && v !== "snooze" && v !== "rule_it",
  );
  const hasSnooze = item.verbs.includes("snooze");
  const needsOption = item.verbs.includes("decide");
  const hasRuleIt = item.verbs.includes("rule_it");
  const canPromote =
    needsOption || hasRuleIt || plainVerbs.some((v) => PROMOTABLE.has(v));

  const act = (verb: string, optionId?: string | null) => {
    const result = ds.decide(item.id, {
      verb,
      option_id: optionId ?? null,
      note,
      idempotency_key: idempotencyKey,
      ...(verb === "snooze"
        ? {
            return_at: snoozeAt,
            return_on_activity: snoozeActivity,
            resume_note: resumeNote.trim() ? resumeNote : null,
          }
        : {}),
      ...(makeRule && PROMOTABLE.has(verb) ? { make_rule: true } : {}),
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setOption(null);
    setNote("");
    setError(null);
    setRuleArmed(false);
    setMakeRule(false);
    onClose();
  };

  /** The confirm gates: muting a type always confirms;
   *  done confirms when the item does not clear at the
   *  source. Everything else posts at the tap. */
  const requestAct = (verb: string, optionId?: string | null) => {
    if (verb === "mute_type" || (verb === "done" && !item.clears_at_source)) {
      setConfirmVerb(verb);
      return;
    }
    act(verb, optionId);
  };

  // A plain action row: the kit Sheet's footer wraps and
  // shrink-protects its children (kit cure, 2026-11-15 —
  // before it, this sheet's four actions ellipsized to
  // stubs at phone width and the app wrapped its own).
  const footer = (
    <>
      <Button variant="ghost" onClick={onClose}>
        Cancel
      </Button>
      {hasSnooze ? (
        <Button variant="secondary" onClick={() => act("snooze")}>
          Snooze
        </Button>
      ) : null}
      {plainVerbs.map((verb) => (
        <Button key={verb} variant="primary" onClick={() => requestAct(verb)}>
          {verbLabel(verb)}
        </Button>
      ))}
      {hasRuleIt ? (
        <Button
          variant={ruleArmed ? "primary" : "secondary"}
          onClick={() => setRuleArmed((a) => !a)}
        >
          {verbLabel("rule_it")}
        </Button>
      ) : null}
      {needsOption || ruleArmed ? (
        <Button
          variant="primary"
          disabled={!option}
          onClick={() =>
            option && act(ruleArmed ? "rule_it" : "decide", option)
          }
        >
          {option
            ? `${ruleArmed ? "Rule it" : "Decide"} · ${item.options?.find((o) => o.id === option)?.label}`
            : ruleArmed
              ? "Tap the option to rule standing"
              : "Choose an option"}
        </Button>
      ) : null}
    </>
  );

  return (
    <>
    <Sheet open title={item.title} onClose={onClose} footer={footer}>
      {/* The kit Sheet's content region scrolls natively
          (kit cure, 2026-11-15); the content rides it. */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <HandlerChip label={item.handler_label} severity={item.severity} />
          <span className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
            {item.waiting_label}
          </span>
        </div>
        {item.rule_hint ? (
          <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
            {item.rule_hint}
          </p>
        ) : null}

        {item.failure ? (
          <div
            className="rounded-md px-3 py-2 text-sm"
            style={{
              backgroundColor: "color-mix(in srgb, var(--wb-status-hard-gate) 12%, transparent)",
              color: "var(--wb-status-hard-gate-text)",
            }}
            role="alert"
          >
            {item.failure}
          </div>
        ) : null}

        {item.history.length > 0 ? (
          <div>
            <div className="glabel">Decision history</div>
            <GroupedList>
              {item.history.map((h, i) => (
                <LogRow
                  key={i}
                  entry={historyEntry(h)}
                  onOpen={() => setOpenHistory(i)}
                />
              ))}
            </GroupedList>
            <LogRowDrawer
              entry={
                openHistory !== null && item.history[openHistory]
                  ? historyEntry(item.history[openHistory])
                  : null
              }
              onClose={() => setOpenHistory(null)}
            />
          </div>
        ) : null}

        {needsOption && item.options ? (
          <Field label="Decision">
            {(id) => (
              <div id={id}>
                <SegmentedControl
                  ariaLabel="Decision options"
                  options={(item.options ?? []).map((o) => ({ value: o.id, label: o.label }))}
                  value={option ?? ""}
                  onChange={(v) => {
                    setOption(v);
                    setError(null);
                  }}
                />
              </div>
            )}
          </Field>
        ) : null}

        {ruleArmed ? (
          <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
            Now tap the option to rule standing.
          </p>
        ) : null}

        {hasSnooze ? (
          <div>
            <GroupLabel>Snooze until — or until there is new activity on it</GroupLabel>
            <Group>
              {item.snooze_options.times.map((t) => (
                <RadioRow
                  key={t.at}
                  label={t.label}
                  selected={snoozeAt === t.at}
                  onSelect={() => setSnoozeAt(t.at)}
                />
              ))}
            </Group>
            {item.snooze_options.on_activity ? (
              <div className="mt-2">
                <Toggle
                  label="Return on new activity"
                  checked={snoozeActivity}
                  onChange={setSnoozeActivity}
                />
              </div>
            ) : null}
            <div className="mt-2">
              <Field label="Resume note">
                {(id) => (
                  <Input
                    id={id}
                    value={resumeNote}
                    onChange={(e) => setResumeNote(e.target.value)}
                    placeholder="What it comes back with"
                  />
                )}
              </Field>
            </div>
          </div>
        ) : null}

        <Field label="Note (optional)">
          {(id) => (
            <Input
              id={id}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Rides the decision record"
            />
          )}
        </Field>

        {canPromote && !ruleArmed ? (
          <LabeledCheckbox
            label="Also make this a standing rule"
            checked={makeRule}
            onChange={setMakeRule}
          />
        ) : null}

        {error ? (
          <p className="text-sm" role="alert" style={{ color: "var(--wb-status-hard-gate-text)" }}>
            {error}
          </p>
        ) : null}
      </div>
    </Sheet>
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
        if (verb) act(verb);
      }}
      onCancel={() => setConfirmVerb(null)}
    />
    </>
  );
}
