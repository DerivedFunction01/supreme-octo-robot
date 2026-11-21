// Mock adapter plan questions + annotations over
// the seeded store: answers written into the plan's
// raw text, anchored threads created and replied to,
// and the working resolved toggle (the fake's).

import {
  anchorStatus,
  applyAnswersToRaw,
} from "../diffModel";
import type { AnnotationThread, Plan } from "../types";
import type { MockHost } from "./host";


export function planQuestions(h: MockHost, bundle: string) {
  return h.plan(bundle)?.questions ?? [];
}

export async function resolvePlanQuestions(h: MockHost, bundle: string, answers: Record<string, string>): Promise<Plan> {
  const p = h.plan(bundle);
  if (!p) throw new Error(`unknown plan ${bundle}`);
  for (const q of p.questions ?? []) {
    const answer = answers[q.id]?.trim();
    if (answer) {
      q.answer = answer;
      q.answeredBy = "owner";
      q.answeredLabel = "Just now";
    }
  }
  p.raw = applyAnswersToRaw(p.raw, answers);
  h.emit();
  return p;
}

export function annotationsForPlan(h: MockHost, bundle: string): AnnotationThread[] {
  const plan = h.plan(bundle);
  return h.s.db.annotations
    .filter((t) => t.bundle === bundle)
    .map((t) => ({
      ...t,
      status: plan ? anchorStatus(plan.raw, t.anchorQuote, t.anchorContext) : t.status,
    }));
}

export async function addAnnotation(h: MockHost, bundle: string, quote: string, body: string): Promise<AnnotationThread> {
  const plan = h.plan(bundle);
  if (!plan) throw new Error(`unknown plan ${bundle}`);
  const line = plan.raw.split("\n").find((l) => l.includes(quote));
  const thread: AnnotationThread = {
    id: `ann-${h.s.db.annotations.length + 1}`,
    bundle,
    project: plan.project,
    anchorQuote: quote,
    anchorContext: line,
    status: line ? "anchored" : "orphaned",
    resolved: false,
    messages: [
      { id: `ann-m-${Date.now()}`, author: "owner", body, when: "Just now" },
    ],
  };
  h.s.db.annotations.push(thread);
  h.emit();
  return thread;
}

export async function replyAnnotation(h: MockHost, id: string, body: string): Promise<AnnotationThread> {
  const t = h.s.db.annotations.find((x) => x.id === id);
  if (!t) throw new Error(`unknown annotation ${id}`);
  t.messages = [
    ...t.messages,
    { id: `${id}-m${t.messages.length + 1}`, author: "owner", body, when: "Just now" },
  ];
  h.emit();
  return t;
}

export function setAnnotationResolved(h: MockHost, id: string, resolved: boolean): AnnotationThread {
  const t = h.s.db.annotations.find((x) => x.id === id);
  if (!t) throw new Error(`unknown annotation ${id}`);
  t.resolved = resolved;
  h.emit();
  return t;
}
