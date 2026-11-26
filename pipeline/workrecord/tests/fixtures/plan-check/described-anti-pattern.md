# Described anti-pattern fixture

Status: draft

## Objective

A plan whose steps describe the formation refusal
class and state the union bound in its own form:
descriptions and the bound make no finding.

## Steps

### Step 1 — plan-check refuses per-row formations and per-item gates

`wb plan-check` gains a refusal class for the
formation anti-patterns the rulings already ban:
a plan whose steps declare a worktree or branch
per row, or a gate fire per item where the queue
trigger applies, refuses with the finding naming
the bound it breaks.

<!-- wb-step
step=1
todos=da-alpha
requires=
est=10m
fanout=class lanes
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the class reads back landed
est: 10m

### Step 2 — The union gate becomes the dispatch default

Gate fires per landing measured 3.2 against the
queue trigger's one union gate per waiting batch.
The dispatch forms the union tree in-container and
gates it once.

<!-- wb-step
step=2
todos=da-beta
requires=da-alpha
est=10m
fanout=dispatch lanes
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the union reads back as the default
est: 10m
