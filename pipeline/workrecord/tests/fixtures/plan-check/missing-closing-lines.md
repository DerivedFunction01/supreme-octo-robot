# Missing closing lines fixture

Status: draft

## Objective

One step whose block is complete but whose closing
lines omit verify: and est:.

## Steps

### Step 1 — Short-closed step

The step's work.

<!-- wb-step
step=1
todos=mcl-one
requires=
est=10m
fanout=one lane
-->
files: lib/example.py
done when: the example reads back changed
