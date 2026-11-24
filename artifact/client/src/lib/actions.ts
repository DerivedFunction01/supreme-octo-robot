// THE single action layer of the one client (owner ruling,
// audit Addendum 3: one integrated frontend).
//
// Every view in this client reaches the server through this
// module and no other: one `createActionClient` typed over
// the merged server registry (`server/src/actions.ts`, which
// spreads the four apps' sets — workbench / scheduler /
// attention / runner — into the space's one `Actions`).
// Types come straight from the server module; there is no
// codegen, no per-app client, no fetch wrapper, and no
// relay: a view calls `api.<action>(args)` and the SDK
// POSTs `{action, args}` to `./actions`.
//
// `import type { Actions }` is type-only by design: the
// client bundle never pulls in any server runtime
// (bun:sqlite, file APIs, etc.). The composed client
// program relaxes `verbatimModuleSyntax` for the app
// graphs it spans, so the `type` here is discipline, not
// enforcement — keep it.

import type { Actions } from "../../../server/src/actions";
import { createActionClient } from "@hatch/space-sdk/client";

export const api = createActionClient<typeof Actions>();

// Re-exported for convenience so views can do
//
//     import { api, type ApiResponse } from "../lib/actions";
//     type SchedulerOverview = ApiResponse<typeof api, "getOverview">;
//
// They are also available directly from "@hatch/space-sdk/client".
export type { ApiRequest, ApiResponse } from "@hatch/space-sdk/client";
