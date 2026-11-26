# Stated total at the critical path

Status: draft
Total: 40m

## Objective

A plan whose stated total equals its wall-clock:
two parallel lanes (30m, 20m) join into a 10m
landing, so the critical path is 30m + 10m = 40m
and the stated 40m stands.

## Steps

### Step 1 — Alpha lane

The alpha lane's work.

<!-- wb-step
step=1
todos=tw-alpha
requires=
est=30m
fanout=alpha lane
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the alpha lane reads back changed
est: 30m

### Step 2 — Beta lane

The beta lane's work, parallel with alpha.

<!-- wb-step
step=2
todos=tw-beta
requires=
est=20m
fanout=beta lane
-->
files: lib/other.py
verify: python3 -m unittest tests.other
done when: the beta lane reads back changed
est: 20m

### Step 3 — Join

The landing both lanes feed.

<!-- wb-step
step=3
todos=tw-join
requires=tw-alpha|tw-beta
est=10m
serial=one landing on main
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the join reads back changed
est: 10m
