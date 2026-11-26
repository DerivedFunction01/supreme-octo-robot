# Both fan-out and serial fixture

Status: draft

## Objective

One step whose block carries both fanout= and
serial= — exactly one is the rule.

## Steps

### Step 1 — Doubly declared step

The step's work.

<!-- wb-step
step=1
todos=fsb-one
requires=
est=10m
fanout=one lane
serial=the shared example file
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m
