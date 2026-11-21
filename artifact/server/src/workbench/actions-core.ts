// Workbench actions — core, home, and registry group
// (split from actions.ts; the barrel composes the four
// groups). Each action forwards exactly one feed/mutation
// call to the workbench backend through the privileged
// wbApi socket contract — actions.ts carries the full
// contract note.
import { defineAction, z } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { callServer } from "./bridge";
import {
  configResult,
  enc,
  healthPayload,
  healthResult,
  projectsPayload,
  projectsResult,
  rawResult,
  slugArg,
} from "./schemas";

export const coreActions = {
  getHealth: defineAction({
    description:
      "Check whether the workbench server is up and report its version and project count.",
    request: z.object({}),
    response: healthResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<z.infer<typeof healthPayload>>(ctx, "/api/health");
    },
  }),

  getConfig: defineAction({
    description: "Fetch the workbench server's public configuration.",
    request: z.object({}),
    response: configResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<z.infer<typeof configResult>["payload"]>(ctx, "/api/config");
    },
  }),

  // The feeds document: the one call the workbench
  // integration entry makes at mount in the rebuilt shape
  // (design §1) — the entry injects the returned document
  // instead of fetching /api/feeds itself.
  getFeeds: defineAction({
    description: "Fetch the workbench feeds document (the route-keyed assembly of every feed).",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/feeds");
    },
  }),

  listProjects: defineAction({
    description: "List the projects in the workbench server's sweep.",
    request: z.object({}),
    response: projectsResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<z.infer<typeof projectsPayload>>(ctx, "/api/projects");
    },
  }),

  rescanProjects: defineAction({
    description:
      "Ask the workbench server to rescan the workspace and return the updated project list.",
    request: z.object({}),
    response: projectsResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<z.infer<typeof projectsPayload>>(ctx, "/api/projects/rescan", "POST", {});
    },
  }),

  // Manual refresh: busts the backend's sweep + feed
  // caches server-side; the client then invalidates every
  // query so the whole shell re-reads fresh.
  forceRefresh: defineAction({
    description:
      "Force-refresh all viewer data: bust the workbench server's sweep and feed caches so every feed re-derives from disk.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/refresh", "POST", {});
    },
  }),
  // -- repo-home additions: the /api namespace, proxied
  // verbatim like everything above. Payloads ride
  // rawResult: their shapes are the backend's contracts,
  // typed on the client in the app lane's transport.
  getHome: defineAction({
    description: "Fetch the workspace home feed with per-project status summaries.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/home");
    },
  }),

  getWorktrees: defineAction({
    description: "Fetch one project's git worktrees with their derivations.",
    request: slugArg,
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/projects/${enc(args.slug)}/worktrees`);
    },
  }),

  getEffectiveSettings: defineAction({
    description: "Fetch the workbench server's effective settings and message-store status.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/settings/effective");
    },
  }),
  getProjectsRegistry: defineAction({
    description: "Fetch the project tracking registry the harness keeps for tracked projects.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/projects/registry");
    },
  }),

  updateProjectsRegistry: defineAction({
    description: "Update one entry of the project tracking registry.",
    request: z.object({
      id: z.string().min(1),
      patch: z.record(z.string(), z.unknown()),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, "/api/projects/registry", "POST", {
        id: args.id,
        patch: args.patch,
      });
    },
  }),
};
