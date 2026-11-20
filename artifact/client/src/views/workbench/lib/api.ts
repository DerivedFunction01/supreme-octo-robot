// Transport seam (INTEGRATION.md §3): the original
// viewer's lib/api.ts created its own action client over
// the server Actions. In the one client there is exactly
// one action layer — src/lib/actions.ts, one
// createActionClient typed over the merged server
// registry — so this module re-exports it and the ported
// sections keep their import surface unchanged. Every
// action the sections call is schema-identical in the
// merged set (restoration hand-back: 39/39), and the
// envelope semantics are the original's: `{ status,
// payload, error }`, payload verbatim, status 0 =
// unreachable, never a hang or a throw.

export { api } from "../../../lib/actions";
export type { ApiRequest, ApiResponse } from "../../../lib/actions";
