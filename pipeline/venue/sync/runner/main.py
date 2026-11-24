#!/usr/bin/env python3
"""Verb routing: --sweep / --poll / --wait and
plant-git-identity never pay the launch path's costs and
dispatch here; everything else is a launch and hands off to
dispatch.launch, whose window is execute.execute.
"""

import json
import os
import sys

from .dispatch import launch
from .sweep import collect_stale_detached, orphan_sweep
from .verbs import plant_git_identity, poll_run, wait_run


def main() -> int:
    args = sys.argv[1:]
    # Verbs that never launch dispatch first: --sweep reconciles
    # records, --poll reconciles one launched run, --wait reads
    # the local record only. None of them may pay the launch
    # path's costs (mirror restore, catalog, acquire).
    core_args = args[: args.index("--")] if "--" in args else list(args)
    if "--sweep" in core_args:
        findings, live_ok = orphan_sweep()
        print(json.dumps({"findings": findings, "live_list_unreadable": not live_ok}, indent=2))
        return 0
    if "--collect-stale" in core_args:
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
    if "--poll" in core_args:
        idx = core_args.index("--poll")
        if idx + 1 >= len(core_args):
            print("usage: colab-run --poll RUN_ID", file=sys.stderr)
            return 2
        return poll_run(core_args[idx + 1])
    if "--wait" in core_args:
        idx = core_args.index("--wait")
        if idx + 1 >= len(core_args):
            print("usage: colab-run --wait RUN_ID [--max SECONDS]", file=sys.stderr)
            return 2
        max_seconds = 120
        if "--max" in core_args:
            midx = core_args.index("--max")
            if midx + 1 >= len(core_args):
                print("usage: colab-run --wait RUN_ID [--max SECONDS]", file=sys.stderr)
                return 2
            try:
                max_seconds = int(core_args[midx + 1])
            except ValueError:
                print("colab-run --wait: --max must be an integer number of seconds", file=sys.stderr)
                return 2
        return wait_run(core_args[idx + 1], max_seconds)
    if "plant-git-identity" in core_args:
        def _flag(name: str) -> "str | None":
            return core_args[core_args.index(name) + 1] if name in core_args and core_args.index(name) + 1 < len(core_args) else None

        _session, _repo, _tree = _flag("--session"), _flag("--repo"), _flag("--tree")
        if not (_session and _repo and _tree):
            print("usage: colab-run plant-git-identity --session NAME --repo ID_OR_PATH --tree SESSION_TREE [--caller TAG]", file=sys.stderr)
            return 2
        return plant_git_identity(_session, _repo, _tree, _flag("--caller") or os.environ.get("COLAB_CALLER"))
    return launch(args)
