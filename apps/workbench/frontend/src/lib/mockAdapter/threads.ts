// Mock adapter message threads over the seeded
// store: compose, reply, the draft-body edit, and
// lifecycle state.

import type { MessageThread } from "../types";
import type { MockHost } from "./host";


export async function composeThread(h: MockHost, input: {
    project: string;
    body: string;
    anchorText?: string;
    sendNow: boolean;
  }): Promise<MessageThread> {
  const body = input.body.trim();
  if (!body) throw new Error("A message needs a body.");
  const thread: MessageThread = {
    id: `th-${h.s.db.threads.length + 1}`,
    project: input.project,
    title: body.split("\n")[0].slice(0, 90),
    state: input.sendNow ? "sent" : "draft",
    anchorText: input.anchorText?.trim() || undefined,
    messages: [
      { id: `th-m-${Date.now()}`, author: "owner", body, when: "Just now" },
    ],
  };
  h.s.db.threads.push(thread);
  h.emit();
  return thread;
}

export async function replyThread(h: MockHost, id: string, body: string): Promise<MessageThread> {
  const t = h.s.db.threads.find((x) => x.id === id);
  if (!t) throw new Error(`unknown thread ${id}`);
  t.messages = [
    ...t.messages,
    { id: `${id}-m${t.messages.length + 1}`, author: "owner", body, when: "Just now" },
  ];
  if (t.state === "draft") t.state = "sent";
  h.emit();
  return t;
}

export async function editThreadMessage(h: MockHost, threadId: string, messageId: string, body: string): Promise<MessageThread> {
  const t = h.s.db.threads.find((x) => x.id === threadId);
  if (!t) throw new Error(`unknown thread ${threadId}`);
  const m = t.messages.find((x) => x.id === messageId);
  if (!m) throw new Error(`unknown message ${messageId}`);
  m.body = body;
  h.emit();
  return t;
}

export async function setThreadState(h: MockHost, id: string, state: "sent" | "done" | "archived"): Promise<MessageThread> {
  const t = h.s.db.threads.find((x) => x.id === id);
  if (!t) throw new Error(`unknown thread ${id}`);
  t.state = state;
  h.emit();
  return t;
}
