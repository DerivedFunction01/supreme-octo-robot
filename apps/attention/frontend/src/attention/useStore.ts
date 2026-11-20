import { createContext, useContext, useSyncExternalStore } from "react";
import type { AttentionDataSource } from "./types";

export const DataContext = createContext<AttentionDataSource | null>(null);

export function useDataSource(): AttentionDataSource {
  const ds = useContext(DataContext);
  if (!ds) throw new Error("AttentionDataSource missing from context");
  return ds;
}

/** Re-render whenever the store's version moves; view
 * getters are called during render and serve ready-made
 * view models (the adapter owns every derivation). */
export function useStoreVersion(): void {
  const ds = useDataSource();
  useSyncExternalStore(ds.subscribe, ds.getVersion, ds.getVersion);
}
