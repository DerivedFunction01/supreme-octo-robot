// The live data seam: the same VenueAdapter interface the
// mock implements, over the venue surface's own HTTP API.
// Split along its seams (served shapes / helpers / state
// and outbox projections / the adapter class); this module
// keeps the full public surface by re-exporting from the
// live-adapter/ modules, so no caller changes.

export { LiveVenueAdapter } from "./live-adapter/adapter";
export { liveSessionName } from "./live-adapter/helpers";
