# Work-record service (`pipeline/workrecord/`)

The pipeline's work-record service (plan §1): the
record of the work itself — **goals are the top level
of this record** (goal → bundles/plans → todos → arms,
§1), the registry of projects, and the arming writers
that project armed todos outward. It is the pinned
workbench harness (pin `b0b9cc5`), consolidated at S4:
the server feeds are not part of this service — the
Workbench app's read surface lands at S8.

The harness's product spec of record is `SPEC.md`
beside this README (ported 2026-11-18 from the
standalone workbench-viewer repo's approved SPEC).

Layout, as landed:

- `wb` — the harness CLI (registry, bundles, todos,
  sweep, progress, doctor verb). The doctor verb's
  checks live in `pipeline/evaluation/`; the CLI loads
  them through the pipeline path seam, so the harness
  carries no server import.
- `lib/` — the record itself: `registry/` (registry.db
  writers, the derived views, and the export fold),
  `plans/` (the plan / bundle / todo parsers),
  `writes/` (the write paths: `bundles.py`, the todo
  writers — every transition re-derives the projections
  in the same call; the file editor, `files.py`; goal
  records; the rename driver), `progress/` (derivation
  plus the two arming writers), `discovery/` (the
  project sweep and the manifest), and `derived/` (the
  read-time derivations: active plans, staleness,
  worktrees, the home feed, fingerprint, annotations).
  The foundation stays flat: `paths.py`, `util.py`,
  `kit.py`, `validators.py`.
- `lib/progress/schedule.py` — the scheduler-entry
  removal path (retired, Step 6: the rendering is
  gone — the attention tick's armed rows are the
  check now). It deletes any lingering wb-progress
  entry from **the pipeline's own registry**
  (`pipeline/scheduling/jobs/`) through the §4.3 seam
  and never writes one. The sibling seams
  (`WB_SCHEDULER_JOBS_DIR`, `WB_WORKSPACE_ROOT`,
  `WB_VIEWER_ROOT`) are retained for external
  adopters, whose projects keep building with the
  harness absent: an absent sibling is a silent no-op.
- `lib/progress/attention.py` — the armed-row writer.
  It writes the record-armed row (contract 03) into
  the pipeline's own armed directory (`armed/` under
  this root, gitignored); contract 14's record-armed
  form is the row's shape, stamped with the adopting
  project's identity. The attention service reads the
  rows from there — nothing is dropped into another
  repo's runtime state.
- Writes ride the unified writer (contract 15):
  `lib/util.py`'s staged writes delegate to
  `pipeline/platform/writer.py`, and the editor's
  guarded saves keep their sha compare-and-swap in
  `lib/writes/files.py` with the write act itself on the
  writer — a stale sha is refused whole (409) before
  anything is written, and the target's mode is
  preserved across the save.

Dispositioned at S6 (§4.5): the carried `lib/messages/`
and `lib/notify.py` retired into `pipeline/dispatch/`
as the substrate's `dispatch.messages` / `dispatch.
notify`; the doctor posts its digest through them
there, and their tests ride with the code. The
server-side derivation modules (`home`, `annotations`,
`fingerprint`) were not moved; they land with the
Workbench app's feed surface at S8.

Tests: `tests/` — the pinned harness and lib suites
at their pinned counts. Run with the service venv
(`python3 init_venv.py` once): `.venv/bin/python -m
unittest discover -s tests -t .` from this directory.
