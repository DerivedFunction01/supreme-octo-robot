import { useSyncExternalStore } from "react";
import { MockVenueAdapter, type VenueAdapter } from "./adapter";
import { LiveVenueAdapter } from "./live-adapter";
import { RelayVenueAdapter, type RelayCall } from "./relay-adapter";

// The one seam instance. The standalone preview
// (src/main.tsx) keeps the mock adapter — its purpose. The
// integration build (src/integration.tsx, the published
// form) injects the live configuration on
// globalThis.__RUNNER_LIVE__ before importing the app, and
// the singleton is then the live adapter over the venue
// surface — the workbench __WORKBENCH_FEEDS__ injection
// pattern. The live base is same-origin: the entry writes
// an empty base, and the seam honours only a same-origin
// relative base from any injection (sanitizeBaseUrl) —
// an absolute or protocol-relative base is refused, so
// no crafted injection can point the adapter's POSTs at
// another origin. ?adapter=mock on the integration entry
// keeps the mock available in the integration shell for
// harness checks.
//
// The rebuilt superapp's frame form (rebuild step 3) is
// the more specific context and wins over the live form:
// the frame's composition injects the shell relay's
// transport on globalThis.__RUNNER_RELAY__ (artifact
// relay.ts's callAppAction) before importing the app, and
// the singleton is then the relay adapter — the live
// adapter's behaviour over the action channel, never a
// direct action client (the step-1 spike: a client built
// inside an iframe does not settle).

declare global {
  var __RUNNER_LIVE__: { baseUrl: string } | undefined;
  var __RUNNER_RELAY__: RelayCall | undefined;
  var __RUNNER_EMBEDDED__: boolean | undefined;
}

/** True when the integration (published) entry booted this
 *  bundle — the App renders its preview harness only in the
 *  standalone preview form. */
export const EMBEDDED: boolean = globalThis.__RUNNER_EMBEDDED__ === true;

/** The live base-url rule: only a same-origin relative
 *  base is honoured — "" (the origin root) or a path
 *  under it ("/panel"). An absolute URL, a protocol-
 *  relative "//host" base, or any other form is refused
 *  and the base falls back to the origin root, so the
 *  adapter's requests can never leave the serving
 *  origin no matter what an injection carries. */
export function sanitizeBaseUrl(baseUrl: string): string {
  if (baseUrl === "") return "";
  if (baseUrl.startsWith("/") && !baseUrl.startsWith("//")) return baseUrl;
  return "";
}

function selectAdapter(): VenueAdapter {
  const relay = globalThis.__RUNNER_RELAY__;
  if (relay) {
    return new RelayVenueAdapter(relay);
  }
  const live = globalThis.__RUNNER_LIVE__;
  if (live) {
    return new LiveVenueAdapter({ baseUrl: sanitizeBaseUrl(live.baseUrl) });
  }
  return new MockVenueAdapter();
}

export const adapter: VenueAdapter = selectAdapter();

export function useSnapshot() {
  useSyncExternalStore(
    (fn) => adapter.subscribe(fn),
    () => adapter.getVersion(),
  );
  return adapter.snapshot();
}

export type { VenueAdapter };
export { DURATION_OPTIONS, fmtDurHours, shapeInfo, fmtTime } from "./adapter";
