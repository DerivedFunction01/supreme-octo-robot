# Pipeline evaluation (`pipeline/evaluation/`)

The pipeline's evaluation derivations: pure functions
over the swept record and the workspace's repos — no
state of their own, no writer.

- `doctor.py` — the consistency checker over the
  swept set (the `wb doctor` verb's engine): plan /
  todo / registry findings plus the progress-entry
  findings. An armed todo's entry is convicted by
  presence, not by an admission field: an entry
  present in the pipeline registry but missing from
  the scheduling engine's next-due table is the
  unscheduled finding (contract 03, amendment 3).
- `repos.py` / `repo_state.py` — the repo census and
  per-repo state derivations.
- `datasets/` — the dataset derivations (schema,
  paged rows, stats, the guarded read-only console)
  over the files the record browses.
- `diffs/` — the grouped-diff derivations.

The package reads the work record through the
`pipeline/workrecord` path seam (its `__init__`
installs it); it never writes the record. The
server-side board/home derivations are not here —
they live with the workbench service's feed surface
(`pipeline/workrecord/server/`).

Tests: `tests/` — the pinned derivation suites, run
from `pipeline/` with the work-record service's venv
interpreter (the dataset derivations need its one
declared dependency, duckdb).
