import type { VerbEntry } from "./steering";

// ---------- Digest content (api/1: build_digest) ----------

export interface DigestSectionRow {
  title: string;
  handle: string;
  handler_label: string;
  provenance_label: string;
  at_label: string;
  age_label: string;
}

export interface DigestSection {
  kind: string;
  kind_label: string;
  owner_label: string;
  rows: DigestSectionRow[];
}

export interface DigestStall {
  handle: string;
  handler_label: string;
  summary: string;
  clearing_act: string | null;
  status_label: string;
  age_hours: number;
  age_label: string;
}

export interface DigestStaffingRow {
  topic: string | null;
  handle: string | null;
  handler_label: string;
  kind: string;
  kind_label: string;
  detail: string;
  /** "Escalated to Main" when the row escalated, else null. */
  escalation_label: string | null;
}

export interface DigestStaffing {
  available: boolean;
  reason: string | null;
  idle_minutes_total: number;
  rows: DigestStaffingRow[];
}

export interface DigestTopicLane {
  handle: string;
  label: string;
  status_label: string | null;
  stale: boolean;
  quick_verbs: VerbEntry[];
}

export interface DigestTopic {
  topic: string;
  worst_label: string | null;
  stalls: number;
  open_counts: { kind: string; kind_label: string; count: number }[];
  lanes: DigestTopicLane[];
}

/** One lane record as the digest serves it on a
 * programme's lane block (the measure's evaluated lane
 * shape, verbatim): the declaration's fields plus the
 * lifecycle read — stale lanes are flagged here and are
 * excluded from the block's served `actual`. */
export interface DigestLaneRecord {
  key: string;
  label: string | null;
  family: string | null;
  queue_item: string | null;
  seat: string | null;
  venue: string | null;
  state: string;
  stale: boolean;
  overrun: boolean;
  terminated: boolean;
  estimate_minutes: number | null;
  estimate_end: string | null;
  renewals: number;
  last_ping_at: string | null;
  ping_gap_minutes: number | null;
  gap_waits_on: string | null;
}

export interface DigestQueueItem {
  key: string;
  label: string | null;
  staffable_when: string | null;
}

/** A programme's lane block, served on the digest's
 * programmes[] entries for every programme whose
 * registry contract names a staffable queue — and
 * absent entirely where no queue is named, so a
 * programme with no block renders no row. `expected`
 * is the queue-derived count and `actual` the counted
 * open, non-stale lanes, both as served. */
export interface DigestProgrammeLanes {
  slug: string;
  label: string;
  declared: number | null;
  expected: number;
  actual: number;
  lanes: DigestLaneRecord[];
  queue_unstaffed: DigestQueueItem[];
}

export interface DigestParkedPlans {
  available: boolean;
  reason: string | null;
  plans: { title: string; project: string; age_label: string }[];
}

export interface DigestContentView {
  sections: DigestSection[];
  stalls: DigestStall[];
  staffing: DigestStaffing;
  programme_lanes: DigestProgrammeLanes[];
  topics: DigestTopic[];
  parked_plans: DigestParkedPlans;
}
