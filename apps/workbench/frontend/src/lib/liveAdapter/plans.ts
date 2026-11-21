// Live adapter plan questions + annotations: the
// sha-guarded resolve route, anchored annotation
// creates and replies over the message store, and the
// derived-only resolved-ness refusal (W-C5).

import {
  anchorStatus,
  applyAnswersToRaw,
  parsePlanQuestions,
} from "../diffModel";
import type { AnnotationThread, Plan } from "../types";
import type { LiveHost } from "./host";
import { dateLabel } from "./shared";


export function planQuestions(h: LiveHost, bundle: string) {
  const p = h.s.planList.find((x) => x.bundle === bundle);
  if (!p) return [];
  return p.questions ?? parsePlanQuestions(p.raw);
}

export async function resolvePlanQuestions(h: LiveHost, bundle: string, answers: Record<string, string>): Promise<Plan> {
  const p = h.s.planList.find((x) => x.bundle === bundle);
  if (!p) throw new Error(`unknown plan ${bundle}`);
  // The resolve route writes the answers into the plan
  // file itself, guarded by the sha256 the document
  // served for it; a stale sha refuses server-side.
  const write = h.s.planWrite.get(bundle);
  if (!write) {
    throw new Error(
      "This plan's file coordinates were not served, so its questions cannot be resolved from here.",
    );
  }
  const result = await h.postJson<{ sha256: string }>(
    `/api/projects/${encodeURIComponent(p.project)}/plan/resolve`,
    { path: write.path, base_sha256: write.sha256, answers },
  );
  h.s.planWrite.set(bundle, { path: write.path, sha256: result.sha256 });
  const questions = p.questions ?? parsePlanQuestions(p.raw);
  for (const q of questions) {
    const answer = answers[q.id]?.trim();
    if (answer) {
      q.answer = answer;
      q.answeredBy = "owner";
      q.answeredLabel = "Just now";
    }
  }
  p.questions = questions;
  p.raw = applyAnswersToRaw(p.raw, answers);
  h.emit();
  return p;
}

export function annotationsForPlan(h: LiveHost, bundle: string): AnnotationThread[] {
  const plan = h.s.planList.find((p) => p.bundle === bundle);
  return h.s.annotationList
    .filter((t) => t.bundle === bundle)
    .map((t) => ({
      ...t,
      status:
        plan && !t.anchorContext
          ? anchorStatus(plan.raw, t.anchorQuote, undefined)
          : t.status,
    }));
}

export async function addAnnotation(h: LiveHost, bundle: string, quote: string, body: string): Promise<AnnotationThread> {
  const plan = h.s.planList.find((p) => p.bundle === bundle);
  if (!plan) throw new Error(`unknown plan ${bundle}`);
  // The annotation is a message (POST /api/messages)
  // anchored to the plan's served path with a §12
  // selection payload — quote + line context is the
  // anchor; the component is the plan document itself
  // (plans/plan-reader), since the composer selects a
  // quote, not a component, and no finer component is
  // honestly claimable from it. Born sent, like a reply:
  // the seam's single act is the finished annotation.
  const write = h.s.planWrite.get(bundle);
  if (!write) {
    throw new Error(
      "This plan's file coordinates were not served, so an annotation cannot be anchored to it from here.",
    );
  }
  const line = plan.raw.split("\n").find((l) => l.includes(quote));
  let prefix = "";
  let suffix = "";
  if (line) {
    const at = line.indexOf(quote);
    prefix = line.slice(Math.max(0, at - 120), at);
    suffix = line.slice(at + quote.length, at + quote.length + 120);
  }
  const res = await h.postJson<{
    message: { id: number; author: string; body: string; created_at: string };
  }>("/api/messages", {
    author: "owner",
    body,
    project_slug: plan.project,
    anchor_type: "text",
    anchor_ref: write.path,
    selection: {
      kind: "text",
      component_id: "plans/plan-reader",
      quote,
      prefix,
      suffix,
    },
    send: true,
  });
  const m = res.message;
  const thread: AnnotationThread = {
    id: `ann-${m.id}`,
    bundle,
    project: plan.project,
    anchorQuote: quote,
    anchorContext: line,
    status: line ? "anchored" : "orphaned",
    resolved: false,
    messages: [
      { id: String(m.id), author: m.author, body: m.body, when: dateLabel(m.created_at) },
    ],
  };
  h.s.annotationList.push(thread);
  h.emit();
  return thread;
}

export async function replyAnnotation(h: LiveHost, id: string, body: string): Promise<AnnotationThread> {
  const t = h.s.annotationList.find((x) => x.id === id);
  if (!t) throw new Error(`unknown annotation ${id}`);
  // A reply is a create with parent_id (POST
  // /api/messages, sent immediately per §7); replies
  // carry no selection — the thread root holds the
  // anchor. The thread id is `ann-<root message id>`,
  // the loader's own form.
  const res = await h.postJson<{
    message: { id: number; author: string; body: string; created_at: string };
  }>("/api/messages", {
    author: "owner",
    body,
    project_slug: t.project,
    parent_id: Number(id.replace(/^ann-/, "")),
    send: true,
  });
  const m = res.message;
  t.messages = [
    ...t.messages,
    { id: String(m.id), author: m.author, body: m.body, when: dateLabel(m.created_at) },
  ];
  h.emit();
  return t;
}

export function setAnnotationResolved(h: LiveHost, id: string, resolved: boolean): AnnotationThread {
  // W-C5 disposition (ruled derived-only in live
  // mode, 2026-11-15): a thread's resolved-ness is
  // DERIVED at load from its messages' lifecycle
  // states (every row done or archived), and the
  // lifecycle offers no verb for it — done is the
  // agent's explicit post-back (§7, acknowledged →
  // done), sent rows cannot reach done without the
  // pickup acknowledgement, and archiving a root
  // files the thread away rather than resolving it.
  // A local projection would be contradicted by the
  // next reload, so the live method refuses honestly
  // and the Plans UI renders the state read-only;
  // the mock keeps the working toggle against the
  // fake. (id/resolved are the seam's shape; the
  // refusal does not depend on them.)
  void id;
  void resolved;
  throw new Error(
    "Annotation resolved-ness is derived from the thread's message lifecycle states — the server has no verb to set it, so it cannot be toggled here.",
  );
}
