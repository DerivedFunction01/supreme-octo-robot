# Overlay inventory — scheduler

The deployed scheduler was an untracked overlay on its
pinned tree: the tree carried the engine, the registry
schema, and two live entries (`jobs/bridge-wake.yaml`,
`jobs/bridge-drain.yaml`); the fleet — the remaining job
entries, all bodies, the caller→chat routing config, the
file-registry manifest, and several member scripts — sat
outside git, held out by the tracked `.gitignore` plus
local-only exclude patterns. The capture classified it:

- **Promote to tracked:** 19 operator job entries, 12
  Markdown bodies (the behavioral contracts for agent
  jobs), 5 overlay-only member scripts, and
  `jobs/RETIRED.md` — the retirement record the schema
  requires, hidden by the local exclude at capture.
- **Machine-derived, captured for validation, not
  promoted:** the per-lease `colab-liveness-*` entries
  (written and deleted by the runner lease core) and the
  `wb-progress-*` entries (written by the workbench
  harness). Their writers own their lifecycle; the
  entries are born and retire with the leases and todos
  they track.
- **Live config:** `config.json` (the connector caller
  registry — token hashes and scopes only, no raw tokens
  — and the Git SSH path pair; tracked specimen
  `config.example.json`), the file-registry manifest
  (live config under the seed/example pattern; tracked
  specimen under `examples/file-registry/`), and two
  routing tables that were misfiled among the bodies —
  `bridge-wake-owners.yaml` and
  `restart-reconcile-owners.yaml`. Routing config is
  config, not body content; the capture separates the
  classes.
- **Runtime state, not carried:** the `state/` stores,
  including the live ledger. No manual ledger export was
  taken at capture: the ledger is the live server's
  SQLite store and changes under the running server, so a
  file copy would be a torn snapshot. Ledger history
  moves at cutover via the server's own export against a
  quiesced store, with its printed SHA-256 as the proof.
- **Credential, reference only:** a plaintext env file
  held a raw connector token (the manifest's finding 2).
  Verified a redundant copy of the live caller token —
  never committed, read by nothing — and removed;
  deletion verified. Recovery, if the live copy is ever
  lost, is a rotation via `bin/sched connector-token`.
- **Not captured:** the repo's own workbench work records
  (the harness reads them in place) and bytecode caches —
  debris, including stale bytecode for retired modules.

Validation stands as the capture's done-evidence: on a
bare checkout of the pin, registry validation reads 1
valid, 1 invalid (`bridge-drain`: its body file does not
exist); with the captured overlay applied, 26 valid
entries, 0 invalid, and the census lists all 26. Only
`bridge-drain` is load-quarantined on the bare pin —
`bridge-wake` validates there because the loader never
checks its wake body or routing config; it is
operationally incomplete on the bare pin and completed
by the overlay.
