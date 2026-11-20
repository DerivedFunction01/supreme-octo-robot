// Scheduler actions: one per /api/v1 surface of the mega
// scheduling backend, in the normalized (workbench)
// dialect — the scheduler original's GET-only args/returns
// dialect cannot carry the graduated write verb, so the
// set rides the common envelope {status, payload, error}
// like every app in this artifact (design §1). Each action
// returns the backend's payload untouched — the backend
// computes everything (labels, streaks, ages against its
// own clock); the client is a consumer. A transport
// failure (status 0 from the privileged socket) surfaces
// in the envelope as a bridge error, distinct from any
// server state, never conflated.
import { defineAction, z } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { callServer } from "./bridge";

const rawResult = z.object({
  status: z.number(),
  payload: z.unknown().nullable(),
  error: z.string().nullable(),
});

export type RawResult = z.infer<typeof rawResult>;

const enc = encodeURIComponent;

export const schedulerActions = {
  getOverview: defineAction({
    description: "Fetch the scheduler overview (registry totals and served time).",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.schedulerApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/overview");
    },
  }),

  getJobs: defineAction({
    description: "Fetch the scheduler's full job list.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.schedulerApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/jobs");
    },
  }),

  getJob: defineAction({
    description: "Fetch one job's detail.",
    request: z.object({ jobId: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.schedulerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/v1/jobs/${enc(args.jobId)}`);
    },
  }),

  getPings: defineAction({
    description: "Fetch the scheduler's pending pings view.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.schedulerApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/v1/pings");
    },
  }),

  getPingsRecent: defineAction({
    description: "Fetch the acked-pings window (recent pings), optionally limited.",
    request: z.object({ limit: z.number().int().min(1).max(100).optional() }),
    response: rawResult,
    privileged: [privileged.schedulerApi],
    async handler(ctx, args) {
      const suffix = args.limit !== undefined ? `?limit=${args.limit}` : "";
      return callServer<unknown>(ctx, `/api/v1/pings/recent${suffix}`);
    },
  }),

  getLedger: defineAction({
    description: "Fetch the scheduler's ledger feed, optionally limited.",
    request: z.object({ limit: z.number().int().min(1).max(500).optional() }),
    response: rawResult,
    privileged: [privileged.schedulerApi],
    async handler(ctx, args) {
      const suffix = args.limit !== undefined ? `?limit=${args.limit}` : "";
      return callServer<unknown>(ctx, `/api/v1/ledger${suffix}`);
    },
  }),

  // The one graduated write verb (contract 09's fire-time
  // seam): the guarded config save. The backend's own
  // contract is {version, values} with an optional caller
  // stamp; its compare-and-swap refusal rides back in the
  // envelope's status/payload like any server answer.
  saveJobConfig: defineAction({
    description: "Save one job's config block through the scheduler's guarded config seam.",
    request: z.object({
      jobId: z.string().min(1),
      version: z.number().int(),
      values: z.record(z.string(), z.unknown()),
      caller: z.string().min(1).optional(),
    }),
    response: rawResult,
    privileged: [privileged.schedulerApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/v1/jobs/${enc(args.jobId)}/config`, "POST", {
        version: args.version,
        values: args.values,
        ...(args.caller ? { caller: args.caller } : {}),
      });
    },
  }),
};
