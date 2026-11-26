# Tooling layer — live checks

The home for genuinely live-requiring checks: checks that
reach a live venue, a network, credentials, or operator
state, and so can never join the gate suite. The gate
suite (`tests/`, verdicted by the gate's pytest leg) is
offline and isolated by construction; this layer stands
beside it, never inside it, so gate collection can never
see a live check.

Each live check is enumerated in `tooling.json` as one
entry of the form `{id, module, reach, job}`: the check's
module in this package, the live surface it reaches for,
and the job manifest it dispatches as. A check runs on
its own terms, as an ordinary job through the runner's
dispatch entries, and its run record is its verdict
artifact — never an ad-hoc skip or a silent drop in the
offline suite.

The layer stands empty. A check is registered here only
when a live need actually commissions it.
