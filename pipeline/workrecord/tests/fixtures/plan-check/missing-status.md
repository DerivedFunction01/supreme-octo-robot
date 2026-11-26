# Missing Status fixture

Executor: the fixture lane

## Objective

A plan whose header carries no Status field: it
declares nothing, and the gate refuses silence.

## Steps

### Step 1 — Conforming step

The step's work.

<!-- wb-step
step=1
todos=ms-one
requires=
est=10m
fanout=one lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m
