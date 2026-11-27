#!/usr/bin/env python3
"""Venue-kind classification for the unified bin/venue-run
entry: which kind's main an invocation belongs to.

The two historical entries were record-compatible twins
over this package — a thin form (this package's main) and
a fat form (its own main in the entry) — and venue-run is
their union: one entry whose main classifies the
invocation and hands it, untouched, to the kind's own
main, so each kind keeps its exact flag surface, defaults,
and refusal forms. Classification reads only the core args
(everything before "--": what follows is the job's own
argv on the Colab form and never classifies). A flag
token's kind is read from its head (the part before any
"="), so an equals-form flag classifies as its bare form
does.

The classification, in order:

- A local-only token (--seal, --verify-sealed, --envelope,
  --union, --check-path) routes local; a Colab-only token
  (--sweep, --collect-stale, plant-git-identity, --resume,
  --seed, --daemonize, --session) routes Colab. Each set is
  a form the other kind's parser refuses, so the token is
  the caller's own declaration of the kind.
- An attach (--poll / --wait — the shared spellings whose
  grammars differ: a value flag on the Colab form, a
  boolean flag with a positional target on the local form,
  the target token the same in both) resolves its target:
  a run record under that id decides by its venue field;
  else a job manifest in one adapter tree decides by the
  tree (a name in both trees is decided by a manifest's
  declared venue — the local smoke job declares "local"
  against the Colab tree's undeclared default); else the
  record store's own scan (the local attach's resolution:
  a record whose job or run id the target names). An
  attach nothing resolves routes local: the local attach
  is the only one of the two that resolves job names and
  scans the store, so the unified entry serves its
  refusal as the one attach contract for a dead target —
  resolvable attaches, the real population, route by
  evidence above, never by this default.
- A bare dispatch (a job name with no mode token) resolves
  by the manifest trees as above; a name in neither tree
  routes Colab, whose launch serves the primary
  no-manifest refusal, as does an invocation with no
  positional at all.

Loaded by path from bin/venue-run (the entry's
_load_runner_leaf form, like local_attach): everything it
needs arrives in the seams dict — the two job trees, the
record store, and the record reader — bound from the
entry module's globals at call time, so a monkeypatched
entry global is the binding classification reads.
"""

import json
from pathlib import Path

LOCAL_ONLY_TOKENS = (
    "--seal", "--verify-sealed", "--envelope", "--union", "--check-path",
)
COLAB_ONLY_TOKENS = (
    "--sweep", "--collect-stale", "plant-git-identity",
    "--resume", "--seed", "--daemonize", "--session",
)
ATTACH_TOKENS = ("--poll", "--wait")
# Shared value flags whose values the positional scan must
# not mistake for a target. (The kind-only value flags —
# --union, --envelope, --session, --resume — classify by
# their token before the scan ever runs.)
_VALUE_FLAGS = ("--caller", "--max")


def _core_args(args):
    core = []
    for token in args:
        if token == "--":
            break
        core.append(token)
    return core


def _head(token):
    return token.split("=", 1)[0]


def _positionals(core):
    """The core args' positional tokens, in order: every
    token that is not a flag and not a shared value flag's
    value. The attach flags scan as booleans here — on the
    Colab form the target is the value after --poll/--wait,
    on the local form it is the positional; in both forms
    that token is the first positional this scan serves. An
    equals-form attach flag (--poll=<id>) contributes its
    value as that positional."""
    out = []
    i = 0
    while i < len(core):
        token = core[i]
        if _head(token) in ATTACH_TOKENS and "=" in token:
            out.append(token.split("=", 1)[1])
            i += 1
            continue
        if token in _VALUE_FLAGS:
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def _manifest_venue(path):
    try:
        job = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return job.get("venue") if isinstance(job, dict) else None


def _job_kind(name, seams):
    """The kind a job name belongs to, by its manifests:
    the tree that holds it, with a declared venue deciding
    a name both trees hold. None when neither tree holds
    it."""
    local_manifest = seams["local_jobs"] / name / "job.json"
    colab_manifest = seams["colab_jobs"] / name / "job.json"
    local_has = local_manifest.exists()
    colab_has = colab_manifest.exists()
    if local_has and colab_has:
        if _manifest_venue(local_manifest) == "local":
            return "local"
        if _manifest_venue(colab_manifest) == "colab":
            return "colab"
        return "colab"
    if local_has:
        return "local"
    if colab_has:
        return "colab"
    return None


def _record_kind(rec):
    return "local" if rec.get("venue") == "local" else "colab"


def _attach_kind(target, seams):
    rec = seams["load_run_record"](target)
    if rec is not None:
        return _record_kind(rec)
    kind = _job_kind(target, seams)
    if kind is not None:
        return kind
    # The local attach's own resolution, mirrored: scan the
    # store's stems through the record reader for a record
    # whose run id or job the target names.
    runs = seams["runs"]
    try:
        stems = sorted(p.stem for p in Path(runs).glob("*.json"))
    except OSError:
        stems = []
    for stem in stems:
        rec = seams["load_run_record"](stem)
        if rec is None:
            continue
        if rec.get("run_id") == target or rec.get("job") == target:
            return _record_kind(rec)
    return "local"


def classify(args, seams):
    """Route one invocation: "local" or "colab". Pure over
    the seams — no state of its own, no writes."""
    core = _core_args(list(args))
    heads = [_head(token) for token in core]
    if any(head in LOCAL_ONLY_TOKENS for head in heads):
        return "local"
    if any(head in COLAB_ONLY_TOKENS for head in heads):
        return "colab"
    positionals = _positionals(core)
    if any(head in ATTACH_TOKENS for head in heads):
        if not positionals:
            return "local"
        return _attach_kind(positionals[0], seams)
    if not positionals:
        return "colab"
    return _job_kind(positionals[0], seams) or "colab"
