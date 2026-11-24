// Entry config for the mock adapter (split from
// mock-adapter.ts): the served CONFIG constants, the
// config projection, and the one writer path (contract
// 09, amendment). The store is the source; the
// engine reads the same record at fire time, and a save
// lands in the same record — the save validates
// everything before applying anything, ledgers one op
// event per applied knob change, and the version CAS
// guard refuses a stale writer with nothing applied.
import type {
  ActionResult,
  ConfigView,
  LedgerEventInput,
} from "../types";
import { ENTRY_CONFIG, type JobRuntime, type Store } from "./seeds";

/** From the tracked fictional example, contracts/fixtures/
 *  scheduler-config.example.json (contract 04's seed pattern). */
export const CONFIG = {
  port: 8796,
  tick_secs: 20,
  // The example says "UTC"; contract 04 records that as the
  // example's error — the code default is America/New_York.
  default_timezone: "America/New_York",
  outbox_ack_timeout_secs: 3600,
  workbench_base_url: "http://127.0.0.1:8792",
};

export const iso = (ms: number) => new Date(ms).toISOString();

/** The adapter surface the writer path needs: its store,
 *  its ledger, and its emit. */
export interface ConfigHost {
  store: Store;
  ledger: (now: number, event: LedgerEventInput) => void;
  emit: () => void;
}

export function configView(rt: JobRuntime): ConfigView | null {
  const seed = ENTRY_CONFIG[rt.entry.id];
  if (!seed || !rt.config) return null;
  const state = rt.config;
  return {
    version: state.version,
    knobs: seed.knobs.map((knob) => ({
      ...knob,
      value: state.values[knob.key] ?? knob.value,
    })),
    constraints: seed.constraints ?? [],
  };
}

export async function saveConfig(
  host: ConfigHost,
  jobId: string,
  version: number,
  values: Record<string, number>,
): Promise<ActionResult> {
  const rt = host.store.jobs.get(jobId);
  if (!rt) return { ok: false, error: "not_found", detail: `No job ${jobId}.` };
  const seed = ENTRY_CONFIG[jobId];
  if (!seed || !rt.config) {
    return {
      ok: false,
      error: "bad_request",
      detail: `${jobId} carries no editable config.`,
    };
  }
  const state = rt.config;
  // The CAS guard: the save must present the version it
  // loaded. A moved version means another writer saved
  // first — refuse with the closed set's compare-failure
  // name and apply nothing.
  if (version !== state.version) {
    return {
      ok: false,
      error: "no_match",
      detail: `${jobId} config changed since it was loaded (now version ${state.version}) — reload and re-apply.`,
    };
  }
  // Validate everything before applying anything: unknown
  // knob, non-number, non-integer, out of the served range,
  // or a declared constraint violated refuses the whole
  // save — never half-applied, never ledgered.
  const merged: Record<string, number> = { ...state.values };
  for (const [key, value] of Object.entries(values)) {
    const knob = seed.knobs.find((k) => k.key === key);
    if (!knob) {
      return { ok: false, error: "bad_request", detail: `Unknown knob ${key}.` };
    }
    if (typeof value !== "number" || Number.isNaN(value)) {
      return {
        ok: false,
        error: "bad_request",
        detail: `${knob.label} must be a number.`,
      };
    }
    if (knob.type === "integer" && !Number.isInteger(value)) {
      return {
        ok: false,
        error: "bad_request",
        detail: `${knob.label} must be a whole number (${knob.unit}).`,
      };
    }
    if (value < knob.min || value > knob.max) {
      return {
        ok: false,
        error: "bad_request",
        detail: `${knob.label} must be between ${knob.min} and ${knob.max} ${knob.unit}.`,
      };
    }
    merged[key] = value;
  }
  for (const constraint of seed.constraints ?? []) {
    if (
      constraint.kind === "lt" &&
      !(merged[constraint.left]! < merged[constraint.right]!)
    ) {
      return { ok: false, error: "bad_request", detail: constraint.message };
    }
  }
  const now = Date.now();
  let changed = false;
  for (const knob of seed.knobs) {
    const next = merged[knob.key]!;
    const prev = state.values[knob.key]!;
    if (next === prev) continue;
    state.values[knob.key] = next;
    changed = true;
    // One op event per applied knob change (entry, knob,
    // old → new) — visible in the Ledger view like every
    // other delegated write (contract 04's audit rule).
    host.ledger(now, {
      kind: "op",
      op: "config",
      caller: "scheduler-app",
      job_id: jobId,
      knob: knob.key,
      label: knob.label,
      old: prev,
      new: next,
      unit: knob.unit,
      status: "ok",
    });
  }
  if (changed) state.version++;
  host.emit();
  return { ok: true };
}
