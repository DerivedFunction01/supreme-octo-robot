# Test tree map — the engine-contract cases

The map of the spec's edge cases (EC-*) to their suites;
the tree carries further suites beyond this map.

- EC-1 (catch-up collapses to latest), EC-4 (consumed before the
  run; a restart never refires), EC-5 (timeout), EC-7 (fail
  pattern), EC-8 (spawn error), EC-9 (registry quarantine),
  EC-10 (corrupt state is fail-safe), EC-11 (single-instance
  lock), EC-15 (activation after a proof run does not
  double-fire), EC-16 (entry deletion voids pending pings):
  `test_engine.py`.
- EC-2 (spring-forward gap) and EC-3 (fall-back repeated hour):
  `test_schedule.py`.
- EC-6 (output flood is tail-capped, process not killed):
  `test_engine.py::ExecutorTests`.
- Outbox semantics (write-before-wake, coalescing, ack
  separation, re-surface once per ack-timeout window):
  `test_outbox.py`.
- Config precedence and /health sources: `test_config.py`.
- Entry schema and validator fixtures: `test_registry.py`.

EC-12 (unit file wiped while the process runs), EC-13 (crash
loop + one ladder attempt per episode), and EC-14 (keeper dead,
pings accumulate) are NOT testable in-process — they are
verified by live drills against the watchdog ladder and the
keeper, exactly as the spec provides.
