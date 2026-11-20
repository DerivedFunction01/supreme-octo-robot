// The mock adapter's config seed blocks — mock data, not
// contract data, since the S8 pipeline serving landed.
//
// The classification table that used to live here is GONE:
// the pipeline now serves audience/family/open_in on every
// job view (pipeline/scheduling/server/classification.py),
// and the live adapter reads the served fields. The mock's
// copy of the fleet classification lives with the mock's
// seed construction (src/mock/seeds.ts), where fake-server
// data belongs.
//
// What remains here is the mock's seed form of the two
// knob-bearing entries' config blocks (contract 09,
// amendment 2026-11-13). They stay adapter-carried — by the
// MOCK adapter only — for one named reason: the demo
// persona's fake server must seed its store from something,
// and the values must mirror the pipeline's backfilled
// served blocks (pipeline/scheduling/jobs/storage-watch.yaml
// and memory-index-watchdog.yaml carry the same blocks at
// version 1) so the demo exercises the same form the live
// surface serves. The live adapter never reads this file:
// it renders the served configView, or config: null where
// the pipeline serves none — e.g. the tools/live fixture
// capture, whose S1-capture entries carry no blocks and so
// serve null honestly.
// flap-watch and bridge-drain were examined and carry NO
// block (the amendment names why) — honest absence, like
// every other knobless entry.

import type { ConfigConstraint, ConfigKnob } from "./types";

export type EntryConfigSeed = {
  knobs: ConfigKnob[];
  constraints?: ConfigConstraint[];
};

export const ENTRY_CONFIG: Record<string, EntryConfigSeed> = {
  // The home free-space tiers: ops/storage_watch.py's
  // HOME_LOW = 50 GB / HOME_CRIT = 45 GB constants — the
  // owner's 2026-11-11 retune figures. (The script's /tmp
  // tiers, 128/32 MB, are not seeded: the ruling named the
  // GB tiers.)
  "storage-watch": {
    knobs: [
      {
        key: "home_low_free_gb",
        label: "Low tier — home free space below",
        type: "integer",
        unit: "GB",
        value: 50,
        min: 1,
        max: 500,
      },
      {
        key: "home_critical_free_gb",
        label: "Critical tier — home free space below",
        type: "integer",
        unit: "GB",
        value: 45,
        min: 1,
        max: 500,
      },
    ],
    constraints: [
      {
        kind: "lt",
        left: "home_critical_free_gb",
        right: "home_low_free_gb",
        message: "The critical tier must sit below the low tier.",
      },
    ],
  },
  // The topic thresholds the held check script
  // (ops/memory_watchdog_check.sh) takes as env parameters:
  // SCHEDULER_TOPIC_FILE_MAX_BYTES (40960) and
  // SCHEDULER_TOPIC_PER_FILE_BYTES (12800, the per-topic
  // register the set total scales from). The script's third
  // parameter (SCHEDULER_TOPIC_TOTAL_MAX_BYTES) is unset by
  // default and is not rendered — a knob with no live value.
  "memory-index-watchdog": {
    knobs: [
      {
        key: "topic_file_max_bytes",
        label: "Topic file cap",
        type: "integer",
        unit: "bytes",
        value: 40960,
        min: 1024,
        max: 1048576,
      },
      {
        key: "topic_per_file_bytes",
        label: "Topic set register — per-topic allowance",
        type: "integer",
        unit: "bytes",
        value: 12800,
        min: 128,
        max: 1048576,
      },
    ],
  },
};
