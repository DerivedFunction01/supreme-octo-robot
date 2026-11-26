# Neither fan-out nor serial fixture

Status: draft

## Objective

One step whose block declares no lane split and
names no serial exception.

## Steps

### Step 1 — Unsplit step

The step's work.

<!-- wb-step
step=1
todos=fsn-one
requires=
est=10m
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m
