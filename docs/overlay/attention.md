# Overlay inventory — owner-attention (existential capture)

Attention's capture was existential: every registry the
product owns — handlers, programmes, rules, templates,
the vocabulary registries — plus presence and the
decision queue lived only in one untracked file,
`var/data/state.json`, written through the API and
seeded from code defaults plus backfill. No registry had
a tracked seed or any file form. If that file had been
lost, every registry it owned was lost with it.

**The store migrated verbatim as data** — never as code,
never re-entered by hand. At capture it carried 10
handlers, 3 programmes, 47 sends, 53 items, and the
vocabulary registries as records (rules, templates with
versions, status codes, fields, wait classes, item
kinds, action rules), presence with its expectation set,
and the ledger-side state (owner actions, dispatch
failures). The captured copy loaded through the pinned
code's own store path with no exception and every count
identical raw vs loaded — the capture's done-evidence.
The consolidated registry gives these registries the
seed/export form they never had
(`pipeline/attention` carries the seeds).

**Also captured as data:** `var/armed/` — the
workbench's machine-written armed rows, verbatim. The
rows appear by existing and retire by disappearing; the
evaluator joins them on `(project, todo)`, and
fixture-class rows never supervise.

**Credential — reference only.** `var/connector/
bridge-token` — the bridge caller credential for the
scheduler harness connector (hash-only on the scheduler
side; the raw token only in this file). Inventoried by
reference only: the value was never copied, read into
any file, printed, or hashed.

**Paths out of the repo are data too.** The store's
programme rows and the pinned settings carried paths
into sibling repos and goal workspaces — the run-records
directory, programme worktree roots, record locations,
contract paths, the armed directory, the bridge-token
path. They were inventoried so the consolidation
re-based them deliberately instead of silently breaking
the evaluator's ground truth after the move.

**Not captured:** working and build debris (`var/xfer/`
probe material, `var/storyboard-build/`, the repo venv —
rebuildable via its init path) and runtime logs. Capture
distinguishes data from debris; the mega repo inherits
records, not debris.
