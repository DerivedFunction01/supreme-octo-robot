// Workbench actions — messages, outbox, and goals group
// (split from actions.ts; the barrel composes the four
// groups). Each action forwards exactly one feed/mutation
// call to the workbench backend through the privileged
// wbApi socket contract — actions.ts carries the full
// contract note.
import { defineAction, z } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { callServer } from "./bridge";
import { enc, rawResult } from "./schemas";

export const messageActions = {
  getMessages: defineAction({
    description: "Fetch inbox messages, optionally filtered by project, state, anchor, or pickup.",
    request: z.object({
      project: z.string().optional(),
      state: z.string().optional(),
      anchorType: z.string().optional(),
      anchorRef: z.string().optional(),
      pickup: z.boolean().optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.project) params.set("project", args.project);
      if (args.state) params.set("state", args.state);
      if (args.anchorType) params.set("anchor_type", args.anchorType);
      if (args.anchorRef) params.set("anchor_ref", args.anchorRef);
      if (args.pickup) params.set("pickup", "1");
      const query = params.toString();
      return callServer<unknown>(ctx, `/api/messages${query ? `?${query}` : ""}`);
    },
  }),

  getOutbox: defineAction({
    description: "Fetch the workbench outbox feed (the mega surface's addition).",
    request: z.object({ after: z.string().optional() }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const suffix = args.after ? `?after=${enc(args.after)}` : "";
      return callServer<unknown>(ctx, `/api/outbox${suffix}`);
    },
  }),

  updateMessageBody: defineAction({
    description: "Replace the body of one inbox message.",
    request: z.object({ id: z.number().int(), body: z.string() }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/messages/${args.id}/body`, "POST", {
        body: args.body,
      });
    },
  }),

  createMessage: defineAction({
    description: "Create a new inbox message or annotation.",
    request: z.object({ body: z.record(z.string(), z.unknown()) }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/messages", "POST", args.body);
    },
  }),

  sendMessage: defineAction({
    description: "Send one drafted inbox message.",
    request: z.object({ id: z.number().int() }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/messages/${args.id}/send`, "POST", {});
    },
  }),

  doneMessage: defineAction({
    description: "Mark one inbox message as done.",
    request: z.object({ id: z.number().int() }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/messages/${args.id}/done`, "POST", {});
    },
  }),

  archiveMessage: defineAction({
    description: "Archive one inbox message.",
    request: z.object({ id: z.number().int() }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/messages/${args.id}/archive`, "POST", {});
    },
  }),

  // -- goals (the mega surface's additions): a goal's
  // ping and status posts from the board.
  goalPing: defineAction({
    description: "Post a ping to one goal's thread.",
    request: z.object({
      slug: z.string().min(1),
      body: z.record(z.string(), z.unknown()),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/goals/${enc(args.slug)}/ping`, "POST", args.body);
    },
  }),

  goalStatus: defineAction({
    description: "Post a status update to one goal.",
    request: z.object({
      slug: z.string().min(1),
      body: z.record(z.string(), z.unknown()),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/goals/${enc(args.slug)}/status`, "POST", args.body);
    },
  }),
};
