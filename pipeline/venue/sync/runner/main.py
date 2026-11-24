#!/usr/bin/env python3
"""Dispatch and the launch path: verb routing (--sweep / --poll
/ --wait never pay the launch path's costs), flag and claim
resolution, the bundle seed, lease acquire, uploads, the
confirmed detached launch, and the foreground poll loop.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .foundation import JOBS, REPO, RUNS, TOKEN, colab, git_identity, lease, mirror, now
from .launch import build_launch_stamp, build_seed_ctx, drive_branch_window, ensure_run_dir, orphan_notes, rewrite_upload_args, run_upload_dir, stamp_transport_span, transport_error, transport_setup, upload_one, upload_seed_files
from .pull import finalize_run, manifest_shape_error, normalize_manifest_outputs, pull_outputs
from .warnings import name_warnings
from .reader import _absence_grace_s, _launch_age_s, read_reader, register_poll_failure, write_reader
from .records import claim_first_save, load_run_record, mark_terminal, save_record, stamp_collector
from .claims import ManifestUnreadable, adopt, attach_verdict, load_manifest, option_like_refusal, spawn_daemon, stamp_takeover
from .replace import acquire_session, record_pin
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
    # Flags travel in pairs and may sit on either side of the job
    # name — extract them first and take the first remaining token
    # as the job. (Job-first-only parsing read a leading --caller
    # as a job name; it bit a consumer following shorthand in a
    # message.)
    resume = caller_flag = session_flag = None
    seed_flag = detach_flag = daemonize_flag = False
    extra_args = []
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--":
            # Everything after -- is the job's own argv (the repo
            # selection seam: env-build -- --repo <id> reaches
            # env_build.sh without a manifest per repo).
            extra_args = args[i + 1:]
            break
        if args[i] == "--seed":
            seed_flag = True
            i += 1
        elif args[i] == "--detach":
            detach_flag = True
            i += 1
        elif args[i] == "--daemonize":
            daemonize_flag = True
            i += 1
        elif args[i] == "--resume" and i + 1 < len(args):
            resume = args[i + 1]
            i += 2
        elif args[i] == "--caller" and i + 1 < len(args):
            caller_flag = args[i + 1]
            i += 2
        elif args[i] == "--session" and i + 1 < len(args):
            session_flag = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1
    if not positional:
        print("usage: colab-run <job-name> [--resume RUN_ID] [--caller TAG] [--seed] [--detach] [--daemonize] [--session NAME] [-- <job args>...]", file=sys.stderr)
        return 2
    job_name = positional[0]
    # Option-like names refuse at parse, before any record
    # is written (claims.option_like_refusal).
    refusal = option_like_refusal(job_name, resume)
    if refusal is not None:
        print(f"colab-run: {refusal}", file=sys.stderr)
        return 2
    if daemonize_flag and not os.environ.get("COLAB_RUN_DAEMON_CHILD"):
        # --daemonize: the fire must survive its firing context.
        # A fire ridden through a bounded context — the
        # scheduler ops route is the standing specimen — dies
        # with that context twice over: the child inherits the
        # context's output pipes, so the context cannot complete
        # while the child lives; and the context's timeout
        # cleanup kills its whole process group (ops.py's
        # killpg on timeout), the merely-nohup'd runner
        # included — read in the ops code and proven by the
        # daemon-proof run, which outlived its
        # op's timeout kill and completed. The daemon form
        # separates both, and claims single-flight (claims.py):
        # the parent claims the record itself, in the claiming
        # state, BEFORE spawning the child in its own session —
        # the run is pollable from the instant the parent
        # prints, and an unadopted claim's loss becomes
        # decidable at its deadline instead of reading as dead.
        if resume:
            print("colab-run: --daemonize is a fresh-launch form; a resumed run is already named and claimed", file=sys.stderr)
            return 2
        if not (JOBS / job_name / "job.json").exists():
            print(f"no job manifest at {JOBS / job_name / 'job.json'}", file=sys.stderr)
            return 2
        try:
            claimed, log_path = spawn_daemon(job_name, args, JOBS / job_name / "job.json")
        except Exception as exc:
            print(f"colab-run: daemonize pre-claim failed for {job_name}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"run_id": claimed, "state": "daemonized", "log": log_path}))
        return 0
    manifest_path = JOBS / job_name / "job.json"
    try:
        job = load_manifest(manifest_path)
    except ManifestUnreadable as exc:
        print(f"no job manifest at {manifest_path}" if exc.missing else f"colab-run: {exc}", file=sys.stderr)
        return 2 if exc.missing else 1
    # Manifest shape, settled once at load, before any session
    # work: outputs normalize to plain local names (mapped
    # entries tolerated), while uploads / args entries that are
    # not plain strings refuse the launch loudly, naming the
    # field and the entry — the shapes have no tolerance
    # semantics, and discovering that mid-launch cost a
    # consumer a crashed run.
    # The transport declaration settles at the same load point
    # (branch transport plan, Step 1): a malformed branch form refuses here.
    shape_err = manifest_shape_error(job) or transport_error(job)
    if shape_err:
        print(f"colab-run: job {job_name}: {shape_err}", file=sys.stderr)
        return 2
    normalize_manifest_outputs(job)
    # Caller claim: flag over the manifest's caller key over
    # $COLAB_CALLER; a presented but unregistered claim is refused
    # at claim time, before anything starts.
    claim_raw = caller_flag if caller_flag is not None else job.get("caller")
    claim_err = lease.caller_claim_error(REPO, flag=claim_raw, env=os.environ.get("COLAB_CALLER"))
    if claim_err:
        print(f"colab-run: {claim_err}", file=sys.stderr)
        return 2
    caller = lease.resolve_caller(REPO, flag=claim_raw, env=os.environ.get("COLAB_CALLER"))
    # Session pin: flag over the env seam, mirroring the caller
    # claim's precedence. A pin names the lease this run must
    # adopt (acquire refuses pin-unavailable rather than
    # substituting another session).
    pin_session = session_flag if session_flag is not None else os.environ.get("COLAB_RUN_SESSION")
    if not TOKEN.exists() and not os.environ.get("COLAB_BIN"):
        print("colab-run: STAGED — no colab login yet. Run ops/bootstrap_local.sh, then the one-time login (see README).", file=sys.stderr)
        return 2

    mirror("restore")

    # A manifest may name its shape; otherwise the config's
    # default_shape is the only fallback — no shape is hardcoded
    # here, and an unresolvable shape fails loudly.
    shape_id = job.get("shape") or lease.default_shape(REPO)
    shapes = lease.catalog_shapes(REPO, colab)
    if not shape_id or shape_id not in shapes:
        print(f"colab-run: job {job_name} names no usable shape (manifest shape or config default_shape required)", file=sys.stderr)
        return 2
    shape = shapes[shape_id]
    # A daemonized fire's parent mints the id and hands it to
    # the child through the env (see --daemonize above); the
    # claim below suffixes it on a collision exactly as for a
    # self-minted id, and the parent reports the claimed name
    # it read off disk, so the two never disagree.
    daemon_id = os.environ.get("COLAB_RUN_ID") if os.environ.get("COLAB_RUN_DAEMON_CHILD") else None
    run_id = resume or daemon_id or f"{job_name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    rec = None
    if resume:
        # A resume continues the run on disk: its launch facts
        # (started_at above all) are the run's history and are
        # never re-stamped — the resume adds its own facts.
        # (a resumed hold came back stamped with the
        # resume moment, erasing its launch time.)
        prior = RUNS / f"{run_id}.json"
        if prior.exists():
            rec = load_run_record(run_id)
            if rec is None:
                # A torn prior (a flap-killed fire's 0-byte
                # record) holds nothing to preserve: the resume
                # starts the run fresh rather than crashing
                # every later entry on the damaged file.
                print(f"colab-run: prior record for {run_id} is unreadable (torn); starting fresh", file=sys.stderr)
            else:
                # Single-flight (claims.py): a resume attaches
                # to a possibly-live execution — an outstanding
                # claim or a confirmed launch — and never
                # relaunches it; only a decidable-lost claim
                # proceeds, stamped as a takeover.
                attach = attach_verdict(rec)
                if attach is not None:
                    print(json.dumps({"run_id": run_id, **attach}))
                    return 0
                if rec.get("state") == "claiming":
                    stamp_takeover(rec)
                # A resurrected run announces its NEW terminal state
                # afresh: the sweep's orphan event is history, not
                # this run's outcome.
                rec.pop("terminal_event_state", None)
                rec.pop("terminal_event_at", None)
                # A run that already launched keeps its launched
                # state across a resume: re-stamping "starting"
                # leaves confirmed-launch facts under a
                # pre-launch state when the resume dies before
                # its own launch (an admincap record
                # froze at "starting" carrying launch_at and
                # launch_confirmed_at). The resume's own launch
                # re-stamps "running" when it lands; a record
                # that never launched re-stamps "starting" as
                # before.
                if rec.get("state") in ("polling", "running"):
                    rec.update(resumed=True, resumed_at=now())
                else:
                    rec.update(state="starting", resumed=True, resumed_at=now())
                # The driver stamp follows the execution: a
                # daemonized run's record names its daemon
                # child as driver, and this resume is the driver
                # now — the sweep's daemon-orphan test reads the
                # stamp as the driver's identity, and the dead
                # daemon's pid must not condemn a run a live
                # resume is driving (claims.stamp_takeover does
                # the same for the claim path).
                if rec.get("daemon_child_pid") is not None:
                    rec["daemon_child_pid"] = os.getpid()
    preclaimed = False
    if rec is None and daemon_id:
        # A daemonized child adopts its parent's pre-claim
        # (claims.py) instead of claiming for itself.
        rec = adopt(run_id, shape_id)
        preclaimed = rec is not None
    if rec is None:
        rec = {"run_id": run_id, "job": job_name, "shape": shape_id, "state": "starting", "started_at": now(), "resumed": bool(resume)}
    if caller:
        rec["caller"] = caller
    if resume or preclaimed:
        save_record(rec)
    else:
        # A fresh launch claims its id with this first save:
        # a same-second parallel launch of the same job gets
        # the next suffix instead of absorbing this run's
        # record (claim_first_save). A resume names its run
        # and keeps the plain save — overwriting its own torn
        # prior is the resume contract.
        run_id = claim_first_save(rec)
    # Bundle seed (--seed — env-build's private-repo route): the
    # job's target repo reaches the VM as a snapshot bundle, never
    # as a VM-side clone — a private repo's plain HTTPS clone
    # cannot authenticate on the VM (no credential lives there by
    # design). The bundle is built locally before any session is
    # held (launch.build_seed_ctx), uploaded in the window below,
    # and seeded into the dest (sync/apply_bundle_remote.py's seed
    # mode); the job then runs with --skip-clone.
    seed_ctx = None
    if seed_flag and not resume:
        seed_err, seed_ctx = build_seed_ctx(extra_args, rec)
        if seed_err is not None:
            rec.update(state="failed", error=seed_err)
            save_record(rec)
            print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
            return 1
        save_record(rec)
    # Transport (branch transport plan): stamp the
    # record's transport, resolve any branch declaration (launch.transport_setup).
    transport, branch_err, branch_ctx = transport_setup(rec, job, seed_ctx)
    if branch_err is not None:
        rec.update(state="failed", error=branch_err)
        save_record(rec)
        print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
        return 1
    try:
        usage_before = colab("usage", timeout=120).stdout.strip()
    except subprocess.TimeoutExpired:
        # Accounting context only — never a dead launcher.
        usage_before = ""
    # Lease model (sync/lease/): adopt-or-acquire the shared session and
    # leave it up at the end; the reaper owns its lifecycle. With the lease
    # disabled in config, fall back to the original per-job session.
    use_lease = bool(lease.load_config(REPO).get("enabled"))
    if detach_flag and not use_lease:
        # --detach leaves the job running with no poller; the
        # lease-disabled fallback's per-run session is stopped by
        # the poller's own finally, so a detached launch there
        # would kill the job it just started.
        rec.update(state="failed", error="--detach requires the lease path (lease.enabled); the fallback per-job session dies with the poller")
        save_record(rec)
        print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
        return 2
    if pin_session and not use_lease:
        # A pin names a lease; the fallback's per-run session is
        # run-named, so there is nothing to pin to.
        rec.update(state="failed", error="--session requires the lease path (lease.enabled); the fallback per-job session is run-named")
        save_record(rec)
        print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
        return 2
    if pin_session is None and use_lease and rec is not None:
        # A resume keeps its recorded lineage: the session the
        # launch actually bound (replace.record_pin) is this
        # fire's pin when the caller names none — never a
        # fresh per-invocation resolution, and never the
        # record's re-stampable current binding.
        pin_session = record_pin(rec)
    session = run_id  # the lease-disabled fallback's per-run session
    if use_lease:
        if pin_session:
            rec["session_pin"] = pin_session
        # The window floor the acquire ranks by: this job's
        # timeout, capped at an hour — the renewal machinery
        # owns windows beyond that; the floor only keeps a
        # fire off a lease in its final hour.
        window_floor_s = min(int(job.get("timeout", 18000)), 3600)
        got = acquire_session(rec, shape_id, caller, pin_session, window_floor_s, resume)
        if got["action"] in ("refused-budget", "create-failed", "shape-refused", "shape-mismatch", "caller-start-refused", "unknown-shape", "pin-unavailable"):
            if got.get("probe"):
                rec["bind_probe"] = got["probe"]
            rec.update(state="failed", error=json.dumps(got)[:300])
            save_record(rec)
            # E1: if live sessions sit unrecorded at this shape,
            # the refusal may be the record loss talking — name
            # the state and the verb that restores it (stderr;
            # stdout stays the run's JSON result).
            for note in orphan_notes(shape_id, shape):
                print(note, file=sys.stderr)
            print(json.dumps({"run_id": run_id, "state": "failed", "lease": got}, indent=2))
            return 1
        rec["lease_action"] = got["action"]
        for key in ("bind_probe", "pin_resolved"):
            if got.get(key):
                rec[key] = got[key]
        if got.get("health_degraded"):
            # Adopted anyway (every candidate was degraded):
            # the record says the launch channel has been
            # failing on this session, so a launch failure here
            # reads as a known condition, not a surprise.
            rec["health_degraded"] = True
        # The lease's session is whatever the acquire created or
        # adopted — a generated name, never a configured one.
        session = got["record"]["session"]
        rec["session"] = session
        lease.touch_job(REPO, run_id)
        save_record(rec)
    if not use_lease:
        rec["session"] = session
        save_record(rec)
        # Session shape gate for the fallback's own `new` below (the
        # lease path is gated inside acquire): a job run is an agent
        # actor unless the env claim says otherwise. A refusal fails
        # the run before any session is created.
        refusal = lease.enforce_session_admission(REPO, shape_id, via="runner", shape=shape, seam="runner", caller=caller)
        if refusal is not None:
            rec.update(state="failed", error=json.dumps(refusal)[:300])
            save_record(rec)
            print(json.dumps({"run_id": run_id, "state": "failed", "lease": refusal}, indent=2))
            return 1
    detached = False
    try:
        if not use_lease:
            new_args = ["new", "-s", session] + lease._session_shape_args(shape)
            r = colab(*new_args, timeout=600)
            if r.returncode != 0 and "already" not in (r.stdout + r.stderr):
                rec.update(state="failed", error=(r.stderr or r.stdout).strip()[-300:])
                save_record(rec)
                return 1
        script = REPO / job["script"]
        # The remote script lands in the run's own upload
        # directory (launch.run_upload_dir, Step 5): the bare
        # basename was one shared slot per session, and two jobs
        # whose scripts share a basename (every lane's run.py)
        # overwrote each other between upload and launch — a run
        # then executed a foreign payload with its own args
        # (remainder lanes: an eraattr payload ran
        # under a rem20d launch; the run-id-prefixed name that
        # cured it is subsumed by the directory). The payload
        # never names its own slot (the runner invokes it), and
        # the script's directory being the run's directory is
        # what resolves a job script's imports of uploaded
        # modules to its own run's copies.
        remote_script = f"{run_upload_dir(run_id)}/{script.name}"
        # Launch-phase stamps: the window from the
        # record's creation to the state=running save below is
        # minutes of CLI round trips on a loaded session
        # (usage, uploads with verify probes, the seed), and a
        # launcher killed inside it — a caller's client timeout
        # is the recurring case — stranded its record at
        # "starting" with no trace of how far it got, so a slow
        # launch and a dead one read identically. The phase is
        # stamped as the launch advances; a stranded record
        # names its phase.
        rec["launch_phase"] = "uploading"
        save_record(rec)
        # The run's remote upload directory first (Step 5):
        # every pre-launch upload below lands inside it, and
        # an upload into a directory that does not exist fails
        # on the far side. One exec, ahead of the uploads.
        err = ensure_run_dir(session, run_id)
        if err is not None:
            rec.update(state="failed", error=err)
            save_record(rec)
            print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
            return 1
        # Uploads land in the run's own directory (Step 5),
        # so a concurrent launch's uploads cannot meet them.
        # Nothing in this launch window serializes against
        # another launch on the session (owner ruling:
        # no sync blocker on the venue job path):
        # every piece of state below is the run's own — its
        # upload directory, its clone, its seed dest, its out
        # dir — and its execs ride the funnel independently,
        # so concurrent launches proceed concurrently.
        err = upload_one(session, script, remote_script, run_id)
        if err is not None:
            rec.update(state="failed", error=f"runner script upload: {err}")
            save_record(rec)
            print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
            return 1
        rec["transport"]["bytes_moved"] = rec["transport"].get("bytes_moved", 0) + script.stat().st_size
        # Manifest-declared extra uploads land in the run's
        # directory before launch: a shell_job payload names its
        # script in args (--script /content/env_build.sh, which
        # the args rewrite below points at the run's copy) and
        # the registry it reads (/content/repos.json), and
        # neither is the runner script itself. Until this loop
        # existed nothing uploaded them, so env-build's shell_job
        # refused in its first second — a declared
        # upload missing locally fails the run here, never
        # launches a job that cannot run.
        for extra in job.get("uploads", []):
            src = REPO / extra
            if not src.is_file():
                rec.update(state="failed", error=f"manifest upload missing locally: {extra}")
                save_record(rec)
                print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                return 1
            err = upload_one(session, src, src.name, run_id, remote_dir=run_upload_dir(run_id))
            if err is not None:
                rec.update(state="failed", error=f"manifest upload failed: {extra}: {err}")
                save_record(rec)
                print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                return 1
            rec["transport"]["bytes_moved"] = rec["transport"].get("bytes_moved", 0) + src.stat().st_size
        if seed_ctx is not None:
            # The seed's uploads: launch.upload_seed_files
            # lands them in the run's directory, and the apply
            # below writes the run's own seed dest under the
            # same directory. A seed whose uploads did not
            # land is a failed run, never a job launched
            # against a missing tree.
            err = upload_seed_files(session, seed_ctx, run_id)
            if err is not None:
                rec.update(state="failed", error=err)
                save_record(rec)
                print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                return 1
        if branch_ctx is not None:
            # Branch transport: drive the base clone to the declared
            # tip before any launch (launch.drive_branch_window).
            err = drive_branch_window(session, rec, transport, branch_ctx, run_id)
            if err is not None:
                rec.update(state="failed", error=err)
                save_record(rec)
                print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                return 1
        seeded = False
        if seed_ctx is not None:
            # Seed the run's own dest on the VM from the run's
            # own bundle copy and verify the manifest's tree in
            # the seed's own output before any launch. The dest
            # stands under the run's upload directory
            # (runs/<run_id>/<dest>), never the shared
            # per-registry dest: two seeded launches used to
            # write one dest, which is what held the seed apply
            # inside the stripped launch lock. The record's
            # bundle_seed stamp keeps naming the registry dest
            # the run's copy serves.
            _ident = seed_ctx.get("git_identity")
            _ident_args = (
                f",'--user-name',{_ident['name']!r},'--user-email',{_ident['email']!r}"
                if _ident
                else ""
            )
            seed_remote = REPO / "var" / f"seed-{run_id}.py"
            seed_remote.write_text(
                "import subprocess\n"
                f"r = subprocess.run(['python3','{run_upload_dir(run_id)}/apply_bundle_remote.py','{run_upload_dir(run_id)}/{seed_ctx['bundle_path'].name}','{run_upload_dir(run_id)}/{seed_ctx['dest']}','--origin-url','{seed_ctx['clone_url']}'{_ident_args}], capture_output=True, text=True)\n"
                "print(r.stdout); print(r.stderr[-500:])\n"
            )
            try:
                sr = colab("exec", "-s", session, "--timeout", "1800", "-f", str(seed_remote), timeout=1900)
                seed_out = sr.stdout
            except subprocess.TimeoutExpired:
                # A seed timeout is a failed seed (the verify
                # below cannot pass on no output), never a dead
                # launcher stranding the record at "starting".
                seed_out = ""
                lease.append_launch_outcome(REPO, session, "seed", False, "seed exec timed out")
            if '"applied": true' not in seed_out or seed_ctx["manifest"]["tree"] not in seed_out:
                rec.update(state="failed", error=f"bundle seed: seed did not verify: {seed_out.strip()[-300:]}")
                save_record(rec)
                print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                return 1
            lease.append_launch_outcome(REPO, session, "seed", True, seed_ctx["dest"])
            # The plant's readback verdict rides the apply's
            # JSON; record it beside the intended pair so the
            # record distinguishes planted from merely meant.
            for _line in reversed(seed_out.splitlines()):
                try:
                    _apply = json.loads(_line)
                except (ValueError, json.JSONDecodeError):
                    continue
                if isinstance(_apply, dict) and "applied" in _apply:
                    rec["bundle_seed"]["git_identity_result"] = _apply.get("git_identity")
                    save_record(rec)
                    break
            seeded = True
        # Relative to the session working dir (/content on a real Colab VM;
        # the fake CLI's sandbox root under test) so the same code runs both.
        # Per-run: a fixed dir leaks the previous run's heartbeat tail,
        # checkpoint, and outputs into this run's completion check.
        remote_out = f"{job_name}-out-{run_id}"
        rec.update(state="running", remote_out=remote_out, launch_session=session, extra_args=extra_args, launch_phase="launching")
        save_record(rec)
        # Detached launch (default pending the kill-matrix verdict): a short
        # exec starts the job under nohup; the CLI is never the job's lifeline.
        # The payload runs under a stamp wrapper (launch.build_launch_stamp):
        # its exit code lands at <remote_out>.exit-code, so a payload that
        # never writes a checkpoint still reports its outcome truthfully
        # (checkpoint-less gate jobs recorded failed on green
        # runs), and the wrapper reaps the run's leaked processes at job
        # end before the stamp lands. Manifest args naming an upload point
        # at the run's own copy (launch.rewrite_upload_args, Step 5); the
        # extra args after -- are the operator's own argv and pass verbatim.
        job_args = "".join(f",'{a}'" for a in rewrite_upload_args(job.get("args", []), {Path(u).name for u in job.get("uploads", [])}, run_id) + (["--skip-clone"] if seeded else []) + extra_args)
        stamp = build_launch_stamp(remote_script, remote_out, job_args, run_id)
        launch = (
            f"import subprocess; subprocess.Popen(['nohup','python3','-c',{stamp!r}],"
            f" stdout=open('{remote_out}.log','w'), stderr=subprocess.STDOUT, start_new_session=True)"
        )
        launcher = REPO / "var" / f"launch-{run_id}.py"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(launch + "\nprint('launched')\n")
        rec["launch_at"] = now()
        save_record(rec)
        # The launch exec's outcome is CHECKED, and the launch is
        # then confirmed against the venue before the record may
        # claim polling. Until this existed the exec's result was
        # ignored entirely — and its timeout re-raised through
        # the launcher — so a launch that never landed (the
        # daemon's exec lost under kernel saturation) left a
        # record claiming a run that did not exist, forever
        # (the consol records). The stamp wrapper opens
        # the job's log at spawn, so a landed launch has a
        # footprint (pids, log, checkpoint, or exit stamp) on
        # the first reader pass; total absence is a lost launch.
        launch_error = None
        launch_timeout = int(os.environ.get("COLAB_RUN_LAUNCH_TIMEOUT_S", "300"))
        try:
            lr = colab("exec", "-s", session, "--timeout", "120", "-f", str(launcher), timeout=launch_timeout)
            if lr.returncode != 0 or "launched" not in lr.stdout:
                launch_error = f"launch exec rc {lr.returncode}: {(lr.stderr or lr.stdout).strip()[-200:]}"
        except subprocess.TimeoutExpired:
            launch_error = "launch exec timed out"
        lease.append_launch_outcome(REPO, session, "launch", launch_error is None, launch_error or run_id)
        reader = write_reader(run_id, remote_out, job.get("outputs", []))
        # The confirmation is a reader pass and shares the poll
        # timeout's discipline (a test that shrinks poll timeouts
        # shrinks this one too), capped at 120 s so a wedged
        # channel cannot hold the launcher for a full poll bound.
        confirm_timeout = int(os.environ.get("COLAB_RUN_CONFIRM_TIMEOUT_S") or min(int(os.environ.get("COLAB_RUN_POLL_TIMEOUT_S", "300")), 120))
        cstate, _confirm_error = read_reader(session, reader, confirm_timeout)
        footprint = bool(cstate) and bool(cstate.get("job_pids") or cstate.get("exit_stamp") is not None or cstate.get("job_log_tail") or cstate.get("checkpoint"))
        if footprint:
            rec["state"] = "polling"
            rec["launch_phase"] = "launched"
            rec["launch_confirmed_at"] = now()
            rec["last_evidence_at"] = rec["launch_confirmed_at"]
            stamp_collector(rec, rec.get("caller"))
            # A confirmed launch is this attempt's truth: a
            # prior attempt's launch_lost / error (a resume
            # carries both on the record) die in this same
            # save — a record must never read confirmed and
            # lost at once (the record-truth item).
            rec.pop("launch_lost", None)
            rec.pop("error", None)
            # The machine that actually runs the job, from
            # the confirmation reader's own probe (cgroup-
            # aware): sizing reads the measured shape, not
            # the lease's declared one.
            machine = cstate.get("machine")
            if isinstance(machine, dict):
                rec["measured_shape"] = {**machine, "at": rec["launch_confirmed_at"]}
            save_record(rec)
        elif cstate is not None:
            # The channel answered and there is no footprint:
            # the launch is lost, and the record closes honestly
            # now instead of claiming a run that does not exist.
            mark_terminal(rec, "failed", launch_lost=True, error=f"launch never landed on {session} ({launch_error or 'no job footprint on the confirmation read'}); relaunch with --resume {run_id} to retry")
            print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
            return 1
        elif launch_error is None:
            # The venue accepted the launch (the exec printed
            # 'launched') but the confirmation read produced no
            # evidence — the refusing channel is the unknown, and
            # an accepted launch reads polling as it always has,
            # stamped unconfirmed with the failed read noted as
            # poll evidence. Reconciles confirm it, or close it
            # past the absence grace if nothing ever lands.
            rec["state"] = "polling"
            rec["launch_unconfirmed_at"] = now()
            rec["last_poll_error"] = _confirm_error
            stamp_collector(rec, rec.get("caller"))
            save_record(rec)
        else:
            # The launch exec itself failed AND the confirmation
            # read is unreadable: nothing is known, and the
            # record stays in the pre-polling "running" state,
            # stamped unconfirmed — polls reconcile it if the
            # job exists, and the sweep's stale-running rule
            # closes it if nothing ever confirms.
            rec["launch_unconfirmed_at"] = now()
            rec["last_poll_error"] = _confirm_error
            stamp_collector(rec, rec.get("caller"))
            save_record(rec)
        # The claim→launch span (branch transport plan; launch.stamp_transport_span).
        stamp_transport_span(rec)
        save_record(rec)
        if detach_flag:
            # E5: launch exactly as the foreground form, write
            # the record, return. usage_before is stamped now —
            # the reconcile that finalizes this run reads it from
            # the record, not from a dead process's locals. The
            # finally below skips the close-out for a detached
            # launch: no finish_job (the registration is the
            # run's liveness evidence), no stop, no capture.
            detached = True
            rec["detached_launch"] = True
            rec["usage_before"] = usage_before
            save_record(rec)
            # The launch result prints BEFORE any advisory
            # pass runs (commission supplement:
            # the overlap crash's worst property was eating the
            # run_id — a lane that loses its launcher before the
            # print cannot even name the run it must adopt).
            # Warnings follow on the record and stderr only —
            # the launch object stays the sole stdout object,
            # exactly as before the check existed, so a consumer
            # parsing stdout whole is untouched.
            print(json.dumps({"run_id": run_id, "session": session, "state": rec["state"]}, indent=2), flush=True)
            name_warnings(rec, session, run_id, job.get("outputs", []))
            return 0
        name_warnings(rec, session, run_id, job.get("outputs", []))
        deadline = time.time() + job.get("timeout", 18000)
        cadence = job.get("checkpoint_pull_seconds", 300)
        # A checkpoint poll that outlives its subprocess timeout
        # is a failed poll, not a dead poller (an
        # uncaught TimeoutExpired killed the poller mid-run and
        # stranded the record at polling while the payload
        # completed). The timeout is env-tunable for the same
        # reason the cadence is a manifest value: tests shrink it.
        poll_timeout = int(os.environ.get("COLAB_RUN_POLL_TIMEOUT_S", "300"))
        state = {}
        while time.time() < deadline:
            time.sleep(cadence)
            # A failed poll — subprocess timeout or unreadable
            # answer — is counted, not fatal (an
            # uncaught TimeoutExpired killed the poller and
            # stranded the record at polling while the payload
            # completed); E11 bounds the count and classifies it.
            state, poll_error = read_reader(session, reader, poll_timeout)
            if state is None:
                if register_poll_failure(rec, session, poll_error, collector=rec.get("caller")) == "failed":
                    print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                    return 1
                continue
            done_units = (state.get("checkpoint") or {}).get("completed_units", 0)
            rec["last_checkpoint_units"] = done_units
            rec["last_evidence_at"] = now()
            stamp_collector(rec, rec.get("caller"))
            rec["poll_failures"] = 0
            save_record(rec)
            if job.get("outputs"):
                pull_outputs(rec, job, session, remote_out, state)
                save_record(rec)
            log = state.get("heartbeat_tail") or []
            # The checkpoint exit_code leg mirrors --poll's: a
            # payload whose checkpoint is its last act while its
            # process lingers has already decided its outcome,
            # and finalize reads that code as authoritative.
            if any("complete" in ln for ln in log) or (job.get("units") and done_units >= job["units"]) or state.get("exit_stamp") is not None or (state.get("checkpoint") or {}).get("exit_code") is not None:
                break
            if not state.get("job_pids") and not state.get("job_log_tail") and state.get("exit_stamp") is None and not state.get("checkpoint") and _launch_age_s(rec) > _absence_grace_s():
                # Total absence past the grace bound: no process,
                # no log, no checkpoint, no stamp — the launch
                # never landed (the confirmation read's one pass
                # can race a slow kernel; a grace of polls cannot).
                mark_terminal(rec, "failed", launch_lost=True, error=f"no job footprint on {session} {_absence_grace_s()}s after launch: the launch never landed; relaunch with --resume {run_id} to retry")
                print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                return 1
            if not state.get("job_pids") and state.get("job_log_tail"):
                # The launched process is gone and its launcher log
                # is all that exists: the job died before producing
                # a checkpoint — shell_job refusing a never-uploaded
                # --script file is the proven case (its
                # one-line refusal sat in this log while the poller
                # polled an empty out dir through two timeouts,
                # ~40 min of apparent progress). A completed job
                # always trips the completion check above in the
                # same poll, so reaching here means death, not
                # completion: fail with the log tail in hand.
                tail = "\n".join(state["job_log_tail"])
                mark_terminal(rec, "failed", error=(f"job exited before completing; remote log tail: {tail}")[-500:])
                print(json.dumps({"run_id": run_id, "state": "failed", "error": rec["error"]}, indent=2))
                return 1
        stamp_collector(rec, rec.get("caller"))
        rc, result = finalize_run(rec, job, session, remote_out, state, usage_before)
        if result.get("state") == "collecting":
            # The payload is done; only the output transfer
            # failed. The finally below tears the session down
            # when this call returns, so the retries live here,
            # on the poll cadence inside a bounded hold: each
            # pass re-reads the session and finalize retries
            # the pull. On expiry one last finalize closes
            # without the hold and names the collection failure
            # on the record — closing is honest there because
            # the teardown ends collection either way.
            hold_deadline = time.time() + int(os.environ.get("COLAB_RUN_COLLECTION_HOLD_S", "900"))
            while result.get("state") == "collecting" and time.time() < hold_deadline:
                time.sleep(cadence)
                state2, _hold_error = read_reader(session, reader, poll_timeout)
                if state2 is not None:
                    state = state2
                stamp_collector(rec, rec.get("caller"))
                rc, result = finalize_run(rec, job, session, remote_out, state, usage_before)
            if result.get("state") == "collecting":
                rc, result = finalize_run(rec, job, session, remote_out, state, usage_before, hold=False)
        print(json.dumps(result, indent=2))
        return rc
    finally:
        # A detached launch returns with the job still running:
        # no finish_job (the registration is the run's liveness
        # evidence until a reconcile closes it out), no stop, no
        # capture — the reconcile owns the close-out.
        if not detached:
            if use_lease:
                lease.finish_job(REPO, run_id)
            else:
                colab("stop", "-s", session, timeout=120)
            mirror("capture")
