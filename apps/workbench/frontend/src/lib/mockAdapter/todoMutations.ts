// Mock adapter todo + message mutations over the
// seeded store: the todo writer (contract 03 arming,
// executed in the write), checkpoints, board-card
// moves, and message dispositions.

import {
  cadenceMinutes,
  deriveTodoName,
  isArmed,
} from "../arming";
import type { BoardCard } from "../seam";
import type { FileTodo } from "../types";
import type { MockHost } from "./host";


export async function writeTodo(h: MockHost, id: string,
    patch: Partial<Pick<FileTodo, "title" | "status" | "progressCheck" | "notes">>,): Promise<{ todo: FileTodo; armed: boolean }> {
  const t = h.s.db.todos.find((x) => x.id === id);
  if (!t) throw new Error(`unknown todo ${id}`);
  if (patch.title !== undefined) {
    if (patch.title.trim().length === 0) throw new Error("title must not be empty");
    t.title = patch.title.trim();
  }
  if (patch.notes !== undefined) t.notes = patch.notes;
  if (patch.progressCheck !== undefined) t.progressCheck = patch.progressCheck;
  if (patch.status !== undefined && patch.status !== t.status) {
    t.status = patch.status;
    if (patch.status === "doing") {
      // The doing transition arms: stamp + both projections,
      // in the same writer call (contract 03).
      if (cadenceMinutes(t.progressCheck) !== null) {
        t.progressArmed = h.clock().toISOString();
      }
    } else {
      // Stop status retires the projections.
      t.progressArmed = undefined;
    }
  }
  // Cadence edited while doing: re-render the projections;
  // opting out disarms.
  if (patch.progressCheck !== undefined && t.status === "doing") {
    if (cadenceMinutes(t.progressCheck) === null) t.progressArmed = undefined;
    else if (!t.progressArmed) t.progressArmed = h.clock().toISOString();
  }
  t.updated = h.clock().toISOString().slice(0, 10);
  h.emit();
  return { todo: t, armed: isArmed(t, h.plan(t.bundle)?.archived ?? false) };
}

export async function addTodo(h: MockHost, project: string, bundle: string, title: string): Promise<FileTodo> {
  const t: FileTodo = {
    id: deriveTodoName(
      title,
      h.s.db.todos.filter((x) => x.project === project).map((x) => x.id),
    ),
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
  h.s.db.todos.push(t);
  h.emit();
  return t;
}

export async function addCheckpoint(h: MockHost, id: string, text: string): Promise<FileTodo> {
  const t = h.s.db.todos.find((x) => x.id === id);
  if (!t) throw new Error(`unknown todo ${id}`);
  t.checkpoints = [...t.checkpoints, { at: h.clock().toISOString(), text }];
  t.updated = h.clock().toISOString().slice(0, 10);
  h.emit();
  return t;
}

export async function moveBoardCard(h: MockHost, cardId: string, lane: BoardCard["lane"]): Promise<void> {
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
    if (lane === "done") p.state = "done";
    else if (lane === "doing") p.state = "in-progress";
    else if (lane === "todo") p.state = "draft";
    h.emit();
    return;
  }
  if (card.target.kind === "entry" && lane === "done") {
    await h.setEntryReview(card.target.id, "approved");
  }
  // Review cards dropped elsewhere stay in the review queue:
  // a disposition is a verdict, not a drag (storyboard frame 3).
}

export async function dismissMessage(h: MockHost, id: string): Promise<void> {
  const m = h.s.db.messages.find((x) => x.id === id);
  if (m) m.disposition = "dismissed";
  h.emit();
}

export function openMessage(h: MockHost, id: string) {
  const m = h.s.db.messages.find((x) => x.id === id);
  if (!m) throw new Error(`unknown message ${id}`);
  if (m.disposition === null) m.disposition = "opened";
  const t = m.target;
  if (t.section === "mockups" && !t.project) {
    // The target's project is the entry's, stamped from
    // the catalogue as data: a message's own project can
    // name a non-project source (the doctor) whose
    // mockups live under a real project.
    const entry = h.s.db.entries.find((e) => e.id === t.entryId);
    if (entry) m.target = { ...t, project: entry.project };
  }
  h.emit();
  return m;
}
