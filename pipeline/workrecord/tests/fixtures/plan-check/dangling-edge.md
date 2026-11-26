# Dangling edge fixture

Status: draft

## Objective

One step requiring a todo no step in this plan
mints and nothing in the project resolves.

## Steps

### Step 1 — Blocked on nothing

The step's work.

<!-- wb-step
step=1
todos=de-one
requires=never-minted-anywhere
est=10m
fanout=one lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m
