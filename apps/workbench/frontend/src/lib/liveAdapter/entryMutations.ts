// Live adapter entry lifecycle: review verdicts,
// status / meta / state writes, archive + supersede,
// and the entry-file peek + guarded save — every
// method lands its write on the server first (D-4).

import type { EntryFileResult, SaveResult } from "../seam";
import type { Entry, RuledStatus } from "../types";
import type { LiveHost } from "./host";


export async function setEntryReview(h: LiveHost, id: string, review: "approved" | "needs-changes" | "stale", note?: string): Promise<Entry> {
  const e = h.s.entryList.find((x) => x.id === id);
  if (!e) throw new Error(`unknown entry ${id}`);
  await h.entryAction(e, {
    verb: "review",
    disposition: review === "approved" ? "approve" : review,
    comment: note,
  });
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
  // The board's review queue is served state: a verdict
  // moves the entry out of it (needs-changes keeps it,
  // with the reason updated).
  const board = h.s.boards.get(e.project);
  if (board) {
    const idx = board.review_queue.findIndex((item) => item.id === id);
    if (review === "needs-changes") {
      if (idx < 0) {
        board.review_queue.push({
          id: e.id,
          kind: e.kind,
          title: e.title,
          project: e.project,
          project_name: e.project,
          reasons: ["needs-changes — unaddressed"],
        });
      }
    } else if (idx >= 0) {
      board.review_queue.splice(idx, 1);
    }
  }
  h.emit();
  return e;
}

function entryOrThrow(h: LiveHost, id: string): Entry {
  const e = h.s.entryList.find((x) => x.id === id);
  if (!e) throw new Error(`unknown entry ${id}`);
  return e;
}

function logEntry(h: LiveHost, e: Entry, label: string) {
  e.reviewLog = [{ label, when: "Just now", actor: "owner" }, ...e.reviewLog];
}

export async function setEntryStatus(h: LiveHost, id: string, status: RuledStatus): Promise<Entry> {
  const e = entryOrThrow(h, id);
  await h.entryAction(e, { verb: "set-status", status });
  e.status = status;
  if (status !== "unexplored" && e.review === "in-triage") e.review = null;
  logEntry(h, e, `Status set · ${status}`);
  h.emit();
  return e;
}

export async function setEntryMeta(h: LiveHost, id: string,
    patch: Partial<Pick<Entry, "title" | "viewport" | "mode">>,): Promise<Entry> {
  const e = entryOrThrow(h, id);
  if (patch.title !== undefined) {
    if (patch.title.trim().length === 0) throw new Error("title must not be empty");
  }
  // Title is a registry field (the set verb); viewport
  // and mode are not registry columns — they live in
  // the entry's state document, so they ride set-state
  // merged into the state the detail route serves.
  if (patch.title !== undefined) {
    await h.entryAction(e, {
      verb: "set",
      fields: { title: patch.title.trim() },
    });
  }
  if (patch.viewport !== undefined || patch.mode !== undefined) {
    // The detail read: over HTTP, GET …/entries/{id};
    // in the frame form, the getEntry action over the
    // relay. Both adapt to the same status/detail pair.
    let detail: {
      entry?: { state_json?: Record<string, unknown> | null };
    };
    if (h.channel) {
      const env = await h.channel("getEntry", {
        slug: e.project,
        entryId: e.id,
      });
      if (env.status < 200 || env.status >= 300) {
        throw new Error(
          env.error ??
            `The entry's current state could not be read (${env.status}) — the metadata was not saved.`,
        );
      }
      detail = (env.payload ?? {}) as typeof detail;
    } else {
      const res = await fetch(
        h.url(
          `/api/projects/${encodeURIComponent(e.project)}/entries/${encodeURIComponent(e.id)}`,
        ),
      );
      if (!res.ok) {
        throw new Error(
          `The entry's current state could not be read (${res.status}) — the metadata was not saved.`,
        );
      }
      detail = (await res.json()) as typeof detail;
    }
    const state: Record<string, unknown> = { ...(detail.entry?.state_json ?? {}) };
    if (patch.viewport !== undefined) state.viewport = patch.viewport;
    if (patch.mode !== undefined) state.mode = patch.mode;
    await h.entryAction(e, { verb: "set-state", state });
  }
  if (patch.title !== undefined) {
    e.title = patch.title.trim();
  }
  if (patch.viewport !== undefined) e.viewport = patch.viewport;
  if (patch.mode !== undefined) e.mode = patch.mode;
  logEntry(h, e, "Metadata edited");
  h.emit();
  return e;
}

export async function verifyEntry(h: LiveHost, id: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  // The server's verify recomputes the entry's state;
  // the detail it answers with carries the real state
  // sha256 — no locally computed hash.
  const detail = await h.entryAction<{
    entry?: { current_state_sha256?: string | null };
    current_state_sha256?: string | null;
  }>(e, { verb: "verify" });
  const served = detail.entry?.current_state_sha256 ?? detail.current_state_sha256;
  if (served) e.stateHash = served;
  logEntry(h, e, `Verified · state ${e.stateHash ?? "—"}`);
  h.emit();
  return e;
}

export async function archiveEntry(h: LiveHost, id: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  await h.entryAction(e, { verb: "archive" });
  e.archived = true;
  logEntry(h, e, "Archived");
  h.emit();
  return e;
}

export async function unarchiveEntry(h: LiveHost, id: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  await h.entryAction(e, { verb: "unarchive" });
  e.archived = false;
  logEntry(h, e, "Unarchived");
  h.emit();
  return e;
}

export async function supersedeEntry(h: LiveHost, id: string, byId: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  const by = entryOrThrow(h, byId);
  await h.entryAction(e, { verb: "supersede", new_id: byId });
  e.staleNote = `Superseded by ${by.title}`;
  e.review = null;
  logEntry(h, e, `Superseded by ${by.id}`);
  logEntry(h, by, `Supersedes ${e.id}`);
  h.emit();
  return e;
}

export async function setEntryState(h: LiveHost, id: string, json: string): Promise<Entry> {
  const e = entryOrThrow(h, id);
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new Error("State must be valid JSON — the entry's state was not touched.");
  }
  await h.entryAction(e, { verb: "set-state", state: parsed });
  e.stateJson = JSON.stringify(parsed, null, 2);
  logEntry(h, e, "State saved");
  h.emit();
  return e;
}

export async function entryFileContent(h: LiveHost, id: string, path: string): Promise<EntryFileResult> {
  const key = `${id}|${path}`;
  const cached = h.s.entryFileCache.get(key);
  const cachedSha = h.s.entryFileShas.get(key);
  if (cached !== undefined && cachedSha) {
    return { ok: true, body: cached, sha: cachedSha };
  }
  const e = h.s.entryList.find((x) => x.id === id);
  if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
  if (!(e.files ?? []).some((f) => f.path === path)) {
    return { ok: false, reason: `The entry serves no file at ${path}.` };
  }
  // The file route's peek: content plus the sha256 the
  // guarded save compares against — served, not computed.
  // In the frame form the getEntryFile action carries
  // the peek over the relay, adapted to the same shape.
  try {
    let peek: {
      content?: string | null;
      sha256?: string | null;
      editable_reason?: string | null;
    };
    if (h.channel) {
      const env = await h.channel("getEntryFile", {
        slug: e.project,
        entryId: id,
        path,
      });
      if (env.status < 200 || env.status >= 300) {
        return {
          ok: false,
          reason: `File read failed: ${env.status} ${env.error ?? ""}`.trim(),
        };
      }
      peek = (env.payload ?? {}) as typeof peek;
    } else {
      const url = `/api/projects/${encodeURIComponent(e.project)}/entries/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`;
      const res = await fetch(h.url(url));
      if (!res.ok) return { ok: false, reason: `File read failed: ${res.status} ${res.statusText}` };
      peek = (await res.json()) as typeof peek;
    }
    if (peek.content == null || !peek.sha256) {
      return {
        ok: false,
        reason: peek.editable_reason ?? "The server does not serve this file's content.",
      };
    }
    h.s.entryFileCache.set(key, peek.content);
    h.s.entryFileShas.set(key, peek.sha256);
    return { ok: true, body: peek.content, sha: peek.sha256 };
  } catch (err) {
    return { ok: false, reason: `File read failed: ${err instanceof Error ? err.message : String(err)}` };
  }
}

export async function saveEntryFile(h: LiveHost, id: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
  const key = `${id}|${path}`;
  if (!h.s.entryFileShas.has(key)) {
    return { ok: false, reason: "Open the file first — the guarded save needs the sha you opened." };
  }
  const e = entryOrThrow(h, id);
  // The server's writer holds the compare-and-swap and
  // answers with the saved sha256 (its stale-sha refusal
  // carries the current sha256, surfaced verbatim). In
  // the frame form the saveEntryFile action carries the
  // same write over the relay, adapted to the same
  // status/payload pair.
  let status: number;
  let payload: {
    sha256?: string;
    error?: string;
    current_sha256?: string;
  } | null;
  let envError: string | null = null;
  if (h.channel) {
    let env;
    try {
      env = await h.channel("saveEntryFile", {
        slug: e.project,
        entryId: id,
        path,
        content,
        baseSha256: baseSha,
      });
    } catch (err) {
      return {
        ok: false,
        reason: `The save could not reach the workbench server — the file was not touched. (${err instanceof Error ? err.message : String(err)})`,
      };
    }
    status = env.status;
    payload = env.payload as typeof payload;
    envError = env.error;
  } else {
    let res: Response;
    try {
      res = await fetch(
        h.url(
          `/api/projects/${encodeURIComponent(e.project)}/entries/${encodeURIComponent(id)}/file`,
        ),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path, content, base_sha256: baseSha }),
        },
      );
    } catch (err) {
      return {
        ok: false,
        reason: `The save could not reach the workbench server — the file was not touched. (${err instanceof Error ? err.message : String(err)})`,
      };
    }
    status = res.status;
    payload = (await res.json().catch(() => null)) as typeof payload;
  }
  if (status < 200 || status >= 300) {
    if (payload?.current_sha256) {
      return {
        ok: false,
        reason: `Save refused — stale sha: the file is at ${payload.current_sha256}, you opened ${baseSha}. The saved file was not touched.`,
      };
    }
    return { ok: false, reason: payload?.error ?? envError ?? `Save refused (${status}). The file was not touched.` };
  }
  const sha = payload?.sha256 ?? baseSha;
  h.s.entryFileCache.set(key, content);
  h.s.entryFileShas.set(key, sha);
  logEntry(h, e, `File saved · ${path}`);
  h.emit();
  return { ok: true, sha, savedLabel: "Just now" };
}
