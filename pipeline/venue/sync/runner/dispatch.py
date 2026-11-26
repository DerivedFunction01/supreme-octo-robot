#!/usr/bin/env python3
"""The launch front end: flag and claim resolution, the
daemonize form, manifest and shape settlement, the
run-record claim (resume / adopt / first save), seed and
transport setup, and lease acquire — everything before the
launch window (execute.execute), which it hands a ctx dict.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from .claims import ManifestUnreadable, adopt, attach_verdict, load_manifest, option_like_refusal, spawn_daemon, stamp_takeover
from .execute import execute
from .foundation import JOBS, REPO, RUNS, TOKEN, colab, lease, mirror, now, repo_registry
from .launch import build_seed_ctx, orphan_notes, transport_setup
from .manifest_shape import parse_transport, pin_resolution_error, preflight_error, script_field_error
from .pull import normalize_manifest_outputs
from .records import claim_first_save, load_run_record, save_record
from .replace import acquire_session, record_pin


def launch(args: list[str]) -> int:
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
    # Pre-dispatch validation (wall-clock plan, step 2): the
    # one pass, settled at load before any session work —
    # the field shapes (uploads / args entries that are not
    # plain strings refuse loudly, naming the field and the
    # entry; the shapes have no tolerance semantics, and
    # discovering that mid-launch cost a consumer a crashed
    # run), the transport declaration, the script field, the
    # shape's resolvability (named in the manifest or the
    # config's default — the catalog check below still
    # settles membership, through the CLI), the declared
    # files' presence, the caller claim's registration, and
    # the branch pin's resolution against the source repo.
    # A defect refuses named, in seconds, with no run record
    # written; nothing below this point discovers a manifest
    # defect holding a session. Outputs normalize after the
    # pass (mapped entries there are tolerated; no verdict
    # reads them).
    claim_raw = caller_flag if caller_flag is not None else job.get("caller")
    field_err = script_field_error(job)
    if field_err is None and not (job.get("shape") or lease.default_shape(REPO)):
        field_err = "manifest names no shape and config/lease.json names no default_shape"
    script = job.get("script")
    preflight = preflight_error(
        job,
        script_path=(REPO / script) if isinstance(script, str) and script else None,
        uploads_base=REPO,
        claim_error=lease.caller_claim_error(REPO, flag=claim_raw, env=os.environ.get("COLAB_CALLER")),
        shape_error=field_err,
        pin_error=pin_resolution_error(parse_transport(job), repo=REPO, repo_registry=repo_registry),
    )
    if preflight:
        print(f"colab-run: job {job_name}: {preflight}", file=sys.stderr)
        return 2
    normalize_manifest_outputs(job)
    # Caller claim: flag over the manifest's caller key over
    # $COLAB_CALLER; its registration settled in the pass
    # above, before anything starts.
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
    ctx = {
        "job_name": job_name,
        "job": job,
        "run_id": run_id,
        "rec": rec,
        "session": session,
        "shape": shape,
        "seed_ctx": seed_ctx,
        "branch_ctx": branch_ctx,
        "transport": transport,
        "usage_before": usage_before,
        "extra_args": extra_args,
        "detach_flag": detach_flag,
        "use_lease": use_lease,
    }
    return execute(ctx)
