# Requires cycle fixture

Status: draft

## Objective

Two steps each requiring the other's todo: the
requires graph closes on itself.

## Steps

### Step 1 — First of the pair

The step's work.

<!-- wb-step
step=1
todos=cy-one
requires=cy-two
est=10m
fanout=one lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m

### Step 2 — Second of the pair

The step's work.

<!-- wb-step
step=2
todos=cy-two
requires=cy-one
est=10m
fanout=another lane
-->
files: lib/other.py
verify: python3 -m unittest tests.other
done when: the other file reads back changed
est: 10m
