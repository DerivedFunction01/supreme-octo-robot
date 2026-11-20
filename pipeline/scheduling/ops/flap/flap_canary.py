#!/usr/bin/env python3
"""Flap canary: run the write-mechanism matrix against a scratch root.

The instrument the flap study built (state/flap-probe-study/);
promoted to ops/flap/ so the scripted flap watcher and the agent-side
probe run the identical matrix.

Usage: flap_canary.py <scratch-root>
Prints one JSON object; exit 0 = all core mechanisms writable,
3 = at least one core mechanism denied, 4 = probe inconclusive.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

CORE = ["python_write_new", "python_overwrite", "shell_redirection",
        "git_object_write", "sqlite_row_write"]
CONTENT = "canary-v1\n"
OVERWRITE_SEED = "seed-v0\n"
OVERWRITE_NEW = "overwritten-v1\n"


def verdict(fn):
    try:
        return fn()
    except PermissionError as e:
        return ("denied", "EPERM: %s" % e)
    except OSError as e:
        if e.errno in (1, 13):
            return ("denied", "errno %s: %s" % (e.errno, e))
        return ("error", "OSError %s: %s" % (e.errno, e))
    except Exception as e:  # noqa: BLE001 - study script reports everything
        return ("error", "%s: %s" % (type(e).__name__, e))


def m_python_write_new(root):
    p = os.path.join(root, "write_new.txt")
    if os.path.exists(p):
        os.unlink(p)
    with open(p, "w") as f:
        f.write(CONTENT)
        f.flush()
        os.fsync(f.fileno())
    with open(p) as f:
        got = f.read()
    if got != CONTENT:
        return ("denied", "read-back mismatch: %r" % got)
    return ("ok", "")


def m_python_overwrite(root):
    p = os.path.join(root, "overwrite.txt")
    known = (OVERWRITE_SEED, OVERWRITE_NEW)
    if not (os.path.exists(p) and open(p).read() in known):
        r = subprocess.run(["bash", "-c", "printf 'seed-v0\\n' > \"$1\"",
                            "_", p], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(p) \
                or open(p).read() != OVERWRITE_SEED:
            return ("error", "setup: could not seed overwrite target")
    with open(p, "w") as f:
        f.write(OVERWRITE_NEW)
        f.flush()
        os.fsync(f.fileno())
    got = open(p).read()
    if got != OVERWRITE_NEW:
        return ("denied", "read-back mismatch: %r" % got)
    return ("ok", "")


def m_shell_redirection(root):
    p = os.path.join(root, "shell_redir.txt")
    if os.path.exists(p):
        os.unlink(p)
    r = subprocess.run(["bash", "-c", "printf 'canary-v1\\n' > \"$1\"",
                        "_", p], capture_output=True, text=True)
    if r.returncode != 0:
        return ("denied", "bash exit %s: %s" % (r.returncode,
                                                 r.stderr.strip()[:120]))
    got = open(p).read() if os.path.exists(p) else None
    if got != CONTENT:
        return ("denied", "read-back mismatch: %r" % got)
    return ("ok", "")


def m_git_object_write(root):
    repo = os.path.join(root, "gitrepo")
    if not os.path.isdir(os.path.join(repo, ".git")):
        os.makedirs(repo, exist_ok=True)
        r = subprocess.run(["git", "init", "-q", repo],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return ("denied", "git init failed: %s"
                    % r.stderr.strip()[:120])
    payload = "canary-%d" % time.time_ns()
    r = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"],
                       input=payload, capture_output=True, text=True)
    if r.returncode != 0:
        return ("denied", "hash-object failed: %s"
                % r.stderr.strip()[:120])
    sha = r.stdout.strip()
    r2 = subprocess.run(["git", "-C", repo, "cat-file", "-p", sha],
                        capture_output=True, text=True)
    if r2.returncode != 0 or r2.stdout != payload:
        return ("denied", "cat-file read-back failed")
    return ("ok", sha[:12])


def m_sqlite_row_write(root):
    p = os.path.join(root, "probe-%d.db" % time.time_ns())
    val = "row-%d" % time.time_ns()
    try:
        con = sqlite3.connect(p)
        try:
            mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode != "wal":
                return ("denied", "journal_mode=%r" % mode)
            con.execute("CREATE TABLE t (v TEXT)")
            con.execute("INSERT INTO t VALUES (?)", (val,))
            con.commit()
        finally:
            con.close()
        con = sqlite3.connect(p)
        try:
            got = con.execute("SELECT v FROM t").fetchone()
        finally:
            con.close()
        if not got or got[0] != val:
            return ("denied", "row read-back mismatch: %r" % (got,))
        return ("ok", "")
    except sqlite3.OperationalError as e:
        msg = str(e)
        if "disk I/O" in msg or "readonly" in msg or "unable to open" in msg:
            return ("denied", "sqlite: %s" % msg)
        return ("error", "sqlite: %s" % msg)
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(p + suffix)
            except OSError:
                pass


def m_rename_over(root):
    src = os.path.join(root, "rename_src.txt")
    dst = os.path.join(root, "rename_dst.txt")
    for q in (src, dst):
        if os.path.exists(q):
            os.unlink(q)
    fd = os.open(src, os.O_CREAT | os.O_WRONLY)
    try:
        os.write(fd, CONTENT.encode())
    finally:
        os.close(fd)
    os.rename(src, dst)
    if not os.path.exists(dst):
        return ("error", "target missing after rename")
    return ("ok", "")


def m_unlink(root):
    p = os.path.join(root, "unlink_me.txt")
    if not os.path.exists(p):
        fd = os.open(p, os.O_CREAT | os.O_WRONLY)
        os.close(fd)
    os.unlink(p)
    if os.path.exists(p):
        return ("error", "file still exists after unlink")
    return ("ok", "")


MECHANISMS = [
    ("python_write_new", m_python_write_new),
    ("python_overwrite", m_python_overwrite),
    ("shell_redirection", m_shell_redirection),
    ("git_object_write", m_git_object_write),
    ("sqlite_row_write", m_sqlite_row_write),
    ("rename_over", m_rename_over),
    ("unlink", m_unlink),
]


def main():
    root = sys.argv[1]
    try:
        os.makedirs(root, exist_ok=True)
        os.listdir(root)
    except OSError as e:
        print(json.dumps({"scratch": "unreachable", "detail": str(e)}))
        return 4
    results = {}
    for name, fn in MECHANISMS:
        status, detail = verdict(lambda: fn(root))
        results[name] = {"status": status, "detail": detail}
    core_denied = [n for n in CORE if results[n]["status"] == "denied"]
    core_error = [n for n in CORE if results[n]["status"] == "error"]
    if core_error:
        v, code = "inconclusive", 4
    elif not core_denied:
        v, code = "down", 0
    elif len(core_denied) == len(CORE):
        v, code = "up", 3
    else:
        v, code = "mixed", 3
    print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
                      "mechanisms": results, "core_denied": core_denied,
                      "verdict": v, "exit": code}, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
