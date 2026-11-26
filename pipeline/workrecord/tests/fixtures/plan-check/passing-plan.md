# Passing plan fixture

Status: draft

## Objective

A plan that satisfies every plan-check rule: each
step carries its block, its closing lines, and a
declared fan-out or serial exception.

## Steps

### Step 1 — First lane

The first lane's work, stated in a line or two.

<!-- wb-step
step=1
todos=pp-alpha
requires=
est=10m
fanout=alpha lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m

### Step 2 — Serial follow-on

The follow-on rides the first lane's todo.

<!-- wb-step
step=2
todos=pp-beta
requires=pp-alpha
est=20m
serial=the shared example file
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the follow-on reads back changed
est: 20m

### Step 3 — Independent lane

A second root step, armed alongside the first.

<!-- wb-step
step=3
todos=pp-gamma
requires=
est=5m
fanout=gamma lane
-->
files: lib/other.py
verify: python3 -m unittest tests.other
done when: the other file reads back changed
est: 5m

## Open questions

- [ ] Which home holds the example?
  Recommendation: the store.
  <!-- wb-question
  id=pp-home
  type=choice
  options=store | registry
  recommended=store
  answer=
  -->
- [ ] A question an agent settles from evidence
  later; it carries no sentinel and is not a
  finding.
