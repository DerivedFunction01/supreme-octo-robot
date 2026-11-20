"""AST-based test targeting (plan §4.16): the check.py
mechanism, ported — a git-status snapshot, a prose-only
filter, and an AST import lineage from changed files to
the tests that exercise them, with explainable reasons.

Ported from the reference implementation in the source repo's
repo (foundation/checks: git_diff, prose, lineage). The
generalizations are the ones a multi-package repo forces:
module names are computed per import root (a file carries
one name per root containing it), classification is
parameterized by a package layout, and the dependency
graph is rebuilt in memory per run — at this repo's scale
the scan takes under a second, so the source house's
on-disk graph cache is not carried.
"""
