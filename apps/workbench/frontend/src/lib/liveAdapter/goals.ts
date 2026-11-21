// Live adapter goal writes: the ping toggle and the
// status post — server-first, the served record
// adopted whole (the writer rules live at the store).

import type { GoalRecord, StatusPost } from "../types";
import type { LiveHost } from "./host";


export async function setGoalPing(h: LiveHost, slug: string, armed: boolean): Promise<GoalRecord> {
  // Server first (POST /api/goals/{slug}/ping): the
  // store's writer owns the rule this adapter used to
  // project locally — a closed goal's retired ping
  // refuses re-arm there — and the response carries the
  // record in its served form, which is adopted whole.
  const res = await h.postJson<{ goal: GoalRecord }>(
    `/api/goals/${encodeURIComponent(slug)}/ping`,
    { armed },
  );
  const i = h.s.goalList.findIndex((x) => x.slug === slug);
  if (i >= 0) h.s.goalList[i] = res.goal;
  h.emit();
  return res.goal;
}

export async function postGoalStatus(h: LiveHost, slug: string, post: Omit<StatusPost, "postedAt">): Promise<GoalRecord> {
  // Server first (POST /api/goals/{slug}/status): the
  // writer rules live at the store — contract 06's
  // closed code set, the blocked post's basis citation,
  // the verification stamp, posted_at, and the terminal
  // post's ping retirement + owner-waiting clear all
  // land there; the served record is adopted whole.
  const res = await h.postJson<{ goal: GoalRecord }>(
    `/api/goals/${encodeURIComponent(slug)}/status`,
    { post },
  );
  const i = h.s.goalList.findIndex((x) => x.slug === slug);
  if (i >= 0) h.s.goalList[i] = res.goal;
  h.emit();
  return res.goal;
}
