// Live adapter message threads: compose, reply, the
// draft-body edit, and lifecycle state — over the
// message store's routes, ids adopted as served.

import type { MessageThread } from "../types";
import type { LiveHost } from "./host";


export async function composeThread(h: LiveHost, input: {
    project: string;
    body: string;
    anchorText?: string;
    sendNow: boolean;
  }): Promise<MessageThread> {
  const body = input.body.trim();
  if (!body) throw new Error("A message needs a body.");
  // POST /api/messages — the store assigns the id; the
  // local thread adopts it, so the thread the UI opens
  // is the record the server holds.
  const anchor = input.anchorText?.trim();
  const created = await h.postJson<{
    message: { id: number | string; state: string };
  }>("/api/messages", {
    author: "owner",
    body,
    project_slug: input.project || undefined,
    anchor_type: anchor ? "text" : "none",
    selection: anchor ? { quote: anchor } : undefined,
    send: input.sendNow,
  });
  const thread: MessageThread = {
    id: String(created.message.id),
    project: input.project,
    title: body.split("\n")[0].slice(0, 90),
    state: input.sendNow ? "sent" : "draft",
    anchorText: input.anchorText?.trim() || undefined,
    messages: [
      { id: String(created.message.id), author: "owner", body, when: "Just now" },
    ],
  };
  h.s.threadList.push(thread);
  h.emit();
  return thread;
}

export async function replyThread(h: LiveHost, id: string, body: string): Promise<MessageThread> {
  const t = h.s.threadList.find((x) => x.id === id);
  if (!t) throw new Error(`unknown thread ${id}`);
  const created = await h.postJson<{
    message: { id: number | string };
  }>("/api/messages", {
    author: "owner",
    body,
    project_slug: t.project || undefined,
    parent_id: Number(id),
    send: t.state !== "draft",
  });
  t.messages = [
    ...t.messages,
    { id: String(created.message.id), author: "owner", body, when: "Just now" },
  ];
  if (t.state === "draft") t.state = "sent";
  h.emit();
  return t;
}

export async function editThreadMessage(h: LiveHost, threadId: string, messageId: string, body: string): Promise<MessageThread> {
  const t = h.s.threadList.find((x) => x.id === threadId);
  if (!t) throw new Error(`unknown thread ${threadId}`);
  const m = t.messages.find((x) => x.id === messageId);
  if (!m) throw new Error(`unknown message ${messageId}`);
  // The draft-body route: the store's one draft path
  // (it refuses non-draft messages, surfaced as-is).
  await h.postJson(`/api/messages/${encodeURIComponent(messageId)}/body`, { body });
  m.body = body;
  h.emit();
  return t;
}

export async function setThreadState(h: LiveHost, id: string, state: "sent" | "done" | "archived"): Promise<MessageThread> {
  const t = h.s.threadList.find((x) => x.id === id);
  if (!t) throw new Error(`unknown thread ${id}`);
  const verb = state === "sent" ? "send" : state === "done" ? "done" : "archive";
  await h.postJson(`/api/messages/${encodeURIComponent(id)}/${verb}`, {});
  t.state = state;
  h.emit();
  return t;
}
