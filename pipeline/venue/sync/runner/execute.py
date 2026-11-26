#!/usr/bin/env python3
"""The launch window: session creation on the lease-disabled
fallback, the run's uploads, the seed and branch windows,
the confirmed detached launch, the foreground poll loop and
finalize — under the close-out finally (lease finish /
fallback stop / mirror capture). Takes the front end's ctx
dict (dispatch.launch): job and job_name, the claimed run_id
and its record, the acquired session and shape, the seed /
branch / transport state, usage_before, extra_args, and the
detach / lease flags.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .foundation import REPO, colab, lease, mirror, now
from .launch import build_launch_stamp, drive_branch_window, ensure_run_dir, rewrite_upload_args, run_upload_dir, stamp_transport_span, upload_one, upload_seed_files
from .pull import finalize_run, pull_outputs
from .reader import _absence_grace_s, _launch_age_s, read_reader, register_poll_failure, write_reader
from .records import mark_terminal, save_record, stamp_collector
from .warnings import name_warnings


def execute(ctx: dict) -> int:
    job_name = ctx["job_name"]
    job = ctx["job"]
    run_id = ctx["run_id"]
    rec = ctx["rec"]
    session = ctx["session"]
    shape = ctx["shape"]
    seed_ctx = ctx["seed_ctx"]
    branch_ctx = ctx["branch_ctx"]
    transport = ctx["transport"]
    usage_before = ctx["usage_before"]
    extra_args = ctx["extra_args"]
    detach_flag = ctx["detach_flag"]
    use_lease = ctx["use_lease"]
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
        # The spawn's pid is the job tree's root on the
        # session (nohup execs the stamp wrapper under the
        # same pid, in its own session): the launcher prints
        # it as root_pid= for the record stamp below
        # (venue-state plan, step 2). A handle with no pid
        # to print — the fake venue's synchronous Popen —
        # prints an empty value and stamps nothing.
        launch = (
            f"import subprocess; _root = subprocess.Popen(['nohup','python3','-c',{stamp!r}],"
            f" stdout=open('{remote_out}.log','w'), stderr=subprocess.STDOUT, start_new_session=True); "
            f"print('root_pid=' + str(getattr(_root, 'pid', '') or ''))"
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
        if launch_error is None:
            # The root_pid the launcher printed (above) rides
            # the record from here: every save below carries
            # it. An exec that failed or timed out read no
            # pid back, and an empty printed value stamps
            # nothing — root_pid is present only when read.
            for _line in lr.stdout.splitlines():
                _line = _line.strip()
                if _line.startswith("root_pid="):
                    try:
                        rec["root_pid"] = int(_line.partition("=")[2])
                    except ValueError:
                        pass
                    break
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
