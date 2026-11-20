// The in-viewer render's action: the one workbench action
// that is not a thin proxy. The backend's loopback address
// resolves on the reader's own device, so no client can
// load an entry page from it — but the bridge can: this
// action reads the entry detail over wbApi, fetches the
// main file's exact bytes over wbRaw from the backend's
// byte route, and hands them to the client, which renders
// the page itself. Nothing is cached or stored; the bytes
// ride the envelope per open and the entry dir on disk
// stays the source of truth. (The workbench original's
// page.ts, unchanged in logic; both routes it rides —
// /api/projects/{slug}/entries/{id} and /raw/{slug}/
// entries/{id}/{rest} — are mega workrecord routes.)

import { defineAction, z } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { callServer, callServerRaw } from "./bridge";

const enc = encodeURIComponent;

function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// The render's result: the main file's content type and
// its exact bytes as base64, plus the decoded byte count
// (the stage's receipt — the client renders bodyBase64,
// never a re-encode). The envelope is the bridge's own
// {status, payload, error}; a refused file answers with
// the byte route's status and its plain-text reason.
const pagePayload = z.looseObject({
  contentType: z.string().nullable(),
  bodyBase64: z.string(),
  bytes: z.number(),
});
const pageResult = z.object({
  status: z.number(),
  payload: pagePayload.nullable(),
  error: z.string().nullable(),
});

export type PageResult = z.infer<typeof pageResult>;

export const getEntryPage = defineAction({
  description:
    "Fetch an entry's main file as exact bytes over the bridge's raw contract, for the stage's in-viewer render.",
  request: z.object({ slug: z.string().min(1), entryId: z.string().min(1) }),
  response: pageResult,
  privileged: [privileged.wbApi, privileged.wbRaw],
  async handler(ctx, args) {
    const detail = await callServer<{
      entry: { main_file: string | null; source_kind: string };
    }>(ctx, `/api/projects/${enc(args.slug)}/entries/${enc(args.entryId)}`);
    if (detail.error != null || detail.payload == null) {
      return {
        status: detail.status,
        payload: null,
        error: detail.error ?? "entry detail unavailable",
      };
    }
    const { entry } = detail.payload;
    if (entry.source_kind !== "entry-dir" || !entry.main_file) {
      return {
        status: 400,
        payload: null,
        error: "entry is held by reference — it has no page of its own to render",
      };
    }
    const rawPath =
      `/raw/${enc(args.slug)}/entries/${enc(args.entryId)}/` +
      entry.main_file.split("/").map(enc).join("/");
    const raw = await callServerRaw(ctx, rawPath);
    if (raw.status === 0) {
      return {
        status: 0,
        payload: null,
        error: "workbench server did not answer the byte route in time",
      };
    }
    const bytes = base64ToBytes(raw.bodyBase64);
    if (raw.status !== 200) {
      const note =
        new TextDecoder().decode(bytes).trim() || `byte route refused the file (${raw.status})`;
      return { status: raw.status, payload: null, error: note };
    }
    return {
      status: 200,
      payload: {
        contentType: raw.contentType,
        bodyBase64: raw.bodyBase64,
        bytes: bytes.length,
      },
      error: null,
    };
  },
});
