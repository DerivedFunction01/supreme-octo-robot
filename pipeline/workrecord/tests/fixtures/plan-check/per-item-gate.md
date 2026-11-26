# Per-item gate fixture

Status: draft

## Objective

A plan whose step declares a gate fire per item:
the formation-class refusal convicts it.

## Steps

### Step 1 — Gate every change on its own

Every change runs one gate per item before it may
land, however many are waiting.

<!-- wb-step
step=1
todos=pg-alpha
requires=
est=10m
fanout=item lanes
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the items read back gated
est: 10m
