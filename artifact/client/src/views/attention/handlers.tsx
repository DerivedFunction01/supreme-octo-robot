// Handlers — the original's renderHandlers() +
// renderHandler(). The list starts from the registries
// portion; storyboard frame 7's richer rows (decisions
// waiting, agent-clearable, muted types) are per-handler
// fields the registries payload does not carry, so each
// row fetches its handler detail portion independently
// and fills in when it lands — no whole-view block.
//
// The detail: the status card (Done / Ongoing / Tail /
// Blockers groups, quick verbs, the derived workbench
// line and its conflicts), the counts card (agent-
// clearable, breakthrough hit rate, muted types with
// Unmute, handler verbs), Your actions, Open items (the
// shared ItemCard), Posts to this thread, and Recent
// decisions — the ledgers on the kit's LogRow.

import { useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Card } from "@workhorse/kit/components/display/Card";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import {
  GroupedList,
  Row,
} from "@workhorse/kit/components/display/GroupedList";
import {
  LogRow,
  LogRowDrawer,
  type LogRowEntry,
} from "@workhorse/kit/components/display/LogRow";
import {
  StatusChip,
  type StatusTone,
} from "@workhorse/kit/components/display/StatusChip";
import { HandlerVerbButton, ItemCard } from "./item-card";
import {
  clock,
  dateToken,
  day,
  type HandlerFreshness,
  type HandlerPayload,
  type RegistriesPayload,
} from "./model";
import { api, call, staleText, usePortion } from "./transport";
import { BandHead, PageColumn, ScopeLine, SlotDot, ViewTitle, useAttentionUi } from "./ui";

/* ---------------- the list ---------------- */

export function HandlersView() {
  const ui = useAttentionUi();
  const registries = usePortion<RegistriesPayload>(
    "registries",
    () => call(api.getRegistries({})),
    ui.refreshKey,
  );
  const handlers = registries.data?.handlers ?? [];

  return (
    <PageColumn>
      {!registries.data ? (
        <ScopeLine>{registries.loading ? "Loading…" : "No handlers are registered."}</ScopeLine>
      ) : !handlers.length ? (
        <ScopeLine>No handlers are registered.</ScopeLine>
      ) : (
        <>
          <ScopeLine>
            Every posting thread and source.{staleText(registries.stale)}
          </ScopeLine>
          <GroupedList>
            {handlers.map((h) => (
              <HandlerRow
                key={h.handle}
                handle={h.handle}
                label={h.label || h.handle}
                slot={h.color_slot}
                freshness={h.freshness}
              />
            ))}
          </GroupedList>
        </>
      )}
    </PageColumn>
  );
}

const BINDING_TONES: Record<string, StatusTone> = {
  "live-seat": "ok",
  superseded: "warn",
  deleted: "fail",
  unresolvable: "idle",
  none: "idle",
};

const VERDICT_TONES: Record<string, StatusTone> = {
  current: "ok",
  stale: "warn",
  "dead-binding": "fail",
  unresolvable: "idle",
  "retired-with-cause": "idle",
};

/** One frame-7 row: the registry facts at once, the
 *  per-handler counts when its detail portion lands.
 *  The freshness record rides the registries payload
 *  itself (the handler-freshness plan): the binding
 *  state as its own chip beside the label, the verdict
 *  chip at the end, and the reconcile age, the last
 *  evidence, and the declaration age as their own
 *  lines — every string served, none derived here. A
 *  retired-with-cause row renders in the retired
 *  register: muted label, its cause named. */
function HandlerRow({
  handle,
  label,
  slot,
  freshness,
}: {
  handle: string;
  label: string;
  slot: number | undefined;
  freshness: HandlerFreshness | undefined;
}) {
  const ui = useAttentionUi();
  const detail = usePortion<HandlerPayload>(
    `handler:${handle}`,
    () => call(api.getHandler({ handle })),
    ui.refreshKey,
  );
  const d = detail.data;
  const decisions = d ? d.items.filter((it) => it.need === "owner_actionable").length : null;

  const facts: string[] = [];
  if (d) {
    if (decisions !== null)
      facts.push(
        decisions
          ? `${decisions} decision${decisions === 1 ? "" : "s"} waiting`
          : "Nothing waiting",
      );
    facts.push(`${d.agent_clearable_count} agent-clearable`);
    if (d.muted_types.length)
      facts.push(`${d.muted_types.length} muted type${d.muted_types.length === 1 ? "" : "s"}`);
    if (d.status?.status_label) facts.push(d.status.status_label);
  }

  const f = freshness;
  const retired = f?.verdict === "retired-with-cause";
  const subLines: string[] = [];
  if (facts.length) subLines.push(facts.join(" · "));
  else if (!f) subLines.push(handle);
  if (f) {
    if (retired) {
      subLines.push(
        f.cause_label ? `Retired — ${f.cause_label}` : "Retired — with cause",
      );
    } else if (f.last_reconcile_at) {
      subLines.push(
        f.reconcile_age_label
          ? `${f.verdict_label} — reconciled ${f.reconcile_age_label}`
          : f.verdict_label,
      );
    } else {
      subLines.push(f.verdict_label);
    }
    if (f.last_evidence)
      subLines.push(
        `Last evidence: ${f.last_evidence.kind_label}${
          f.last_evidence.age_label ? ` · ${f.last_evidence.age_label}` : ""
        } · ${f.last_evidence.ref}`,
      );
    if (f.declaration_age_days !== null && f.declaration_age_days !== undefined)
      subLines.push(
        `Declaration ${f.declaration_age_days} day${f.declaration_age_days === 1 ? "" : "s"} old`,
      );
  }

  return (
    <Row
      label={
        <span className="flex items-center gap-2">
          <SlotDot slot={slot} />
          <span style={retired ? { color: "var(--ui-content-muted)" } : undefined}>
            {label}
          </span>
          {f ? (
            <StatusChip
              tone={BINDING_TONES[f.binding_state] ?? "idle"}
              label={f.binding_label}
            />
          ) : null}
        </span>
      }
      sub={
        subLines.length === 1 ? (
          subLines[0]
        ) : (
          <span>
            {subLines.map((line, i) => (
              <span key={i} className="block">
                {line}
              </span>
            ))}
          </span>
        )
      }
      end={
        f || (decisions !== null && decisions > 0) ? (
          <>
            {f ? (
              <StatusChip
                tone={VERDICT_TONES[f.verdict] ?? "idle"}
                label={f.verdict_label}
              />
            ) : null}
            {decisions !== null && decisions > 0 ? (
              <StatusChip tone="fail" label={`${decisions} waiting`} />
            ) : null}
          </>
        ) : undefined
      }
      chevron
      onClick={() => ui.navigate(`#/attention/handlers/${encodeURIComponent(handle)}`)}
    />
  );
}

/* ---------------- the detail ---------------- */

export function HandlerDetailView({ handle }: { handle: string }) {
  const ui = useAttentionUi();
  const [openSend, setOpenSend] = useState<LogRowEntry | null>(null);
  const portion = usePortion<HandlerPayload>(
    `handler:${handle}`,
    () => call(api.getHandler({ handle })),
    ui.refreshKey,
  );
  const d = portion.data;

  if (!d) {
    return (
      <PageColumn>
        <ViewTitle>{handle}</ViewTitle>
        <ScopeLine>{portion.loading ? "Loading…" : "No such handler."}</ScopeLine>
      </PageColumn>
    );
  }

  const tid = d.thread_id
    ? d.thread_id.length > 14
      ? `${d.thread_id.slice(0, 6)}…${d.thread_id.slice(-4)}`
      : d.thread_id
    : null;
  const s = d.status;

  return (
    <PageColumn>
      <div className="mb-2">
        <Button variant="ghost" onClick={() => ui.navigate("#/attention/handlers")}>
          ← All handlers
        </Button>
      </div>
      <ViewTitle>{d.label}</ViewTitle>
      <ScopeLine>
        {d.handle}
        {tid ? ` · thread ${tid}` : ""}
        {staleText(portion.stale)}
      </ScopeLine>

      {s ? (
        <Card className="mb-3">
          <div className="mb-2">
            <StatusChip
              tone={s.need === "owner_actionable" ? "fail" : "info"}
              label={s.status_label || s.status_code}
            />
          </div>
          <p className="text-sm [overflow-wrap:anywhere]">{s.summary}</p>
          <p className="mt-1 text-[13px]" style={{ color: "var(--ui-content-muted)" }}>
            {day(s.at)}
          </p>
          {s.done?.length ? (
            <StatusGroup title="Done" lines={s.done.map((line) => `✓ ${line}`)} />
          ) : null}
          {s.ongoing?.length ? (
            <StatusGroup title="Ongoing" lines={s.ongoing.map((line) => `• ${line}`)} />
          ) : null}
          {s.tail?.length ? (
            <div className="mt-3">
              <p className="text-sm font-semibold">Tail</p>
              {s.tail.map((t, i) => (
                <p key={i} className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                  <StatusChip tone="idle" label={t.kind_label} />
                  <span className="min-w-0 [overflow-wrap:anywhere]">{t.title}</span>
                  <span style={{ color: "var(--ui-content-muted)" }}>
                    {t.owner === "owner" ? "· your tap" : "· closeout"}
                  </span>
                </p>
              ))}
            </div>
          ) : null}
          {s.blockers?.length ? (
            <div className="mt-3">
              <p className="text-sm font-semibold">Blocked</p>
              {s.blockers.map((b, i) => (
                <p key={i} className="mt-1 text-sm [overflow-wrap:anywhere]">
                  {b.summary}{" "}
                  <span style={{ color: "var(--ui-content-muted)" }}>
                    — clears when: {b.clearing_act} ({b.whose === "hard" ? "hard stop" : "yours"})
                  </span>
                </p>
              ))}
            </div>
          ) : null}
          {s.quick_verbs?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {s.quick_verbs.map((v) => (
                <HandlerVerbButton key={v.verb} handle={d.handle} verb={v.verb} label={v.label} />
              ))}
            </div>
          ) : null}
          {s.derived ? <DerivedLine derived={s.derived} /> : null}
        </Card>
      ) : null}

      <Card className="mb-3">
        <p className="text-sm">
          <b>{d.agent_clearable_count}</b> agent-clearable open
        </p>
        <p className="mt-1 text-sm">
          Breakthrough hit rate:{" "}
          <b>
            {d.breakthrough_hit_rate === null
              ? "no deliveries yet"
              : `${Math.round(d.breakthrough_hit_rate * 100)}%`}
          </b>
        </p>
        {d.muted_types.map((m) => (
          <p key={m.kind} className="mt-1.5 flex flex-wrap items-center gap-2 text-sm">
            <span>Muted: {m.label}</span>
            <Button
              variant="ghost"
              onClick={async () => {
                try {
                  await call(api.unmuteHandler({ handle, kind: m.kind }));
                  ui.notify("Unmuted");
                  ui.refresh();
                } catch (e) {
                  ui.notify(`Unmute failed: ${e instanceof Error ? e.message : String(e)}`);
                }
              }}
            >
              Unmute
            </Button>
          </p>
        ))}
        {d.handler_verbs?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {d.handler_verbs.map((v) => (
              <HandlerVerbButton key={v.verb} handle={d.handle} verb={v.verb} label={v.label} />
            ))}
          </div>
        ) : null}
      </Card>

      {d.owner_actions?.length ? (
        <>
          <BandHead label="Your actions" />
          <GroupedList>
            {d.owner_actions.map((a, i) => (
              <LogRow
                key={i}
                entry={{
                  dateToken: dateToken(a.at),
                  time: clock(a.at),
                  headline: a.verb_label,
                  meta: [
                    a.actor === "rule" ? `by rule ${a.rule_id ?? ""}${a.shadow ? " (shadow)" : ""}` : "",
                    a.note ?? "",
                  ]
                    .filter(Boolean)
                    .join(" · "),
                }}
              />
            ))}
          </GroupedList>
        </>
      ) : null}

      <BandHead label="Open items" />
      {d.items.length ? (
        d.items.map((it) => <ItemCard key={it.id} item={it} band="" />)
      ) : (
        <EmptyState message="Nothing is waiting." />
      )}

      {d.sends?.length ? (
        <>
          <BandHead label="Posts to this thread" />
          <GroupedList>
            {d.sends.map((send, i) => {
              const entry: LogRowEntry = {
                dateToken: dateToken(send.at),
                time: clock(send.at),
                headline: send.template,
                kind:
                  send.mode === "shadow"
                    ? { label: "Shadow", tone: "warn" }
                    : { label: send.outcome_label || send.outcome, tone: "ok" },
                meta: [
                  `v${send.version} · attempt ${send.attempt}`,
                  `while ${send.presence_label || send.presence}`,
                  send.dispatch ? send.dispatch.state_label : "",
                  send.dispatch?.state === "delivered" && send.dispatch.delivered_at
                    ? `delivered ${day(send.dispatch.delivered_at)}`
                    : "",
                ]
                  .filter(Boolean)
                  .join(" · "),
                detail: {
                  message: send.text,
                  factsLabel: "Post",
                  facts: [
                    { label: "Template", value: send.template },
                    { label: "Version", value: `v${send.version}` },
                    { label: "Attempt", value: String(send.attempt) },
                    { label: "Presence", value: send.presence_label || send.presence },
                    ...(send.dispatch
                      ? [{ label: "Dispatch", value: send.dispatch.state_label }]
                      : []),
                  ],
                },
              };
              return <LogRow key={i} entry={entry} onOpen={() => setOpenSend(entry)} />;
            })}
          </GroupedList>
          <LogRowDrawer entry={openSend} onClose={() => setOpenSend(null)} />
        </>
      ) : null}

      {d.auto_applied?.length ? (
        <>
          <BandHead label="Recent decisions" />
          <GroupedList>
            {d.auto_applied.map((l, i) => (
              <LogRow
                key={i}
                entry={{
                  dateToken: dateToken(l.at),
                  time: clock(l.at),
                  headline: l.decision_label || l.decision,
                  meta: [l.wait_class ?? "", l.rule_id ? `rule ${l.rule_id}` : "", l.shadow ? "shadow" : ""]
                    .filter(Boolean)
                    .join(" · "),
                }}
              />
            ))}
          </GroupedList>
        </>
      ) : null}
    </PageColumn>
  );
}

function StatusGroup({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="mt-3">
      <p className="text-sm font-semibold">{title}</p>
      {lines.map((line, i) => (
        <p key={i} className="mt-0.5 text-sm [overflow-wrap:anywhere]">
          {line}
        </p>
      ))}
    </div>
  );
}

function DerivedLine({
  derived,
}: {
  derived: NonNullable<HandlerPayload["status"]>["derived"];
}) {
  if (!derived) return null;
  return (
    <>
      {!derived.available ? (
        <p className="mt-3 text-sm" style={{ color: "var(--ui-content-secondary)" }}>
          Workbench state unavailable — {derived.reason ?? ""}
          {derived.last_good_at ? ` · last good ${day(derived.last_good_at)}` : ""}
        </p>
      ) : derived.todos ? (
        <p className="mt-3 text-sm" style={{ color: "var(--ui-content-secondary)" }}>
          Workbench — {derived.todos.done}/{derived.todos.total} todos done
          {derived.todos.blocked ? ` · ${derived.todos.blocked} blocked` : ""}
          {derived.todos.doing ? ` · ${derived.todos.doing} in progress` : ""}
        </p>
      ) : null}
      {(derived.conflicts ?? []).map((c, i) => (
        <p key={i} className="mt-1.5 flex flex-wrap items-center gap-2 text-sm">
          <StatusChip tone="warn" label="Conflict" />
          <span className="min-w-0 [overflow-wrap:anywhere]">{c.message}</span>
        </p>
      ))}
    </>
  );
}
