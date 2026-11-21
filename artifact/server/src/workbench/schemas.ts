// Payload schemas for the workbench actions (split from
// actions.ts): looseObjects — known fields typed,
// everything else carried through untouched — plus the
// shared argument schemas and the path encoders the
// action groups ride.
import { z } from "@hatch/space-sdk";

// ---------------------------------------------------------------------------
// Payload schemas (loose: the server's fields, verbatim + typed where known)
// ---------------------------------------------------------------------------

export const projectSections = z.looseObject({
  entries: z.boolean(),
  todos: z.boolean(),
  plans: z.boolean(),
  registry_declared: z.boolean(),
  plans_declared: z.boolean(),
});

export const projectSummary = z.looseObject({
  slug: z.string(),
  name: z.string(),
  root: z.string(),
  sections: projectSections,
});

export const healthPayload = z.looseObject({
  ok: z.boolean(),
  version: z.string(),
  host: z.string(),
  port: z.number(),
  projects_count: z.number(),
});

export const projectsPayload = z.looseObject({
  projects: z.array(projectSummary),
  errors: z.array(z.unknown()),
});

export const feedEnvelope = z.looseObject({
  slug: z.string(),
  name: z.string(),
  degraded: z.boolean(),
  available: z.boolean(),
});

// One envelope for every proxied call: the HTTP status (0 =
// the socket never got an answer), the payload verbatim, and
// the server's error string when it sent one.
export const proxied = <T extends z.ZodType>(payload: T) =>
  z.object({
    status: z.number(),
    payload: payload.nullable(),
    error: z.string().nullable(),
  });

export const healthResult = proxied(healthPayload);
export const projectsResult = proxied(projectsPayload);
export const configResult = proxied(z.looseObject({ config: z.record(z.string(), z.unknown()) }));
export const feedResult = proxied(feedEnvelope);
export const rawResult = proxied(z.unknown());

export type HealthResult = z.infer<typeof healthResult>;
export type ProjectsResult = z.infer<typeof projectsResult>;
export type ConfigResult = z.infer<typeof configResult>;
export type FeedResult = z.infer<typeof feedResult>;
export type RawResult = z.infer<typeof rawResult>;

export const slugArg = z.object({ slug: z.string().min(1) });
export const entryArg = z.object({ slug: z.string().min(1), entryId: z.string().min(1) });
export const codeArg = z.object({
  projectId: z.string().min(1),
  checkout: z.string().min(1).optional(),
});

export const enc = encodeURIComponent;

// Project ids may be workspace-relative paths (a
// repository-only project's census id) and may contain
// slashes: each segment is encoded, the slashes ride
// through (the server joins the trailing segments back
// into the id).
export const encProjectId = (id: string) => id.split("/").map(enc).join("/");
