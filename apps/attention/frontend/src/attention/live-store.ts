// The LIVE attention store: AttentionDataSource over the
// attention backend's api/1 (pipeline/attention, served on
// the platform process). The published form's data source —
// the integration entry constructs this store by default;
// the mock store remains the standalone preview's source.
//
// Shape discipline (the sibling adapters' rule): the
// backend's payloads are the shapes of record; this store
// projects them into the app's view types and derives
// nothing the backend serves. Where a view field encodes
// something no route serves, the field serves its honest
// absence and the lane report names it (item detail, the
// fulfilled ledger, the waits list, digest settings writes).
//
// The interface is synchronous (the verdict-at-the-tap
// form), so writes compose their result at the tap from
// the snapshot — validated against the served verb sets,
// options, and registries with the same checks the mock
// mirrors from the backend — and POST in the background;
// the next poll reconciles from the server's state, which
// is always the truth. Idempotency keys short-circuit
// client-side exactly as the mock's guards do.
//
// Refresh model: getters are synchronous over a snapshot
// cache. Poll cadences follow the surface's own shape —
// the glance portions (glance / today / digest) at 15 s,
// handler details and item waits at 30 s, the slow
// registries (registries / rules / programmes / sends) at
// 60 s. One request per portion in flight; a failed fetch
// keeps the last-good portion (stale data, never a blank).
// now() is the real clock — the mock's scenario clock
// stays with the mock.
//
// The store is one class split by surface: state,
// transport, and shared derivations live in
// ./live-store/base.ts; the write surface in
// ./live-store/writes.ts; the read surface (the getters
// below) here.

import { LiveStoreWrites } from "./live-store/writes";
import type {
  ActionRuleView,
  DigestView,
  GlanceView,
  HandlerDetailView,
  HandlerStatusView,
  HandlersView,
  OwnerActionView,
  ProgrammeCardView,
  RegistriesView,
  RuleView,
  SendRow,
  Severity,
  TodayView,
  AttentionDataSource,
} from "./types";
import {
  ServerItem,
  ServerSend,
} from "./live-store/server-types";
import {
  timeLabel,
  durationLabel,
  classLabel,
  clockFmt,
  dateFmt,
  weekdayFmt,
} from "./live-store/time";

export class LiveAttentionStore extends LiveStoreWrites implements AttentionDataSource {
  getGlance = (night = false): GlanceView => {
    const now = new Date();
    const glance = this.glance;
    const presence = this.getPresence();
    const clockLabel = clockFmt.format(glance ? new Date(glance.clock.now) : now);
    const dateLabel = dateFmt.format(glance ? new Date(glance.clock.now) : now);
    const nextWindow = glance?.clock.next_window_at ?? this.digest?.window.next_at ?? null;
    const windowRow = nextWindow
      ? [{ label: "Digest window", value: timeLabel(nextWindow) }]
      : [];
    const breakthroughItems = this.bandItems("breakthrough").map((i) => this.toItemView(i));

    if (night || presence.mode === "away") {
      // Presence-filtered (contract 09): breakthroughs
      // listed, next-due withheld. The night frame serves
      // the same live set with the real presence and the
      // real clock — the mock's fabricated night persona
      // (a fixed 11:48, an invented away record) has no
      // live counterpart and is not reproduced.
      const held = glance?.held_count ?? 0;
      return {
        clock_label: clockLabel,
        date_label: dateLabel,
        presence,
        count: glance?.breakthrough_count ?? breakthroughItems.length,
        count_label: `${glance?.breakthrough_count ?? breakthroughItems.length} needs you`,
        sub_label: presence.expectation,
        next: breakthroughItems,
        rows_label: night ? "Tomorrow" : "Today",
        rows: windowRow,
        down_sources: glance?.down_sources ?? [],
        held_label:
          held > 0
            ? `${held} held for your return — everything held surfaces at the next digest, or when you're Active again`
            : null,
      };
    }

    const ownerItems = [...this.bandItems("breakthrough"), ...this.bandItems("needs_decision")].sort(
      (a, b) => Date.parse(a.waiting_since) - Date.parse(b.waiting_since),
    );
    const dueRows = this.allOpenItems()
      .filter((i) => i.due_at)
      .sort((a, b) => Date.parse(a.due_at as string) - Date.parse(b.due_at as string))
      .map((i) => ({ label: i.title, value: timeLabel(i.due_at as string) }));
    const oldest = ownerItems.length
      ? durationLabel(Date.now() - Math.min(...ownerItems.map((i) => Date.parse(i.waiting_since))))
      : null;
    const count = glance?.decision_count ?? ownerItems.length;
    return {
      clock_label: clockLabel,
      date_label: dateLabel,
      presence,
      count,
      count_label: `${count} need you`,
      sub_label:
        presence.mode === "focus"
          ? presence.expectation
          : `decisions waiting${oldest ? ` · oldest ${oldest}` : ""}`,
      next: ownerItems.slice(0, 2).map((i) => this.toItemView(i)),
      rows_label: "Today",
      rows: [...windowRow, ...dueRows],
      down_sources: glance?.down_sources ?? [],
      held_label:
        presence.mode === "focus" && (glance?.held_count ?? 0) > 0
          ? `${glance?.held_count} held while you focus — everything held surfaces at the next digest, or when you're Active again`
          : null,
    };
  };

  getToday = (): TodayView => {
    const now = new Date();
    const nextWindow = this.digest?.window.next_at ?? this.glance?.clock.next_window_at ?? null;
    const dateLabel = dateFmt.format(now);
    const fyiItems = this.bandItems("fyi");
    const newestFyi = fyiItems.length
      ? [...fyiItems].sort((a, b) => Date.parse(b.waiting_since) - Date.parse(a.waiting_since))[0]
      : null;
    return {
      date_label: dateLabel,
      subtitle: `${dateLabel} · next digest window ${nextWindow ? timeLabel(nextWindow) : "—"}`,
      presence: this.getPresence(),
      decision_count: this.today?.headline_count ?? 0,
      breakthrough: this.bandItems("breakthrough").map((i) => this.toItemView(i)),
      decisions: this.bandItems("needs_decision").map((i) => this.toItemView(i)),
      awaiting: this.bandItems("decided").map((i) => this.toAwaitingView(i)),
      // Bands are exclusive: a decidable item due today
      // stands here, not in needs_decision. Items carrying
      // verbs render as decision cards (due_decidable);
      // only the rest stay plain schedule rows.
      due_decidable: this.bandItems("due_today")
        .filter((i) => i.verbs.length > 0)
        .map((i) => this.toItemView(i)),
      due_today: [
        { label: "Digest window", sub: "All handlers", value: nextWindow ? timeLabel(nextWindow) : "—" },
        ...this.bandItems("due_today")
          .filter((i) => i.verbs.length === 0)
          .map((i) => ({
            label: i.title,
            sub: i.handler.label,
            value: i.due_at ? timeLabel(i.due_at) : "",
          })),
      ],
      waiting_on_others: this.bandItems("waiting").map((i) => this.toItemView(i)),
      fyi: {
        count: fyiItems.length,
        newest_title: newestFyi ? newestFyi.title : null,
        items: fyiItems.map((i) => this.toItemView(i)),
      },
      // The bands' served unavailability, verbatim: the
      // view renders the warning where the original did —
      // a down source's items are missing from this
      // picture and the picture must say so.
      unavailable: (this.today?.bands ?? [])
        .filter((b) => b.unavailable)
        .map((b) => ({
          reason: b.unavailable?.reason ?? "",
          last_good_label: b.unavailable?.last_good_at
            ? `${weekdayFmt.format(new Date(b.unavailable.last_good_at))} · ${timeLabel(b.unavailable.last_good_at)}`
            : "an earlier copy",
        })),
    };
  };

  getHandlers = (): HandlersView => {
    const rows = (this.registries?.handlers ?? [])
      .filter((h) => !h.retired)
      .map((h) => {
        const open = this.allOpenItems().filter((i) => i.handler.handle === h.handle);
        const waiting = open.filter(
          (i) => i.tier === "breakthrough" || this.bandItems("needs_decision").includes(i),
        ).length;
        const detail = this.handlerDetails.get(h.handle);
        const clearable = detail?.agent_clearable_count ?? 0;
        const mutedCount = detail?.muted_types.length ?? 0;
        let sub: string;
        if (waiting > 0) {
          sub = `${waiting} decision${waiting === 1 ? "" : "s"} waiting${clearable ? ` · ${clearable} agent-clearable` : ""}`;
        } else if (open.length > 0) {
          sub = `${open.length} item${open.length === 1 ? "" : "s"} open`;
        } else {
          sub = `Nothing waiting${mutedCount ? ` · ${mutedCount} muted type${mutedCount === 1 ? "" : "s"}` : ""}`;
        }
        const severity = this.handlerSeverity(h.handle);
        return {
          handle: h.handle,
          label: h.label,
          color_slot: h.color_slot,
          icon: h.icon,
          sub_label: sub,
          severity,
          trailing:
            waiting > 0
              ? { label: `${waiting} waiting`, severity }
              : open.length > 0
                ? { label: `${open.length} open`, severity: "idle" as Severity }
                : null,
        };
      });
    const totalWaiting = rows.reduce((n, r) => {
      const m = /^(\d+) waiting$/.exec(r.trailing?.label ?? "");
      return n + (m ? Number(m[1]) : 0);
    }, 0);
    return {
      subtitle: `${rows.length} handlers · ${totalWaiting} decisions waiting`,
      rows,
    };
  };

  getHandlerDetail = (handle: string): HandlerDetailView | null => {
    const row = this.handlerRow(handle);
    if (!row) return null;
    const detail = this.handlerDetails.get(handle);
    if (!detail) void this.refreshDetails();
    const openSource = detail?.items ?? this.allOpenItems().filter((i) => i.handler.handle === handle);
    // The backend serves every live item for the handler,
    // FYI tier included — no client-side tier filter.
    const openItems = openSource;
    const waiting = openItems.filter(
      (i) => i.need === "owner_actionable",
    ).length;
    const status: HandlerStatusView | null = detail?.status
      ? {
          status_code: detail.status.status_code,
          status_label: detail.status.status_label,
          need: detail.status.need,
          summary: detail.status.summary,
          at_label: timeLabel(detail.status.at),
          age_hours: Math.round(((Date.now() - Date.parse(detail.status.at)) / 3_600_000) * 10) / 10,
          done: detail.status.done ?? null,
          ongoing: detail.status.ongoing ?? null,
          tail: (detail.status.tail ?? []).map((t) => ({
            kind: t.kind,
            kind_label: t.kind_label,
            title: t.title,
            owner_label: t.owner === "owner" ? "your tap" : "closeout",
          })),
          blockers: (detail.status.blockers ?? []).map((b) => ({
            summary: b.summary,
            clearing_act: b.clearing_act,
            whose_label: b.whose === "hard" ? "hard stop" : "yours",
          })),
          quick_verbs: (detail.status.quick_verbs ?? []).map((v) => ({
            verb: v.verb,
            label: v.label,
            primary: v.primary,
            rule_hint: v.rule_hint ?? null,
          })),
          derived: detail.status.derived
            ? {
                label: !detail.status.derived.available
                  ? `Workbench state unavailable — ${detail.status.derived.reason ?? ""}${
                      detail.status.derived.last_good_at
                        ? ` · last good ${timeLabel(detail.status.derived.last_good_at)}`
                        : ""
                    }`
                  : detail.status.derived.todos
                    ? `Workbench — ${detail.status.derived.todos.done}/${detail.status.derived.todos.total} todos done${
                        detail.status.derived.todos.blocked
                          ? ` · ${detail.status.derived.todos.blocked} blocked`
                          : ""
                      }${
                        detail.status.derived.todos.doing
                          ? ` · ${detail.status.derived.todos.doing} in progress`
                          : ""
                      }`
                    : "",
                conflicts: (detail.status.derived.conflicts ?? []).map((c) => c.message),
              }
            : null,
        }
      : null;
    const ownerActions: OwnerActionView[] = [...(detail?.owner_actions ?? [])]
      .slice(-10)
      .reverse()
      .map((a) => ({
        id: a.id,
        verb: a.verb,
        verb_label: a.verb_label,
        at_label: timeLabel(a.at),
        note: a.note,
        actor_label: a.actor === "rule" ? `rule ${a.rule_id ?? ""}`.trim() : a.actor,
        shadow: a.shadow ?? false,
      }));
    return {
      handler: {
        handle: row.handle,
        label: row.label,
        color_slot: row.color_slot,
        icon: row.icon,
        thread_id: row.thread_id ?? "",
        ui_surface: row.ui_surface,
        retired: row.retired,
      },
      subtitle: `${row.label} · ${waiting} decision${waiting === 1 ? "" : "s"} waiting`,
      open_items: openItems.map((i) => this.toItemView(i)),
      awaiting: this.bandItems("decided")
        .filter((i) => i.handler.handle === handle)
        .map((i) => this.toAwaitingView(i)),
      agent_clearable_label: `${detail?.agent_clearable_count ?? 0} items`,
      breakthrough_hit_rate:
        detail?.breakthrough_hit_rate == null
          ? "—"
          : `${Math.round(detail.breakthrough_hit_rate * 100)}%`,
      muted_types: (detail?.muted_types ?? []).map((m) => ({ type: m.label, muted: true })),
      status,
      handler_verbs: (detail?.handler_verbs ?? []).map((v) => ({
        verb: v.verb,
        label: v.label,
        primary: v.primary,
        rule_hint: v.rule_hint ?? null,
      })),
      owner_actions: ownerActions,
      sends: (detail?.sends ?? []).map((s) => this.toSendRow(s)),
      auto_applied: (detail?.auto_applied ?? []).map((a) => ({
        at: a.at,
        wait_class: a.wait_class,
        decision_label: a.decision_label,
        rule_id: a.rule_id,
        shadow: a.shadow,
      })),
    };
  };

  getProgrammes = (): ProgrammeCardView[] => {
    return this.programmes
      .filter((p) => !p.retired)
      .map((p) => {
        const inProgramme = (i: ServerItem) => p.handles.includes(i.handler.handle);
        const openDecisions = [
          ...this.bandItems("breakthrough"),
          ...this.bandItems("needs_decision"),
        ].filter(inProgramme).length;
        const awaiting = this.bandItems("decided").filter(inProgramme).length;
        return {
          slug: p.slug,
          label: p.label,
          handles: p.handles.map((handle) => {
            const h = this.handlerRow(handle);
            return { handle, label: h?.label ?? handle, color_slot: h?.color_slot ?? 0 };
          }),
          cadence_label: `${p.cadence_minutes} min cadence`,
          band_label: p.staffing_band
            ? `staffing band ${p.staffing_band.min}–${p.staffing_band.max}`
            : "staffing band —",
          escalation_label: `escalates after ${p.escalation_hours} h`,
          venue_label: p.venue === "colab" ? "Colab venue" : "No venue",
          open_decisions: openDecisions,
          awaiting,
          rule_text: p.rule_text,
        };
      });
  };

  getDigest = (): DigestView => {
    const digest = this.digest;
    const nextAt = digest?.window.next_at ?? this.glance?.clock.next_window_at ?? null;
    const times = digest?.window.times ?? [];
    const enabledTimes = digest?.window.enabled_times;
    const windows = times.map((time) => {
      const hour = Number(time.split(":")[0]);
      return {
        id: time,
        label: hour < 11 ? "Morning" : hour < 15 ? "Midday" : "Evening",
        time,
        enabled: enabledTimes ? enabledTimes.includes(time) : true,
      };
    });
    // The next window's label + day, from the served
    // next_at's own wall fields (the server's zone rides
    // the ISO) matched against the served window times.
    let nextLabel = "No window enabled";
    let nextDetail = "";
    if (nextAt) {
      const wall = /T(\d{2}):(\d{2})/.exec(nextAt);
      const match = wall ? windows.find((w) => w.time === `${wall[1]}:${wall[2]}`) : undefined;
      const serverNow = this.glance?.clock.now;
      const sameDay = serverNow ? serverNow.slice(0, 10) === nextAt.slice(0, 10) : true;
      nextLabel = match ? `${sameDay ? "Today" : "Tomorrow"} · ${match.label}` : timeLabel(nextAt);
      nextDetail = `${timeLabel(nextAt)} · in ${durationLabel(Date.parse(nextAt) - Date.now())}`;
    }
    const today = this.getToday();
    const counts = {
      decisions: today.decision_count,
      waiting: today.waiting_on_others.length,
      fyi: today.fyi.count,
    };
    // The include flags are the server's stored prefs
    // (AC-8): the preview composes from the served flags
    // and the live counts — arithmetic over served data.
    const include = digest?.include ?? { decisions: true, waiting: true, fyi: true };
    const parts: string[] = [];
    if (include.decisions) parts.push(`${counts.decisions} decisions`);
    if (include.waiting) parts.push(`${counts.waiting} waiting`);
    if (include.fyi) parts.push(`${counts.fyi} FYI`);
    return {
      windows,
      next_label: nextLabel,
      next_detail: nextDetail,
      include,
      preview_label: parts.length
        ? `Will include: ${parts.join(" · ")}`
        : "Will include: nothing — all sections off",
      content: {
        sections: (digest?.sections ?? []).map((s) => ({
          kind: s.kind,
          kind_label: s.kind_label,
          owner_label: s.owner_label,
          rows: s.rows.map((r) => ({
            title: r.title,
            handle: r.handle,
            handler_label: r.handler_label,
            provenance_label: r.provenance_label,
            at_label: timeLabel(r.at),
            age_label: r.age_label,
          })),
        })),
        stalls: digest?.stalls ?? [],
        staffing: {
          available: digest?.staffing.available ?? false,
          reason: digest?.staffing.reason ?? null,
          idle_minutes_total: digest?.staffing.idle_minutes_total ?? 0,
          rows: (digest?.staffing.rows ?? []).map((r) => ({
            topic: r.topic,
            handle: r.handle,
            handler_label: r.handler_label || r.kind_label,
            kind: r.kind,
            kind_label: r.kind_label,
            detail: r.detail,
            escalation_label: r.escalation === "main" ? "Escalated to Main" : null,
          })),
        },
        topics: (digest?.topics ?? []).map((t) => ({
          topic: t.topic,
          worst_label: t.worst_label,
          stalls: t.stalls,
          open_counts: t.open_counts,
          lanes: t.lanes.map((l) => ({
            handle: l.handle,
            label: l.label,
            status_label: l.status_label,
            stale: l.stale,
            quick_verbs: l.quick_verbs.map((v) => ({
              verb: v.verb,
              label: v.label,
              primary: v.primary,
              rule_hint: v.rule_hint ?? null,
            })),
          })),
        })),
        parked_plans: {
          available: digest?.parked_plans.available ?? false,
          reason: digest?.parked_plans.reason ?? null,
          plans: (digest?.parked_plans.plans ?? []).map((p) => ({
            title: p.title ?? p.path ?? "",
            project: p.project,
            age_label:
              p.age_days === null || p.age_days === undefined
                ? ""
                : `waiting ${p.age_days} day${p.age_days === 1 ? "" : "s"}`,
          })),
        },
      },
    };
  };

  getRegistries = (): RegistriesView => {
    const r = this.registries;
    return {
      status_codes: r?.status_codes ?? [],
      fields: r?.fields ?? [],
      wait_classes: r?.wait_classes ?? [],
      operators: r?.operators ?? [],
      triggers: r?.triggers ?? [],
      actions: r?.actions ?? [],
      templates: r?.templates ?? [],
      item_kinds: r?.item_kinds ?? [],
      handlers: (r?.handlers ?? []).map((h) => ({
        handle: h.handle,
        label: h.label,
        thread_id: h.thread_id ?? "",
      })),
    };
  };

  getRules = (): RuleView[] => {
    return [...this.rules]
      .sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id))
      .map((r) => ({ ...r, name: r.name ?? null }));
  };

  getActionRules = (): ActionRuleView[] => {
    const createdLabels: Record<string, string> = {
      proposal: "From a proposal",
      rule_it: "Ruled standing",
      approve_rule: "Approve + make rule",
      make_rule: "Made a rule",
    };
    const statusLabel = (code: string) =>
      this.registries?.status_codes.find((c) => c.code === code)?.label ?? code;
    const kindLabel = (kind: string) =>
      this.registries?.item_kinds.find((k) => k.kind === kind)?.label ?? kind;
    return (this.registries?.action_rules ?? []).map((r) => {
      const parts: string[] = [];
      if (r.match.handle) parts.push(`handler is ${r.match.handle}`);
      if (r.match.wait_class) parts.push(`class is ${classLabel(r.match.wait_class)}`);
      if (r.match.kind) parts.push(`kind is ${kindLabel(r.match.kind)}`);
      if (r.match.status_code) {
        const codes = Array.isArray(r.match.status_code) ? r.match.status_code : [r.match.status_code];
        parts.push(`status is ${codes.map(statusLabel).join(" or ")}`);
      }
      return {
        id: r.id,
        match_label: parts.join(" · ") || "Any item",
        verb: r.verb,
        verb_label: this.verbLabelOf(r.verb),
        mode: r.mode,
        created_from: r.created_from,
        created_label: createdLabels[r.created_from] ?? r.created_from,
        at_label: r.at ? timeLabel(r.at) : "",
      };
    });
  };

  protected toSendRow(s: ServerSend): SendRow {
    return {
      id: s.id,
      at: s.at,
      rule_id: s.rule_id,
      wait_id: s.wait_id,
      handle: s.handle,
      target: s.target,
      template: s.template,
      version: s.version,
      attempt: s.attempt,
      presence: s.presence,
      text: s.text,
      fact_hash: s.fact_hash ?? "",
      mode: s.mode,
      outcome: s.outcome ?? "",
      dispatch: {
        attempts: s.dispatch.attempts,
        claim_expires_at: s.dispatch.claim_expires_at,
        claimed_at: s.dispatch.claimed_at,
        consumer: s.dispatch.consumer,
        delivered_at: s.dispatch.delivered_at,
        delivery_ref: s.dispatch.delivery_ref,
        suppress_reason: s.dispatch.suppressed_reason ?? undefined,
      },
      bridge_request_id: s.dispatch.bridge_request_id ?? undefined,
    };
  }

  getSends = (): SendRow[] => {
    return this.sends.map((s) => this.toSendRow(s));
  };

  // ---------- writes ----------

  /** One write. `act` names the act for the refusal
   * notice ("That decision"); `onRefusal` replaces the
   * default notice when the caller must also unwind its
   * optimistic state (idempotency caches, ping marks). */
}
