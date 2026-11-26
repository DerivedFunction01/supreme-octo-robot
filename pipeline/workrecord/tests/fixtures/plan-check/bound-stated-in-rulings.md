# Bound stated in rulings fixture

Status: draft

## Objective

A plan that states the formation bound as a
prohibition and fans out per family: the
formation class makes no finding on it.

## Rulings

- Worktrees are bounded per formation group, never
  per row; grouped changes share one worktree.
- No gate per item runs: several items waiting for
  tests merge into one union gated once.

## Steps

### Step 1 — Build the families together

The families form one group on one worktree and
gate as one union.

<!-- wb-step
step=1
todos=pb-alpha
requires=
est=10m
fanout=family lanes
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the families read back built
est: 10m
