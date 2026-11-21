// Live adapter served documents: the entry page over
// the byte route (or the relay channel, in the frame
// form) and the entry's document as served segments.

import type { FeedEntrySegments } from "../feeds";
import type { EntryPageResult, EntrySegmentsResult } from "../seam";
import type { WbChannel } from "../transport";
import type { Entry } from "../types";
import type { LiveHost } from "./host";


/** The entry's page over the byte route (SPEC §7): the
 *  main file's exact bytes, fetched from /raw — the same
 *  construction the viewer's getEntryPage action used.
 *  The route answers refusals as plain text; the reason
 *  rides the result, never a partial page. */
export async function entryPage(h: LiveHost, id: string): Promise<EntryPageResult> {
  const e = h.entry(id);
  if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
  const main = h.s.pagePaths.get(id);
  if (!main) {
    return {
      ok: false,
      reason:
        "Page unavailable — this entry is held by reference; its files live outside the harness.",
    };
  }
  if (h.channel) return entryPageViaChannel(h, e, id);
  const enc = encodeURIComponent;
  const url =
    `/raw/${enc(e.project)}/entries/${enc(id)}/` +
    main.split("/").map(enc).join("/");
  let res: Response;
  try {
    res = await fetch(h.url(url));
  } catch {
    return {
      ok: false,
      reason:
        "The page could not be fetched — the byte route did not answer. Nothing was rendered.",
    };
  }
  const body = await res.text();
  if (!res.ok) {
    return {
      ok: false,
      reason: body.trim() || `The byte route refused this page (status ${res.status}).`,
    };
  }
  return {
    ok: true,
    body,
    contentType: res.headers.get("content-type") ?? "text/html; charset=utf-8",
  };
}

/** entryPage over the relay channel (the frame form):
 *  the getEntryPage action reads the detail over wbApi
 *  and the main file's exact bytes over wbRaw server-
 *  side, and hands them back base64-encoded in the
 *  envelope — the client decodes and renders, exactly
 *  as with the byte route's bytes. A refusal rides the
 *  envelope's error text; a status-0 envelope is the
 *  bridge's unreachable diagnosis. */
async function entryPageViaChannel(h: LiveHost, e: Entry,
    id: string,): Promise<EntryPageResult> {
  const channel = h.channel as WbChannel;
  let env;
  try {
    env = await channel("getEntryPage", {
      slug: e.project,
      entryId: id,
    });
  } catch {
    return {
      ok: false,
      reason:
        "The page could not be fetched — the byte route did not answer. Nothing was rendered.",
    };
  }
  const payload = env.payload as {
    contentType?: string | null;
    bodyBase64?: string;
    bytes?: number;
  } | null;
  if (env.status !== 200 || !payload?.bodyBase64) {
    return {
      ok: false,
      reason:
        env.error ||
        `The byte route refused this page (status ${env.status}).`,
    };
  }
  const binary = atob(payload.bodyBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return {
    ok: true,
    body: new TextDecoder().decode(bytes),
    contentType: payload.contentType ?? "text/html; charset=utf-8",
  };
}

/** The entry's document as served segments (the
 *  segment feed): blocks of text runs plus math nodes,
 *  segmented by the pipeline — the client renders the
 *  served shape and never parses the document itself.
 *  Refusals (held by reference, main file a rendered
 *  page) ride the result with the route's own reason;
 *  the stage falls back to the byte route on a refusal. */
export async function entrySegments(h: LiveHost, id: string): Promise<EntrySegmentsResult> {
  const e = h.entry(id);
  if (!e) return { ok: false, reason: `Unknown entry: ${id}` };
  if (h.channel) {
    let env;
    try {
      env = await h.channel("getEntrySegments", {
        slug: e.project,
        entryId: id,
      });
    } catch {
      return {
        ok: false,
        reason:
          "The document could not be fetched — the segment feed did not answer. Nothing was rendered.",
      };
    }
    if (env.status !== 200) {
      const payload = env.payload as { error?: string } | null;
      return {
        ok: false,
        reason:
          env.error ||
          payload?.error ||
          `The segment feed refused this document (status ${env.status}).`,
      };
    }
    const payload = env.payload as FeedEntrySegments;
    return { ok: true, mainFile: payload.main_file, blocks: payload.blocks };
  }
  const enc = encodeURIComponent;
  const url = `/api/projects/${enc(e.project)}/entries/${enc(id)}/segments`;
  let res: Response;
  try {
    res = await fetch(h.url(url));
  } catch {
    return {
      ok: false,
      reason:
        "The document could not be fetched — the segment feed did not answer. Nothing was rendered.",
    };
  }
  if (!res.ok) {
    let reason = "";
    try {
      const payload = (await res.json()) as { error?: string };
      reason = payload.error ?? "";
    } catch {
      reason = "";
    }
    return {
      ok: false,
      reason: reason || `The segment feed refused this document (status ${res.status}).`,
    };
  }
  const payload = (await res.json()) as FeedEntrySegments;
  return { ok: true, mainFile: payload.main_file, blocks: payload.blocks };
}
