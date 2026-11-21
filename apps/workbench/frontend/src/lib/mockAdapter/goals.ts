// Mock adapter goal writes over the seeded store:
// the ping toggle (a closed goal's ping stays
// retired) and the status post (contract 11's writer
// rules: basis citation, terminal clearing).

import { STATUS_VOCABULARY } from "../seed";
import type {
  AppSettings,
  GoalRecord,
  StatusPost,
} from "../types";
import type { MockHost } from "./host";


export async function setGoalPing(h: MockHost, slug: string, armed: boolean) {
  const g = h.s.db.goals.find((x) => x.slug === slug);
  if (!g) throw new Error(`unknown goal ${slug}`);
  if (armed) {
    // A terminal post retires the record's ping for good:
    // a closed goal's entry is never re-armed.
    const row = STATUS_VOCABULARY.find((r) => r.code === g.lastPost?.status_code);
    if (row?.terminal) {
      throw new Error("This goal is closed — its ping is retired and cannot be re-armed.");
    }
  }
  g.ping.armed = armed;
  h.emit();
  return g;
}

export async function postGoalStatus(h: MockHost, slug: string, post: Omit<StatusPost, "postedAt">) {
  const g = h.s.db.goals.find((x) => x.slug === slug);
  if (!g) throw new Error(`unknown goal ${slug}`);
  if (post.status_code === "BLOCKED-OWNER" || post.status_code === "BLOCKED-HARD") {
    // Contract 11 amendment (2026-11-13): a blocked post
    // without its cited basis is invalid at the writer.
    // The citation is the poster's; the verification stamp
    // is applied here, by the verifying party (main), as
    // the post is recorded.
    if (!post.basis_citation || post.basis_citation.thread.trim().length === 0) {
      throw new Error(
        "A blocked post must carry its basis citation — the owner's message reference (thread + time). Uncited blocked posts are refused at the writer.",
      );
    }
    post = {
      ...post,
      verification: post.verification ?? { by: "main", at: h.clock().toISOString() },
    };
  }
  g.lastPost = { ...post, postedAt: h.clock().toISOString() };
  if (post.status_code === "DONE" || post.status_code === "CLOSED") {
    // A terminal post clears the sticky owner-waiting
    // declaration (contract 03, ATT10).
    if (g.lastPost.owner_waiting) g.lastPost = { ...g.lastPost, owner_waiting: null };
  }
  h.emit();
  return g;
}

export function updateSettings(h: MockHost, patch: Partial<AppSettings>): AppSettings {
  h.s.settingsState = { ...h.s.settingsState, ...patch };
  h.emit();
  return h.s.settingsState;
}
