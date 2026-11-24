// The scheduler app's data seam.
//
// Every surface renders only what this interface serves, and
// every control acts only through it. Stage D2 ships the
// stateful mock implementation (src/mock/); S8 adds the live
// adapter (src/live/) — HTTP over the pipeline's /api/v1,
// contract 09 — behind this same interface with no frontend
// rewrite (plan §8, mock-first amendment). The integration
// entry selects the adapter (?adapter=live); the mock
// remains the default for the demo persona.
//
// Note on the action verbs (gap G8, decided at S8 from the
// contracts — contract 09's S8 dispositions): contract 09
// records the pinned viewer's standing rule that the shell
// stays read-only (ack, suspend, admit live in the operator
// CLIs), and nothing in the contracts graduates runNow /
// setJobEnabled / ackPing to the live shell, so the live
// adapter refuses them (outside_scope) while the mock —
// under the owner's mock-first ruling that
// every storyboarded control WORK against the mock store —
// implements them end-to-end. saveConfig is the graduated
// verb (the contract 09 amendment designs it for the app):
// the pipeline now serves config blocks and the guarded
// save behind them (POST /api/v1/jobs/<id>/config), so the
// live adapter wires to that route. The verb is async —
// the live save is a round trip; the mock resolves
// immediately against its store.

import type {
  ActionResult,
  JobDetailView,
  JobView,
  LedgerView,
  OverviewView,
  PingView,
} from "./types";

export interface SchedulerApi {
  getOverview(): OverviewView;
  listJobs(): JobView[];
  getJob(id: string): JobDetailView | null;
  /** Pending pings, oldest first (contract 09). */
  listPings(): PingView[];
  /** Recently acked pings, newest first — the storyboard's
   *  Recent group; the records are the outbox's own. */
  listRecentPings(): PingView[];
  getLedger(limit: number): LedgerView;

  /** Fire a job now. A fire while the job is running follows
   *  contract 13: the point is skipped and ledgered
   *  (skipped_overlap), never duplicated. */
  runNow(jobId: string): ActionResult;
  /** Pause = suspend the entry (contract 14 status), resume =
   *  back to active. Contract 13: the engine fires an entry iff
   *  its status is active and it stands in the registry. */
  setJobEnabled(jobId: string, enabled: boolean): ActionResult;
  /** Acknowledge a pending ping (the ping view's Acknowledge
   *  control); the ack is ledgered (ping_acked). */
  ackPing(pingId: string, ackedBy: string): ActionResult;
  /** Save a knob-bearing entry's config (contract 09,
   *  amendment). The save presents the config
   *  version the form loaded: a stale save is refused
   *  (no_match), a value outside its served range — or
   *  violating the block's declared constraints — is
   *  refused whole (bad_request) with nothing applied, and
   *  an unknown job is refused (not_found). Every applied
   *  knob change is ledgered as an op event (entry, knob,
   *  old → new). The engine reads the saved values at fire
   *  time from the same store record. Async: the live
   *  adapter's save is the POST round trip; on success the
   *  adapter's cached detail already carries the new served
   *  config when this resolves. */
  saveConfig(
    jobId: string,
    version: number,
    values: Record<string, number>,
  ): Promise<ActionResult>;

  /** Fires whenever served state may have changed (engine tick,
   *  action, simulated wake). Returns the unsubscribe. */
  subscribe(listener: () => void): () => void;
}
