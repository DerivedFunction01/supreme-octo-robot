# Example flaky check — escalation body for `example-flaky-check`

The flaky check's simulated dependency reported DOWN. This
body is what an agent works when the failure ping arrives:

1. Check whether the failure is expected: if the marker
   file `state/flaky-on` exists, someone toggled the
   simulation on (see `examples/example_flaky.sh`) — say so
   in one line and stop.
2. Otherwise treat it as a real dependency failure: report
   to the operator what the check saw (the ping carries the
   run's captured output) and when it started.
3. Acknowledge the ping (`bin/sched ack <ping-id>`) only
   after the report is delivered.
