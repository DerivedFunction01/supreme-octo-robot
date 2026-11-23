# pipeline/venue/adapters/colab

The Colab adapter: everything Colab-shaped in the runner,
extracted as adapter material — never core.

- **Lands in:** step S5 (plan §7 V2/V3), from the runner pin
  `636033b`; the colab-runner repo itself is not edited
  (D4) and stays in service as this adapter's home repo
  until the extracted adapter replaces its use (S11).
- **Carries:** the funnel dispatch behind the injected
  channel callable (per-venue shape catalog, stop/exec verb
  set, adapter-side OAuth token guard), the bridge
  (hash-signed command queue at `/content/bridge`),
  endpoint host-grammar shape reading, `snippets/` and
  `probes/` classes, and the repo's own `jobs/` manifests.
- **Physical home (S5):** `snippets/`, `probes/`, and
  `jobs/` physically live in this directory; the core
  reaches them only through `foundation.snippet_path` /
  `foundation.adapter_jobs_dir` (lease core) and the runner
  foundation's `JOBS` constant. The funnel dispatch table is
  `sync/cli.py`'s `VENUES` / `venue_dispatch` (this venue's
  registration: cli-help catalog source, the Colab verb set,
  the OAuth token guard as adapter-side auth); the shape
  catalog source registry is `sync/lease/core/catalog.py`'s
  `shape_catalog`. The bridge and the endpoint host-grammar
  reading stay inside the lease core's modules as adapter
  subsystems behind the funnel (review §3 names them the
  most Colab-shaped parts; their channel is the injected
  callable, and no core path reaches around it).
- **Governed by:** plan §7; the adapter contract takes the
  scope the working Colab adapter needs (D1 — proven or
  extended when a second venue exists).
