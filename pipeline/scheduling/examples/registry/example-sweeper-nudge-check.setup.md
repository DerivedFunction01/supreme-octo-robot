# Setup documentation — sweeper nudge check

What this adoption requires in documentation. Adopting the
entry establishes none of this by itself: each item below is
a described, recorded step for the adopting deployment,
performed as its own act — never an invisible side effect
of running the adopt verb. The verb records this doc with
the adoption (state/adoptions/<live-id>/) and names it in
its report.

## The status vocabulary is a setup requirement

The checker classifies task-mode thread state by exact
match against the "Task-mode status vocabulary" section of
the workspace AGENTS.md — the STATUS terms and ITEM kinds
and their exact spellings are its classification table. An
adoption into a workspace without that section, or with
locally altered terms, does not fail loudly: it classifies
against nothing and the affected cases go silent. The
adopting deployment's workspace AGENTS.md must carry the
section, terms unmodified; amending the vocabulary is a
change to the checker, made in both places or neither.

## The cross-system reference: the workbench

This is the first setup doc that references the workbench,
because the sweeper's judgment reads workbench state. Its
stall and unarmed-watch cases are decided over the
workbench harness's own records: which todos carry armed
progress schedules (the wb-progress entries the harness
renders into this registry), how todos are classified at
each transition, and whether the workbench viewer itself is
healthy. An adoption without the workbench side leaves
those cases undecidable — the checker stays silent on them
by design — and an adoption that changes the harness's
entry shape or todo vocabulary changes what this checker
can see. Neither system's docs own this dependency; this
setup doc is where it is made explicit.

## The ledger discipline

The checker's decisions land in the nudge store only
through the ledger CLI's verbs (see the store declaration
in the entry's setup). That rule lives in this repo's
AGENTS.md and the sweeper body; an adoption that bypasses
it — direct SQL, a side JSONL — forks the record the
checker reconciles against.
