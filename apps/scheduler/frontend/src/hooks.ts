import { useEffect, useState } from "react";
import type { SchedulerApi } from "./api";

/** Re-render whenever the adapter signals served state may have
 *  changed (engine ticks at 1 s, so ages and countdowns stay live). */
export function useApiTick(api: SchedulerApi): void {
  const [, setVersion] = useState(0);
  useEffect(
    () => api.subscribe(() => setVersion((v) => v + 1)),
    [api],
  );
}
