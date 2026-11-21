// The mock store's digest content composition
// (build_digest): stalls, topics, staffing, and the
// parked plans, composed from the same state the other
// surfaces read.
import type { MockStoreCtx } from "./context";
import type {
  DigestContentView,
} from "../types";
import {
  STALL_AFTER_HOURS,
  PROVENANCE_LABELS,
  DIGEST_OWNER_LABELS,
  STAFFING_KIND_LABELS,
} from "./constants";
import {
  timeLabel,
} from "./time";

export function createDigest(ctx: MockStoreCtx): MockStoreCtx["digest"] {
  const { state, nowMs, handlerOf } = ctx;

// ---------- digest content (build_digest, composed) ----------

function topicOf(handle: string): string {
  const bare = handle.replace(/^@/, "");
  return bare.includes("-") ? bare.split("-")[0] : bare;
}

function digestStalls(): DigestContentView["stalls"] {
  const terminal = new Set(
    state.registries.status_codes.filter((c) => c.terminal).map((c) => c.code),
  );
  const stalls: DigestContentView["stalls"] = [];
  for (const h of state.handlers) {
    if (h.retired) continue;
    const rec = state.statuses[h.handle];
    if (!rec || terminal.has(rec.status_code) || rec.status_code === "PARKED")
      continue;
    const ownerBlockers = (rec.blockers ?? []).filter(
      (b) => (b.whose ?? "owner") === "owner",
    );
    if (!ownerBlockers.length) continue;
    const ageH = (nowMs() - Date.parse(rec.at)) / 3_600_000;
    if (ageH > STALL_AFTER_HOURS) {
      stalls.push({
        handle: h.handle,
        handler_label: h.label,
        summary: ownerBlockers[0].summary,
        clearing_act: ownerBlockers[0].clearing_act,
        status_label: ctx.labels.statusLabelOf(rec.status_code),
        age_hours: Math.round(ageH * 10) / 10,
        age_label: ctx.labels.ageLabel(rec.at),
      });
    }
  }
  return stalls.sort((a, b) => b.age_hours - a.age_hours);
}

const WORST_RANK: Record<string, number> = {
  "BLOCKED-HARD": 0,
  "BLOCKED-OWNER": 0,
  REVIEW: 1,
  WORKING: 2,
  CONTINUE: 2,
  PARKED: 3,
  DONE: 4,
  CLOSED: 5,
};

interface TopicAcc {
  topic: string;
  worst_label: string | null;
  worst_rank: number;
  stalls: number;
  counts: Map<string, number>;
  lanes: DigestContentView["topics"][number]["lanes"];
}

function digestTopics(stalls: DigestContentView["stalls"]): DigestContentView["topics"] {
  const handles = new Set<string>([
    ...Object.keys(state.statuses),
    ...ctx.derivations.openItems().map((i) => i.handle),
  ]);
  const byTopic = new Map<string, TopicAcc>();
  for (const handle of handles) {
    const topic = topicOf(handle);
    const lane = state.handlers.find((h) => h.handle === handle);
    const rec = state.statuses[handle];
    const entry: TopicAcc = byTopic.get(topic) ?? {
      topic,
      worst_label: null,
      worst_rank: 6,
      stalls: 0,
      counts: new Map<string, number>(),
      lanes: [],
    };
    entry.lanes.push({
      handle,
      label: lane?.label ?? handle,
      status_label: rec ? ctx.labels.statusLabelOf(rec.status_code) : null,
      stale: stalls.some((s) => s.handle === handle),
      quick_verbs: rec ? ctx.steering.quickVerbsFor(rec.status_code) : [],
    });
    if (stalls.some((s) => s.handle === handle)) entry.stalls += 1;
    if (rec) {
      const rank = WORST_RANK[rec.status_code] ?? 6;
      if (rank < entry.worst_rank) {
        entry.worst_rank = rank;
        entry.worst_label = ctx.labels.statusLabelOf(rec.status_code);
      }
    }
    for (const item of ctx.derivations.openItems()) {
      if (item.handle === handle)
        entry.counts.set(item.kind, (entry.counts.get(item.kind) ?? 0) + 1);
    }
    byTopic.set(topic, entry);
  }
  return [...byTopic.values()]
    .sort((a, b) => a.topic.localeCompare(b.topic))
    .map((t) => ({
      topic: t.topic,
      worst_label: t.worst_label,
      stalls: t.stalls,
      open_counts: [...t.counts.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([kind, count]) => ({ kind, kind_label: ctx.labels.kindLabel(kind), count })),
      lanes: [...t.lanes].sort((a, b) => a.handle.localeCompare(b.handle)),
    }));
}

function digestContent(): DigestContentView {
  const stalls = digestStalls();
  const seed = state.digestContent;
  return {
    sections: seed.sections.map((s) => {
      const kindEntry = state.registries.item_kinds.find((k) => k.kind === s.kind);
      const owner = kindEntry?.digest_owner ?? "owner";
      return {
        kind: s.kind,
        kind_label: kindEntry?.label ?? s.kind,
        owner_label: DIGEST_OWNER_LABELS[owner] ?? owner,
        rows: s.rows.map((r) => ({
          title: r.title,
          handle: r.handle,
          handler_label: handlerOf(r.handle).label,
          provenance_label: PROVENANCE_LABELS[r.provenance] ?? r.provenance,
          at_label: timeLabel(r.at),
          age_label: ctx.labels.ageLabel(r.at),
        })),
      };
    }),
    stalls,
    staffing: {
      available: seed.staffing.available,
      reason: seed.staffing.reason,
      idle_minutes_total: seed.staffing.idle_minutes_total,
      rows: seed.staffing.rows.map((r) => ({
        topic: r.topic,
        handle: r.handle,
        handler_label: r.handle
          ? handlerOf(r.handle).label
          : (STAFFING_KIND_LABELS[r.kind] ?? r.kind),
        kind: r.kind,
        kind_label: STAFFING_KIND_LABELS[r.kind] ?? r.kind,
        detail: r.detail,
        escalation_label: r.escalation === "main" ? "Escalated to Main" : null,
      })),
    },
    topics: digestTopics(stalls),
    parked_plans: {
      available: seed.parked_plans.available,
      reason: seed.parked_plans.reason,
      plans: seed.parked_plans.plans.map((p) => ({
        title: p.title ?? p.path,
        project: p.project,
        age_label:
          p.age_days === null
            ? ""
            : `waiting ${p.age_days} day${p.age_days === 1 ? "" : "s"}`,
      })),
    },
  };
}

  return { topicOf, digestStalls, digestTopics, digestContent };
}
