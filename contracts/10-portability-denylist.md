# 10 — Portability/denylist seam

**Canonical owner:** the pipeline gate runner — one gate
component; denylists stay untracked per deployment. (Plan
§4.10; the gate runner itself is plan §6 P1 and plan
§4.16.)

**The contract in one line:** the scanner is tracked code,
the denylist is untracked data, and the two never swap —
no personal literal ever enters a tracked file, and no
tracked file ever carries the list.

## The seam

- **Tracked scanner:** the portability scanner component
  in the gate package (`pipeline/gate/portability.py`) —
  it enforces the anchor rule over tracked files and runs
  the personal-literal leg only when a denylist is
  provisioned. The scheduler's
  `pipeline/scheduling/tools/portability_scan.py` re-points
  to this component.
- **Untracked denylist:** personal literals live only in
  untracked files, in the layered form — one provisioning
  convention per repo: the `STARTER_DENYLIST_FILE` env
  var, else the ground at the repo's one home,
  `pipeline/platform/state/denylist.txt`, with the repo
  layer beside the resolved ground (`denylist.repo.txt`
  in the ground's directory) unioned with the ground on
  read when present. The ground is homed once and
  inherited; instance-shaped literals live in the repo
  layer only. Ground-only provisioning is legitimate, and
  a layer never rescues a set-but-unreadable ground. No
  per-package list copies and no per-component env aliases
  exist; divergent copies converge by union into the one
  home, and a literal leaves the list only by deliberate
  removal. Absent a provisioned
  list, the leg prints a notice and skips; where a list is
  provisioned, the gate fails on its findings
  (`--fail-on-denylist`, passed by the gate exactly when a
  denylist is provisioned).
- **The anchor rule (SCH9's portability half):** tracked
  files carry `${REPO}` / `${WS}` / `${HOME}` anchors, never
  absolute, home-anchored, or outside-repo paths — the
  no-machine-literals rule. Registry entries enforce it at
  validation (contract 02); this scanner enforces it over
  the whole tracked tree at the gate. Findings report rule,
  path, and line only — never the matched content.

## Home in the gate runner

The seam lives in the automatic gate runner, not as a
per-repo script: the root gate (`check.py`) composes the
gate package's shared legs — line cap,
portability/denylist, ruff, policy scanners, test
isolation, AST-targeted tests — over every package's
declared gate (`gate.json`), with repo-scoped portability
coverage scanning every tracked file no package's leg
covers, so the whole tracked tree is scanned exactly
once. The runner records verdicts against tree SHAs at
formation, landing, and stage deploy.

## Preserve clauses carried

SCH9's portability-anchors + no-machine-literals half. (The
watchdog/keeper half of SCH9 is carried in contract 04.)
