// Live adapter todo + message mutations: server-first
// writes (contract 03 arming, the todo writers, the
// message store's done verb) mirrored into the
// projected state only on the server's acceptance.

import { cadenceMinutes, isArmed } from "../arming";
import type { FeedBoardCard } from "../feeds";
import type { BoardCard } from "../seam";
import type { FileTodo } from "../types";
import type { LiveHost } from "./host";


function moveTodoCard(h: LiveHost, id: string, to: FileTodo["status"]) {
  const todo = h.todo(id);
  if (!todo) return;
  const board = h.s.boards.get(todo.project);
  if (!board) return;
  const lanes = board.todos as Record<string, FeedBoardCard[]>;
  for (const lane of Object.values(lanes)) {
    const idx = lane.findIndex((c) => c.id === id);
    if (idx >= 0) lane.splice(idx, 1);
  }
  const target = lanes[to];
  if (target && !target.some((c) => c.id === id)) {
    target.push({
      id,
      title: todo.title,
      bundle: todo.bundle,
      project: todo.project,
      project_name: todo.project,
    });
  }
}

export async function writeTodo(h: LiveHost, id: string,
    patch: Partial<Pick<FileTodo, "title" | "status" | "progressCheck" | "notes">>,): Promise<{ todo: FileTodo; armed: boolean }> {
  const t = h.s.todoList.find((x) => x.id === id);
  if (!t) throw new Error(`unknown todo ${id}`);
  if (patch.title !== undefined && patch.title.trim().length === 0) {
    throw new Error("title must not be empty");
  }
  // Server first (the one mutation path): title/notes
  // ride set-fields; a status or cadence change rides
  // set-status, whose writer arms/retires the progress
  // schedule in the same write. Local state below moves
  // only on the server's acceptance.
  const todosPath = `/api/projects/${encodeURIComponent(t.project)}/todos`;
  if (patch.title !== undefined || patch.notes !== undefined) {
    await h.postJson(todosPath, {
      verb: "set-fields",
      id,
      title: patch.title,
      notes: patch.notes,
    });
  }
  if (patch.status !== undefined || patch.progressCheck !== undefined) {
    const body: Record<string, unknown> = {
      verb: "set-status",
      id,
      status: patch.status ?? t.status,
    };
    if (patch.progressCheck !== undefined) {
      if (patch.progressCheck === "off") body.no_progress = true;
      else if (patch.progressCheck) body.progress = patch.progressCheck;
    }
    await h.postJson(todosPath, body);
  }
  if (patch.title !== undefined) {
    if (patch.title.trim().length === 0) throw new Error("title must not be empty");
    t.title = patch.title.trim();
  }
  if (patch.notes !== undefined) t.notes = patch.notes;
  if (patch.progressCheck !== undefined) t.progressCheck = patch.progressCheck;
  if (patch.status !== undefined && patch.status !== t.status) {
    t.status = patch.status;
    if (patch.status === "doing") {
      if (cadenceMinutes(t.progressCheck) !== null) {
        t.progressArmed = h.clock().toISOString();
      }
    } else {
      t.progressArmed = undefined;
    }
    moveTodoCard(h, id, patch.status);
  }
  if (patch.progressCheck !== undefined && t.status === "doing") {
    if (cadenceMinutes(t.progressCheck) === null) t.progressArmed = undefined;
    else if (!t.progressArmed) t.progressArmed = h.clock().toISOString();
  }
  t.updated = h.clock().toISOString().slice(0, 10);
  h.s.mutatedTodos.add(id);
  h.emit();
  return { todo: t, armed: isArmed(t, h.plan(t.bundle)?.archived ?? false) };
}

export async function addTodo(h: LiveHost, project: string, bundle: string, title: string): Promise<FileTodo> {
  // The server's writer assigns the id (project-wide
  // slug rule); the local projection adopts it verbatim.
  const created = await h.postJson<{ todo: { id: string } }>(
    `/api/projects/${encodeURIComponent(project)}/todos`,
    { verb: "create", bundle, title },
  );
  const t: FileTodo = {
    id: created.todo.id,
    project,
    bundle,
    title,
    status: "todo",
    created: h.clock().toISOString().slice(0, 10),
    updated: h.clock().toISOString().slice(0, 10),
    checkpoints: [],
    notes: "",
    extra: {},
  };
  h.s.todoList.push(t);
  const board = h.s.boards.get(project);
  if (board) {
    board.todos.todo.push({
      id: t.id,
      title,
      bundle,
      project,
      project_name: project,
    });
  }
  h.emit();
  return t;
}

export async function addCheckpoint(h: LiveHost, id: string, text: string): Promise<FileTodo> {
  const t = h.s.todoList.find((x) => x.id === id);
  if (!t) throw new Error(`unknown todo ${id}`);
  // A checkpoint is a note in the record's own format,
  // appended by the status writer at the todo's current
  // status (the conforming progress-checkpoint line).
  const at = h.clock().toISOString();
  await h.postJson(
    `/api/projects/${encodeURIComponent(t.project)}/todos`,
    {
      verb: "set-status",
      id,
      status: t.status,
      note: `progress-checkpoint: ${at} — ${text}`,
    },
  );
  t.checkpoints = [...t.checkpoints, { at, text }];
  t.updated = h.clock().toISOString().slice(0, 10);
  h.s.mutatedTodos.add(id);
  h.emit();
  return t;
}

export async function moveBoardCard(h: LiveHost, cardId: string, lane: BoardCard["lane"]): Promise<void> {
  const card = h.board().find((c) => c.id === cardId);
  if (!card) return;
  if (card.target.kind === "todo") {
    const status = lane === "done" ? "done" : lane === "todo" ? "todo" : lane === "doing" ? "doing" : null;
    if (status) await writeTodo(h, card.target.id, { status });
    return;
  }
  if (card.target.kind === "plan") {
    const p = h.plan(card.target.bundle);
    if (!p) return;
    const state = lane === "done" ? "done" : lane === "doing" ? "in-progress" : lane === "todo" ? "draft" : null;
    if (!state) return;
    p.state = state;
    const board = h.s.boards.get(p.project);
    if (board) {
      for (const l of ["todo", "doing", "done"] as const) {
        const idx = board.plans[l].findIndex((c) => c.bundle === p.bundle);
        if (idx >= 0) {
          const [moved] = board.plans[l].splice(idx, 1);
          board.plans[lane === "done" ? "done" : lane === "doing" ? "doing" : "todo"].push(moved);
          break;
        }
      }
    }
    h.emit();
    return;
  }
  if (card.target.kind === "entry" && lane === "done") {
    await h.setEntryReview(card.target.id, "approved");
  }
  // Review cards dropped elsewhere stay in the review
  // queue: a disposition is a verdict, not a drag.
}

export async function dismissMessage(h: LiveHost, id: string): Promise<void> {
  const m = h.s.messageList.find((x) => x.id === id);
  if (!m) return;
  // Dismissal is the store's done verb; the local
  // disposition moves only on its acceptance.
  await h.postJson(`/api/messages/${encodeURIComponent(id)}/done`, {});
  m.disposition = "dismissed";
  h.s.dispositions.set(id, "dismissed");
  h.emit();
}

export function openMessage(h: LiveHost, id: string) {
  const m = h.s.messageList.find((x) => x.id === id);
  if (!m) throw new Error(`unknown message ${id}`);
  if (m.disposition === null) {
    m.disposition = "opened";
    h.s.dispositions.set(id, "opened");
  }
  h.emit();
  return m;
}
