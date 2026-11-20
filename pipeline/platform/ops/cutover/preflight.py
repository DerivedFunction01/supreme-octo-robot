#!/usr/bin/env python3
"""Cutover preflight — fails loudly on any unmet readiness
condition. Run before the freeze opens; the freeze does not
start on a red preflight.

Two kinds of checks:

  Tree-side (mechanical, always run): the one-run.py
  serving topology is present (the root run.py, the one
  mega unit template, the watchdog ladder), and this kit
  is complete on disk. The rollback's renders are the
  four installed units step 8 backs up before it installs
  anything; the originals keep their own unit templates
  in their frozen repos.

  Record-side (attested): the freeze record carries each
  readiness condition as pass + a proof pointer, and every
  proof pointer names a file that exists. An attestation
  without its proof artifact on disk is not a pass.

The five readiness conditions are the goal's: S8 live-fed;
code consolidated with the union gate green; zero
undispositioned divergence at the final resync; data
cutovers rehearsed (including the todo slug rename); the
reversible switch armed. The generic remake gate, the
run.py boot proof, and the published-surface re-embed are
checked as their own conditions.

The remake check's basis: the genericity cures (688a553)
and gate legs (947ba24) brought the tracked tree to zero
CURE-class hits, proven three ways (census report:
genericity-census-report.md). The binding form here is
unchanged: the every-object scan of the remade history,
recorded in the freeze record. The published-surface
check binds the Library artifact's publish to that same
remade head — and, since the contract 09 rebuild, to the
served-data proof (pipeline/platform/ops/publish_proof.py):
the proof report the record points at must carry per-app
pass verdicts over the artifact's OWN action channel,
name the record's live_version as its artifact_version,
and postdate the recorded publish. Bundle-hash equality
(dist_hashes_match) is information only and no part of
the pass condition: the v37 embed was hash-verified and
mock-fed at once, which is the failure the proof exists
to make impossible.

With --slug-jobs/--slug-attention/--slug-workrecord, the
post-rename slug verification runs against those surfaces
(the freeze's post-migration form of this check). With
--assembled-jobs (and --assembled-ws, the workspace root
the assembled registry's ${WS} anchor names), the
argv-target verification runs over the assembled
registry: every assembled entry's anchored argv target
must exist, and any miss fails loudly, listed.

Exit 0 = all checks pass. Exit 1 = one FAIL line per unmet
condition. Read-only.
"""

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = importlib.util.spec_from_file_location(
    "platform_paths",
    next(_p for _p in (
        os.path.join(os.path.dirname(
            os.path.dirname(_here)), "paths.py"),
        os.path.join(os.path.dirname(_here), "paths.py"),
        os.path.join(_here, "paths.py"))
        if os.path.isfile(_p)))
paths = importlib.util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

HERE = _here
PIPELINE_ROOT = paths.PIPELINE_ROOT
REPO_ROOT = paths.REPO_ROOT

# The tolerant ISO parse home is the workrecord lib's
# (one owner per helper); both call sites below parse the
# publisher's own Z-aware stamps, on which the home's
# naive-to-UTC forcing never fires.
sys.path.insert(0, os.path.join(PIPELINE_ROOT, "workrecord"))
from lib.util import parse_instant as _parse_instant  # noqa: E402

KIT_FILES = ["preflight.py", "provision_config.py",
             "mint_tokens.py", "export_ledger.py",
             "migrate_attention.py", "migrate_workrecord.py",
             "migrate_venue.py", "assemble_registry.py",
             "render_units.py", "verify_endpoints.py",
             "verify_todo_slugs.py", "verify_argv_targets.py",
             "README.md", "freeze_record.example.json"]

MEGA_UNIT_TEMPLATE = ("pipeline/platform/ops/"
                      "workhorse.service.tmpl")

WATCHDOG_LADDER = ["pipeline/platform/ops/healthcheck.py",
                   "pipeline/platform/ops/watchdog.sh"]

CONDITIONS = ["live_fed", "consolidated_gate_green",
              "zero_divergence", "data_cutovers_rehearsed",
              "reversible_switch"]

REHEARSALS = ["provision_config", "mint_tokens",
              "export_ledger", "migrate_attention",
              "migrate_workrecord", "migrate_venue",
              "assemble_registry", "render_units",
              "verify_endpoints", "verify_todo_slugs",
              "verify_argv_targets"]


def _proof_exists(record, *keys):
    node = record
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) and node else None


def run_checks(record_path, slug_surfaces, assembled=None):
    checks = []  # (name, ok, detail)

    missing = [f for f in KIT_FILES
               if not os.path.isfile(os.path.join(HERE, f))]
    checks.append(("kit complete", not missing,
                   "missing: " + ", ".join(missing)
                   if missing else f"{len(KIT_FILES)} files"))

    mega_tmpl = os.path.isfile(
        os.path.join(REPO_ROOT, MEGA_UNIT_TEMPLATE))
    checks.append(("mega unit template present "
                   "(step 8 renders it)", mega_tmpl,
                   MEGA_UNIT_TEMPLATE if mega_tmpl else
                   "missing: " + MEGA_UNIT_TEMPLATE +
                   " — the serving build has not landed"))

    missing = [f for f in WATCHDOG_LADDER
               if not os.path.isfile(os.path.join(REPO_ROOT, f))]
    checks.append(("watchdog ladder present (step 7 "
                   "healthcheck flip basis)", not missing,
                   "missing: " + ", ".join(missing)
                   if missing else
                   "healthcheck.py + watchdog.sh"))

    candidates = [os.path.join(REPO_ROOT, "run.py"),
                  os.path.join(PIPELINE_ROOT, "run.py")]
    found = [c for c in candidates if os.path.isfile(c)]
    checks.append(("one run.py serving entry present",
                   bool(found),
                   "found: " + ", ".join(
                       os.path.relpath(c, REPO_ROOT)
                       for c in found)
                   if found else
                   "no run.py at the repo root or the "
                   "pipeline root — the serving build has "
                   "not landed"))

    record = None
    if record_path and os.path.isfile(record_path):
        with open(record_path, encoding="utf-8") as fh:
            record = json.load(fh)
    if record is None:
        for name in CONDITIONS + ["generic remake gate",
                                  "published surface re-embedded",
                                  "run.py boot proof",
                                  "todo slug rename rehearsed",
                                  "kit rehearsals current"]:
            checks.append((name, False,
                           "no freeze record supplied "
                           "(--record) — unattested"))
    else:
        conds = record.get("conditions", {})
        for name in CONDITIONS:
            entry = conds.get(name, {})
            proof = _proof_exists(entry, "proof")
            ok = (entry.get("status") == "pass"
                  and proof is not None
                  and os.path.exists(proof))
            detail = ("proof: " + proof) if ok else (
                "status/proof missing or proof file "
                "absent for " + name)
            checks.append((f"readiness: {name}", ok, detail))

        remake = record.get("remake", {})
        ok = (remake.get("scan_hits") == 0
              and remake.get("gate_green") is True
              and bool(remake.get("head")))
        checks.append(("generic remake gate", ok,
                       f"head {remake.get('head')}, "
                       f"scan hits {remake.get('scan_hits')} "
                       f"(every-object scan of the remade "
                       f"history; tree basis 688a553 + "
                       f"947ba24, three-way zero-hit proof)"
                       if ok else
                       "record.remake must carry scan_hits 0, "
                       "gate_green true, and the remade head"))

        published = record.get("published_surface", {})
        proof = _proof_exists(published, "proof")
        proof_bits = []
        proof_ok = False
        if proof is None or not os.path.exists(proof):
            proof_bits.append("no proof report on disk")
        else:
            try:
                with open(proof, encoding="utf-8") as fh:
                    proof_report = json.load(fh)
            except (OSError, ValueError) as exc:
                proof_report = None
                proof_bits.append(
                    f"proof pointer does not parse as a "
                    f"proof report ({exc})")
            if proof_report is not None:
                apps = proof_report.get("apps", {})
                verdicts = {app: entry.get("verdict")
                            for app, entry in apps.items()
                            if isinstance(entry, dict)}
                if not verdicts or any(
                        v != "pass" for v in verdicts.values()):
                    proof_bits.append(
                        f"proof per-app verdicts not all "
                        f"pass: {verdicts}")
                if proof_report.get("artifact_version") != \
                        published.get("live_version"):
                    proof_bits.append(
                        f"proof artifact_version "
                        f"{proof_report.get('artifact_version')!r} "
                        f"!= live_version "
                        f"{published.get('live_version')!r}")
                proved_at = _parse_instant(
                    proof_report.get("proved_at"))
                published_at = _parse_instant(
                    published.get("republished_at"))
                if proved_at is None or published_at is None \
                        or proved_at <= published_at:
                    proof_bits.append(
                        f"proof proved_at "
                        f"{proof_report.get('proved_at')!r} "
                        f"does not postdate the publish "
                        f"{published.get('republished_at')!r}")
                proof_ok = not proof_bits
        binding_ok = (bool(published.get("live_version"))
                      and bool(remake.get("head"))
                      and published.get("republished_from")
                      == remake.get("head"))
        ok = binding_ok and proof_ok
        bits = []
        if not binding_ok:
            bits.append(
                f"republished_from "
                f"{published.get('republished_from')!r} does "
                f"not name the remade head "
                f"{remake.get('head')!r}")
        bits.extend(proof_bits)
        bits.append(
            f"dist_hashes_match "
            f"{published.get('dist_hashes_match')!r} "
            f"(information only — not a pass condition)")
        checks.append(("published surface re-embedded", ok,
                       "republished from the remade head; "
                       "served-data proof all-pass over the "
                       "artifact's own action channel"
                       if ok else "; ".join(bits)))

        serving = record.get("serving", {})
        boot = _proof_exists(serving, "boot_proof")
        ok = (serving.get("gate_green") is True
              and boot is not None
              and os.path.exists(boot)
              and bool(found)
              and os.path.abspath(serving.get("run_py", ""))
              in [os.path.abspath(c) for c in found])
        checks.append(("run.py boot proof", ok,
                       "gate green; boot proof: " + str(boot)
                       if ok else
                       "record.serving must name the landed "
                       "run.py, gate_green true, and a boot "
                       "proof (all four surfaces answering "
                       "on their ports against fixture "
                       "state) that exists on disk"))

        rename = record.get("todo_rename", {})
        proof = _proof_exists(rename, "report")
        ok = (rename.get("driver_landed") is True
              and proof is not None
              and os.path.exists(proof))
        checks.append(("todo slug rename rehearsed", ok,
                       "driver report: " + str(proof) if ok
                       else "record.todo_rename must carry "
                       "driver_landed true and the naming "
                       "lane's report as its proof"))

        manifest_path = _proof_exists(record, "rehearsals",
                                      "manifest")
        detail = "no rehearsal manifest in the record"
        ok = False
        if manifest_path and os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            stale = [r for r in REHEARSALS
                     if manifest.get(r) != "pass"]
            ok = not stale
            detail = ("all drivers pass" if ok else
                      "not passing: " + ", ".join(stale))
        checks.append(("kit rehearsals current", ok, detail))

    if any(slug_surfaces.values()):
        sys.path.insert(0, HERE)
        import verify_todo_slugs as vts
        fails = []
        slug_ids = set()
        if slug_surfaces.get("workrecord"):
            found_fails, slug_ids = vts.check_workrecord(
                slug_surfaces["workrecord"])
            fails.extend(found_fails)
        if slug_surfaces.get("attention"):
            fails.extend(vts.check_attention_state(
                slug_surfaces["attention"]))
        if slug_surfaces.get("jobs"):
            fails.extend(vts.check_jobs(
                slug_surfaces["jobs"], slug_ids))
        checks.append((
            "todo references resolve by slug "
            "(post-migration)", not fails,
            "; ".join(fails) if fails else
            "no live reference resolves only by a legacy id"))

    if assembled and assembled.get("jobs"):
        sys.path.insert(0, HERE)
        import verify_argv_targets as vat
        ws = assembled.get("ws") or \
            os.path.dirname(REPO_ROOT)
        anchors = vat.bindings(REPO_ROOT, ws)
        missing = vat.missing_targets(assembled["jobs"],
                                      anchors)
        checks.append((
            "assembled argv targets exist", not missing,
            "; ".join(missing) if missing else
            "every anchored argv target in the assembled "
            "registry resolves to an existing file"))

    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record",
                    help="the freeze record (JSON); without "
                    "it every attested condition fails")
    ap.add_argument("--slug-jobs")
    ap.add_argument("--slug-attention")
    ap.add_argument("--slug-workrecord")
    ap.add_argument("--assembled-jobs",
                    help="the assembled registry dir; "
                    "runs the argv-target verification "
                    "over it")
    ap.add_argument("--assembled-ws",
                    help="the workspace root the assembled "
                    "registry's ${WS} anchor names "
                    "(default: the parent of this repo)")
    args = ap.parse_args(argv)

    checks = run_checks(args.record, {
        "jobs": args.slug_jobs,
        "attention": args.slug_attention,
        "workrecord": args.slug_workrecord}, {
        "jobs": args.assembled_jobs,
        "ws": args.assembled_ws})
    failed = 0
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name} — {detail}")
        failed += 0 if ok else 1
    print(f"SUMMARY {json.dumps({'checks': len(checks), 'failed': failed}, sort_keys=True)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
