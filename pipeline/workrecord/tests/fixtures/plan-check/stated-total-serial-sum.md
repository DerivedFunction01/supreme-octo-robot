# Stated total equal to the serial sum

Status: draft
Total: 70m

## Objective

The specimen headline failure: the stated total
is the plain serial sum of the step estimates
(30m + 30m + 10m) while two steps declare a
fan-out and run in parallel — the wall-clock is
the 40m critical path, not 70m.

## Steps

### Step 1 — Alpha lane

The alpha lane's work.

<!-- wb-step
step=1
todos=ss-alpha
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
todos=ss-beta
requires=
est=30m
fanout=beta lane
-->
files: lib/other.py
verify: python3 -m unittest tests.other
done when: the beta lane reads back changed
est: 30m

### Step 3 — Join

The landing both lanes feed.

<!-- wb-step
step=3
todos=ss-join
requires=ss-alpha|ss-beta
est=10m
serial=one landing on main
-->
files: lib/example.py
verify: python3 -m unittest tests.example
done when: the join reads back changed
est: 10m
