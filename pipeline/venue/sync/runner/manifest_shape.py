"""The manifest's load-point shape contract: pure verdicts
over a loaded manifest dict, homed in a leaf module so every
fire form validates through the one home.

Two verdicts, both loud-refusal strings naming the field and
the offending entry (None when the shape is the contract's):

- manifest_shape_error: uploads and args are consumed as
  plain strings (a path to upload, an argv entry to quote);
  a mapped entry there crashed a launch mid-flight in the
  wild, so the shapes carry no tolerance semantics. (Outputs
  are the tolerated field — mapped entries normalize to
  plain local names at load; that normalizer lives with the
  pull consumers in pull.py.)
- transport_error / parse_transport: the branch-transport
  declaration — kind branch requires a repos-registry key, a
  branch name, and a full expected SHA; a missing or
  malformed field refuses at load, never mid-launch.

Placement is the contract's other half: the verdicts run at
fire time in BOTH fire forms — the attached flow in dispatch
and the daemonize parent in claims, before its claim — so a
shape-invalid manifest refuses named, with no run record
written, instead of claiming a run whose daemon child then
dies at its own load (the steampower-criticjd-gate specimen,
2026-11-25: a dict-form uploads entry claimed a run that
never launched). The module imports nothing from the
package, so the standalone module loaders in the test suite
reach it without the runner's foundation.
"""

import re

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def manifest_shape_error(job) -> "str | None":
    """A loud-refusal verdict for the manifest fields that have
    no tolerance semantics: uploads and args are consumed as
    plain strings (a path to upload, an argv entry to quote),
    and a mapped entry there crashed a launch mid-flight in
    the wild (dict-shaped uploads). Returns an
    error naming the field and the offending entry, or None
    when the shapes are the contract's."""
    for field in ("uploads", "args"):
        entries = job.get(field)
        if entries is None:
            continue
        if not isinstance(entries, list):
            return f"manifest {field} must be a list of strings, got {type(entries).__name__}"
        for entry in entries:
            if not isinstance(entry, str):
                return f"manifest {field} entry is not a string: {entry!r}"
    return None


def transport_error(job) -> "str | None":
    """A loud-refusal verdict for the manifest's transport
    declaration (branch transport plan): the
    manifest declares the tree's form and the runner holds
    the preference — a committed, pushed tree names
    transport {kind: branch, repo, branch, sha}; an
    uncommitted tree names no transport and takes the
    snapshot-bundle path. Branch is the only declared kind:
    kind branch requires a repos-registry key, a branch
    name, and a full expected SHA, and a missing or
    malformed field refuses here, at load, naming the
    field — never mid-launch. Returns an error string, or
    None when the declaration is the contract's (or absent)."""
    declared = job.get("transport")
    if declared is None:
        return None
    if not isinstance(declared, dict):
        return f"manifest transport must be an object, got {type(declared).__name__}"
    kind = declared.get("kind")
    if kind is None:
        return "manifest transport is missing its kind field"
    if kind != "branch":
        return f"manifest transport kind {kind!r} is not a declared transport (only 'branch' is)"
    for field in ("repo", "branch", "sha"):
        value = declared.get(field)
        if value is None:
            return f"manifest transport (kind branch) is missing its {field} field"
        if not isinstance(value, str) or not value:
            return f"manifest transport {field} must be a non-empty string, got {value!r}"
    if not _FULL_SHA.match(declared["sha"]):
        return f"manifest transport sha must be a full 40-hex commit SHA, got {declared['sha']!r}"
    return None


def parse_transport(job) -> "dict | None":
    """The manifest's validated branch-transport declaration
    as a plain dict, or None when the job names no transport
    (the bundle path). Call only after transport_error has
    cleared the manifest."""
    declared = job.get("transport")
    if not isinstance(declared, dict) or declared.get("kind") != "branch":
        return None
    return {"kind": "branch", "repo": declared["repo"], "branch": declared["branch"], "sha": declared["sha"]}


def parse_transport(job) -> "dict | None":
    """The manifest's validated branch-transport declaration
    as a plain dict, or None when the job names no transport
    (the bundle path). Call only after transport_error has
    cleared the manifest."""
    declared = job.get("transport")
    if not isinstance(declared, dict) or declared.get("kind") != "branch":
        return None
    return {"kind": "branch", "repo": declared["repo"], "branch": declared["branch"], "sha": declared["sha"]}
