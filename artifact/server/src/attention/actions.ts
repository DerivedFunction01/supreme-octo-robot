// Attention actions: the set the mega attention app's live
// store calls (design §1) — the reads (glance, today,
// digest, registries, rules, programmes, sends, handler
// detail, wait detail) and the writes the store performs
// (presence, digest prefs, item/handler actions, handler
// mute/unmute, rule add/preview, the five vocab adds).
// Writes are IN (coordinator's disposition at design
// adoption). There was no original server set to port —
// attention's original was a static page on its own
// backend (AC-0) — so this set is new in the workbench
// pattern: one action per backend route, payload verbatim,
// the common envelope {status, payload, error}. The
// agent-tier routes (/api/v1/agent/* writes, sends
// claim/ack/suppress) are the dispatch surface's, not the
// app's, and are not in this set — the one agent read the
// store performs (a wait's detail) is.
import { defineAction, z } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { callServer } from "./bridge";

const rawResult = z.object({
  status: z.number(),
  payload: z.unknown().nullable(),
  error: z.string().nullable(),
});

export type RawResult = z.infer<typeof rawResult>;

const bodyArg = z.object({ body: z.record(z.string(), z.unknown()) });

const enc = encodeURIComponent;

export const attentionActions = {
  getGlance: defineAction({
    description: "Fetch the attention glance (the Today header's served summary).",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/glance");
    },
  }),

  getToday: defineAction({
    description: "Fetch the attention Today view's served payload.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/today");
    },
  }),

  getDigest: defineAction({
    description: "Fetch the attention digest's served payload.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/digest");
    },
  }),

  getRegistries: defineAction({
    description: "Fetch the attention registries (status codes, fields, kinds, templates).",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/registries");
    },
  }),

  getRules: defineAction({
    description: "Fetch the attention routing rules.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/rules");
    },
  }),

  getProgrammes: defineAction({
    description: "Fetch the attention programmes list.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/programmes");
    },
  }),

  getSends: defineAction({
    description: "Fetch the attention sends list.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/sends");
    },
  }),

  getHandler: defineAction({
    description: "Fetch one handler's detail (state, muted types, recent items).",
    request: z.object({ handle: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/v1/handlers/${enc(args.handle)}`);
    },
  }),

  getWait: defineAction({
    description: "Fetch one agent wait's detail.",
    request: z.object({ waitId: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/v1/agent/waits/${enc(args.waitId)}`);
    },
  }),

  postPresence: defineAction({
    description: "Write the presence state (mode, expiry, expectation) to the attention backend.",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/presence", "POST", args.body);
    },
  }),

  postDigestPrefs: defineAction({
    description: "Write a digest preference (window time/enabled or include key/enabled).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/digest/prefs", "POST", args.body);
    },
  }),

  itemAction: defineAction({
    description: "Run a decision/action on one attention item.",
    request: z.object({
      itemId: z.string().min(1),
      body: z.record(z.string(), z.unknown()),
    }),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(
        ctx,
        `/api/v1/items/${enc(args.itemId)}/action`,
        "POST",
        args.body,
      );
    },
  }),

  handlerAction: defineAction({
    description: "Run a steering action on one handler.",
    request: z.object({
      handle: z.string().min(1),
      body: z.record(z.string(), z.unknown()),
    }),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(
        ctx,
        `/api/v1/handlers/${enc(args.handle)}/action`,
        "POST",
        args.body,
      );
    },
  }),

  muteHandler: defineAction({
    description: "Mute one item kind for one handler.",
    request: z.object({ handle: z.string().min(1), kind: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/v1/handlers/${enc(args.handle)}/mute`, "POST", {
        kind: args.kind,
      });
    },
  }),

  unmuteHandler: defineAction({
    description: "Unmute one item kind for one handler.",
    request: z.object({ handle: z.string().min(1), kind: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/v1/handlers/${enc(args.handle)}/unmute`, "POST", {
        kind: args.kind,
      });
    },
  }),

  addRule: defineAction({
    description: "Add a routing rule (validated against the registries by the backend).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/rules", "POST", args.body);
    },
  }),

  previewRule: defineAction({
    description: "Dry-run a candidate routing rule over the open items.",
    request: z.object({ rule: z.record(z.string(), z.unknown()) }),
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/rules/preview", "POST", { rule: args.rule });
    },
  }),

  addVocabStatusCode: defineAction({
    description: "Add a status-code vocabulary entry.",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/vocab/status-codes", "POST", args.body);
    },
  }),

  addVocabField: defineAction({
    description: "Add a poster-settable field vocabulary entry.",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/vocab/fields", "POST", args.body);
    },
  }),

  addVocabClass: defineAction({
    description: "Add a wait-class vocabulary entry.",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/vocab/classes", "POST", args.body);
    },
  }),

  addVocabTemplate: defineAction({
    description: "Add a template vocabulary entry.",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/vocab/templates", "POST", args.body);
    },
  }),

  addVocabKind: defineAction({
    description: "Add an item-kind vocabulary entry.",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.attentionApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/v1/vocab/kinds", "POST", args.body);
    },
  }),
};
