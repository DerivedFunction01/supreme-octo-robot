"""Execution of one scripted entry (spec Step 3 / EC-5–EC-8).

Runs the entry's argv in its own subprocess group, captures
stdout/stderr keeping only the tail up to the configured cap (the
process is never killed for output alone, EC-6), kills the whole
group on timeout (EC-5), and classifies the run: ok, failure (exit
outside ok_exit_codes, or a fail_patterns hit on an ok exit, EC-7),
timeout, or spawn_error (EC-8).
"""
import os
import signal
import subprocess
import threading

from .. import registry as registry_mod


class TailBuffer:
    def __init__(self, cap):
        self.cap = cap
        self._buf = bytearray()
        self._lock = threading.Lock()

    def feed(self, chunk):
        with self._lock:
            self._buf.extend(chunk)
            overflow = len(self._buf) - self.cap
            if overflow > 0:
                del self._buf[:overflow]

    def text(self):
        with self._lock:
            return bytes(self._buf).decode("utf-8", errors="replace")


def _pump(stream, tail):
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            tail.feed(chunk)
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


class RunResult:
    def __init__(self, job_id, due):
        self.job_id = job_id
        self.due = due
        self.status = "ok"          # ok | failure | timeout | spawn_error
        self.exit_code = None
        self.matched_pattern = None
        self.stdout_tail = ""
        self.stderr_tail = ""
        self.error = None

    @property
    def output(self):
        return (self.stdout_tail + "\n" + self.stderr_tail).strip()

    def detail(self):
        return {
            "exit_code": self.exit_code,
            "matched_pattern": self.matched_pattern,
            "error": self.error,
            "stdout_tail": self.stdout_tail[-2000:],
            "stderr_tail": self.stderr_tail[-2000:],
        }


def _build_env(entry):
    env = dict(os.environ)
    for name in entry.get("run", {}).get("env_names") or []:
        if name in os.environ:
            env[name] = os.environ[name]
    # The fire-time config seam (contract 09): the entry
    # record is re-read on every tick's rescan, so the block
    # as it stands at fire time is what resolves here — a
    # config saved since the last fire governs this one,
    # with no restart. The mapping is declared per knob on
    # the block itself (registry.config_env); an entry with
    # no block, or no knob declaring a variable, fires with
    # exactly the environment above.
    env.update(registry_mod.config_env(entry))
    return env


def run_entry(entry, due, capture_cap):
    result = RunResult(entry.id, due)
    run = entry.get("run", {})
    argv = run.get("argv")
    if run.get("shell"):
        cmd = ["bash", "-c", argv] if isinstance(argv, str) else argv
    else:
        cmd = list(argv)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=run.get("cwd") or None,
            env=_build_env(entry),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        result.status = "spawn_error"
        result.error = str(exc)
        return result
    out_tail, err_tail = TailBuffer(capture_cap), TailBuffer(capture_cap)
    threads = [
        threading.Thread(target=_pump, args=(proc.stdout, out_tail), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, err_tail), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        proc.wait(timeout=entry.timeout_secs)
        result.exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        result.status = "timeout"
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=5)
        result.exit_code = proc.returncode
    for thread in threads:
        thread.join(timeout=5)
    result.stdout_tail = out_tail.text()
    result.stderr_tail = err_tail.text()
    if result.status == "timeout":
        return result
    report = entry.report
    if result.exit_code not in report["ok_exit_codes"]:
        result.status = "failure"
        return result
    combined = result.stdout_tail + "\n" + result.stderr_tail
    for pattern in report["fail_patterns"]:
        if pattern in combined:
            result.status = "failure"
            result.matched_pattern = pattern
            return result
    result.status = "ok"
    return result
