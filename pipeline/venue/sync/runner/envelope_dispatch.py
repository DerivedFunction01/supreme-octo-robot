"""The grouped envelope's dispatch form: compose the
declared jobs into ONE launch on the envelope's venue,
under the budget the envelope leaf (envelope.py) divides.

Placement: bin/local-run routes its --envelope form here
with its own seams passed in (the manifest_shape pattern —
this module imports nothing from the package), because the
bin entry stands near the file cap and the composition is
a seam of its own. Every seam is a callable or value the
entry already holds: the manifest loader and preflight
pass, the lease module, the sealed register, the record
machinery, the SSH and warmup seams, the wait form.

The launch: one run record for the envelope (constituents
recorded in declaration order, the union form's recording
generalized from branch tips to jobs), one run dir per job
under the envelope's run dir on the venue (the runs root,
then the envelope run id, then the job name), per-job exit
files, and the envelope's own exit —
written by the launch wrapper from the launcher's exit
code, the first non-zero job exit in order or 0. The
grouped jobs run CONCURRENTLY: the generated launcher
starts every job tree, then waits for all of them. Each
job's root pid is stamped by the launcher (the exec'd
tree's $!) into its run dir's root.pid. A poll of the
envelope run id attaches through the entry's standing poll
form — the envelope record settles when its exit file
lands, which is when its last job settles.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def envelope_launcher(jobs) -> bytes:
    """The generated venue-side launcher for one envelope:
    start every job tree under its stamps, stamp each
    tree's root pid, wait for all, write each job's exit
    file, and exit with the first non-zero job exit in
    envelope order (0 when all are green). Job names are
    declaration-validated path-safe names and every stamp
    value is an integer the leaf computed, so the text is
    interpolated directly."""
    lines = [
        "#!/bin/bash",
        "# Grouped envelope launcher (generated): every job",
        "# tree starts first and all run concurrently at",
        "# their divided shares; the waits then collect the",
        "# exits in envelope order.",
        'cd "$(dirname "$0")"',
        "envelope_code=0",
        "pids=()",
        "names=()",
    ]
    for job in jobs:
        stamps = job["stamps"]
        env = (
            f"GATE_WORKERS={stamps['workers']} "
            f"ENVELOPE_THREADS={stamps['thread_share']} "
            f"ENVELOPE_JOB_INDEX={job['index']} "
            f"ENVELOPE_JOB_COUNT={len(jobs)} "
            f"OMP_THREAD_LIMIT={stamps['pool_cap']} "
            f"OPENBLAS_NUM_THREADS={stamps['pool_cap']} "
            f"MKL_NUM_THREADS={stamps['pool_cap']} "
            f"NUMEXPR_NUM_THREADS={stamps['pool_cap']}"
        )
        lines.append(
            f"( cd {job['name']} && exec env {env} bash run.sh > output.log 2>&1 ) &"
        )
        lines.append(f"echo $! > {job['name']}/root.pid")
        lines.append("pids+=($!)")
        lines.append(f"names+=({job['name']})")
    lines += [
        'for i in "${!pids[@]}"; do',
        '  wait "${pids[$i]}"; code=$?',
        '  echo $code > "${names[$i]}/exit"',
        "  if [ $envelope_code -eq 0 ] && [ $code -ne 0 ]; then envelope_code=$code; fi",
        "done",
        "exit $envelope_code",
    ]
    return ("\n".join(lines) + "\n").encode()


def launch_envelope(rec, jobs, target, ssh, launch_step) -> "str | None":
    """Ship the envelope to the venue and launch it: the
    run dirs, each job's script and uploads into its own
    subdir, the generated launcher, and the marker-guarded
    launch — every step under the entry's warmup discipline
    (launch_step), exactly as the solo launch composes its
    steps. Returns an error string, or None on a confirmed
    launch."""
    base = f"runs/{rec['run_id']}"

    def mkdir() -> "str | None":
        dirs = " ".join(f"~/{base}/{job['name']}" for job in jobs)
        r = ssh(target, f"mkdir -p {dirs}", timeout=90)
        if r.returncode != 0:
            return f"venue mkdir failed: {r.stderr.decode(errors='replace').strip()[-200:]}"
        return None

    def make_upload(remote: str, data: bytes, label: str):
        def step() -> "str | None":
            r = ssh(target, f"cat > {remote}", input_bytes=data, timeout=90)
            if r.returncode != 0:
                return f"{label} upload failed: {r.stderr.decode(errors='replace').strip()[-200:]}"
            return None

        return step

    def launch() -> "str | None":
        cmd = (
            f"cd ~/{base} && if [ ! -f .launched ]; then touch .launched; "
            f"nohup bash -c 'bash envelope.sh > output.log 2>&1; echo $? > exit' "
            ">/dev/null 2>&1 & fi; echo launched"
        )
        r = ssh(target, cmd, timeout=90)
        if r.returncode != 0 or b"launched" not in r.stdout:
            return f"launch failed: {r.stderr.decode(errors='replace').strip()[-200:]}"
        return None

    steps = [mkdir]
    for job in jobs:
        steps.append(
            make_upload(
                f"~/{base}/{job['name']}/run.sh", job["script"], f"script {job['name']}"
            )
        )
        for name, data in job["uploads"]:
            steps.append(
                make_upload(
                    f"~/{base}/{job['name']}/{name}",
                    data,
                    f"upload {job['name']}/{name}",
                )
            )
    steps.append(
        make_upload(f"~/{base}/envelope.sh", envelope_launcher(jobs), "launcher")
    )
    steps.append(launch)
    for step in steps:
        try:
            err, timed_out = launch_step(step)
        except OSError as exc:
            return f"venue unreachable: {exc}"
        if timed_out:
            return (
                "venue warmup: launch timed out on all attempts; "
                "the transport was still warming and the venue was not reached — "
                "the dispatch may be retried"
            )
        if err is not None:
            return err
    return None


def _name_safe(name: str) -> bool:
    return (
        bool(name)
        and name[0].isalnum()
        and all(ch.isalnum() or ch in "._-" for ch in name)
    )


def dispatch(name, flags, seams) -> int:
    """The --envelope dispatch, routed from bin/local-run's
    main with the entry's seams. Exit codes mirror the solo
    dispatch: 2 for a defective declaration or manifest, 1
    for a launch failure or a failed run, 0 complete, 3
    still running at the wait bound."""
    fail = seams["fail"]
    envelope = seams["envelope"]
    jobs_dir = seams["jobs_dir"]
    if not _name_safe(name):
        return fail(f"envelope name {name!r} is not a path-safe name")
    decl_path = jobs_dir / name / "envelope.json"
    if not decl_path.exists():
        return fail(f"no envelope declaration at {decl_path}")
    try:
        spec = json.loads(decl_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return fail(f"envelope declaration at {decl_path} does not parse: {exc}")
    spec_error = envelope.envelope_error(spec)
    if spec_error is not None:
        return fail(f"envelope {name}: {spec_error}")
    shape_id = spec["shape"]
    capacity = envelope.declared_capacity(shape_id)
    fraction = spec.get("fraction", envelope.DEFAULT_FRACTION)
    burst = spec.get("burst_per_worker", envelope.DEFAULT_BURST_PER_WORKER)
    budget = envelope.envelope_budget(capacity["pids"], fraction)
    entries = spec["jobs"]
    divisions = envelope.divide(
        budget,
        capacity["cores"],
        len(entries),
        burst_per_worker=burst,
        worst_cases=[envelope.declared_worst_case(e) for e in entries],
    )
    lease = seams["lease"]
    sealed = seams["sealed"]
    claim_raw = flags.get("caller")
    if claim_raw is None:
        claim_raw = spec.get("caller")
    claim_error = lease.caller_claim_error(
        seams["repo"], flag=claim_raw, env=seams["caller_env"]
    )
    if claim_error:
        return fail(f"envelope {name}: {claim_error}")
    register = sealed.load_register(seams["repo"])
    jobs = []
    constituents = []
    timeout_s = spec.get("timeout_s")
    for index, entry in enumerate(entries):
        job_name = envelope.entry_name(entry)
        manifest_path = jobs_dir / job_name / "job.json"
        if not manifest_path.exists():
            return fail(f"envelope {name}: no job manifest at {manifest_path}")
        try:
            job = seams["load_manifest"](manifest_path)
        except seams["manifest_unreadable"] as exc:
            return fail(f"envelope {name}: job {job_name}: {exc}")
        if job.get("venue") not in (None, "local"):
            return fail(
                f"envelope {name}: job {job_name}: venue {job.get('venue')!r} is not the local venue"
            )
        if sealed.entry_for(register, job_name) is not None:
            return fail(
                f"envelope {name}: job {job_name} is sealed — a sealed job "
                "dispatches from its blob on the solo form, never inside an envelope"
            )
        script_name = job.get("script") or "run.sh"
        script_path = manifest_path.parent / script_name
        field_err = None
        if "script" in job and not isinstance(job.get("script"), str):
            field_err = f"manifest script must be a string, got {job.get('script')!r}"
        preflight = seams["preflight_error"](
            job,
            script_path=script_path,
            uploads_base=seams["repo"],
            claim_error=None,
            shape_error=field_err,
        )
        if preflight:
            return fail(f"envelope {name}: job {job_name}: {preflight}")
        uploads = []
        seen = {script_name}
        for rel in job.get("uploads") or []:
            rel_path = Path(rel)
            base_name = rel_path.name
            if (
                rel_path.is_absolute()
                or ".." in rel_path.parts
                or not base_name
                or base_name in seen
            ):
                return fail(
                    f"envelope {name}: job {job_name}: upload {rel!r} does not stage under a fresh basename inside the venue root"
                )
            seen.add(base_name)
            uploads.append((base_name, (seams["repo"] / rel).read_bytes()))
        stamps = divisions[index]
        jobs.append(
            {
                "name": job_name,
                "index": index,
                "script": script_path.read_bytes(),
                "uploads": uploads,
                "stamps": stamps,
            }
        )
        constituent = {"job": job_name, **stamps}
        worst = envelope.declared_worst_case(entry)
        if worst is not None:
            constituent["per_worker_worst_case"] = worst
        if uploads:
            constituent["uploads"] = [n for n, _d in uploads]
        constituents.append(constituent)
        if timeout_s is None:
            timeout_s = int(job.get("timeout_s") or 18000)
        else:
            timeout_s = max(timeout_s, int(job.get("timeout_s") or 18000))
    caller = lease.resolve_caller(
        seams["repo"], flag=claim_raw, env=seams["caller_env"]
    )
    acquired = lease.acquire_local(seams["repo"], shape_id, caller=caller, hours=None)
    if acquired.get("action") not in ("created", "adopted"):
        return fail(
            f"local lease refused: {acquired.get('reason') or acquired.get('action')}"
        )
    session = acquired["record"]["session"]
    target = seams["record_target"](acquired["record"])
    if target is None:
        return fail(
            "no local venue target resolves for this shape (config/lease.json venue_targets.local)"
        )
    seams["ensure_transport"](target)
    run_id = f"{name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    rec = {
        "run_id": run_id,
        "job": name,
        "envelope": True,
        "shape": shape_id,
        "session": session,
        **(
            {"target": acquired["record"]["target"]}
            if acquired["record"].get("target")
            else {}
        ),
        "caller": caller,
        "venue": "local",
        "state": "starting",
        "started_at": seams["now"](),
        "timeout_s": int(timeout_s),
        "constituents": constituents,
        "envelope_budget": budget,
        "envelope_fraction": fraction,
    }
    seams["save_record"](rec)
    err = launch_envelope(rec, jobs, target, seams["ssh"], seams["launch_step"])
    if err is not None:
        seams["mark_terminal"](rec, "failed", error=err, finished_at=seams["now"]())
        print(json.dumps({"run_id": run_id, "state": "failed", "error": err}, indent=2))
        return 1
    rec.update(state="running")
    seams["save_record"](rec)
    if flags["detach"]:
        print(
            json.dumps(
                {"run_id": run_id, "state": "running", "session": session}, indent=2
            )
        )
        return 0
    return seams["wait"](rec, target, int(timeout_s), int(timeout_s))
