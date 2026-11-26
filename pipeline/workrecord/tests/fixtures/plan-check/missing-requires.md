# Missing requires fixture

Status: draft

## Objective

One step whose wb-step block omits the requires=
field entirely: an empty requires and an undeclared
one both read as no prerequisites, and only the
declared form passes.

## Steps

### Step 1 — Undeclared prerequisites

The step's work.

<!-- wb-step
step=1
todos=mr-one
est=10m
fanout=one lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m
