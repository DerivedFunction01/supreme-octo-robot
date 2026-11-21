// The mock store's read surface: presence, glance,
// today, handlers, programmes, and digest reads over
// the derivations, plus the small settings writes
// (digest windows/include, muted types, presence).
import type { MockStoreCtx } from "./context";
import type {
  DigestView,
  ExpiryChoice,
  HandlersView,
  PresenceMode,
  PresenceView,
  ProgrammeCardView,
  Severity,
  SurfaceHealth,
  TodayView,
  AttentionDataSource,
} from "../types";
import {
  EXPECTATIONS,
  clone,
} from "./constants";
import {
  wallParts,
  scenarioInstant,
  dateFmt,
  clockFmt,
  timeLabel,
  durationLabel,
} from "./time";

export function createApiReads(ctx: MockStoreCtx): Pick<AttentionDataSource, "getPresence" | "setPresence" | "getGlance" | "getToday" | "getSurfaceHealth" | "getWriteNotice" | "getHandlers" | "getHandlerDetail" | "getProgrammes" | "getDigest" | "setDigestWindow" | "setDigestInclude" | "setMutedType"> {
  const { state, nowMs, bump, handlerOf } = ctx;

  const surface: Pick<AttentionDataSource, "getPresence" | "setPresence" | "getGlance" | "getToday" | "getSurfaceHealth" | "getWriteNotice" | "getHandlers" | "getHandlerDetail" | "getProgrammes" | "getDigest" | "setDigestWindow" | "setDigestInclude" | "setMutedType"> = {
    getPresence: () => ctx.derivations.resolvePresence(state.presence),

    setPresence(mode, expiry, customExpiresAt) {
      const p = wallParts(new Date(nowMs()));
      let expires: string | null = null;
      if (expiry === "1h") expires = new Date(nowMs() + 3_600_000).toISOString();
      if (expiry === "17:00") expires = new Date(scenarioInstant(p.y, p.mo, p.da, 17, 0)).toISOString();
      if (expiry === "tomorrow-08:00") {
        const t = new Date(scenarioInstant(p.y, p.mo, p.da, 8, 0) + 86_400_000);
        expires = t.toISOString();
      }
      // A custom expiry arrives as the absolute instant the
      // owner picked — the same expires_at the backend's
      // presence write accepts verbatim.
      if (expiry === "custom") expires = customExpiresAt ?? null;
      state.presence = { mode, expires_at: expires, expectation: EXPECTATIONS[mode] };
      ctx.lastPresenceWrite = { choice: expiry, expires_at: expires };
      bump();
    },

    getGlance(night = false) {
      const open = ctx.derivations.openItems();
      const breakthroughs = open.filter((i) => i.kind === "breakthrough");
      const presence = night
        ? ({
            mode: "away" as PresenceMode,
            expires_at: null,
            expiry_choice: "tomorrow-08:00" as ExpiryChoice,
            expectation: "held for the morning window unless it breaks through",
            chip_label: "Away · until 8:00 AM",
            chip_severity: "warn" as Severity,
          } satisfies PresenceView)
        : ctx.derivations.resolvePresence(state.presence);
      const nd = ctx.derivations.nextDigest();
      const dueRows = open
        .filter((i) => i.due_at)
        .sort((a, b) => Date.parse(a.due_at as string) - Date.parse(b.due_at as string))
        .map((i) => ({ label: `${handlerOf(i.handle).label} lease decision`, value: timeLabel(i.due_at as string) }));

      const heldCount = ctx.derivations.waitingItems(open).length;
      const heldLabel =
        heldCount > 0
          ? `${heldCount} held for your return — everything held surfaces at the next digest, or when you're Active again`
          : null;
      if (night) {
        return {
          clock_label: "11:48",
          date_label: dateFmt.format(new Date(nowMs())),
          presence,
          count: breakthroughs.length,
          count_label: `${breakthroughs.length} needs you`,
          sub_label: presence.expectation,
          next: breakthroughs.map(ctx.derivations.toItemView),
          rows_label: "Tomorrow",
          rows: [{ label: "Digest window", value: "8:00 AM" }],
          down_sources: [],
          held_label: heldLabel,
        };
      }
      if (presence.mode === "away") {
        // Presence-filtered (contract 09): breakthrough
        // listed, next-due withheld.
        return {
          clock_label: clockFmt.format(new Date(nowMs())),
          date_label: dateFmt.format(new Date(nowMs())),
          presence,
          count: breakthroughs.length,
          count_label: `${breakthroughs.length} needs you`,
          sub_label: presence.expectation,
          next: breakthroughs.map(ctx.derivations.toItemView),
          rows_label: "Today",
          rows: [{ label: "Digest window", value: nd.time }],
          down_sources: [],
          held_label: heldLabel,
        };
      }
      const waiting = ctx.derivations.waitingItems(open);
      const pool = [...waiting].sort(
        (a, b) => Date.parse(a.waiting_since) - Date.parse(b.waiting_since),
      );
      const oldest = waiting.length
        ? durationLabel(nowMs() - Math.min(...waiting.map((d) => Date.parse(d.waiting_since))))
        : null;
      return {
        clock_label: clockFmt.format(new Date(nowMs())),
        date_label: dateFmt.format(new Date(nowMs())),
        presence,
        count: waiting.length,
        count_label: `${waiting.length} need you`,
        sub_label:
          presence.mode === "focus"
            ? presence.expectation
            : `decisions waiting${oldest ? ` · oldest ${oldest}` : ""}`,
        next: pool.slice(0, 2).map(ctx.derivations.toItemView),
        rows_label: "Today",
        rows: [{ label: "Digest window", value: nd.time }, ...dueRows],
        down_sources: [],
        held_label:
          presence.mode === "focus" && waiting.length > 0
            ? `${waiting.length} held while you focus — everything held surfaces at the next digest, or when you're Active again`
            : null,
      };
    },

    getToday(): TodayView {
      const open = ctx.derivations.openItems();
      const decisions = open
        .filter((i) => i.kind === "decision" || i.kind === "rule_proposal")
        .sort((a, b) => Date.parse(a.waiting_since) - Date.parse(b.waiting_since));
      const nd = ctx.derivations.nextDigest();
      const fyiVisible = open.filter((i) => {
        if (i.kind !== "fyi") return false;
        const muted = state.handlerSurfaces[i.handle]?.muted_types.find((m) => m.type === i.notice_type);
        return !muted?.muted;
      });
      return {
        date_label: dateFmt.format(new Date(nowMs())),
        subtitle: `${dateFmt.format(new Date(nowMs()))} · next digest window ${nd.time}`,
        presence: ctx.derivations.resolvePresence(state.presence),
        decision_count: ctx.derivations.waitingItems(open).length,
        breakthrough: open.filter((i) => i.kind === "breakthrough").map(ctx.derivations.toItemView),
        decisions: decisions.map(ctx.derivations.toItemView),
        awaiting: state.items.filter((i) => i.decision).map(ctx.derivations.toAwaitingView),
        due_today: [
          { label: "Digest window", sub: "All handlers", value: nd.time },
          ...open
            .filter((i) => i.due_at)
            .map((i) => ({ label: i.title, sub: handlerOf(i.handle).label, value: timeLabel(i.due_at as string) })),
        ],
        due_decidable: [],
        waiting_on_others: open.filter((i) => i.kind === "waiting").map(ctx.derivations.toItemView),
        fyi: {
          count: fyiVisible.length,
          newest_title: fyiVisible.length
            ? [...fyiVisible].sort((a, b) => Date.parse(b.waiting_since) - Date.parse(a.waiting_since))[0].title
            : null,
          items: fyiVisible.map(ctx.derivations.toItemView),
        },
        unavailable: [],
      };
    },

    getSurfaceHealth(): SurfaceHealth {
      // The mock is in-process: its portions never fail.
      const ok = { state: "ok" as const, last_good_at: null };
      return { glance: ok, today: ok, digest: ok };
    },

    getWriteNotice(): string | null {
      // The mock applies its writes synchronously and
      // returns their real verdicts; nothing is refused
      // behind the caller's back.
      return null;
    },

    getHandlers(): HandlersView {
      const rows = state.handlers
        .filter((h) => !h.retired)
        .map((h) => {
          const open = state.items.filter(
            (i) => i.handle === h.handle && !i.decision && !state.mutedItems.has(i.id),
          );
          const waiting = ctx.derivations.waitingItems(open).length;
          const surface = state.handlerSurfaces[h.handle];
          const clearable = surface?.agent_clearable ?? 0;
          const mutedCount = surface?.muted_types.filter((m) => m.muted).length ?? 0;
          let sub: string;
          if (waiting > 0) {
            sub = `${waiting} decision${waiting === 1 ? "" : "s"} waiting${clearable ? ` · ${clearable} agent-clearable` : ""}`;
          } else if (open.length > 0) {
            sub = `${open.length} item${open.length === 1 ? "" : "s"} open`;
          } else {
            sub = `Nothing waiting${mutedCount ? ` · ${mutedCount} muted type${mutedCount === 1 ? "" : "s"}` : ""}`;
          }
          return {
            handle: h.handle,
            label: h.label,
            color_slot: h.color_slot,
            icon: h.icon,
            sub_label: sub,
            severity: ctx.derivations.handlerSeverity(h.handle),
            trailing:
              waiting > 0
                ? { label: `${waiting} waiting`, severity: ctx.derivations.handlerSeverity(h.handle) }
                : open.length > 0
                  ? { label: `${open.length} open`, severity: "idle" as Severity }
                  : null,
          };
        });
      // The subtitle total is the per-row waiting set
      // summed over the same rows — the one ctx.derivations.waitingItems
      // derivation, partitioned by handler.
      const totalWaiting = rows.reduce(
        (n, r) =>
          n +
          ctx.derivations.waitingItems(state.items.filter((i) => i.handle === r.handle && !i.decision)).length,
        0,
      );
      return {
        subtitle: `${rows.length} handlers · ${totalWaiting} decisions waiting`,
        rows,
      };
    },

    getHandlerDetail(handle) {
      const h = state.handlers.find((x) => x.handle === handle);
      if (!h) return null;
      const surface = state.handlerSurfaces[handle];
      const open = state.items.filter(
        (i) => i.handle === handle && !i.decision && !state.mutedItems.has(i.id),
      );
      const waiting = ctx.derivations.waitingItems(open).length;
      return {
        handler: h,
        subtitle: `${h.label} · ${waiting} decision${waiting === 1 ? "" : "s"} waiting`,
        open_items: open.filter((i) => i.kind !== "fyi" && i.kind !== "waiting").map(ctx.derivations.toItemView),
        awaiting: state.items.filter((i) => i.handle === handle && i.decision).map(ctx.derivations.toAwaitingView),
        agent_clearable_label: `${surface?.agent_clearable ?? 0} items`,
        breakthrough_hit_rate: surface?.breakthrough_hit_rate ?? "—",
        muted_types: surface?.muted_types ?? [],
        status: ctx.steering.statusViewOf(handle),
        handler_verbs: ctx.steering.handlerVerbsFor(handle),
        owner_actions: ctx.steering.ownerActionsFor(handle),
        sends: clone(state.sends.filter((s) => s.handle === handle)),
        // The mock's evaluator records no auto-applied
        // log; its rules surface and preview only.
        auto_applied: [],
      };
    },

    getProgrammes(): ProgrammeCardView[] {
      return state.programmes
        .filter((p) => !p.retired)
        .map((p) => {
          const open = state.items.filter(
            (i) => p.handles.includes(i.handle) && !i.decision && !state.mutedItems.has(i.id),
          );
          return {
            slug: p.slug,
            label: p.label,
            handles: p.handles.map((handle) => {
              const h = handlerOf(handle);
              return { handle, label: h.label, color_slot: h.color_slot };
            }),
            cadence_label: `${p.cadence_minutes} min cadence`,
            band_label: `staffing band ${p.staffing_band.min}–${p.staffing_band.max}`,
            escalation_label: `escalates after ${p.escalation_hours} h`,
            venue_label: p.venue === "colab" ? "Colab venue" : "No venue",
            open_decisions: ctx.derivations.waitingItems(open).length,
            awaiting: state.items.filter((i) => p.handles.includes(i.handle) && i.decision).length,
            rule_text: p.rule_text,
          };
        });
    },

    getDigest(): DigestView {
      const at = ctx.derivations.nextDigestAt();
      const nd = ctx.derivations.nextDigest();
      const open = ctx.derivations.openItems();
      const counts = {
        decisions: ctx.derivations.waitingItems(open).length,
        waiting: open.filter((i) => i.kind === "waiting").length,
        fyi: surface.getToday().fyi.count,
      };
      const parts: string[] = [];
      if (state.digest.include.decisions) parts.push(`${counts.decisions} decisions`);
      if (state.digest.include.waiting) parts.push(`${counts.waiting} waiting`);
      if (state.digest.include.fyi) parts.push(`${counts.fyi} FYI`);
      return {
        windows: state.digest.windows,
        next_label: at ? nd.detail : "No window enabled",
        next_detail: at ? ctx.derivations.digestDetail(at) : "",
        include: state.digest.include,
        preview_label: parts.length ? `Will include: ${parts.join(" · ")}` : "Will include: nothing — all sections off",
        content: ctx.digest.digestContent(),
      };
    },

    setDigestWindow(id, enabled) {
      const w = state.digest.windows.find((x) => x.id === id);
      if (w) {
        w.enabled = enabled;
        bump();
      }
    },

    setDigestInclude(key, enabled) {
      state.digest.include[key] = enabled;
      bump();
    },

    setMutedType(handle, type, muted) {
      const surface = state.handlerSurfaces[handle];
      const row = surface?.muted_types.find((m) => m.type === type);
      if (row) row.muted = muted;
      // The flag and the held items move together (backend
      // triage): muting holds every open item of the type,
      // unmuting releases them back to the queue.
      const heldBefore = state.mutedItems.size;
      for (const item of state.items) {
        if (item.handle !== handle || item.notice_type !== type) continue;
        if (muted) state.mutedItems.add(item.id);
        else state.mutedItems.delete(item.id);
      }
      if (row || state.mutedItems.size !== heldBefore) bump();
    },
  };
  return surface;
}
