// The data seam's interface: the frontend consumes ONLY
// this interface and its served projections. Implemented
// by the mock (./mock) today and by the live adapter
// (src/venue/live-adapter) behind the same seam.

import type {
  AcquireInput,
  BudgetCaps,
  GrantView,
  LeaseView,
  RunView,
  Snapshot,
} from "../types";

export interface VenueAdapter {
  subscribe(fn: () => void): () => void;
  getVersion(): number;
  now(): string;
  snapshot(): Snapshot;
  registeredCallers(): string[];
  probe(): Promise<{ reachable: boolean; at: string }>;
  restartServer(): Promise<void>;
  setReachable(reachable: boolean): void;
  acquire(input: AcquireInput): Promise<LeaseView>;
  extend(session: string, hours: number): Promise<{ lease: LeaseView; note: string }>;
  shorten(
    session: string,
    target: { hours: number } | { deadline: string },
  ): Promise<{ lease: LeaseView; note: string }>;
  release(session: string): Promise<void>;
  startGrant(input: { hours: number; burst: string }): Promise<GrantView>;
  extendGrant(hours: number): Promise<{ grant: GrantView | null; note: string }>;
  ungrant(): Promise<void>;
  releaseAccess(session: string): Promise<void>;
  /** Update one account's budget caps (venue rework): each cap
   *  is a non-negative number or null (no cap). Resolves with
   *  the caps in force after the write. */
  setBudgetCaps(input: { venue: string; account: string; caps: BudgetCaps }): Promise<BudgetCaps>;
  adoptOrphan(session: string, caller: string, shape?: string): Promise<LeaseView>;
  /** The endpoint form of adoption, for a nameless census
   *  row (an assignment that lost its name server-side):
   *  a fresh name is minted and bound to the endpoint,
   *  and the record restores under it. */
  adoptNamelessOrphan(endpoint: string, caller: string, shape?: string): Promise<LeaseView>;
  /** The endpoint form of release, for a nameless census
   *  row: the endpoint is the unassign key. */
  releaseNamelessOrphan(endpoint: string): Promise<void>;
  releaseOrphan(session: string): Promise<void>;
  exec(session: string, job: string, caller: string): Promise<RunView>;
}
