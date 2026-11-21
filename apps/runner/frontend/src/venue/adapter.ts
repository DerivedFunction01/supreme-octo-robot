// The data seam. The frontend consumes ONLY this interface and
// its served projections. Today the implementation is the
// stateful mock below, seeded with contract-12-shaped data;
// at S8 the live adapter replaces it behind the same seam
// with no frontend rewrite (plan §8, mock-first amendment).
//
// The mock implements the D1 adapter verbs against its store —
// acquire / extend / shorten / release / exec / probe, the
// two-tier grant lifecycle (grant / extend-grant / ungrant),
// and the access release — with the pinned semantics contract
// 12 / contract 01 name: placement by latest-deadline
// adoption, adoption-only pins, spend counted from the
// store's own lease segments (never balance deltas), exactly
// one run-terminal event per terminal transition, and caller
// attribution (presented-but-unregistered refused, absent =
// unattributed).
//
// Split along its seams (catalog data / formatting / the
// mock store and its projections); this module keeps the
// full public surface by re-exporting from the adapter/
// modules, so no caller changes.

export type { VenueAdapter } from "./adapter/interface";
export { MockVenueAdapter } from "./adapter/mock";
export { DURATION_OPTIONS, fmtDurHours, shapeInfo } from "./adapter/catalog";
export {
  KIND_LABEL,
  fmtDateToken,
  fmtDuration,
  fmtTime,
  fmtTimeLong,
} from "./adapter/format";
