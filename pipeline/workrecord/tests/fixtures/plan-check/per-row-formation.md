# Per-row formation fixture

Status: draft

## Objective

A plan whose steps declare formations per row: the
formation-class refusal convicts it.

## Steps

### Step 1 — Build each row apart

Each family row builds in a worktree per row, so
the rows never share a formation.

<!-- wb-step
step=1
todos=pf-alpha
requires=
est=10m
fanout=row lanes
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the rows read back built
est: 10m

### Step 2 — Fan out by row worktrees

The second wave staffs the remaining rows.

<!-- wb-step
step=2
todos=pf-beta
requires=pf-alpha
est=10m
fanout=per-row worktrees
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the second wave reads back built
est: 10m
