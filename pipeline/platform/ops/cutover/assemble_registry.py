#!/usr/bin/env python3
"""Assemble the mega scheduler registry from the LIVE
set (freeze step 7, scripted).

The flip is not a file copy: the mega server must read a
registry whose entries are the live set with the workhorse
pointers re-homed. This assembler takes the live jobs dir
(read-only) and writes the assembled dir:

  carried     an entry whose pointers needed no change
              (scheduler-self entries anchored at the
              server home travel as-is; their state rides
              the ledger export, not this assembly)
  re-pointed  pointer prefixes rewritten to the mega
              homes, text-preserving apart from the
              pointer itself:
                ${WS}/<runner home>/     -> the mega
                                            venue home
                ${WS}/<workbench home>/  -> the mega
                                            workrecord home
                ${WS}/<scheduler home>/  -> the mega
                                            scheduling home
              (the workspace-relative anchor is kept;
              the mega root is an argument, never a
              literal baked into this script)
  flagged     DECISION — an attention-pointing entry
              (the healthcheck): flips only if the mega
              serving step lands an equivalent watchdog
              ladder, else retires; the assembler copies
              it and flags it, never silently re-points.
              REMINT — a per-session liveness entry:
              carried and re-pointed, to be re-minted
              per live session at the freeze.
              BODY-MISSING — an entry naming a body file
              the mega bodies dir does not carry.
  mega-only   entries the mega registry holds that the
              live set does not: listed, never copied in.
              Their admission is a separate freeze act
              (the card-watch entry arms at the freeze by
              its own plan).
  provisioned instance files the assembled entries
              reference under the scheduler home (anchored
              argv targets, bodies) that the mega home
              does not carry but the live home does are
              copied from the live home at assembly —
              untracked instance data, never tracked
              content — and recorded per file in the
              report. A referenced file missing in both
              homes is not provisioned; it stays flagged
              and fails the verification below.

After assembly, every assembled entry's anchored argv
targets are verified to exist (the check lives in
verify_argv_targets.py; preflight runs the same check
standalone over the assembled registry). Any miss fails
the run, listing each missing target. Provisioning is
scoped to the scheduler home — the one home whose live
set this assembler assembles; another home's missing
target fails verification loudly rather than being
copied across homes.

Any pointer to an original home that no rule covered
fails the run — an unre-pointed pointer is exactly the
divergence the freeze exists to catch. The assembled dir
is validated by placing it as a scheduling home's jobs/
and running that home's `bin/sched validate` (the
runbook's act; --validate-home does it here).

--strip-provenance drops the past-migration provenance
keys (migrated, migrated_at, migration_note) from the
assembled copies: every live entry carries them and the
mega registry schema refuses unknown fields, so an
assembled registry keeping them does not load. Nothing
is lost — the runbook snapshots the original jobs dir
before assembly, and the freeze record itself is this
migration's provenance. Every stripped key is listed per
entry in the report; without the flag nothing is dropped
and validation fails loudly.

Prints a table + one SUMMARY line (JSON); the full
report lands at --report when given.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import verify_argv_targets as vat

ORIGINALS = [("colab-runner", "venue"),
             ("workbench-viewer", "workrecord"),
             ("scheduler", "scheduling")]

PROVENANCE_KEYS = ("migrated", "migrated_at",
                   "migration_note")


def _mega_prefix(ws, mega_root, package):
    rel = os.path.relpath(os.path.join(mega_root, "pipeline",
                                       package), ws)
    return "${WS}/" + rel.replace(os.sep, "/") + "/"


def _place(report, done, entry_id, target, source, dest):
    """Copy one instance file from the live home to its
    mega home, once, recording it. A destination that
    already exists is the mega's own file and is never
    overwritten; a source that is not a file leaves the
    reference for the flags and verification to name."""
    if os.path.exists(dest) or dest in done:
        return
    if not os.path.isfile(source):
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(source, dest)
    done.add(dest)
    report["provisioned"].append({
        "entry": entry_id, "target": target,
        "source": source, "dest": dest})


def _provision(text, entry_id, anchors, live_home,
               mega_bodies, report, done):
    """Provision the scheduler-home instance files one
    assembled entry references: its anchored argv targets
    resolving under the mega scheduling home, and its
    bodies. Scoped to the scheduler home by design (see
    the module docstring)."""
    sched_home = anchors["REPO"]
    for token in vat.anchored_tokens(text):
        resolved = vat.expand(token, anchors)
        if resolved == sched_home or \
                resolved.startswith(sched_home + os.sep):
            rel = os.path.relpath(resolved, sched_home)
            _place(report, done, entry_id, token,
                   os.path.join(live_home, rel), resolved)
    for body in re.findall(r"bodies/([\w.-]+\.md)", text):
        _place(report, done, entry_id, f"bodies/{body}",
               os.path.join(live_home, "bodies", body),
               os.path.join(mega_bodies, body))


def assemble(live_dir, mega_dir, out_dir, ws, mega_root,
             mega_bodies, strip_provenance=False,
             live_home=None):
    report = {"carried": [], "repointed": {}, "decision": [],
              "remint": [], "body_missing": [],
              "mega_only": [], "unrepointed": [],
              "stripped": {}, "provisioned": [],
              "argv_missing": []}
    if live_home is None:
        live_home = os.path.dirname(
            os.path.abspath(live_dir))
    anchors = vat.bindings(mega_root, ws)
    provisioned_done = set()
    rules = []
    for original, package in ORIGINALS:
        rules.append((f"${{WS}}/{original}/",
                      _mega_prefix(ws, mega_root, package),
                      original))
    attention_re = re.compile(r"\$\{WS\}/owner-attention/")

    live_entries = {f for f in os.listdir(live_dir)
                    if f.endswith(".yaml")}
    mega_entries = ({f for f in os.listdir(mega_dir)
                     if f.endswith(".yaml")}
                    if os.path.isdir(mega_dir) else set())
    report["mega_only"] = sorted(mega_entries - live_entries)

    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(live_entries):
        with open(os.path.join(live_dir, name),
                  encoding="utf-8") as fh:
            text = fh.read()
        changed = {}
        for old, new, original in rules:
            count = text.count(old)
            if count:
                text = text.replace(old, new)
                changed[original] = count
        entry_id = name[:-len(".yaml")]
        if strip_provenance:
            kept, dropped = [], []
            for line in text.splitlines(keepends=True):
                key = line.split(":", 1)[0].strip()
                if not line.startswith((" ", "\t")) and \
                        key in PROVENANCE_KEYS:
                    dropped.append(key)
                else:
                    kept.append(line)
            if dropped:
                text = "".join(kept)
                report["stripped"][entry_id] = dropped
        if attention_re.search(text):
            report["decision"].append(entry_id)
        if name.startswith("colab-liveness-"):
            report["remint"].append(entry_id)
        _provision(text, entry_id, anchors, live_home,
                   mega_bodies, report, provisioned_done)
        for body in re.findall(r"bodies/([\w.-]+\.md)", text):
            if not os.path.isfile(os.path.join(mega_bodies,
                                               body)):
                report["body_missing"].append(
                    f"{entry_id}:{body}")
        leftovers = [original for original, _pkg in ORIGINALS
                     if f"${{WS}}/{original}/" in text]
        if leftovers:
            report["unrepointed"].append(
                f"{entry_id}:{','.join(leftovers)}")
        with open(os.path.join(out_dir, name), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
        if changed:
            report["repointed"][entry_id] = changed
        else:
            report["carried"].append(entry_id)
    report["argv_missing"] = vat.missing_targets(out_dir,
                                                 anchors)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live-jobs", required=True)
    ap.add_argument("--live-home",
                    help="the live scheduler home the "
                    "instance files are provisioned from "
                    "(default: the parent of --live-jobs)")
    ap.add_argument("--mega-jobs", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ws", required=True,
                    help="the workspace root the ${WS} "
                    "anchor names")
    ap.add_argument("--mega-root", required=True,
                    help="the mega repo checkout root")
    ap.add_argument("--mega-bodies",
                    help="the mega bodies dir (default: "
                    "the mega scheduling package's)")
    ap.add_argument("--validate-home",
                    help="a scheduling home to validate "
                    "the assembly with (its jobs/ is "
                    "backed up and restored)")
    ap.add_argument("--report")
    ap.add_argument("--strip-provenance",
                    action="store_true",
                    help="drop the past-migration "
                    "provenance keys from assembled "
                    "copies (reported per entry)")
    args = ap.parse_args(argv)

    mega_bodies = args.mega_bodies or os.path.join(
        args.mega_root, "pipeline", "scheduling", "bodies")
    report = assemble(args.live_jobs, args.mega_jobs,
                      args.out_dir, args.ws, args.mega_root,
                      mega_bodies,
                      strip_provenance=args.strip_provenance,
                      live_home=args.live_home)
    for key in ("carried", "decision", "remint",
                "body_missing", "mega_only", "unrepointed",
                "argv_missing"):
        print(f"{key}: {len(report[key])} "
              f"{report[key] if report[key] else ''}")
    print(f"repointed: {len(report['repointed'])} "
          f"{sorted(report['repointed'])}")
    print(f"provisioned: {len(report['provisioned'])} "
          f"{[p['entry'] + ':' + p['target'] for p in report['provisioned']]}")

    failed = bool(report["unrepointed"]) or \
        bool(report["argv_missing"])
    if args.validate_home:
        home = os.path.abspath(args.validate_home)
        jobs = os.path.join(home, "jobs")
        aside = jobs + ".pre-assembly"
        shutil.move(jobs, aside)
        try:
            shutil.copytree(args.out_dir, jobs)
            proc = subprocess.run(
                [sys.executable,
                 os.path.join(home, "bin", "sched"),
                 "validate"],
                cwd=home, capture_output=True, text=True)
            out_lines = (proc.stdout or proc.stderr) \
                .strip().splitlines()
            report["validate"] = {
                "exit": proc.returncode,
                "invalid": [line for line in out_lines
                            if "INVALID" in line][:30],
                "tail": out_lines[-3:]}
            failed |= proc.returncode != 0
        finally:
            shutil.rmtree(jobs)
            shutil.move(aside, jobs)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
    print(f"SUMMARY {json.dumps({'entries': len(report['carried']) + len(report['repointed']), 'unrepointed': report['unrepointed'], 'argv_missing': report['argv_missing']}, sort_keys=True)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
