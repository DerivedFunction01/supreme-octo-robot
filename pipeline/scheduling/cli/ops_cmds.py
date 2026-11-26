"""The ops commands proper — write, patch, exec: file and
command work performed by the server process over the /ops
endpoint, so it lands even while the write denial is
denying this shell. Each verb's surface is a unified-argv
declaration (pipeline/platform/argv.py): both value forms
parse identically, an unknown flag or a flag in last
position is a usage refusal, never a traceback."""
import sys

from cli.ops_client import (
    CALLER_FLAG, _ops_post, _ops_report, caller_of, parse_decl)

WRITE_DECL = {
    "name": "sched write",
    "summary": "write the file at <path> (content on stdin), "
               "performed by the server process",
    "flags": {"caller": CALLER_FLAG},
    "positionals": [{"name": "path", "required": True}],
}

PATCH_DECL = {
    "name": "sched patch",
    "summary": "replace the exact text in <old-file> with the "
               "text in <new-file> at <path> (exactly one match "
               "required), performed by the server process",
    "flags": {"caller": CALLER_FLAG},
    "positionals": [{"name": "path", "required": True},
                    {"name": "old-file", "required": True},
                    {"name": "new-file", "required": True}],
}

# The exec head: the client's own flags, living before the
# "--" separator. The tail after it is the delivered argv
# and passes verbatim, never flag-scanned.
EXEC_DECL = {
    "name": "sched exec",
    "summary": "run a command in the server's process "
               "(after '--': the argv)",
    "flags": {"caller": CALLER_FLAG,
              "cwd": {"takes_value": True,
                      "help": "working directory for the command"},
              "timeout": {"takes_value": True,
                          "help": "seconds before the command "
                                  "times out"}},
}


def cmd_write(argv):
    result, code = parse_decl(WRITE_DECL, argv)
    if result is None:
        return code
    req = {"caller": caller_of(result), "op": "write",
           "path": result["positionals"]["path"],
           "content": sys.stdin.read()}
    payload = _ops_post(req, http_timeout=30)
    code = _ops_report("write", payload)
    if code == 0:
        print(f"wrote {payload['path']} ({payload['bytes']} bytes,"
              f" sha256 {payload['sha256'][:12]})")
    return code


def cmd_patch(argv):
    result, code = parse_decl(PATCH_DECL, argv)
    if result is None:
        return code
    pos = result["positionals"]
    try:
        with open(pos["old-file"], encoding="utf-8") as fh:
            old = fh.read()
        with open(pos["new-file"], encoding="utf-8") as fh:
            new = fh.read()
    except OSError as exc:
        print(f"sched patch: cannot read match files: {exc}", file=sys.stderr)
        return 2
    req = {"caller": caller_of(result), "op": "patch",
           "path": pos["path"], "old": old, "new": new}
    payload = _ops_post(req, http_timeout=30)
    code = _ops_report("patch", payload)
    if code == 0:
        print(f"patched {payload['path']} ({payload['bytes']} bytes,"
              f" sha256 {payload['sha256'][:12]})")
    return code


def cmd_exec(argv):
    # Own flags live before "--"; the tail is the delivered
    # argv and passes verbatim, never flag-scanned.
    sep = -1
    for i, tok in enumerate(argv):
        if tok == "--":
            sep = i
            break
    head, cmd = argv[:sep], argv[sep + 1:]
    if sep < 0 or not cmd:
        print("usage: sched exec [--cwd <dir>] [--timeout <secs>]"
              " [--caller <name>] -- <argv...>")
        return 2
    result, code = parse_decl(EXEC_DECL, head)
    if result is None:
        return code
    flags = result["flags"]
    req = {"caller": caller_of(result), "op": "exec", "argv": cmd}
    http_timeout = 30
    if flags.get("cwd"):
        req["cwd"] = flags["cwd"]
    if flags.get("timeout"):
        try:
            req["timeout"] = int(flags["timeout"])
        except ValueError:
            print(f"sched exec: --timeout must be an int: {flags['timeout']}")
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
