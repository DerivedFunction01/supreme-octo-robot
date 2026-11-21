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

export interface DigestParkedPlans {
  available: boolean;
  reason: string | null;
  plans: { title: string; project: string; age_label: string }[];
}

export interface DigestContentView {
  sections: DigestSection[];
  stalls: DigestStall[];
  staffing: DigestStaffing;
  topics: DigestTopic[];
  parked_plans: DigestParkedPlans;
}
