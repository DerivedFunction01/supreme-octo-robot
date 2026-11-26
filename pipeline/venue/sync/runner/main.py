#!/usr/bin/env python3
"""Verb routing: --sweep / --poll / --wait and
plant-git-identity never pay the launch path's costs and
dispatch here; everything else is a launch and hands off to
dispatch.launch, whose window is execute.execute.

The router's own surface parses through the unified argv
contract (pipeline/platform/argv.py): an invocation
carrying a router verb validates in full against the
declaration below — an unrecognised token is a usage
refusal (exit 2), never a fall-through to a full launch,
and two verb forms in one invocation refuse rather than
one silently winning. An invocation with no router verb
is a launch and reaches dispatch.launch untouched.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

from .dispatch import launch
from .sweep import collect_stale_detached, orphan_sweep
from .verbs import plant_git_identity, poll_run, wait_run

# The unified argv contract home, loaded by location under
# a private name (the stdlib owns the bare name `platform`),
# through the venue paths spine — the form foundation.py
# loads the same spine by.
_paths_spec = importlib.util.spec_from_file_location(
    "venue_paths", Path(__file__).parent.parent.parent / "paths.py")
_paths = importlib.util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)
_argv_spec = importlib.util.spec_from_file_location(
    "pipeline_platform_argv", _paths.PLATFORM_ARGV)
platform_argv = importlib.util.module_from_spec(_argv_spec)
_argv_spec.loader.exec_module(platform_argv)

DECLARATION = {
    "name": "colab-run",
    "summary": "run a named job on Colab, or work a router verb",
    "flags": {
        "sweep": {"help": "reconcile run records against "
                          "live sessions"},
        "collect-stale": {"help": "collect stale detached runs"},
        "poll": {"takes_value": True,
                 "help": "reconcile one launched run"},
        "wait": {"takes_value": True,
                 "help": "read one run's local record only"},
        "max": {"takes_value": True,
                "help": "--wait bound, in seconds (default 120)"},
        "session": {"takes_value": True,
                    "help": "plant-git-identity: the session name"},
        "repo": {"takes_value": True,
                 "help": "plant-git-identity: the repo id or path"},
        "tree": {"takes_value": True,
                 "help": "plant-git-identity: the session tree"},
        "caller": {"takes_value": True,
                   "help": "caller attribution tag"},
    },
    "positionals": [{"name": "command"}],
}

# The tokens that make an invocation a router invocation.
# --session / --caller are also launch flags, so they never
# trigger the router parse on their own.
_ROUTER_TOKENS = ("--sweep", "--collect-stale", "--poll",
                  "--wait", "plant-git-identity")

_VERB_FLAGS = ("sweep", "collect-stale", "poll", "wait")


def _usage_refusal(message):
    print(f"colab-run: {message}", file=sys.stderr)
    print(platform_argv.help_text(DECLARATION),
          file=sys.stderr, end="")
    return platform_argv.USAGE_EXIT


def main() -> int:
    args = sys.argv[1:]
    # Verbs that never launch dispatch first: --sweep reconciles
    # records, --poll reconciles one launched run, --wait reads
    # the local record only. None of them may pay the launch
    # path's costs (mirror restore, catalog, acquire).
    core_args = list(args)
    for i, token in enumerate(args):
        if token == "--":
            core_args = args[:i]
            break
    if not set(_ROUTER_TOKENS) & set(core_args):
        return launch(args)
    try:
        parsed = platform_argv.parse(DECLARATION, core_args)
    except platform_argv.UsageError as exc:
        return _usage_refusal(str(exc))
    if "help" in parsed:
        print(parsed["help"], end="")
        return 0
    flags = parsed["flags"]
    present = set(parsed["present"])
    command = parsed["positionals"]["command"]
    verb_forms = [name for name in _VERB_FLAGS if name in present]
    if command is not None:
        verb_forms.append(command)
    if len(verb_forms) != 1 or verb_forms[0] not in (
            *_VERB_FLAGS, "plant-git-identity"):
        return _usage_refusal(
            "one router verb per invocation "
            f"({'|'.join([*_VERB_FLAGS, 'plant-git-identity'])}); "
            f"got {verb_forms}")
    if "sweep" in present:
        findings, live_ok = orphan_sweep()
        print(json.dumps({"findings": findings, "live_list_unreadable": not live_ok}, indent=2))
        return 0
    if "collect-stale" in present:
        # The reap command's collector ride passes its remaining
        # command budget through the env; a direct call keeps the
        # pass's own default budget.
        raw_budget = os.environ.get("COLAB_COLLECT_BUDGET_S")
        budget_s = None
        if raw_budget:
            try:
                budget_s = float(raw_budget)
            except ValueError:
                budget_s = None
        summary = collect_stale_detached(budget_s=budget_s) if budget_s is not None else collect_stale_detached()
        print(json.dumps(summary, indent=2))
        return 0
    if "poll" in present:
        return poll_run(flags["poll"])
    if "wait" in present:
        max_seconds = 120
        if "max" in present:
            try:
                max_seconds = int(flags["max"])
            except ValueError:
                print("colab-run --wait: --max must be an integer number of seconds", file=sys.stderr)
                return 2
        return wait_run(flags["wait"], max_seconds)
    # plant-git-identity
    session, repo, tree = flags["session"], flags["repo"], flags["tree"]
    if not (session and repo and tree):
        return _usage_refusal(
            "plant-git-identity needs --session NAME "
            "--repo ID_OR_PATH --tree SESSION_TREE [--caller TAG]")
    return plant_git_identity(session, repo, tree, flags["caller"] or os.environ.get("COLAB_CALLER"))
