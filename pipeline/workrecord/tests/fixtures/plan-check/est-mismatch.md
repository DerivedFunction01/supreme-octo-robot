# Estimate mismatch fixture

Status: draft

## Objective

One step whose sentinel est= and closing est: line
state different estimates.

## Steps

### Step 1 — Disagreeing step

The step's work.

<!-- wb-step
step=1
todos=em-one
requires=
est=30m
fanout=one lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 45m
