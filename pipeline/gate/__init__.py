"""Pipeline gate (plan §4.16): the shared gate legs, one home.

Every package in the pipeline declares the legs it runs in a
gate.json beside its code; the repo-root check.py composes
them. The components here are the single implementations of
the legs that used to be copied per repo: the line cap, the
portability/denylist scanner, ruff format/lint, the policy
scanner leg, the test-isolation state hash, AST-based test
targeting, and the venv bootstrap.
"""
