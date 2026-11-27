// Runner actions: one per route of the venue lease panel
// (design §1) — the state reads (the whole /api/state
// document or one named part, the outbox) and the panel's
// mutations, which are KEPT in the published app by the
// owner's ruling (design §6.1). The mutation names are
// the canonical VenueAdapter verb names (the lease-card
// unification): acquire/release/extend/shorten/
// adoptOrphan, access release, startGrant, grant extend,
// ungrant, budget config, server restart. There was no
// original server set to port — the runner's original was
// a static panel on its own server, the same defect class
// as AC-0 — so this set is new in the workbench pattern:
// payload verbatim, the common envelope {status, payload,
// error}. Mutation bodies ride as records: their field
// sets are the panel's own contracts, validated by the
// panel, exactly as its live adapter posts them today.
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

export const runnerActions = {
  getState: defineAction({
    description: "Fetch the lease panel's full state document.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/state");
    },
  }),

  getStatePart: defineAction({
    description:
      "Fetch one named part of the lease panel's state (records, orphans, specs, budget, grant, listeners, meta).",
    request: z.object({ part: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/state/${enc(args.part)}`);
    },
  }),

  // Named for the panel, not the bare route: the workbench
  // set already carries getOutbox (its own /api/outbox),
  // and the merged registry admits no name twice.
  getLeaseOutbox: defineAction({
    description: "Fetch the lease panel's outbox, optionally after a sequence number.",
    request: z.object({ after: z.number().int().min(0).optional() }),
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      const suffix = args.after !== undefined ? `?after=${args.after}` : "";
      return callServer<unknown>(ctx, `/api/outbox${suffix}`);
    },
  }),

  acquire: defineAction({
    description: "Acquire a lease (the panel's lease/start mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/lease/start", "POST", args.body);
    },
  }),

  release: defineAction({
    description: "Release a lease (the panel's lease/stop mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/lease/stop", "POST", args.body);
    },
  }),

  extend: defineAction({
    description: "Extend a lease (the panel's lease/extend mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/lease/extend", "POST", args.body);
    },
  }),

  adoptOrphan: defineAction({
    description: "Adopt an orphaned session as a lease (the panel's lease/adopt mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/lease/adopt", "POST", args.body);
    },
  }),

  shorten: defineAction({
    description: "Shorten a lease (the panel's lease/shorten mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/lease/shorten", "POST", args.body);
    },
  }),

  releaseAccess: defineAction({
    description: "Release a session's access hold (the panel's access/release mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/access/release", "POST", args.body);
    },
  }),

  startGrant: defineAction({
    description: "Start the venue access grant (the panel's grant mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/grant", "POST", args.body);
    },
  }),

  extendGrant: defineAction({
    description: "Extend the venue access grant (the panel's grant/extend mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/grant/extend", "POST", args.body);
    },
  }),

  ungrant: defineAction({
    description: "Revoke the venue access grant (the panel's ungrant mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/ungrant", "POST", args.body);
    },
  }),

  setBudgetCaps: defineAction({
    description: "Set an account's budget caps (the panel's config/budget mutation).",
    request: bodyArg,
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/config/budget", "POST", args.body);
    },
  }),

  restartServer: defineAction({
    description: "Restart the lease panel server (the panel's server/restart mutation).",
    request: z.object({ body: z.record(z.string(), z.unknown()).optional() }),
    response: rawResult,
    privileged: [privileged.runnerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/server/restart", "POST", args.body ?? {});
    },
  }),
};
