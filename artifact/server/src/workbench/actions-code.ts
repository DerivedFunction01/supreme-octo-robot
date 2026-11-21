// Workbench actions — projects index and Code facet
// group (split from actions.ts; the barrel composes the
// four groups). Each action forwards exactly one
// feed/mutation call to the workbench backend through
// the privileged wbApi socket contract — actions.ts
// carries the full contract note.
import { defineAction, z } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { callServer } from "./bridge";
import { codeArg, encProjectId, rawResult } from "./schemas";

export const codeActions = {
  // -- projects index + Code facet (SPEC §21): the
  // unified project index, and one project's git
  // surface — status / files / peek / save / history /
  // datasets — addressed by canonical project id with
  // an optional checkout (a linked worktree's census
  // id). Payloads ride rawResult: their shapes are the
  // backend's contracts, typed on the client in the
  // app lane's transport.
  getProjectsIndex: defineAction({
    description: "Fetch the unified project index: adopted and repository-only projects with code summaries.",
    request: z.object({}),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx) {
      return callServer<unknown>(ctx, "/api/projects-index");
    },
  }),

  getCodeStatus: defineAction({
    description: "Fetch one project's detailed git status, commits, and branches for a checkout.",
    request: codeArg,
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.checkout) params.set("checkout", args.checkout);
      const query = params.toString();
      return callServer<unknown>(
        ctx,
        `/api/projects/code/${encProjectId(args.projectId)}/status${query ? `?${query}` : ""}`,
      );
    },
  }),

  getCodeFiles: defineAction({
    description: "List one directory of a project's file tree, or the full tree, for the Files view.",
    request: z.object({
      projectId: z.string().min(1),
      checkout: z.string().min(1).optional(),
      all: z.boolean().optional(),
      dir: z.string().optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.checkout) params.set("checkout", args.checkout);
      if (args.dir != null) params.set("dir", args.dir);
      else if (args.all) params.set("all", "1");
      const query = params.toString();
      const suffix = query ? `?${query}` : "";
      return callServer<unknown>(ctx, `/api/projects/code/${encProjectId(args.projectId)}/files${suffix}`);
    },
  }),

  getCodeFile: defineAction({
    description:
      "Read one project file for the peek and editor, optionally revealing a withheld secret-shaped file.",
    request: z.object({
      projectId: z.string().min(1),
      checkout: z.string().min(1).optional(),
      path: z.string().min(1),
      reveal: z.boolean().optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      params.set("path", args.path);
      if (args.checkout) params.set("checkout", args.checkout);
      if (args.reveal) params.set("reveal", "1");
      return callServer<unknown>(
        ctx,
        `/api/projects/code/${encProjectId(args.projectId)}/file?${params.toString()}`,
      );
    },
  }),

  saveCodeFile: defineAction({
    description:
      "Save an edited project file with compare-and-swap protection, preserving its permissions.",
    request: z.object({
      projectId: z.string().min(1),
      checkout: z.string().min(1).optional(),
      path: z.string().min(1),
      content: z.string(),
      baseSha256: z.string().min(1),
      confirmSecret: z.boolean().optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.checkout) params.set("checkout", args.checkout);
      const query = params.toString();
      return callServer<unknown>(
        ctx,
        `/api/projects/code/${encProjectId(args.projectId)}/file${query ? `?${query}` : ""}`,
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

  // -- datasets: the Table view over dataset-kind
  // project files — described schema, one bounded rows
  // page, on-demand column stats, and the guarded SQL
  // console.
  getCodeDataset: defineAction({
    description: "Describe a dataset file's schema for the Table view.",
    request: z.object({
      projectId: z.string().min(1),
      checkout: z.string().min(1).optional(),
      path: z.string().min(1),
      table: z.string().min(1).optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      params.set("path", args.path);
      if (args.checkout) params.set("checkout", args.checkout);
      if (args.table) params.set("table", args.table);
      return callServer<unknown>(
        ctx,
        `/api/projects/code/${encProjectId(args.projectId)}/dataset?${params.toString()}`,
      );
    },
  }),

  getCodeDatasetRows: defineAction({
    description: "Fetch one bounded, sortable, filterable page of dataset rows.",
    request: z.object({
      projectId: z.string().min(1),
      checkout: z.string().min(1).optional(),
      path: z.string().min(1),
      table: z.string().min(1).optional(),
      limit: z.number().int().positive().optional(),
      offset: z.number().int().nonnegative().optional(),
      sort: z.string().min(1).optional(),
      dir: z.enum(["asc", "desc"]).optional(),
      filtersJson: z.string().optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      params.set("path", args.path);
      if (args.checkout) params.set("checkout", args.checkout);
      if (args.table) params.set("table", args.table);
      if (args.limit != null) params.set("limit", String(args.limit));
      if (args.offset != null) params.set("offset", String(args.offset));
      if (args.sort) params.set("sort", args.sort);
      if (args.dir) params.set("dir", args.dir);
      if (args.filtersJson) params.set("filters", args.filtersJson);
      return callServer<unknown>(
        ctx,
        `/api/projects/code/${encProjectId(args.projectId)}/dataset/rows?${params.toString()}`,
      );
    },
  }),

  getCodeDatasetStats: defineAction({
    description: "Compute on-demand column statistics for a dataset file.",
    request: z.object({
      projectId: z.string().min(1),
      checkout: z.string().min(1).optional(),
      path: z.string().min(1),
      table: z.string().min(1).optional(),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      params.set("path", args.path);
      if (args.checkout) params.set("checkout", args.checkout);
      if (args.table) params.set("table", args.table);
      return callServer<unknown>(
        ctx,
        `/api/projects/code/${encProjectId(args.projectId)}/dataset/stats?${params.toString()}`,
      );
    },
  }),

  postCodeDatasetSql: defineAction({
    description: "Run one guarded read-only SQL query against a dataset file.",
    request: z.object({
      projectId: z.string().min(1),
      checkout: z.string().min(1).optional(),
      path: z.string().min(1),
      table: z.string().min(1).optional(),
      sql: z.string().min(1),
    }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      const params = new URLSearchParams();
      if (args.checkout) params.set("checkout", args.checkout);
      const query = params.toString();
      return callServer<unknown>(
        ctx,
        `/api/projects/code/${encProjectId(args.projectId)}/dataset/sql${query ? `?${query}` : ""}`,
        "POST",
        {
          path: args.path,
          table: args.table,
          sql: args.sql,
        },
      );
    },
  }),

  getCodeHistory: defineAction({
    description: "Fetch one project's recorded status history and timeline.",
    request: z.object({ projectId: z.string().min(1) }),
    response: rawResult,
    privileged: [privileged.wbApi],
    async handler(ctx, args) {
      return callServer<unknown>(ctx, `/api/projects/code/${encProjectId(args.projectId)}/history`);
    },
  }),
};
