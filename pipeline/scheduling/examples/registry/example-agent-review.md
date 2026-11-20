# Example agent review — body for `example-agent-review`

An agent job's body is the instruction the operator's agent
surface follows when this job's ping is worked. This example
reviews the server's own recent record:

1. Read the last day of the ledger (`bin/sched logs export
   --all`, or the read API's ledger feed) and the registry
   census (`bin/sched census`).
2. Note every failed run, every escalation, and every job
   that has not run inside twice its cadence.
3. Report to the operator in at most three lines: what
   failed, what is stale, or that the day was clean. Do not
   repair anything — reporting is this job's whole scope.
4. Acknowledge the ping (`bin/sched ack <ping-id>`) only
   after the report is delivered.
