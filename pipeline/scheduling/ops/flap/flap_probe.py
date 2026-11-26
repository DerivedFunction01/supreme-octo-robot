#!/usr/bin/env python3
"""Write-denial flap probe: can this process class write, by every
mechanism real work depends on?

The sandbox write-denial flap is wave-like at minute scale and
discriminates by write mechanism: Python open/write is denied
first and most reliably, shell redirection fails in stronger
waves, a SQLite WAL open dies with a disk I/O error, git
loose-object writes fail, and rename-over / unlink have succeeded
in every probe to date. A single-mechanism canary therefore
cannot answer for the others — this probe runs the full matrix
against its own scratch tree and reports per-mechanism verdicts.

Matrix (each step read-back verified, so a truncate-without-
content reads as denied, never as success):
  python_write_new   open('w') on a new file + fsync
  python_overwrite   open('w') on an existing file + fsync
  shell_redirection  bash printf > file
  git_object_write   git hash-object -w in a scratch repo
  sqlite_row_write   scratch DB: WAL mode, insert a row, commit,
                     read it back (the shape that fails on the
                     scheduler ledger from a denied class)
  rename_over        rename staging over target (create, write,
                     and rename reported separately in detail)
  unlink             create + unlink + verify gone

Core mechanisms (the ones runner records, commits, and ledgers
depend on): the first five. Exit code: 0 = no core mechanism
denied (verdict "down"); 3 = at least one core mechanism denied
(verdict "mixed", or "up" when every core mechanism is denied);
4 = inconclusive (a core mechanism errored without a denial —
e.g. git missing — or the scratch tree is unreachable).

State: the probe maintains state/flap-state.json (its own member
state, recorded in the job entry's state_paths): the current
verdict, since when, the last sample time, and the latest
per-mechanism map. The write is staged + rename-over; if the
staging write is itself denied, the recorded state simply ages
and readers judge staleness by the sample time — the state file
can never be torn by the flap it describes. On a verdict change
the probe prints a TRANSITION line before its JSON sample, which
is what the job entry's report rule turns into a ping.

Hosting matters: this probe only tells the truth when the
process running it sits in the denied class (an agent-class
process). Spawned from a never-denied class (the scheduler
server's children, the service plane) it reports "down" forever;
Step 1 of the plan records the per-class evidence.

Stdlib only; no imports from server/ (ops scripts stand alone).
Paths derive from this file's location.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

REPO = paths.REPO_ROOT

CORE = (
    "python_write_new",
    "python_overwrite",
    "shell_redirection",
    "git_object_write",
    "sqlite_row_write",
)
CONTENT = "flap-probe-v1\n"
SEED = "flap-probe-seed\n"
OVERWRITTEN = "flap-probe-overwritten\n"


def classify_os_error(exc):
    if isinstance(exc, PermissionError) or getattr(exc, "errno", None) in (1, 13):
        return ("denied", "EPERM: %s" % exc)
    return ("error", "OSError %s: %s" % (getattr(exc, "errno", "?"), exc))


class RealOps:
    """The live write primitives. Tests inject a fake with the
    same surface so verdict logic never touches a real disk."""

    def write_new(self, path, content):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())

    def overwrite(self, path, content):
        self.write_new(path, content)

    def read(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    def exists(self, path):
        return os.path.exists(path)

    def shell_write(self, path, content):
        script = "printf '%s' \"$2\" > \"$1\""
        proc = subprocess.run(
            ["bash", "-c", script, "_", path, content],
            capture_output=True, text=True, timeout=30,
        )
        return proc.returncode, proc.stderr.strip()

    def git_write(self, repo, payload):
        if not os.path.isdir(os.path.join(repo, ".git")):
            os.makedirs(repo, exist_ok=True)
            proc = subprocess.run(["git", "init", "-q", repo],
                                  capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return ("denied" if "Operation not permitted" in proc.stderr
                        else "error",
                        "git init: %s" % proc.stderr.strip()[:160])
        proc = subprocess.run(["git", "-C", repo, "hash-object", "-w",
                               "--stdin"],
                              input=payload, capture_output=True, text=True,
                              timeout=30)
        if proc.returncode != 0:
            return ("denied" if "Operation not permitted" in proc.stderr
                    else "error",
                    "hash-object: %s" % proc.stderr.strip()[:160])
        sha = proc.stdout.strip()
        back = subprocess.run(["git", "-C", repo, "cat-file", "-p", sha],
                              capture_output=True, text=True, timeout=30)
        if back.returncode != 0 or back.stdout != payload:
            return ("denied", "cat-file read-back failed")
        return ("ok", sha[:12])

    def sqlite_write(self, path, value):
        con = sqlite3.connect(path)
        try:
            mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode != "wal":
                return ("denied", "journal_mode=%r" % mode)
            con.execute("CREATE TABLE t (v TEXT)")
            con.execute("INSERT INTO t VALUES (?)", (value,))
            con.commit()
        finally:
            con.close()
        con = sqlite3.connect(path)
        try:
            row = con.execute("SELECT v FROM t").fetchone()
        finally:
            con.close()
        if not row or row[0] != value:
            return ("denied", "row read-back mismatch: %r" % (row,))
        return ("ok", "")

    def create(self, path, content):
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
        try:
            os.write(fd, content.encode("utf-8"))
        finally:
            os.close(fd)

    def rename(self, src, dst):
        os.rename(src, dst)

    def unlink(self, path):
        os.unlink(path)


def _guarded(fn):
    """Run one mechanism; map exceptions onto (status, detail)."""
    try:
        return fn()
    except (PermissionError, OSError) as exc:
        return classify_os_error(exc)
    except sqlite3.OperationalError as exc:
        msg = str(exc)
        if "disk I/O" in msg or "readonly" in msg or "unable to open" in msg:
            return ("denied", "sqlite: %s" % msg)
        return ("error", "sqlite: %s" % msg)
    except FileNotFoundError as exc:
        return ("error", "missing binary: %s" % exc)
    except Exception as exc:  # noqa: BLE001 - a probe reports, never crashes
        return ("error", "%s: %s" % (type(exc).__name__, exc))


def m_python_write_new(root, ops):
    path = os.path.join(root, "write_new.txt")
    if ops.exists(path):
        ops.unlink(path)
    ops.write_new(path, CONTENT)
    if ops.read(path) != CONTENT:
        return ("denied", "read-back mismatch")
    return ("ok", "")


def m_python_overwrite(root, ops):
    path = os.path.join(root, "overwrite.txt")
    if ops.read(path) not in (SEED, OVERWRITTEN):
        seeded = False
        create_error = None
        try:
            ops.create(path, SEED)
            seeded = ops.read(path) == SEED
            if not seeded:
                return ("denied", "setup: seed read-back mismatch")
        except (PermissionError, OSError) as exc:
            create_error = exc
        if not seeded:
            rc, err = ops.shell_write(path, SEED)
            if rc == 0 and ops.read(path) == SEED:
                seeded = True
            elif create_error is not None:
                status, detail = classify_os_error(create_error)
                if status == "denied" or "Operation not permitted" in err:
                    return ("denied", "setup denied: %s" % detail)
                return ("error", "setup: %s" % detail)
            else:
                return ("error", "setup: could not seed target (%s)"
                        % err[:80])
    ops.overwrite(path, OVERWRITTEN)
    if ops.read(path) != OVERWRITTEN:
        return ("denied", "read-back mismatch")
    return ("ok", "")


def m_shell_redirection(root, ops):
    path = os.path.join(root, "shell_redir.txt")
    if ops.exists(path):
        ops.unlink(path)
    rc, err = ops.shell_write(path, CONTENT)
    if rc != 0:
        return ("denied", "bash exit %s: %s" % (rc, err[:120]))
    if ops.read(path) != CONTENT:
        return ("denied", "read-back mismatch")
    return ("ok", "")


def m_git_object_write(root, ops):
    repo = os.path.join(root, "gitrepo")
    return ops.git_write(repo, "flap-probe-%d" % time.time_ns())


def m_sqlite_row_write(root, ops):
    path = os.path.join(root, "probe-%d.db" % time.time_ns())
    try:
        return ops.sqlite_write(path, "row-%d" % time.time_ns())
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                ops.unlink(path + suffix)
            except OSError:
                pass


def m_rename_over(root, ops):
    src = os.path.join(root, "rename_src.txt")
    dst = os.path.join(root, "rename_dst.txt")
    for path in (src, dst):
        if ops.exists(path):
            ops.unlink(path)
    steps = []
    try:
        ops.create(src, CONTENT)
        steps.append("create ok")
    except (PermissionError, OSError) as exc:
        status, detail = classify_os_error(exc)
        return (status, "at create: %s" % detail)
    ops.rename(src, dst)
    steps.append("rename ok")
    if not ops.exists(dst):
        return ("error", "target missing after rename")
    return ("ok", "; ".join(steps))


def m_unlink(root, ops):
    path = os.path.join(root, "unlink_me.txt")
    if not ops.exists(path):
        ops.create(path, CONTENT)
    ops.unlink(path)
    if ops.exists(path):
        return ("error", "file still exists after unlink")
    return ("ok", "")


MECHANISMS = (
    ("python_write_new", m_python_write_new),
    ("python_overwrite", m_python_overwrite),
    ("shell_redirection", m_shell_redirection),
    ("git_object_write", m_git_object_write),
    ("sqlite_row_write", m_sqlite_row_write),
    ("rename_over", m_rename_over),
    ("unlink", m_unlink),
)


def run_matrix(root, ops):
    results = {}
    for name, fn in MECHANISMS:
        results[name] = _guarded(lambda: fn(root, ops))
    return {
        name: {"status": status, "detail": detail}
        for name, (status, detail) in results.items()
    }


def compute_verdict(results):
    """(verdict, exit_code) from a per-mechanism results map."""
    core = [results[name]["status"] for name in CORE]
    if any(status == "error" for status in core):
        return ("inconclusive", 4)
    denied = sum(1 for status in core if status == "denied")
    if denied == 0:
        return ("down", 0)
    if denied == len(CORE):
        return ("up", 3)
    return ("mixed", 3)


def load_state(path, ops):
    raw = ops.read(path)
    if raw is None:
        return None
    try:
        state = json.loads(raw)
    except ValueError:
        return None
    return state if isinstance(state, dict) else None


def build_state(previous, sample):
    verdict = sample["verdict"]
    if previous and previous.get("verdict") == verdict:
        since = previous.get("since", sample["at"])
    else:
        since = sample["at"]
    return {
        "verdict": verdict,
        "since": since,
        "last_sample_at": sample["at"],
        "mechanisms": sample["mechanisms"],
    }


def write_state(path, state, ops):
    """Staged write + rename-over; False when the flap ate it."""
    tmp = path + ".tmp"
    try:
        ops.write_new(tmp, json.dumps(state, indent=1) + "\n")
        ops.rename(tmp, path)
    except (PermissionError, OSError):
        return False
    return True


def sweep(root, ops, now):
    """Bounded residue control: drop day-old scratch files (the
    scratch git repo keeps its own tiny objects; they are swept
    by age inside .git/objects as well)."""
    day = 86400
    try:
        names = os.listdir(root)
    except OSError:
        return
    for name in names:
        path = os.path.join(root, name)
        try:
            if os.path.isfile(path) and now - os.path.getmtime(path) > day:
                ops.unlink(path)
        except OSError:
            pass
    objects = os.path.join(root, "gitrepo", ".git", "objects")
    try:
        for sub in os.listdir(objects):
            subdir = os.path.join(objects, sub)
            if not os.path.isdir(subdir) or len(sub) != 2:
                continue
            for name in os.listdir(subdir):
                path = os.path.join(subdir, name)
                try:
                    if now - os.path.getmtime(path) > 7 * day:
                        ops.unlink(path)
                except OSError:
                    pass
    except OSError:
        pass


DECL = {
    "name": "flap_probe",
    "summary": "The write-denial flap probe: per-mechanism "
               "write trials against a scratch tree, verdict "
               "recorded to the state file.",
    "flags": {
        "root": {"takes_value": True,
                 "default": os.path.join(paths.STATE_DIR, "flap-probe"),
                 "help": "scratch tree (default: state/flap-probe)"},
        "state": {"takes_value": True,
                  "default": os.path.join(paths.STATE_DIR,
                                          "flap-state.json"),
                  "help": "state file (default: state/flap-state.json)"},
    },
}


class _Args:
    """The parsed surface in attribute form (root, state)."""


def main(argv=None):
    result, code = paths.parse_argv(
        DECL, sys.argv[1:] if argv is None else argv)
    if result is None:
        return code
    args = _Args()
    args.root = result["flags"]["root"]
    args.state = result["flags"]["state"]
    ops = RealOps()
    try:
        os.makedirs(args.root, exist_ok=True)
        os.listdir(args.root)
    except OSError as exc:
        print(json.dumps({"verdict": "inconclusive",
                          "detail": "scratch unreachable: %s" % exc}))
        return 4
    now = time.time()
    sweep(args.root, ops, now)
    results = run_matrix(args.root, ops)
    verdict, exit_code = compute_verdict(results)
    sample = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "verdict": verdict,
        "exit": exit_code,
        "mechanisms": results,
        "core_denied": [n for n in CORE if results[n]["status"] == "denied"],
    }
    previous = load_state(args.state, ops)
    state = build_state(previous, sample)
    sample["state_written"] = write_state(args.state, state, ops)
    if previous and previous.get("verdict") != verdict:
        print("TRANSITION %s -> %s at %s (core denied: %s)"
              % (previous.get("verdict"), verdict, sample["at"],
                 ", ".join(sample["core_denied"]) or "none"))
    print(json.dumps(sample))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
