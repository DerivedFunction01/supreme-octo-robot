// Workbench actions — entries, plans, and todos group
// (split from actions.ts; the barrel composes the four
// groups). Each action forwards exactly one feed/mutation
// call to the workbench backend through the privileged
// wbApi socket contract — actions.ts carries the full
// contract note.
import { defineAction, z } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { callServer } from "./bridge";
import { getEntryPage } from "./page";
import {
  enc,
  entryArg,
  feedEnvelope,
  feedResult,
  rawResult,
  slugArg,
} from "./schemas";

export const entryActions = {
  getEntries: defineAction({
    description: "Fetch one project's entries feed, optionally including archived entries.",
    request: z.object({ slug: z.string().min(1), archived: z.boolean().optional() }),
    response: feedResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const suffix = args.archived ? "?archived=1" : "";
      return callServer<z.infer<typeof feedEnvelope>>(
        ctx,
        `/api/projects/${enc(args.slug)}/entries${suffix}`,
      );
    },
  }),

  getEntry: defineAction({
    description: "Fetch one entry's detail, files, and history.",
    request: entryArg,
    // The entry-detail payload ({entry, files, history,
    // latest_review, approval, derived}) is NOT a feed
    // envelope — it carries no slug/name/degraded/available —
    // so it passes through verbatim like getEntryFile.
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(
        ctx,
        `/api/projects/${enc(args.slug)}/entries/${enc(args.entryId)}`,
      );
    },
  }),

  getEntrySegments: defineAction({
    description: "Fetch one entry's segments (the mega surface's per-entry segment feed).",
    request: entryArg,
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(
        ctx,
        `/api/projects/${enc(args.slug)}/entries/${enc(args.entryId)}/segments`,
      );
    },
  }),

  getEntryFile: defineAction({
    description: "Read one file of an entry, optionally revealing a withheld secret-shaped file.",
    request: z.object({
      slug: z.string().min(1),
      entryId: z.string().min(1),
      path: z.string().optional(),
      reveal: z.boolean().optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.path) params.set("path", args.path);
      if (args.reveal) params.set("reveal", "1");
      const query = params.toString();
      const suffix = query ? `?${query}` : "";
      return callServer<unknown>(
        ctx,
        `/api/projects/${enc(args.slug)}/entries/${enc(args.entryId)}/file${suffix}`,
      );
    },
  }),

  saveEntryFile: defineAction({
    description:
      "Save an edited entry file through the workbench server with compare-and-swap protection.",
    request: z.object({
      slug: z.string().min(1),
      entryId: z.string().min(1),
      path: z.string().min(1),
      content: z.string(),
      baseSha256: z.string().min(1),
      confirmSecret: z.boolean().optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer(
        ctx,
        `/api/projects/${enc(args.slug)}/entries/${enc(args.entryId)}/file`,
        "POST",
        {
          path: args.path,
          content: args.content,
          base_sha256: args.baseSha256,
          confirm_secret: args.confirmSecret === true,
        },
      );
    },
  }),

  // The in-viewer render's action (page.ts): the one
  // action that is not a proxy of one backend route.
  getEntryPage,

  entryAction: defineAction({
    description: "Run a lifecycle action such as review, approve, or archive on an entry.",
    request: z.object({
      slug: z.string().min(1),
      entryId: z.string().min(1),
      body: z.record(z.string(), z.unknown()),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer(
        ctx,
        `/api/projects/${enc(args.slug)}/entries/${enc(args.entryId)}/action`,
        "POST",
        args.body,
      );
    },
  }),

  getPlans: defineAction({
    description: "Fetch one project's plans and bundles feed.",
    request: slugArg,
    response: feedResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<z.infer<typeof feedEnvelope>>(ctx, `/api/projects/${enc(args.slug)}/plans`);
    },
  }),

  getPlan: defineAction({
    description: "Fetch one plan document's structured content.",
    request: z.object({ slug: z.string().min(1), path: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(
        ctx,
        `/api/projects/${enc(args.slug)}/plan?path=${enc(args.path)}`,
      );
    },
  }),

  resolvePlanQuestions: defineAction({
    description: "Record answers to a plan's open questions back into the plan file.",
    request: z.object({
      slug: z.string().min(1),
      path: z.string().min(1),
      baseSha256: z.string().min(1),
      answers: z.record(z.string(), z.string()),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/projects/${enc(args.slug)}/plan/resolve`, "POST", {
        path: args.path,
        base_sha256: args.baseSha256,
        answers: args.answers,
      });
    },
  }),

  getProjectTodos: defineAction({
    description: "Fetch one project's todo feed.",
    request: slugArg,
    response: feedResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<z.infer<typeof feedEnvelope>>(ctx, `/api/projects/${enc(args.slug)}/todos`);
    },
  }),

  todoAction: defineAction({
    description: "Create, update, or complete a todo in one project.",
    request: z.object({
      slug: z.string().min(1),
      body: z.record(z.string(), z.unknown()),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer(ctx, `/api/projects/${enc(args.slug)}/todos`, "POST", args.body);
    },
  }),

  getClassification: defineAction({
    description: "Fetch one project's classification feed (the mega surface's addition).",
    request: slugArg,
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/projects/${enc(args.slug)}/classification`);
    },
  }),

  getDiff: defineAction({
    description: "Fetch the anchored diff for one project's worktree, bundle, or commit.",
    request: z.object({
      slug: z.string().min(1),
      worktree: z.string().optional(),
      mode: z.string().optional(),
      base: z.string().optional(),
      target: z.string().optional(),
      bundle: z.string().optional(),
      all: z.boolean().optional(),
      peek: z.string().optional(),
    }),
    // The diff payload is its own shape, not a feed
    // envelope — verbatim, like getPlan.
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.worktree) params.set("worktree", args.worktree);
      if (args.mode) params.set("mode", args.mode);
      if (args.base) params.set("base", args.base);
      if (args.target) params.set("target", args.target);
      if (args.bundle) params.set("bundle", args.bundle);
      if (args.all) params.set("all", "1");
      if (args.peek) params.set("peek", args.peek);
      const query = params.toString();
      const suffix = query ? `?${query}` : "";
      return callServer<unknown>(ctx, `/api/projects/${enc(args.slug)}/diff${suffix}`);
    },
  }),

  // One project's board portion (heavy-feed batching):
  // card projections with the done lanes paginated —
  // the board screen assembles portions client-side.
  getBoardProject: defineAction({
    description: "Fetch one project's board portion: card projections with paginated done lanes.",
    request: z.object({
      slug: z.string(),
      doneOffset: z.number().int().min(0).optional(),
      doneLimit: z.number().int().min(1).max(500).optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.doneOffset !== undefined) {
        params.set("done_offset", String(args.doneOffset));
      }
      if (args.doneLimit !== undefined) {
        params.set("done_limit", String(args.doneLimit));
      }
      const query = params.toString();
      const suffix = query ? `?${query}` : "";
      return callServer<unknown>(ctx, `/api/projects/${enc(args.slug)}/board${suffix}`);
    },
  }),
};
