#!/usr/bin/env python3
"""Served-payload capture for the S8 (scheduler) payload diff.

Builds ONE fixture store — the S1 overlay capture's 26 fleet
entries (docs/overlay/holding/scheduler + the pinned repo's two
tracked entries), the crafted ledger seed and outbox seed in
this directory — and serves contract 09's five /api/v1 views
from one tree's own api module at a fixed instant:

    python3 dump_served.py pinned   payloads-pinned.json
    python3 dump_served.py pipeline payloads-pipeline.json

`pinned` runs the scheduler app of record at its pin
(cf910ce, extracted from the pinned scheduler repo named by
DUMP_SERVED_PINNED_REPO by git archive; the repo is only
read). Its fixture entries are the capture verbatim
(migration family present, as pinned).

`pipeline` runs the mega repo's moved scheduling server
(pipeline/scheduling/server/serving/api.py over pipeline/dispatch).
Its fixture entries are the same capture with the migration
field family stripped — amendment 3's target form, verified
byte-identical to pipeline/scheduling/jobs/ as landed at S3.

Engine construction is pinned to T0 and every view is served
at NOW, so the payloads are deterministic apart from the
process pid (normalized by diff_served.py). Nothing live is
touched: the store lives in a scratch home, the live service
on 8796 is never contacted.
"""
import glob
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(
    os.path.join(HERE, "..", "..", "..", "..", ".."))
CAPTURE_JOBS = os.path.join(
    REPO, "docs", "overlay", "holding", "scheduler", "jobs")
CAPTURE_BODIES = os.path.join(
    REPO, "docs", "overlay", "holding", "scheduler", "bodies")
PINNED_REPO = os.environ.get("DUMP_SERVED_PINNED_REPO", "")
PIN = "cf910ce6a2b1c696bb7bcdbc5c9fe49460cea779"

# One fixed home path for both runs: registry entries expand
# ${REPO}/${WS} anchors from it, so the served payloads carry
# identical expansions and diff clean.
HOME = os.path.join(tempfile.gettempdir(), "workhorse-s8-fixture-home")
SCRATCH = os.path.join(tempfile.gettempdir(), "workhorse-s8-pinned-tree")

T0 = datetime(2026, 11, 13, 21, 30, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 13, 22, 0, tzinfo=timezone.utc)

MIGRATION_KEYS = ("migrated", "migrated_at", "proof_pending",
                  "migration_note")
CONFIG = {
    "host": "127.0.0.1",
    "port": 8796,
    "tick_secs": 20,
    "default_timezone": "America/New_York",
    "outbox_ack_timeout_secs": 3600,
    "ledger_retention_days": 90,
    "capture_cap_bytes": 65536,
}


def fixture_jobs(dst, strip):
    """The 26-entry fleet: the pinned repo's tracked pair plus
    the S1 capture's 24, optionally stripped to target form."""
    os.makedirs(dst)
    sources = []
    raw = subprocess.run(
        ["git", "-C", PINNED_REPO, "archive", PIN, "jobs"],
        capture_output=True, check=True).stdout
    import io
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar.getmembers():
            if member.name.endswith(".yaml"):
                sources.append(
                    (os.path.basename(member.name),
                     tar.extractfile(member).read().decode("utf-8")))
    for path in sorted(glob.glob(os.path.join(CAPTURE_JOBS, "*.yaml"))):
        with open(path, encoding="utf-8") as fh:
            sources.append((os.path.basename(path), fh.read()))
    for name, text in sources:
        if strip:
            text = "".join(
                line for line in text.splitlines(keepends=True)
                if not any(line.startswith(k + ":")
                           for k in MIGRATION_KEYS))
        with open(os.path.join(dst, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    return len(sources)


def build_home(strip):
    shutil.rmtree(HOME, ignore_errors=True)
    os.makedirs(os.path.join(HOME, "state"))
    count = fixture_jobs(os.path.join(HOME, "jobs"), strip)
    shutil.copytree(CAPTURE_BODIES, os.path.join(HOME, "bodies"))
    with open(os.path.join(HOME, "config.json"), "w",
              encoding="utf-8") as fh:
        json.dump(CONFIG, fh, indent=1, sort_keys=True)
    shutil.copyfile(os.path.join(HERE, "seed-outbox.json"),
                    os.path.join(HOME, "state", "outbox.json"))
    return count


def serve(tree):
    if tree == "pinned":
        shutil.rmtree(SCRATCH, ignore_errors=True)
        os.makedirs(SCRATCH)
        raw = subprocess.run(
            ["git", "-C", PINNED_REPO, "archive", PIN, "server"],
            capture_output=True, check=True).stdout
        import io
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            tar.extractall(SCRATCH)
        sys.path.insert(0, SCRATCH)
        count = build_home(strip=False)
    elif tree == "pipeline":
        sys.path.insert(0, os.path.join(REPO, "pipeline", "scheduling"))
        sys.path.insert(0, os.path.join(REPO, "pipeline"))
        count = build_home(strip=True)
    else:
        raise SystemExit(f"unknown tree {tree!r}")

    from server import config as config_mod
    from server.firing.engine import Engine
    from server.serving import api

    values, _sources = config_mod.resolve(
        path=os.path.join(HOME, "config.json"), env={})
    engine = Engine(values, jobs_dir=os.path.join(HOME, "jobs"),
                    state_dir=os.path.join(HOME, "state"),
                    now_fn=lambda: T0)
    if len(engine.entries) != count:
        raise SystemExit(
            f"registry loaded {len(engine.entries)} of {count} entries; "
            f"errors: {engine.registry_errors}")
    imported, sha = engine.ledger.import_jsonl(
        os.path.join(HERE, "seed-ledger.jsonl"))
    payloads = {
        "tree": tree,
        "pin": PIN,
        "served_at": NOW.isoformat(),
        "seed_ledger_events": imported,
        "seed_ledger_sha256": sha,
        "overview": api.overview(engine, NOW),
        "jobs": api.jobs_list(engine, NOW),
        "details": {job_id: api.job_detail(engine, job_id, NOW)
                    for job_id in sorted(engine.entries)},
        "pings": api.pings_list(engine, NOW),
        "ledger": api.ledger_feed(engine, NOW, limit=500),
    }
    # The G5 acked window exists only on the pipeline tree
    # (the pinned api has no pings_recent route); the key is
    # pipeline-only and diff_served.py dispositions it as
    # such, by name.
    if hasattr(api, "pings_recent"):
        payloads["recent_pings"] = api.pings_recent(engine, NOW)
    return payloads


# The declared surface, parsed by the unified argv
# module (pipeline/platform/argv.py): the tree and the
# output path are required positionals; a short or
# surplus argv is a usage refusal at exit 2, never an
# IndexError.
DECL = {
    "name": "dump-served",
    "positionals": [
        {"name": "tree", "required": True},
        {"name": "out", "required": True},
    ],
}


def _load_argv():
    """The unified argv module, loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_argv",
        os.path.join(REPO, "pipeline", "platform", "argv.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_platform_argv"] = module
    spec.loader.exec_module(module)
    return module


uargv = _load_argv()


def main():
    outcome = uargv.parse_only(DECL, sys.argv[1:])
    if not outcome["ok"]:
        print(outcome["error"], file=sys.stderr)
        print(outcome["usage"], file=sys.stderr)
        raise SystemExit(uargv.USAGE_EXIT)
    if "help" in outcome:
        print(outcome["help"], end="")
        raise SystemExit(0)
    positionals = outcome["result"]["positionals"]
    tree, out_path = positionals["tree"], positionals["out"]
    if tree == "pinned" and not PINNED_REPO:
        raise SystemExit(
            "DUMP_SERVED_PINNED_REPO is not set — the pinned "
            "tree needs the original scheduler repo's path")
    payloads = serve(tree)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payloads, fh, indent=1, sort_keys=True)
    print(f"{tree}: {len(payloads['jobs']['jobs'])} jobs, "
          f"{len(payloads['details'])} details, "
          f"{len(payloads['pings']['pings'])} pending pings, "
          f"{len(payloads['ledger']['events'])} ledger events "
          f"-> {out_path}")


if __name__ == "__main__":
    main()
