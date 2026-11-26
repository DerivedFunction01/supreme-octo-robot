# Prose-only step fixture

Status: draft

## Objective

One step whose form is left to prose: closing lines
present, no wb-step sentinel at all.

## Steps

### Step 1 — Undeclared step

The step's work, with closing lines but no block —
its prerequisites, estimate, and fan-out exist
nowhere as data.

files: lib/example.py
verify: python3 -m unittest tests.example
done when: the example reads back changed
est: 10m
