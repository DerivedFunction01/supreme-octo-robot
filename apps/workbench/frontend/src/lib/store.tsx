import { createContext, useContext, useSyncExternalStore } from "react";
import type { WorkbenchFeeds } from "./feeds";
import { createLiveAdapter } from "./liveAdapter";
import { createMockAdapter } from "./mockAdapter";
import type { WorkbenchAdapter } from "./seam";
import type { WbChannel } from "./transport";

// One adapter instance behind the seam for the whole app.
// Selection is evaluated once, when this module loads:
// - A feeds document present as globalThis.__WORKBENCH_FEEDS__
//   → the LIVE adapter over pipeline data. The document
//   arrives two ways: injected by the serving shell before
//   the app loads (the original topology), or fetched over
//   HTTP from GET /api/feeds by the integration entry,
//   which injects it before the app module graph evaluates
//   (the published form — see integration.tsx).
// - No document → the stateful mock, the demo persona:
//   the standalone preview's adapter, and the integration
//   entry's explicit ?adapter=mock opt-out.
// __WORKBENCH_API_BASE__ (set by the integration entry
// from its ?api= parameter) prefixes the live adapter's
// own fetches; absent, they are same-origin, exactly as
// the serving shell's topology serves them.
// __WORKBENCH_CHANNEL__ (set by the integration entry in
// its ?transport=relay form — the rebuilt superapp's
// frame) swaps the adapter's channel to the workhorse:*
// postMessage relay (transport.ts): every call rides an
// action to the shell instead of an HTTP fetch, with the
// seam's semantics unchanged.
const globals = globalThis as {
  __WORKBENCH_FEEDS__?: WorkbenchFeeds;
  __WORKBENCH_API_BASE__?: string;
  __WORKBENCH_CHANNEL__?: WbChannel;
};
const feeds = globals.__WORKBENCH_FEEDS__;
export const adapter: WorkbenchAdapter = feeds
  ? createLiveAdapter(
      feeds,
      globals.__WORKBENCH_API_BASE__ ?? "",
      globals.__WORKBENCH_CHANNEL__,
    )
  : createMockAdapter();

export const AdapterContext = createContext<WorkbenchAdapter>(adapter);

export function useAdapter(): WorkbenchAdapter {
  return useContext(AdapterContext);
}

/** Re-render when the store changes (any mutation bumps the
 *  adapter's version). */
export function useStoreVersion(): number {
  const a = useAdapter();
  const getSnapshot = () => a.version();
  return useSyncExternalStore((fn) => a.subscribe(fn), getSnapshot, getSnapshot);
}
