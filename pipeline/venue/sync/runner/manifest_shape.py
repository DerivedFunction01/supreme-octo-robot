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
dies at its own load (the steampower-criticjd-gate specimen:
a dict-form uploads entry claimed a run that
never launched). The module imports nothing from the
package, so the standalone module loaders in the test suite
reach it without the runner's foundation.

The pre-dispatch pass (wall-clock plan, step 2) is homed
here on the same terms: preflight_error composes every
verdict a dispatch can know before any upload, lease, or
launch work — the shape verdicts above, the entry-resolved
field verdicts (script_field_error for the Colab form's
required script field; the caller's shape resolution), the
presence of the script file and every declared upload on
disk, the caller claim's registration verdict, and the
branch pin's resolution verdict. A defect refuses in
seconds, naming itself; a fire never discovers one minutes
in, holding a session. Each entry computes the verdicts
that need its own seams (the lease registry, the repos
registry) and passes them in as settled strings — the pass
itself stays a pure composition, and both dispatch entries
(local-run included, through the package's exports) consume
the same one.
"""

import os
import re
import subprocess
from pathlib import Path

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


def script_field_error(job) -> "str | None":
    """A loud-refusal verdict for the Colab form's required
    script field: the launch window consumes job["script"]
    as a repo-relative path, so a manifest without the field
    (or with a non-string one) is a defect of the manifest
    itself — refused at load, not discovered as a KeyError
    inside the launch window after the lease is held. The
    local form defaults its script name and checks the
    field's type at its own entry; this verdict is the
    Colab form's, where no default exists."""
    script = job.get("script")
    if script is None:
        return "manifest is missing its script field"
    if not isinstance(script, str) or not script:
        return f"manifest script must be a non-empty string, got {script!r}"
    return None


def presence_error(job, *, script_path=None, uploads_base=None) -> "str | None":
    """A loud-refusal verdict for the files the manifest
    declares: the script file and every declared upload must
    stand on disk at dispatch. Each entry names its own
    bases — the Colab form resolves both against the repo
    root; the local form resolves the script beside the
    manifest (or its sealed blob) and its uploads against
    the venue root. An absent declared file is a manifest
    defect: the fire refuses here rather than failing the
    run inside the launch window, holding a session, over a
    file that was never going to arrive."""
    if script_path is not None and not script_path.is_file():
        return f"manifest script not found at {script_path}"
    if uploads_base is not None:
        for rel in job.get("uploads") or []:
            if not (uploads_base / rel).is_file():
                return f"manifest upload {rel} not found at {uploads_base / rel}"
    return None


def pin_resolution_error(transport, *, repo, repo_registry) -> "str | None":
    """Resolve a branch declaration's pin against the source
    repo, as a pre-dispatch verdict (wall-clock plan,
    step 2): the registry key resolves, the entry's local
    checkout stands, and the declared SHA names a commit in
    it. The launch window's own assertion (prepare_branch)
    proves the fetched tip on the session; this leg proves
    the pin is real before any session work is spent on it —
    a pin naming a commit the source repo does not hold is a
    manifest defect, refused in seconds at dispatch rather
    than discovered at the clone, minutes in. The registry
    module arrives injected (the caller's foundation seam),
    so this module keeps importing nothing from the package.
    Returns an error string, or None when the pin resolves
    (or no transport is declared)."""
    if transport is None:
        return None
    try:
        registry = repo_registry.load_local_registry(repo)
        _repo_id, entry = repo_registry.get_entry(registry, transport["repo"])
    except ValueError as exc:
        return f"branch transport: {exc}"
    checkout = Path(os.path.expanduser(entry["local_path"]))
    if not checkout.is_dir():
        return f"branch transport: the source repo checkout for {transport['repo']!r} does not stand at {checkout} — the pin cannot be resolved"
    try:
        probe = subprocess.run(
            ["git", "-C", str(checkout), "cat-file", "-e", f"{transport['sha']}^{{commit}}"],
            capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"branch transport: the pin probe against the source repo at {checkout} could not run ({type(exc).__name__})"
    if probe.returncode != 0:
        return f"branch transport: pinned sha {transport['sha']} does not resolve to a commit in the source repo at {checkout}"
    return None


def preflight_error(job, *, script_path=None, uploads_base=None, claim_error=None, shape_error=None, pin_error=None) -> "str | None":
    """The one pre-dispatch validation pass: every verdict a
    dispatch can know before any upload, lease, or launch
    work, composed in the order the fire would meet them —
    the manifest's field shapes, its transport declaration,
    the entry-resolved field verdicts (shape_error: the
    script field, the shape resolution), the declared files'
    presence, the caller claim's registration, and the
    branch pin's resolution. Returns the first refusal, or
    None when the manifest is dispatchable. Verdicts that
    need an entry's own seams arrive as settled strings
    (claim_error from the lease core's caller registry,
    pin_error from pin_resolution_error above), so the
    composition is one home consumed by both dispatch
    entries and both Colab fire forms."""
    return (
        manifest_shape_error(job)
        or transport_error(job)
        or shape_error
        or presence_error(job, script_path=script_path, uploads_base=uploads_base)
        or claim_error
        or pin_error
    )


def parse_transport(job) -> "dict | None":
    """The manifest's branch-transport declaration as a plain
    dict, or None when the job names no transport (the bundle
    path) or the declaration is incomplete — a branch
    declaration missing a field, or carrying a non-string
    one, parses to None here, and transport_error names the
    defect in the composed pass. The parse never raises on
    the declaration's shape: the dispatch entries compute
    the pin verdict through this function while composing
    the pass, before transport_error's own verdict lands,
    so an incomplete declaration must reach that verdict as
    data, not die here as a KeyError."""
    declared = job.get("transport")
    if not isinstance(declared, dict) or declared.get("kind") != "branch":
        return None
    fields = {name: declared.get(name) for name in ("repo", "branch", "sha")}
    if any(not isinstance(value, str) or not value for value in fields.values()):
        return None
    return {"kind": "branch", **fields}
