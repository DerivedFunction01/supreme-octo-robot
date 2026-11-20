# 10 — Portability/denylist seam

**Canonical owner:** the pipeline gate runner — one gate
component; denylists stay untracked per deployment. (Plan
§4.10; the gate runner itself is plan §6 P1, step S9.)

**The contract in one line:** the scanner is tracked code,
the denylist is untracked data, and the two never swap —
no personal literal ever enters a tracked file, and no
tracked file ever carries the list.

## The seam

- **Tracked scanner:** the portability scanner class
  (`tools/portability_scan.py` in the scheduler at the pin)
  — it enforces the anchor rule over tracked files and runs
  the personal-literal leg only when a denylist is
  provisioned.
- **Untracked denylist:** personal literals live only in an
  untracked file — provisioned via `SCHEDULER_DENYLIST_FILE`
  or `state/denylist.txt` scheduler-side; the runner's
  `config/denylist.txt` is the same class in its config
  pattern (contract 04). One component class, one
  provisioning rule per deployment.
- **The anchor rule (SCH9's portability half):** tracked
  files carry `${REPO}` / `${WS}` / `${HOME}` anchors, never
  absolute, home-anchored, or outside-repo paths — the
  no-machine-literals rule. Registry entries enforce it at
  validation (contract 02); this scanner enforces it over
  the whole tracked tree at the gate.

## Home in the gate runner

The seam lands in the automatic gate runner (§6 P1), not
as a per-repo script. The pinned gate shape it joins:
line cap → portability scan → registry validate → census →
tests (the scheduler's `check.sh`) — seed material for the
runner, which records verdicts against tree SHAs at
formation, landing, and stage deploy.

## Preserve clauses carried

SCH9's portability-anchors + no-machine-literals half. (The
watchdog/keeper half of SCH9 is carried in contract 04.)
