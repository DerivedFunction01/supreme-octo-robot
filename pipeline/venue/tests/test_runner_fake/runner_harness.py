"""Shared harness for the runner fake leaves (the split of the
former tests/test_runner_fake.py, consolidation Lane A).

Owns the fixtures import (the CLI environment builder lives in
tests/fixtures/), the deterministic control hash, the CLI
driver helpers, the wrapper factories (logging, flaky,
upload-fail), the bare-job installer several leaves share, and
the in-process fake venue (FakeVenue + runner_inprocess) the
determinism-cured leaves drive. Subject helpers used by a
single leaf live in that leaf.
"""

import hashlib
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import traceback
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FAKE = REPO / "tests" / "fixtures" / "fake_colab.py"

sys.path.insert(0, str(REPO / "tests" / "fixtures"))
import module_loader  # noqa: E402
from env_fixtures import runner_env  # noqa: E402, F401


def control_sha(seed: str, unit: int) -> str:
    payload = hashlib.sha256(f"{seed}:{unit}".encode()).hexdigest().encode() * 64
    return hashlib.sha256(payload).hexdigest()


def run_bin(env):
    return Path(env["TEST_REPO_ROOT"]) / "bin" / "colab-run"


def runs_dir(env):
    return Path(env["TEST_REPO_ROOT"]) / "results" / "runs"


def run_verb(env, *argv):
    return subprocess.run([sys.executable, str(run_bin(env)), *argv], capture_output=True, text=True, env=env, timeout=300)


def outbox_events(env):
    path = Path(env["COLAB_RUNNER_VAR"]) / "ui-outbox.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def terminal_events(env, run_id):
    return [e for e in outbox_events(env) if e.get("kind") == "run-terminal" and e.get("detail", {}).get("run_id") == run_id]


def logging_wrapper(tmp_path):
    """A COLAB_BIN wrapper that journals every invocation's argv
    (one JSON list per line) and delegates to the real fake."""
    wrapper = tmp_path / "wrapper_colab.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "state = Path(os.environ['FAKE_COLAB_STATE'])\n"
        "state.mkdir(parents=True, exist_ok=True)\n"
        "with (state / 'cli-calls.log').open('a') as fh:\n"
        "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(subprocess.run([sys.executable, os.environ['FAKE_COLAB_REAL'], *sys.argv[1:]]).returncode)\n"
    )
    wrapper.chmod(0o755)
    return wrapper


def cli_calls(env):
    log = Path(env["FAKE_COLAB_STATE"]) / "cli-calls.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def _fire_smoke(env):
    r = subprocess.run([sys.executable, str(run_bin(env)), "smoke"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def _write_run_record(runs, run_id, session, state="running"):
    p = runs / f"{run_id}.json"
    p.write_text(json.dumps({"run_id": run_id, "job": "smoke", "session": session, "state": state, "started_at": "2000-01-01T00:00:00+00:00"}))
    return p


def flaky_wrapper(tmp_path):
    """A COLAB_BIN wrapper with a test-controlled failure budget,
    steered by a JSON control file in the fake state dir:
    {"fail_reads": N} makes the next N reader execs exit 1;
    {"sessions_mode": "auth"} makes `sessions` answer with the
    CLI's auth prompt (the lease core's definitive-unknown read).
    Everything else delegates to the real fake."""
    wrapper = tmp_path / "flaky_colab.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "state = Path(os.environ['FAKE_COLAB_STATE'])\n"
        "ctl_path = state / 'flaky.json'\n"
        "ctl = json.loads(ctl_path.read_text()) if ctl_path.exists() else {}\n"
        "args = sys.argv[1:]\n"
        "if 'sessions' in args and ctl.get('sessions_mode') == 'auth':\n"
        "    print('Enter the authorization code:')\n"
        "    sys.exit(0)\n"
        "if 'exec' in args and any('read-' in a for a in args):\n"
        "    left = int(ctl.get('fail_reads', 0))\n"
        "    if left > 0:\n"
        "        ctl['fail_reads'] = left - 1\n"
        "        ctl_path.write_text(json.dumps(ctl))\n"
        "        print('flaky wrapper: reader refused', file=sys.stderr)\n"
        "        sys.exit(1)\n"
        "sys.exit(subprocess.run([sys.executable, os.environ['FAKE_COLAB_REAL'], *args]).returncode)\n"
    )
    wrapper.chmod(0o755)
    return wrapper


def flaky_env(tmp_path, ctl=None):
    env = runner_env(tmp_path)
    env.update(COLAB_BIN=str(flaky_wrapper(tmp_path)), FAKE_COLAB_REAL=str(FAKE))
    if ctl is not None:
        state = Path(env["FAKE_COLAB_STATE"])
        state.mkdir(parents=True, exist_ok=True)
        (state / "flaky.json").write_text(json.dumps(ctl))
    return env


def set_flaky_ctl(env, ctl):
    state = Path(env["FAKE_COLAB_STATE"])
    state.mkdir(parents=True, exist_ok=True)
    (state / "flaky.json").write_text(json.dumps(ctl))


def _detach_smoke(env):
    r = subprocess.run([sys.executable, str(run_bin(env)), "smoke", "--detach"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def install_bare_job(env, name, exit_code, uploads=None):
    """Replace the fixture repo's jobs symlink with a real dir
    holding one checkpoint-less job: its payload writes its
    declared output and exits with the given code, speaking
    none of the runner's completion protocol (no checkpoint,
    no 'complete' line) — the shape the remainder
    gate jobs had when green runs recorded failed."""
    root = Path(env["TEST_REPO_ROOT"])
    jobs_dir = root / "adapters" / "colab" / "jobs"
    if jobs_dir.is_symlink():
        jobs_dir.unlink()
    job_dir = jobs_dir / name
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "payload.py").write_text(
        "import argparse, sys\n"
        "from pathlib import Path\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--out', required=True)\n"
        "a = ap.parse_args()\n"
        "out = Path(a.out)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'result.txt').write_text('bare-result\\n')\n"
        f"sys.exit({exit_code})\n"
    )
    manifest = {"name": name, "script": f"adapters/colab/jobs/{name}/payload.py", "args": [], "outputs": ["result.txt"], "shape": "cpu-highram", "checkpoint_pull_seconds": 1, "timeout": 180}
    if uploads:
        manifest["uploads"] = uploads
    (job_dir / "job.json").write_text(json.dumps(manifest))
    return job_dir


def upload_sleep_wrapper(tmp_path):
    """A COLAB_BIN wrapper that sleeps before delegating an
    upload of one named file (ctl {"sleep_upload_named":
    "name", "sleep_seconds": N} in the fake state dir) — a
    dead channel's shape: the upload neither lands nor fails,
    it simply never answers."""
    wrapper = tmp_path / "uploadsleep_colab.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "state = Path(os.environ['FAKE_COLAB_STATE'])\n"
        "ctl_path = state / 'uploadsleep.json'\n"
        "ctl = json.loads(ctl_path.read_text()) if ctl_path.exists() else {}\n"
        "args = sys.argv[1:]\n"
        "if 'upload' in args and ctl.get('sleep_upload_named') and any(ctl['sleep_upload_named'] in a for a in args):\n"
        "    time.sleep(float(ctl.get('sleep_seconds', 60)))\n"
        "sys.exit(subprocess.run([sys.executable, os.environ['FAKE_COLAB_REAL'], *args]).returncode)\n"
    )
    wrapper.chmod(0o755)
    return wrapper


# --- The in-process fake venue (the determinism cure) -----------------
# Two leaves' end-to-end fires were live-process/timing-shaped:
# the payload ran as a detached host process while a poller
# raced it on a wall clock, and the reader payload's pgrep read
# the HOST process table (box-global under xdist), so under
# full-suite contention the verdicts moved. The owner's
# determinism ruling prohibits that shape: no
# live-server or timing tests — a test pins against fakes.
# FakeVenue is the funnel seam faked: the same verbs and output
# shapes as tests/fixtures/fake_colab.py, answered in-process.
# Its one defining fiction is the launch: a detached launch
# runs to completion INSIDE the launch exec (the payload's
# Popen is synchronous), so by the time any reader looks, the
# job's whole footprint — outputs, checkpoint, exit stamp —
# already exists, exactly as a finished venue job's does. And
# the process table a reader payload consults is the venue's
# own: no job process is ever alive at a read, and no foreign
# host process can impersonate one.

FAKE_NEW_HELP = """
 Usage: colab new [OPTIONS]

 Create a new session

  Options:
  --session   -s      <str>  Session name
  --tpu               <str>  TPU accelerator variant. Supported: v5e1, v6e1.
  --gpu               <str>  GPU accelerator variant. Supported: T4, L4, G4,
                             H100, A100.
  --high-mem                 Request a high-RAM machine shape (CPU, T4, A100,
                             etc.). Requires a paid entitlement.
                             Ignored for accelerators that only offer a single
                             shape (L4, v5e1).
  --help      -h             Show this message and exit
"""


def _parse_cli(argv):
    """fake_colab.parse, minus the --auth strip (the funnel's
    callers pass verb-first argv; FakeVenue sits where the
    funnel sits, not where the binary sits)."""
    args = list(argv)
    if args[:1] == ["--auth"]:
        args = args[2:]
    cmd, opts, pos = args[0], {}, []
    i = 1
    while i < len(args):
        a = args[i]
        if a in ("-s", "--timeout", "-f", "--gpu", "--tpu"):
            opts[a] = args[i + 1]
            i += 2
        elif a == "--":
            pos.extend(args[i + 1 :])
            break
        elif a.startswith("-"):
            i += 1
        else:
            pos.append(a)
            i += 1
    return cmd, opts, pos


def _venue_subprocess(root):
    """The subprocess module as a venue payload sees it: real,
    except the process table is the venue's own (a pgrep finds
    nothing — a synchronously-launched job is finished, never
    alive at a read) and a detached spawn (Popen) runs to
    completion before it returns, which is what makes the
    venue's launch deterministic."""
    real = subprocess
    shim = types.ModuleType("subprocess")
    for name in ("PIPE", "STDOUT", "DEVNULL", "CompletedProcess", "TimeoutExpired", "CalledProcessError", "SubprocessError"):
        setattr(shim, name, getattr(real, name))

    def run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd] if isinstance(cmd, (list, tuple)) else None
        if argv and argv[0] == "pgrep":
            return real.CompletedProcess(argv, 1, "", "")
        return real.run(cmd, *args, **kwargs)

    class _SyncPopen:
        """A Popen that has already finished: the launched
        command ran to completion inside the launch."""

        def __init__(self, completed):
            self._completed = completed
            self.returncode = completed.returncode
            self.stdout = completed.stdout
            self.stderr = completed.stderr

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

        def communicate(self, input=None, timeout=None):
            return self.stdout, self.stderr

        def kill(self):
            pass

        def terminate(self):
            pass

    def popen(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        if argv and argv[0] == "nohup":
            argv = argv[1:]
        if argv and argv[0] in ("python3", "python"):
            argv[0] = sys.executable
        kwargs.pop("start_new_session", None)
        kwargs.pop("preexec_fn", None)
        kwargs.pop("restore_signals", None)
        kwargs.setdefault("cwd", str(root))
        return _SyncPopen(real.run(argv, *args, **kwargs))

    shim.run = run
    shim.Popen = popen
    return shim


class FakeVenue:
    """An in-process fake of the colab CLI, callable with the
    funnel's own signature (colab(*args, timeout=...) ->
    CompletedProcess). State mirrors fake_colab.py's: one
    sandbox dir per session under the state root, playing the
    session's /content."""

    def __init__(self, state_dir):
        self.state = Path(state_dir)
        self.calls = []

    def session_dir(self, name):
        return self.state / "sessions" / name

    def live_names(self):
        base = self.state / "sessions"
        if not base.exists():
            return []
        return sorted(d.name for d in base.iterdir() if (d / "ACTIVE").exists())

    def _write_binding(self, name, argv):
        # The real CLI records a local binding for a session it
        # creates, with an endpoint whose class names the shape
        # it was handed — fake_colab.py's form, including its
        # guard: the binding is written only into a test home,
        # recognised by the dummy token planted beside it.
        cls = os.environ.get("FAKE_COLAB_FORCE_CLASS") or ("hm" if "--high-mem" in argv else "s")
        binding_path = Path.home() / ".config" / "colab-cli" / "sessions.json"
        try:
            token_text = (binding_path.parent / "token.json").read_text()
        except OSError:
            token_text = ""
        if "fake" not in token_text:
            return
        try:
            binding = json.loads(binding_path.read_text()) if binding_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            binding = {}
        if isinstance(binding, dict):
            binding[name] = {"endpoint": f"https://m-{cls}-fake.prod.r.colab.dev"}
            binding_path.parent.mkdir(parents=True, exist_ok=True)
            binding_path.write_text(json.dumps(binding))

    def _exec(self, session, file_arg):
        """Run one exec'd payload inside the session sandbox,
        in-process: the payload's prints are its stdout, its
        SystemExit is its return code, and the subprocess
        module it imports is the venue's (see _venue_subprocess)."""
        root = self.session_dir(session)
        root.mkdir(parents=True, exist_ok=True)
        local_f = root / Path(file_arg).name
        if not local_f.exists():
            shutil.copy2(file_arg, local_f)
        source = local_f.read_text()
        out_buf, err_buf = io.StringIO(), io.StringIO()
        real_subprocess_module = sys.modules["subprocess"]
        old_cwd, old_argv = os.getcwd(), sys.argv
        rc = 0
        sys.modules["subprocess"] = _venue_subprocess(root)
        try:
            os.chdir(root)
            sys.argv = [str(local_f)]
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                exec(compile(source, str(local_f), "exec"), {"__name__": "__main__", "__file__": str(local_f)})
        except SystemExit as exc:
            code = exc.code
            rc = code if isinstance(code, int) else (0 if code is None else 1)
        except BaseException:  # noqa: BLE001 — a payload crash is exit 1 + its traceback, as under the CLI
            err_buf.write(traceback.format_exc())
            rc = 1
        finally:
            sys.modules["subprocess"] = real_subprocess_module
            os.chdir(old_cwd)
            sys.argv = old_argv
        out = out_buf.getvalue()
        if local_f.name == "misplaced-probe.py":
            # Production shape, as in fake_colab.py: the real
            # CLI's exec stdout opens with its update-check
            # preamble.
            out = "\n[colab] A new version of Colab CLI is available: 0.8.0 (current: 0.7.5)\n[colab] Run 'colab update' to update.\n\n" + out
        return rc, out, err_buf.getvalue()

    def __call__(self, *args, timeout=None):
        argv = [str(a) for a in args]
        self.calls.append(tuple(argv))
        cmd, opts, pos = _parse_cli(argv)
        name = opts.get("-s", "default")
        root = self.session_dir(name)
        rc, out, err = 0, "", ""
        if cmd == "version":
            out = "google-colab-cli 0.7.5 (fake)\n"
        elif cmd == "new":
            if "--help" in argv:
                out = FAKE_NEW_HELP
            else:
                root.mkdir(parents=True, exist_ok=True)
                (root / "ACTIVE").write_text("1")
                self._write_binding(name, argv)
                out = f"session {name} created (fake)\n"
        elif cmd == "stop":
            (root / "ACTIVE").unlink(missing_ok=True)
            out = f"session {name} stopped (fake)\n"
        elif cmd == "sessions":
            out = json.dumps(self.live_names()) + "\n"
        elif cmd == "status":
            out = f"session {name}: {'active' if (root / 'ACTIVE').exists() else 'stopped'} (fake)\n"
        elif cmd == "usage":
            out = "balance: 500 CU (fake)\n"
        elif cmd == "install":
            out = f"installed (fake): {' '.join(pos)}\n"
        elif cmd == "upload":
            src = Path(pos[0])
            remote = pos[1] if len(pos) > 1 else src.name
            dest = root / (remote[len("/content/") :] if remote.startswith("/content/") else remote)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            out = f"uploaded {src.name} (fake)\n"
        elif cmd == "download":
            remote = pos[0]
            if remote.startswith("/content/"):
                remote = remote[len("/content/") :]
            src_f, dest = root / remote, Path(pos[1])
            if not src_f.exists():
                err = f"fake download: no such remote file {pos[0]}\n"
                rc = 1
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_f, dest)
                out = f"downloaded {pos[0]} (fake)\n"
        elif cmd in ("exec", "run"):
            f = opts.get("-f") or (pos[0] if pos else None)
            if not f:
                err = "fake exec: no file\n"
                rc = 1
            else:
                rc, out, err = self._exec(name, f)
        else:
            err = f"fake colab: unimplemented {cmd}\n"
            rc = 1
        return subprocess.CompletedProcess(argv, rc, out, err)


_INPROC_SEQ = itertools.count()


def runner_inprocess(tmp_path, monkeypatch):
    """The in-process runner fake: the fixture environment
    applied to THIS process, a fresh sync/runner package loaded
    from the fixture repo the environment names (the same
    symlinked-sync fixture the subprocess form boots), and its
    funnel bound to a FakeVenue. Returns (env, venue, package).
    The transient-mirror subprocess is stood down (its restore
    / capture is orthogonal to every verdict these leaves pin,
    and it is the one subprocess the close-out would otherwise
    still pay)."""
    env = runner_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    venue = FakeVenue(env["FAKE_COLAB_STATE"])
    root = Path(env["TEST_REPO_ROOT"])
    # A previous load's registrations would serve this load the
    # FIRST fixture's modules: bin/_load is imported by name,
    # and the lease package registers itself under its bare
    # name on every load. Both are re-bound by the fresh load.
    for stale in ("_load", "lease"):
        sys.modules.pop(stale, None)
    name = f"runner_inproc_{next(_INPROC_SEQ)}"
    pkg = module_loader.load_module(name, root / "sync" / "runner" / "__init__.py", register=True, search_locations=[str(root / "sync" / "runner")])
    main_mod = sys.modules[f"{name}.main"]
    dispatch_mod = sys.modules[f"{name}.dispatch"]
    execute_mod = sys.modules[f"{name}.execute"]
    for leaf in (pkg.foundation, pkg.reader, pkg.sweep, pkg.launch, pkg.pull, main_mod, dispatch_mod, execute_mod):
        leaf.colab = venue
    main_mod.mirror = lambda op: None
    dispatch_mod.mirror = lambda op: None
    execute_mod.mirror = lambda op: None
    pkg.verbs.mirror = lambda op: None
    return env, venue, pkg


def upload_fail_wrapper(tmp_path):
    """A COLAB_BIN wrapper that fails uploads of one named file
    (ctl {"fail_upload_named": "name"} in the fake state dir),
    delegating everything else to the real fake — flaky_wrapper's
    shape, aimed at the upload verb."""
    wrapper = tmp_path / "uploadfail_colab.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "state = Path(os.environ['FAKE_COLAB_STATE'])\n"
        "ctl_path = state / 'uploadfail.json'\n"
        "ctl = json.loads(ctl_path.read_text()) if ctl_path.exists() else {}\n"
        "args = sys.argv[1:]\n"
        "if 'upload' in args and ctl.get('fail_upload_named') and any(ctl['fail_upload_named'] in a for a in args):\n"
        "    print('uploadfail wrapper: upload refused', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "sys.exit(subprocess.run([sys.executable, os.environ['FAKE_COLAB_REAL'], *args]).returncode)\n"
    )
    wrapper.chmod(0o755)
    return wrapper
