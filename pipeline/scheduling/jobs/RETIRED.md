# Retired jobs — the register

Every job whose entry has been deleted from the
registry, with what it was and why it is retired, so
the census stays complete. The registry itself admits
active jobs only; nothing here runs.

- **facade-plan-closeout-push** — a closeout job that
  completed its work and removed its own cron (EC-16)
  before the server migration; it never ran on the
  server. Its registry entry and body are removed.
- **git-repo-viewer-healthcheck**,
  **git-repo-viewer-digest** — a disabled pair, deleted
  under the inactive-schedules ruling; never
  registered.
- **recruiter-reply-drafter** — retired by direction
  (unneeded until a decision re-enables it).
  Its registry entry is deleted under the
  inactive-schedules ruling; its body and member state
  are untouched, and the deleted entry is preserved in
  the owning goal's files, so re-registration on a
  decision is a restore, not a rebuild. The body file is
  not carried in this tracked tree under the genericity
  ruling — it serves a per-deployment programme and
  its content is that programme's own record.
- **flap-study-server-sample** — a temporary study
  entry for the write-denial flap tracking plan;
  registered, fired, and deleted once its samples were
  recorded. Its finding stands: a server-spawned child
  does NOT reproduce the write denial (all canary
  mechanisms writable while agent-class processes were
  denied in the same window), so the tracker probe
  cannot be hosted as a plain scripted job command.
- **approval-sweeper**, **sweeper-nudge-check**,
  **sweeper-deliver**, **sweeper-derive** — the
  sweeper apparatus (the agentic cycle and its scripted
  checker, delivery, and approvals-derivation tiers),
  retired at the apparatus's closeout under the
  commission as boundary-corrected. The successor
  system is owner-attention.
- **Five per-deployment entries** serving programmes
  outside this repo — three operator entries (with
  their driver scripts and one agent body) and two
  machine-rendered progress arms — removed from the
  tracked registry under the genericity ruling: the
  tracked registry carries this system's own fleet
  only; per-deployment entries are provisioned in the
  deployment, and their records live with their
  programmes. Their ids are deliberately not recorded
  here.
- **workbench-viewer-healthcheck** — the S11
  one-process entry ran the platform watchdog with no
  unit distinction against the shared episode marker;
  superseded by per-unit healthcheck entries, one per
  systemd unit, each with its own episode marker and
  escalation body. Its entry and body are removed; the
  body's ladder instructions named the retired per-repo
  tree, and its content survives in the original repo's
  archive.
- **owner-attention-healthcheck** — retired for the
  same reason: the one-process entry is superseded by
  the per-unit entries (the attention surface is
  supervised under workhorse-healthcheck, the coupled
  unit that serves it). Its entry and body are removed,
  with the same archive disposition as above.
- **workhorse-healthcheck**,
  **workbench-healthcheck**, **venue-healthcheck** —
  the per-unit healthcheck entries, retired in the
  watchdog actuation cure: their driver was the
  scheduler server inside workhorse.service, so that
  unit's failure silenced the ladder for the whole
  fleet. The ladder is now driven by systemd timers
  (workhorse-watchdog.timer, workbench-watchdog.timer,
  venue-watchdog.timer, rendered and installed by the
  platform unit machinery in pipeline/platform/ops),
  which survive any watched unit's death; the ladder
  also carries the failed-unit rung (reset-failed, then
  start). Their entries are removed; their escalation
  bodies are untracked local artefacts and remain on
  disk.
- **wb-progress-\*** — the workbench harness's
  machine-rendered progress entries: the rendering is
  retired (supervision plan Step 6), the lingering
  entries are deleted, and the app tick carries the
  supervision measures the entries armed (the three
  Muse supervision crons — specimen-parallel-staffing-
  reminder, gap-closure-sweep, greenfield-progress-
  watch — stand disabled with them). The todo files
  remain the record of truth for the work the entries
  tracked.
- **load-venue-watch** — retired on admission of its
  successor **load-monitor**: the entry stood suspended
  with its admission proof run never completed and
  caught nothing while suspended. The successor reworks
  the same watch script with per-process naming, both
  venue fleets, and the snapshot store the Task Manager
  section serves.
- **gap-closure-sweep** — the scheduler-registry twin
  of the gap-closure sweep, retired because its
  agent-due pings have no designated executor: the
  keeper worker polls the job, cannot run it (its
  actuators are agent acts), and its occurrences
  coalesced unworked. The executing home is the Muse
  cron of the same name, re-enabled with the cured
  body text, until the stopped-lane actuation build's
  coverage handover is proven class by class. Its
  registry entry is deleted; the body file remains on
  disk as the text both forms read. The coalesced
  backlog ping is written off with the retirement,
  not drained.
- **declaration-reconcile** — the scheduler-registry
  form of the declaration reconcile, retired under the
  agent-job admission rule: its agent-due pings had no
  designated executing surface (its standing ping
  coalesced 43 occurrences unacked), so the entry could
  not name an executor and does not arm. The executing
  home is its Muse cron twin (hourly), which runs the
  registry body text and reports the pass's output to
  main. Its registry entry is deleted; the body file
  remains on disk as the text the cron reads. The
  standing ping is written off with the retirement,
  not drained.
