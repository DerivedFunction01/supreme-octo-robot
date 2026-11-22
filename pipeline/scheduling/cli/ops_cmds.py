"""The ops commands proper — write, patch, exec: file and
command work performed by the server process over the /ops
endpoint, so it lands even while the write denial is
denying this shell."""
import sys

from cli.ops_client import _ops_caller, _ops_post, _ops_report, _take_flag


def cmd_write(argv):
    caller = _ops_caller(argv)
    _c, argv = _take_flag(argv, "--caller")
    if len(argv) != 1:
        print("usage: sched write <path> [--caller <name>]  (content on stdin)")
        return 2
    req = {"caller": caller, "op": "write", "path": argv[0],
           "content": sys.stdin.read()}
    payload = _ops_post(req, http_timeout=30)
    code = _ops_report("write", payload)
    if code == 0:
        print(f"wrote {payload['path']} ({payload['bytes']} bytes,"
              f" sha256 {payload['sha256'][:12]})")
    return code


def cmd_patch(argv):
    caller = _ops_caller(argv)
    _c, argv = _take_flag(argv, "--caller")
    if len(argv) != 3:
        print("usage: sched patch <path> <old-file> <new-file> [--caller <name>]")
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            old = fh.read()
        with open(argv[2], encoding="utf-8") as fh:
            new = fh.read()
    except OSError as exc:
        print(f"sched patch: cannot read match files: {exc}", file=sys.stderr)
        return 2
    req = {"caller": caller, "op": "patch", "path": argv[0],
           "old": old, "new": new}
    payload = _ops_post(req, http_timeout=30)
    code = _ops_report("patch", payload)
    if code == 0:
        print(f"patched {payload['path']} ({payload['bytes']} bytes,"
              f" sha256 {payload['sha256'][:12]})")
    return code


def cmd_exec(argv):
    # Own flags live before "--"; the tail is the delivered
    # argv and passes verbatim, never flag-scanned.
    sep = argv.index("--") if "--" in argv else -1
    head, cmd = argv[:sep], argv[sep + 1:]
    if sep < 0 or not cmd:
        print("usage: sched exec [--cwd <dir>] [--timeout <secs>]"
              " [--caller <name>] -- <argv...>")
        return 2
    caller = _ops_caller(head)
    _c, head = _take_flag(head, "--caller")
    cwd, head = _take_flag(head, "--cwd")
    timeout_raw, head = _take_flag(head, "--timeout")
    req = {"caller": caller, "op": "exec", "argv": cmd}
    http_timeout = 30
    if cwd:
        req["cwd"] = cwd
    if timeout_raw:
        try:
            req["timeout"] = int(timeout_raw)
        except ValueError:
            print(f"sched exec: --timeout must be an int: {timeout_raw}")
            return 2
        http_timeout = req["timeout"] + 30
    payload = _ops_post(req, http_timeout=http_timeout)
    code = _ops_report("exec", payload)
    if not isinstance(payload, dict) or not payload.get("ok"):
        return code
    sys.stdout.write(payload.get("stdout_tail", ""))
    sys.stdout.flush()
    sys.stderr.write(payload.get("stderr_tail", ""))
    if payload.get("timed_out"):
        print("sched exec: command timed out", file=sys.stderr)
        return 124
    return int(payload.get("exit_code") or 0)
