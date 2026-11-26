# Question without a recommendation fixture

Status: draft

## Objective

A conforming step, and one owner-ruling question
whose sentinel omits the recommended field.

## Steps

### Step 1 — Conforming step

The step's work.

<!-- wb-step
step=1
todos=qr-one
requires=
est=10m
fanout=one lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m

## Open questions

- [ ] Which home holds the example?
  <!-- wb-question
  id=qr-home
  type=choice
  options=store | registry
  answer=
  -->
