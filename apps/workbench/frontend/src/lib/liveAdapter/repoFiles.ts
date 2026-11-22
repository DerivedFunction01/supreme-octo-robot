// Live adapter repo-file surface: the guarded save
// (the server's writer holds the compare-and-swap on
// the served sha256), the on-demand file peek, and
// registry tracking updates.

import type { EntryFileResult, SaveResult } from "../seam";
import type { Repo, RepoFile } from "../types";
import type { LiveHost } from "./host";
import { findFileInTree } from "./shared";


export async function guardedSave(h: LiveHost, repoSlug: string, path: string, content: string, baseSha: string): Promise<SaveResult> {
  if (!h.s.settingsState.guardedSaves) {
    return { ok: false, reason: "Guarded file saves are off — enable them in Settings → Workbench." };
  }
  const repo = h.repo(repoSlug);
  const find = (files: RepoFile[], parts: string[]): RepoFile | undefined => {
    const [head, ...rest] = parts;
    const node = files.find((f) => f.name === head);
    if (!node) return undefined;
    return rest.length === 0 ? node : find(node.children ?? [], rest);
  };
  const file = repo ? find(repo.files, path.split("/")) : undefined;
  if (!repo || !file) return { ok: false, reason: `No such file: ${path}` };
  if (file.editable !== "guarded") {
    return { ok: false, reason: file.editableNote ?? "This file is not editable in the viewer." };
  }
  // The guarded save itself: the server's writer holds
  // the compare-and-swap (base_sha256 against the file's
  // real sha256 — the sha the peek served, never a
  // locally computed one) and returns the saved sha256.
  // In the frame form the saveRepoFile action carries
  // the same write over the relay; the envelope adapts
  // to the same status/payload pair below.
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
      env = await h.channel("saveRepoFile", {
        repoId: repoSlug,
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
      res = await fetch(h.url(`/api/projects/code/${repoSlug}/file`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, content, base_sha256: baseSha }),
      });
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
  file.content = content;
  file.headContent = content;
  file.sha = payload?.sha256 ?? file.sha;
  file.lines = content.split("\n").length;
  file.sizeLabel = `${content.length.toLocaleString()} bytes · ${file.lines} lines`;
  repo.modifiedCount = Math.max(0, repo.modifiedCount - 1);
  h.emit();
  return { ok: true, sha: file.sha ?? "", savedLabel: "Just now" };
}

/** Open one of the repo's files on demand: files whose
 *  peek the document deferred carry no content, so the
 *  open rides GET …/file (the repo peek route) and the
 *  served sha256 becomes the file's sha — the guarded
 *  save's CAS base. A file the document already serves
 *  content for answers from the snapshot. */
export async function repoFileContent(h: LiveHost, repoSlug: string, path: string): Promise<EntryFileResult> {
  const repo = h.repo(repoSlug);
  if (!repo) return { ok: false, reason: `No such file: ${path}` };
  // The document no longer carries the file tree (SPEC
  // §21: code detail serves on demand), so absence from
  // the tree is not absence from the repo — the peek
  // route itself answers for a missing file. The tree
  // node, when one exists, is the content cache.
  const file = findFileInTree(repo.files, path);
  if (file && file.content !== undefined && file.sha) {
    return { ok: true, body: file.content, sha: file.sha };
  }
  // The peek: over HTTP, GET …/file; in the frame form,
  // the getRepoFile action over the relay. Both adapt
  // to the same status/peek pair below.
  let status: number;
  let statusText = "";
  let peek: {
    content?: string | null;
    sha256?: string | null;
    editable?: boolean;
    editable_reason?: string | null;
    line_count?: number;
    size_bytes?: number;
  };
  if (h.channel) {
    let env;
    try {
      env = await h.channel("getRepoFile", {
        repoId: repoSlug,
        path,
      });
    } catch (err) {
      return {
        ok: false,
        reason: `The file could not be fetched — the file route did not answer. (${err instanceof Error ? err.message : String(err)})`,
      };
    }
    status = env.status;
    statusText = env.error ?? "";
    peek = (env.payload ?? {}) as typeof peek;
  } else {
    let res: Response;
    try {
      res = await fetch(
        h.url(`/api/projects/code/${repoSlug}/file?path=${encodeURIComponent(path)}`),
      );
    } catch (err) {
      return {
        ok: false,
        reason: `The file could not be fetched — the file route did not answer. (${err instanceof Error ? err.message : String(err)})`,
      };
    }
    status = res.status;
    statusText = res.statusText;
    if (status >= 200 && status < 300) {
      peek = (await res.json()) as typeof peek;
    } else {
      peek = {};
    }
  }
  if (status < 200 || status >= 300) {
    return { ok: false, reason: `File read failed: ${status} ${statusText}` };
  }
  if (peek.content == null || !peek.sha256) {
    return {
      ok: false,
      reason: peek.editable_reason ?? "The server does not serve this file's content.",
    };
  }
  // Cache the peek on the repo's tree — upserting the
  // node when the document served no tree (SPEC §21):
  // the tree is a cache the peeks populate, and the
  // guarded save's lookup + editable gate read it.
  let node = file;
  if (!node) {
    const parts = path.split("/").filter(Boolean);
    let level = repo.files;
    for (const part of parts.slice(0, -1)) {
      let folder = level.find((f) => f.name === part);
      if (!folder) {
        folder = { name: part, kind: "folder", children: [] };
        level.push(folder);
      }
      folder.children ??= [];
      level = folder.children;
    }
    node = { name: parts[parts.length - 1] ?? path, kind: "file" };
    level.push(node);
  }
  node.content = peek.content;
  node.sha = peek.sha256;
  if (peek.line_count != null) node.lines = peek.line_count;
  if (peek.size_bytes != null) {
    node.sizeLabel = `${peek.size_bytes.toLocaleString()} bytes · ${peek.line_count ?? node.lines ?? 0} lines`;
  }
  node.editable = peek.editable ? "guarded" : "no";
  h.emit();
  return { ok: true, body: peek.content, sha: peek.sha256 };
}

export async function updateRepoTracking(h: LiveHost, slug: string,
    patch: Partial<NonNullable<Repo["tracking"]>> & { name?: string },): Promise<Repo> {
  const r = h.s.repoList.find((x) => x.slug === slug);
  if (!r) throw new Error(`unknown repo ${slug}`);
  // POST /api/projects/registry {id, patch} — the registry
  // record is the server's store; local state follows.
  await h.postJson("/api/projects/registry", { id: slug, patch });
  if (patch.name !== undefined && patch.name.trim()) r.name = patch.name.trim();
  const { name: _name, ...tracking } = patch;
  r.tracking = {
    expected: r.tracking?.expected ?? "",
    pinned: r.tracking?.pinned ?? false,
    ignored: r.tracking?.ignored ?? false,
    notes: r.tracking?.notes ?? "",
    ...tracking,
  };
  h.emit();
  return r;
}
