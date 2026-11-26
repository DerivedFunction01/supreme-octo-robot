# Stated total over the critical path

Status: draft
Total: 2h

## Objective

A plan whose header states a total above its
wall-clock: two parallel lanes join into a short
serial landing, so the critical path is 40m, not
the stated 2h.

## Steps

### Step 1 — Alpha lane

The alpha lane's work.

<!-- wb-step
step=1
todos=st-alpha
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
todos=st-beta
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
todos=st-join
requires=st-alpha|st-beta
est=10m
serial=one landing on main
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the join reads back changed
est: 10m
