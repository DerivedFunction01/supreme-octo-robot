// Mock adapter entry lifecycle over the seeded
// store: review verdicts, status / meta / state
// writes, archive + supersede, entry-file bodies and
// saves, and the guarded repo-file save.

import type { EntryFileResult, SaveResult } from "../seam";
import type { Entry, RuledStatus } from "../types";
import { findFile, shaOf, standinEntryPage } from "./helpers";
import type { MockHost } from "./host";


export async function setEntryReview(h: MockHost, id: string, review: "approved" | "needs-changes" | "stale", note?: string): Promise<Entry> {
  const e = h.s.db.entries.find((x) => x.id === id);
  if (!e) throw new Error(`unknown entry ${id}`);
  if (review === "approved") {
    e.review = "approved";
    e.approvedBy = "owner";
    e.reviewLog = [
      { label: `Approved · state ${e.stateHash ?? "—"}`, when: "Just now", actor: "owner" },
      ...e.reviewLog,
    ];
  } else if (review === "needs-changes") {
    e.review = "needs-changes";
    e.reviewCount = (e.reviewCount ?? 0) + 1;
    e.reviewLog = [
      { label: `Needs changes · ${e.reviewCount} open`, when: "Just now", actor: "owner" },
      ...e.reviewLog,
    ];
  } else {
    e.review = null;
    e.staleNote = "Stale · marked by owner";
    e.reviewLog = [
      { label: note ?? "Marked stale", when: "Just now", actor: "owner" },
      ...e.reviewLog,
    ];
  }
  h.emit();
  return e;
}

export async function guardedSave(h: MockHost, repoSlug: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
  if (!h.s.settingsState.guardedSaves) {
    return { ok: false, reason: "Guarded file saves are off — enable them in Settings → Workbench." };
  }
  const repo = h.repo(repoSlug);
  const file = repo ? findFile(repo.files, path) : undefined;
  if (!repo || !file) return { ok: false, reason: `No such file: ${path}` };
  if (file.editable !== "guarded") {
    return { ok: false, reason: file.editableNote ?? "This file is not editable in the viewer." };
  }
  if (file.sha !== baseSha) {
    return {
      ok: false,
      reason: `Save refused — stale sha: the file is at ${file.sha ?? "—"}, you opened ${baseSha}. The saved file was not touched.`,
    };
  }
  file.content = content;
  file.headContent = content;
  file.sha = shaOf(content);
  file.lines = content.split("\n").length;
  file.sizeLabel = `${content.length.toLocaleString()} bytes · ${file.lines} lines`;
  repo.modifiedCount = Math.max(0, repo.modifiedCount - 1);
  h.emit();
  return { ok: true, sha: file.sha, savedLabel: "Just now" };
}

function entryOrThrow(h: MockHost, id: string): Entry {
  const e = h.s.db.entries.find((x) => x.id === id);
  if (!e) throw new Error(`unknown entry ${id}`);
  return e;
}

function logEntry(h: MockHost, e: Entry, label: string) {
  e.reviewLog = [{ label, when: "Just now", actor: "owner" }, ...e.reviewLog];
}

export async function setEntryStatus(h: MockHost, id: string, status: RuledStatus): Promise<Entry> {
  const e = entryOrThrow(h, id);
  e.status = status;
  if (status !== "unexplored" && e.review === "in-triage") e.review = null;
  logEntry(h, e, `Status set · ${status}`);
  h.emit();
  return e;
}

export async function setEntryMeta(h: MockHost, id: string,
    patch: Partial<Pick<Entry, "title" | "viewport" | "mode">>,): Promise<Entry> {
  const e = entryOrThrow(h, id);
  if (patch.title !== undefined) {
    if (patch.title.trim().length === 0) throw new Error("title must not be empty");
    e.title = patch.title.trim();
  }
  if (patch.viewport !== undefined) e.viewport = patch.viewport;
  if (patch.mode !== undefined) e.mode = patch.mode;
  logEntry(h, e, "Metadata edited");
  h.emit();
  return e;
}

export async function verifyEntry(h: MockHost, id: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  e.stateHash = shaOf(
    JSON.stringify({ t: e.title, s: e.status, v: e.version, f: e.files?.map((f) => f.path) }),
  );
  logEntry(h, e, `Verified · state ${e.stateHash}`);
  h.emit();
  return e;
}

export async function archiveEntry(h: MockHost, id: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  e.archived = true;
  logEntry(h, e, "Archived");
  h.emit();
  return e;
}

export async function unarchiveEntry(h: MockHost, id: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  e.archived = false;
  logEntry(h, e, "Unarchived");
  h.emit();
  return e;
}

export async function supersedeEntry(h: MockHost, id: string, byId: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  const by = entryOrThrow(h, byId);
  e.staleNote = `Superseded by ${by.title}`;
  e.review = null;
  logEntry(h, e, `Superseded by ${by.id}`);
  logEntry(h, by, `Supersedes ${e.id}`);
  h.emit();
  return e;
}

export async function setEntryState(h: MockHost, id: string, json: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new Error("State must be valid JSON — the entry's state was not touched.");
  }
  e.stateJson = JSON.stringify(parsed, null, 2);
  logEntry(h, e, "State saved");
  h.emit();
  return e;
}

function entryFileBody(h: MockHost, id: string, path: string): { body: string } | { reason: string } {
  const e = h.s.db.entries.find((x) => x.id === id);
  if (!e) return { reason: `Unknown entry: ${id}` };
  const override = h.s.entryFileOverrides.get(`${id}|${path}`);
  if (override !== undefined) return { body: override };
  const info = e.files?.find((f) => f.path === path);
  if (!info) return { reason: `The entry serves no file at ${path}.` };
  if (e.repoPath && path === e.repoPath.path) {
    const repo = h.s.db.repos.find((r) => r.slug === e.repoPath!.repo);
    const file = repo ? findFile(repo.files, path.split("/").slice(1).join("/")) ?? findFile(repo.files, path) : undefined;
    if (file?.content) return { body: file.content };
  }
  if (info.isMain && e.kind === "mockup") return { body: standinEntryPage(e) };
  if (info.isMain && e.kind === "plan") {
    const plan = h.s.db.plans.find((p) => p.project === e.project);
    if (plan) return { body: plan.raw };
  }
  return {
    body: `/* ${path} — a file of "${e.title}".\n   The demo store authors no body for this file;\n   a save here replaces this stand-in. */\n`,
  };
}

export async function entryFileContent(h: MockHost, id: string, path: string): Promise<EntryFileResult> {
  const found = entryFileBody(h, id, path);
  if ("reason" in found) return { ok: false, reason: found.reason };
  return { ok: true, body: found.body, sha: shaOf(found.body) };
}

export async function repoFileContent(h: MockHost, repoSlug: string, path: string): Promise<EntryFileResult> {
  const repo = h.repo(repoSlug);
  const file = repo ? findFile(repo.files, path) : undefined;
  if (!repo || !file) return { ok: false, reason: `No such file: ${path}` };
  if (file.content === undefined) {
    return { ok: false, reason: file.editableNote ?? "The mock does not serve this file's content." };
  }
  return { ok: true, body: file.content, sha: file.sha ?? shaOf(file.content) };
}

export async function saveEntryFile(h: MockHost, id: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
  const found = entryFileBody(h, id, path);
  if ("reason" in found) return { ok: false, reason: found.reason };
  const currentSha = shaOf(found.body);
  if (currentSha !== baseSha) {
    return {
      ok: false,
      reason: `Save refused — stale sha: the file is at ${currentSha}, you opened ${baseSha}. The saved file was not touched.`,
    };
  }
  h.s.entryFileOverrides.set(`${id}|${path}`, content);
  const e = entryOrThrow(h, id);
  logEntry(h, e, `File saved · ${path}`);
  h.emit();
  return { ok: true, sha: shaOf(content), savedLabel: "Just now" };
}
