// Transport for the attention views: the one client's
// action layer (lib/actions.ts) unwrapped to the original
// client's semantics (pages/attention/app.js):
//
//   api()     — an HTTP error status composes its message
//               from the problem body (detail, field
//               errors, title) and throws; a bridge-down
//               status 0 is a failure with the bridge's
//               diagnosis, never data.
//   portion() — a failed read falls back to the last good
//               copy, flagged stale; with no last good
//               copy the portion is absent (null), and the
//               view renders its honest unreachable state.
//
// The last-good store is module-level so portions survive
// subroute changes inside the attention mount, exactly as
// the original's `lastGood` object did across its views.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/actions";

export { api };

export interface Envelope {
  status: number;
  payload: unknown;
  error: string | null;
}

interface ProblemBody {
  detail?: string;
  title?: string;
  field_errors?: { field?: string; message: string }[];
  errors?: { field?: string; message: string }[];
}

/** Compose the original's error message from a problem
 *  body: "detail — field: message; field: message", then
 *  title, then the status. */
function problemMessage(body: ProblemBody | null, status: number): string {
  if (body) {
    const fields = (body.field_errors ?? body.errors ?? [])
      .map((e) => (e.field ? `${e.field}: ` : "") + e.message)
      .join("; ");
    const msg = [body.detail, fields].filter(Boolean).join(" — ");
    if (msg) return msg;
    if (body.title) return body.title;
  }
  return `Request failed (${status})`;
}

/** Unwrap one action envelope to its payload, throwing
 *  the original's composed error on any failure status.
 *  Status 0 (bridge unreachable/timeout) throws the
 *  bridge's diagnosis — it must surface as a failure so
 *  the views' last-good semantics stay honest. */
export function unwrap<T>(env: Envelope): T {
  if (env.status === 0) {
    throw new Error(env.error ?? "The surface is unreachable.");
  }
  const payload = (env.payload ?? null) as T | null;
  if (env.status >= 400) {
    throw new Error(problemMessage(payload as ProblemBody | null, env.status));
  }
  if (payload === null) {
    throw new Error(env.error ?? problemMessage(null, env.status));
  }
  return payload;
}

/** Await one action call and unwrap its envelope. */
export async function call<T>(result: Promise<Envelope>): Promise<T> {
  return unwrap<T>(await result);
}

/** The original's idempotency key on every write. */
export function idem(): string {
  return crypto.randomUUID();
}

/* ---------------- portion(): last-good reads ---------------- */

const lastGood = new Map<string, unknown>();

/** Forget one portion's last good copy (the original's
 *  `REG = null` move after a write that changes it). */
export function forgetPortion(key: string): void {
  lastGood.delete(key);
}

export interface Portion<T> {
  /** The portion's data: fresh, or the last good copy
   *  when `stale`. Null when nothing has ever loaded. */
  data: T | null;
  /** True when `data` is the last good copy after a
   *  failed refresh. */
  stale: boolean;
  /** True while the first load is in flight. */
  loading: boolean;
  /** The failure message when the portion could not
   *  load and no last good copy exists. */
  error: string | null;
  refresh: () => void;
}

/** Load one named portion with last-good fallback.
 *  `fetcher` is read at fetch time; the portion refetches
 *  when its key or the view's refresh nonce changes. */
export function usePortion<T>(
  key: string,
  fetcher: () => Promise<T>,
  refreshKey: number,
): Portion<T> {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<{
    data: T | null;
    stale: boolean;
    loading: boolean;
    error: string | null;
  }>(() => {
    const good = lastGood.get(key) as T | undefined;
    return { data: good ?? null, stale: false, loading: true, error: null };
  });

  useEffect(() => {
    let live = true;
    setState((prev) => ({ ...prev, loading: prev.data === null }));
    fetcher()
      .then((data) => {
        if (!live) return;
        lastGood.set(key, data);
        setState({ data, stale: false, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (!live) return;
        const good = lastGood.get(key) as T | undefined;
        setState({
          data: good ?? null,
          stale: good !== undefined,
          loading: false,
          error: good !== undefined ? null : e instanceof Error ? e.message : String(e),
        });
      });
    return () => {
      live = false;
    };
    // The fetcher is chosen by the key; refreshKey/nonce drive refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, refreshKey, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, refresh };
}

/** The stale tag the original appends to its scope lines. */
export function staleText(stale: boolean): string {
  return stale ? " · showing last good copy" : "";
}
