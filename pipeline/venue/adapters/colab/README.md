# pipeline/venue/adapters/colab

The Colab adapter: everything Colab-shaped in the runner,
as adapter material — never core. It is in service as
this tree's Colab venue: the funnel dispatch reaches it
through the injected channel callable.

- **Carries:** the funnel dispatch behind the injected
  channel callable (per-venue shape catalog, stop/exec verb
  set, adapter-side OAuth token guard), the bridge
  (hash-signed command queue at `/content/bridge`),
  endpoint host-grammar shape reading, `snippets/` and
  `probes/` classes, and the adapter's own `jobs/` manifests.
- **Physical home:** `snippets/`, `probes/`, and
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
  extended as further venues land).
