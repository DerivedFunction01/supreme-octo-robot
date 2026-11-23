#!/usr/bin/env python3
"""Run a shell script as a job — the payload is bash, not Python.

The shell program arrives as a heredoc on stdin (or via --script FILE):

    python3 shell_job.py --out DIR <<'EOF'
    ... shell commands ...
    EOF

It is written verbatim to <out>/job.sh and executed with bash as a
real process. This Python file is only the launcher/harness: it gives
shell work the runner's heartbeat contract — <out>/heartbeat.log
streams the script's output and ends with a line containing
"complete"; <out>/checkpoint.json carries completed_units (0 while
running, 1 at the end) plus the shell exit code. The launcher's own
exit code is the shell script's exit code.

Launch it detached (nohup, start_new_session) for long work, the same
pattern as every other job snippet; run it in the foreground for
short work. VM-side only in practice — it runs wherever it is started.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def port_base_for(run_id: str) -> int:
    """A per-run port base in [20000, 40000), aligned to 10:
    deterministic in the run id, so two runs sharing a session
    hold disjoint port ranges with overwhelming probability
    and a payload can key its servers on $SHELL_JOB_PORT_BASE
    instead of a fixed per-mode port — the fixed-port half of
    the twin-execution collision."""
    digest = hashlib.sha256(run_id.encode()).hexdigest()
    return 20000 + (int(digest[:8], 16) % 2000) * 10


def run_id_for(out: Path):
    """The runner's remote out dir is <job>-out-<run_id>
    (per-run by construction); recover the run id from it, or
    None when the name carries none."""
    name = out.name
    if "-out-" not in name:
        return None
    return name.rsplit("-out-", 1)[1] or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--script", help="shell script file (default: read stdin)")
    ap.add_argument("--cwd", default="/content", help="working directory for the script")
    args, payload_args = ap.parse_known_args()

    if args.script:
        script_path = Path(args.script)
        if not script_path.is_file() and script_path.is_absolute():
            # Session-root resolution. The runner addresses
            # session files as /content/<name>; the session root
            # is /content on a real VM and the working dir under
            # the fake CLI (the same dual-world seam as the cwd
            # below — the discriminator is where this process
            # runs, not whether a /content happens to exist on
            # the local filesystem). Uploads land in the run's
            # own directory, runs/<run_id>/ (runner Step 5): the
            # run's copy of a same-named file wins over the
            # shared root slot, whose contents are another
            # launch's history. The run id is recovered from
            # --out, per-run by construction. A genuinely
            # missing file still refuses exactly as before.
            root = Path("/content") if Path.cwd() == Path("/content") else Path.cwd()
            rid = run_id_for(Path(args.out))
            alts = []
            if rid:
                alts.append(root / "runs" / rid / script_path.name)
            if script_path.parts[:2] == ("/", "content"):
                alts.append(root.joinpath(*script_path.parts[2:]))
            if Path.cwd() != Path("/content"):
                alts.append(Path(script_path.name))
            for alt in alts:
                if alt.is_file():
                    script_path = alt
                    break
        if not script_path.is_file():
            print(f"shell_job: --script file not found: {args.script} "
                  "(upload it to the VM first, e.g. /content/env_build.sh)", file=sys.stderr)
            return 2
        script = script_path.read_text()
    else:
        if sys.stdin.isatty():
            print("shell_job: no --script and stdin is a TTY (pipe a heredoc)", file=sys.stderr)
            return 2
        script = sys.stdin.read()
    if not script.strip():
        print("shell_job: empty shell script", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    job = out / "job.sh"
    job.write_text(script)
    ckpt = out / "checkpoint.json"
    ckpt.write_text(json.dumps({"completed_units": 0, "state": "running"}))

    cwd = Path(args.cwd)
    if Path.cwd() != Path("/content") and (cwd == Path("/content") or not cwd.is_dir()):
        # Same dual-world seam as the script path above, keyed the
        # same way: under the fake CLI the session root is the
        # working dir, not /content — a stray local /content
        # directory must not lure the job into running there while
        # its files live in the session root.
        cwd = Path.cwd()

    with open(out / "heartbeat.log", "a") as log:
        log.write(f"start shell_job cwd={cwd} t={time.time():.1f}\n")
        log.flush()
        env = dict(os.environ)
        env["SHELL_JOB_OUT"] = str(out)
        # Per-run session state (the twin-execution
        # cure): the payload keys its work dir and ports on
        # these instead of fixed per-mode names, so two runs
        # sharing a session never share state. SHELL_JOB_WORK
        # is the per-run scratch root (the out dir itself).
        env["SHELL_JOB_WORK"] = str(out)
        run_id = run_id_for(out)
        if run_id:
            env["SHELL_JOB_RUN_ID"] = run_id
            env["SHELL_JOB_PORT_BASE"] = str(port_base_for(run_id))
            # The run's upload directory (runner Step 5): a
            # payload reads its sibling uploads from here
            # instead of the shared /content/<name> slots,
            # whose contents are another launch's history.
            # Exported only when the directory exists — a job
            # with no uploads has none.
            root = Path("/content") if Path.cwd() == Path("/content") else Path.cwd()
            uploads = root / "runs" / run_id
            if uploads.is_dir():
                env["SHELL_JOB_UPLOADS"] = str(uploads)
        r = subprocess.run(["bash", str(job), *payload_args], cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env)
        log.write(f"complete exit_code={r.returncode} t={time.time():.1f}\n")
        log.flush()
    ckpt.write_text(json.dumps({"completed_units": 1, "exit_code": r.returncode}))
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
