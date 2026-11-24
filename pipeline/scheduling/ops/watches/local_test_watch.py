#!/usr/bin/env python3
"""Local execution watcher: deterministic detection of code
running on this machine's local CPUs.

The venue rule: while the high-RAM compute fleet is live,
NO checks or code run locally — the fleet is paid capacity
and local runs are both slower and a discipline leak (owner
ruling, tightening the original watcher). The
watcher samples running processes each cycle (argv, cwd,
pid/ppid via /proc — reads only) and works in two modes:

- Normal mode (no fleet session live): the original
  matcher — a test-runner process whose cwd sits inside
  the workspace flags on sight, with the narrow drafting
  pre-check exemption (one test file plus a name filter;
  pytest <= 5 named node ids from one file, or one file
  plus -k). check.py and package-test runs always flag.
- Strict mode (at least one colab-liveness entry stands
  in the registry — a live fleet session): the exemption
  is SUSPENDED, and the trigger broadens to any local
  check/code execution from a workspace repo — test
  runners and gates, dev/backend servers, and experiment
  scripts (a Python/Node/shell interpreter running a
  script file). The attention CLI's status transport
  (pipeline/attention/cli.py post status / post item)
  never flags either: it is the prescribed status-posting
  surface every lane drives — supervision machinery, not
  a check or code execution (the watch flagged a lane's
  status posts as local execution; the exemption is keyed
  on the resolved script identity
  plus the transport verb pair, so the CLI's other verbs
  classify normally). Managed infrastructure never flags:
  automation surfaces matched by resolved script identity
  — a real file under any workspace repo's ops/ or bin/,
  or a repo's named service surface (watchdog, healthcheck, autorepair, linkprobe, install-unit, deploy) script (the
  scripted legs, this watcher, and the other repos'
  surfaces the scheduler's legs invoke, by job argv or by
  a relative invocation from the repo root) — and the
  deployment's service patterns (untracked routes file:
  the long-running servers, the fleet machinery), matched
  against the argv as invoked and as resolved, are
  excluded. Ancestry is NOT the discriminator: agent work
  routed through the server's
  ops channel runs as server children too, and must
  still flag.

Warnings fire on FIRST SIGHTING: a new episode prints its
warning line in the same cycle, naming the owning thread
for the repo (untracked routes file) — no waiting on
downstream classification. When a route and a connector
token are configured, the warning is also sent directly
to the owning thread via the harness connector
(envelope-deduped per episode), and a copy is sent to
the main destination the routes file declares under its
`main` key. Every first sighting (both modes) also
raises a DEFECT item on the attention surface and opens
an entry in the disposition record — the enforcement
half lives in local_test_defects.py: the item names the
programme, the process, and the venue state at flag
time, and it clears only by a disposition recorded
through this watcher's `disposition` verb (reason,
actor, stamp in the record), never by an ack or by the
episode ending. Before any of that, a first sighting is
consulted against the scheduler ledger (local_test_ledger.py):
a process covered by a kind-'op' ledger entry — a scheduler-
server child executing through the ops route — is recorded
as ops-route on the cycle line and never warned; an
unreadable ledger leaves the warning standing. A reappearing episode whose signature
carries a closed, reasoned disposition is the same
explained process: it raises nothing and prints one
line saying so. A failed or unconfigured send never
fails the cycle — the printed line is the record, with
the routing outcome for EACH destination on it (owning
thread, main, defect item), so a silent drop is visible
on the line itself.

Episode discipline: state/local-test-watch.json holds the
active episode signatures (cwd + argv). A finding prints
once per episode per signature; repeat sightings of a
continuing episode stay silent; an episode closes when
its signature is absent from a sample, so a later
reappearance reports as a new episode. No state file:
current matches report as new episodes (a lost state
file must not swallow a live violation). The load average
rides along as context and never gates a finding.

Exit codes: 0 = sampled (silent or findings printed);
3 = /proc could not be listed at all (loud, by design).
Stdlib only; paths derive from this file's location.
Tests inject fixture process lists; production reads /proc.
"""
import hashlib
import json
import os
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

_timestamps_spec = _importlib_util.spec_from_file_location(
    "ops_timestamps",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "timestamps.py"),
                       os.path.join(_here, "timestamps.py"))
         if os.path.isfile(_p)))
timestamps = _importlib_util.module_from_spec(_timestamps_spec)
_timestamps_spec.loader.exec_module(timestamps)

_defects_spec = _importlib_util.spec_from_file_location(
    "local_test_defects",
    os.path.join(_here, "local_test_defects.py"))
defects = _importlib_util.module_from_spec(_defects_spec)
_defects_spec.loader.exec_module(defects)

_ledger_spec = _importlib_util.spec_from_file_location(
    "local_test_ledger",
    os.path.join(_here, "local_test_ledger.py"))
ledger = _importlib_util.module_from_spec(_ledger_spec)
_ledger_spec.loader.exec_module(ledger)

_episodes_spec = _importlib_util.spec_from_file_location(
    "local_test_episodes",
    os.path.join(_here, "local_test_episodes.py"))
episodes_mod = _importlib_util.module_from_spec(_episodes_spec)
_episodes_spec.loader.exec_module(episodes_mod)

REPO = paths.REPO_ROOT
# The harness connector client lives with the bridge cluster
# (ops/bridge/connector_client.py), not beside this watcher.
BRIDGE_DIR = paths.BRIDGE_DIR
WORKSPACE = paths.WORKSPACE_ROOT
STATE = os.environ.get(
    "LOCAL_TEST_WATCH_STATE",
    os.path.join(paths.STATE_DIR, "local-test-watch.json"))
ROUTES = os.environ.get(
    "LOCAL_TEST_WATCH_ROUTES",
    os.path.join(paths.STATE_DIR, "local-test-watch-routes.json"))
DISPOSITIONS = os.environ.get(
    "LOCAL_TEST_WATCH_DISPOSITIONS",
    os.path.join(paths.STATE_DIR,
                 "local-test-watch-dispositions.json"))
TOKEN_FILE = os.environ.get(
    "LOCAL_TEST_WATCH_TOKEN",
    os.path.join(paths.STATE_DIR, "connector",
                 "local-test-watch.token"))
JOBS_DIR = os.environ.get(
    "LOCAL_TEST_WATCH_JOBS", paths.JOBS_DIR)
PROC_ROOT = os.environ.get("LOCAL_TEST_WATCH_PROC", "/proc")

RUNNER_BASENAMES = {
    "vitest": "vitest", "vitest.mjs": "vitest",
    "jest": "jest", "jest.js": "jest",
    "playwright": "playwright",
    "pytest": "pytest", "py.test": "pytest",
}
NAME_FILTER_FLAGS = ("-t", "--testNamePattern", "-g", "--grep", "-k")
VALUE_FLAGS = {
    "-t", "--testNamePattern", "-g", "--grep", "-k", "-m",
    "--pool", "--config", "-c", "--project", "--shard",
    "--workers", "--worker", "--reporter", "--timeout",
    "--dir", "--output", "--update", "-u", "--seed",
}
MAX_NAMED_CASES = 5

SERVER_BASENAMES = {
    "uvicorn": "uvicorn", "gunicorn": "gunicorn",
    "flask": "flask", "streamlit": "streamlit",
    "waitress-serve": "waitress",
}
SERVER_SCRIPT_NAMES = {"run.py", "server.py", "app.py",
                       "main.py", "serve.py"}
INTERPRETERS = {"python3", "python", "node", "bash", "sh"}


now = timestamps.zstamp_now


def basename(token):
    return token.rsplit("/", 1)[-1]


def detect_runner(argv):
    """(runner, index of the runner token) or None."""
    for i, token in enumerate(argv):
        base = basename(token)
        if base in RUNNER_BASENAMES:
            return RUNNER_BASENAMES[base], i
        if base == "check.py" and (i == 0 or basename(argv[0]) in (
                "python3", "python", "bash", "sh")):
            return "check.py", i
        if base in ("python3", "python") and token != argv[-1]:
            nxt = argv[i + 1:i + 3]
            if nxt == ["-m", "pytest"]:
                return "pytest", i + 2
        if base in ("npm", "pnpm", "yarn") and i + 1 < len(argv):
            if argv[i + 1] == "test":
                return "package-test", i
            if argv[i + 1] == "run" and i + 2 < len(argv) \
                    and argv[i + 2].startswith("test"):
                return "package-test", i
    return None


def positionals(argv, start):
    """Non-flag tokens after index start, skipping the values
    of known value-taking flags."""
    out = []
    skip_next = False
    for token in argv[start + 1:]:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            if token in VALUE_FLAGS and "=" not in token:
                skip_next = True
            continue
        out.append(token)
    return out


def is_test_file(token):
    return ".test." in token or ".spec." in token \
        or token.endswith("_test.py") or "/test_" in token \
        or basename(token).startswith("test_")


def narrow_precheck(runner, argv, idx):
    """The mechanical exemption: one test file plus a name
    filter, or pytest's named-cases shape. Nothing else."""
    has_filter = any(t in NAME_FILTER_FLAGS or
                     t.split("=")[0] in NAME_FILTER_FLAGS
                     for t in argv[idx + 1:])
    pos = positionals(argv, idx)
    if runner in ("vitest", "playwright") and pos \
            and pos[0] in ("run", "test"):
        pos = pos[1:]
    if runner in ("vitest", "jest", "playwright"):
        return has_filter and len(pos) == 1 and is_test_file(pos[0])
    if runner == "pytest":
        if pos and all("::" in p for p in pos):
            files = {p.split("::")[0] for p in pos}
            return len(pos) <= MAX_NAMED_CASES and len(files) == 1
        return has_filter and len(pos) == 1 and pos[0].endswith(".py")
    return False


def locate(argv, cwd, workspace):
    """(effective cwd, derived?) — the process's cwd when
    readable; otherwise, for a process whose cwd does not
    cross the mount boundary into the server's context
    (agent-sandbox processes: cmdline readable, cwd link
    empty), the location implied by the first absolute
    workspace path in argv (usually the script being run).
    None when neither source locates the process."""
    if cwd:
        return cwd, False
    for token in argv:
        if token == workspace or token.startswith(
                workspace + os.sep):
            return os.path.dirname(token), True
    return None, False


def classify(argv, cwd, workspace):
    """Normal mode: a finding dict, or None (no match,
    exempt, or the process does not run inside the
    workspace)."""
    if not argv:
        return None
    cwd, derived = locate(argv, cwd, workspace)
    if cwd is None:
        return None
    if cwd != workspace and not cwd.startswith(workspace + os.sep):
        return None
    found = detect_runner(argv)
    if found is None:
        return None
    runner, idx = found
    if runner != "check.py" and runner != "package-test" \
            and narrow_precheck(runner, argv, idx):
        return None
    return {"runner": runner, "kind": "test",
            "cwd": cwd, "argv": list(argv), "derived": derived}


def interpreter_script(argv):
    """(interpreter index, script token) when argv runs a
    script file through an interpreter, else None."""
    for i, token in enumerate(argv):
        if basename(token) not in INTERPRETERS:
            continue
        if i + 1 >= len(argv):
            return None
        nxt = argv[i + 1]
        if nxt.startswith("-"):
            return None
        if nxt.endswith((".py", ".js", ".mjs", ".cjs", ".sh")):
            return i, nxt
        return None
    return None


def detect_server(argv):
    """A dev/backend server label, or None."""
    for i, token in enumerate(argv):
        base = basename(token)
        if base in SERVER_BASENAMES:
            return SERVER_BASENAMES[base]
        if base in ("npm", "pnpm", "yarn") and i + 2 < len(argv) \
                and argv[i + 1] == "run" \
                and argv[i + 2] in ("dev", "serve", "start"):
            return "package-dev"
        if base in ("python3", "python") \
                and argv[i + 1:i + 3] == ["-m", "http.server"]:
            return "http.server"
    found = interpreter_script(argv)
    if found is not None:
        _i, script = found
        if basename(script) in SERVER_SCRIPT_NAMES:
            return basename(script)
    return None


def detect_script(argv):
    """An experiment-script label, or None."""
    found = interpreter_script(argv)
    if found is None:
        return None
    _i, script = found
    return "script:" + basename(script)


def classify_strict(argv, cwd, workspace, service_patterns=()):
    """Strict mode (fleet live): any local check/code
    execution from a workspace repo, exemption suspended.
    Service-pattern argv never flags."""
    if not argv:
        return None
    cwd, derived = locate(argv, cwd, workspace)
    if cwd is None:
        return None
    if cwd != workspace and not cwd.startswith(workspace + os.sep):
        return None
    joined = " ".join(argv)
    # Service patterns match the argv as invoked AND as
    # resolved: a relative invocation from the repo root
    # (bash sync/make_snapshot_bundle.sh from the
    # colab-runner cwd — the runner's own seeding mechanic)
    # carries no repo segment in its raw argv, so the
    # pattern colab-runner/sync/ only matches the resolved
    # path (a pattern for the absolute shape alone misses
    # the relative one and fires on it).
    haystacks = [joined]
    for token in _surface_scripts(argv):
        path = token
        if not os.path.isabs(path) and cwd:
            path = os.path.join(cwd, path)
        haystacks.append(os.path.normpath(path))
    if any(pat in hay for pat in service_patterns
           for hay in haystacks):
        return None
    if is_infrastructure(argv, cwd):
        return None
    if is_attention_transport(argv, cwd):
        return None
    found = detect_runner(argv)
    if found is not None:
        runner, _idx = found
        return {"runner": runner, "kind": "test",
                "cwd": cwd, "argv": list(argv), "derived": derived}
    server = detect_server(argv)
    if server is not None:
        return {"runner": server, "kind": "server",
                "cwd": cwd, "argv": list(argv), "derived": derived}
    script = detect_script(argv)
    if script is not None:
        return {"runner": script, "kind": "script",
                "cwd": cwd, "argv": list(argv), "derived": derived}
    return None


def signature(finding):
    raw = finding["cwd"] + "\0" + "\0".join(finding["argv"])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def sample_processes(proc_root):
    """(argv, cwd, pid, ppid) per readable process."""
    out = []
    for name in os.listdir(proc_root):
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, name, "cmdline"),
                      "rb") as fh:
                argv = [p.decode("utf-8", "replace")
                        for p in fh.read().split(b"\0") if p]
            try:
                cwd = os.readlink(os.path.join(proc_root, name, "cwd"))
            except OSError:
                cwd = None
            if not cwd:
                # A sandbox process's cwd link reads empty
                # from outside its mount namespace; keep the
                # process — classify locates it from argv.
                cwd = None
            ppid = None
            with open(os.path.join(proc_root, name, "stat"),
                      "rb") as fh:
                raw = fh.read().decode("utf-8", "replace")
            rest = raw[raw.rindex(")") + 2:].split()
            if len(rest) > 1:
                ppid = int(rest[1])
        except (OSError, ValueError):
            continue
        if argv:
            out.append((argv, cwd, int(name), ppid))
    return out


def _surface_scripts(argv):
    """The script tokens argv executes: argv[0] itself
    (direct execution) plus an interpreter's script
    argument."""
    out = []
    if argv:
        out.append(argv[0])
    found = interpreter_script(argv)
    if found is not None:
        out.append(found[1])
    return out


def _is_infra_path(path):
    """Resolved script identity -> automation surface, for
    any workspace repo: a real file under an ops/ or bin/
    directory anywhere in the repo's tree (depth-independent:
    a repo nested in a larger tree — the mega repo's
    pipeline/scheduling — carries its surface deeper than a
    standalone repo does), or a repo's named service surface (watchdog, healthcheck, autorepair, linkprobe, install-unit, deploy) script
    wherever it lives in that repo (server/healthcheck.py
    is the standing specimen). The scheduler's legs run
    other repos' ops and health surfaces as machinery —
    workbench-viewer/ops/doctor.sh, colab-runner/ops/
    mirror_transient.py, workbench-viewer/server/
    healthcheck.py are standing specimens of surfaces that
    would otherwise flag as task scripts; the cross-repo
    case is covered."""
    if not os.path.isfile(path):
        return False
    rel = os.path.relpath(path, WORKSPACE)
    if rel.startswith(".." + os.sep):
        return False
    parts = rel.split(os.sep)
    if any(part in ("ops", "bin") for part in parts[:-1]):
        return True
    stem = os.path.splitext(os.path.basename(path))[0]
    return len(parts) >= 2 and stem in (
        "watchdog", "healthcheck", "autorepair", "linkprobe",
        "install-unit", "deploy")


def is_infrastructure(argv, cwd=None):
    """The workspace's own automation surface: any argv
    running a script under a workspace repo's ops/ or bin/,
    or a repo's named service surface (watchdog, healthcheck, autorepair, linkprobe, install-unit, deploy) — matched by
    RESOLVED script identity, so a relative invocation from
    the repo root (an agent running a leg by hand, this
    watcher included) is the same surface as the absolute
    job argv. Agent work never lives there; agent work
    routed through the server's ops channel keeps its own
    argv and still flags."""
    joined = " ".join(argv)
    if (REPO + "/ops/") in joined or (REPO + "/bin/") in joined:
        return True
    for token in _surface_scripts(argv):
        path = token
        if not os.path.isabs(path):
            if not cwd:
                continue
            path = os.path.join(cwd, path)
        if _is_infra_path(os.path.normpath(path)):
            return True
    return False


def is_attention_transport(argv, cwd=None):
    """The attention CLI's status transport: the
    prescribed status-posting surface every lane drives —
    pipeline/attention/cli.py post status / post item.
    Supervision machinery, not a check or code execution;
    never flags. Matched on the script's resolved identity
    (the attention package's cli.py) plus the transport
    verb pair, so the CLI's other verbs and any other
    package's cli.py classify normally."""
    found = interpreter_script(argv)
    if found is not None:
        idx, script = found
        verb_at = idx + 2
    elif argv and basename(argv[0]) == "cli.py":
        script = argv[0]
        verb_at = 1
    else:
        return False
    path = script
    if not os.path.isabs(path) and cwd:
        path = os.path.join(cwd, path)
    parts = os.path.normpath(path).split(os.sep)
    if parts[-3:] != ["pipeline", "attention", "cli.py"]:
        return False
    return argv[verb_at:verb_at + 2] in (["post", "status"],
                                         ["post", "item"])


def sessions_live(jobs_dir):
    """Live fleet sessions = colab-liveness entries standing
    in the registry (the lease core renders one per live
    session and removes it at lease end)."""
    try:
        return sum(1 for name in os.listdir(jobs_dir)
                   if name.startswith("colab-liveness-")
                   and name.endswith(".yaml"))
    except OSError:
        return 0


def load_routes():
    try:
        with open(ROUTES, encoding="utf-8") as fh:
            data = json.load(fh)
        return {"threads": data.get("threads") or {},
                "service_patterns":
                    data.get("service_patterns") or [],
                "main": data.get("main") or None}
    except (OSError, ValueError):
        return {"threads": {}, "service_patterns": [],
                "main": None}


def route_for(cwd, workspace, routes):
    """The owning thread for a finding's repo root (the
    first path segment under the workspace)."""
    rel = os.path.relpath(cwd, workspace)
    root = os.path.join(workspace, rel.split(os.sep)[0])
    return routes.get("threads", {}).get(root)


def loadavg(proc_root):
    try:
        with open(os.path.join(proc_root, "loadavg"),
                  encoding="utf-8") as fh:
            parts = fh.read().split()
        return " ".join(parts[:3])
    except OSError:
        return "unknown"


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("episodes") or {}
    except (OSError, ValueError):
        return {}


def save_state(episodes):
    paths.save_json(STATE, {"episodes": episodes})


def default_sender():
    """A connector sender for first-sighting warnings, or
    None when no token is configured (print-only mode). The
    token is read from its file at call time and never
    printed. A short poll: queueing the bridged send IS the
    routing — fulfillment rides the bridge drain, the
    printed line is the immediate record."""
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            token = fh.read().strip()
    except OSError:
        return None
    if not token:
        return None
    sys.path.insert(0, BRIDGE_DIR)
    import connector_client

    client = connector_client.Client(token=token, poll_seconds=5)

    def send(chat_id, text, envelope_id):
        client.call("chat_send", {"chat_id": chat_id, "text": text},
                    envelope_id=envelope_id)
        return True

    return send


def run(proc_root, workspace, procs=None, load=None, at=None,
        live_count=None, routes=None, sender=None,
        item_poster=None, dispositions=None, ledger_lookup=None):
    """One cycle: returns (exit_code, report_lines).

    `item_poster` is the defect-item seam (a callable
    (payload, at), or None when unconfigured) and
    `dispositions` the disposition record dict; both
    default to the module's live state in production and
    are injected as fakes/scratch in tests."""
    if procs is None:
        try:
            procs = sample_processes(proc_root)
        except OSError:
            return 3, ["LOCAL-TEST WATCH: /proc could not be listed"]
    procs = [(p[0], p[1], p[2] if len(p) > 2 else None,
              p[3] if len(p) > 3 else None) for p in procs]
    if load is None:
        load = loadavg(proc_root)
    at = at or now()
    if live_count is None:
        live_count = sessions_live(JOBS_DIR)
    strict = live_count > 0
    mode = "strict" if strict else "normal"
    if routes is None:
        routes = load_routes()
    if dispositions is None:
        dispositions = defects.load_dispositions(DISPOSITIONS)
    if ledger_lookup is None:
        ledger_lookup = ledger.covered_by_op
    current = {}
    for argv, cwd, pid, _ppid in procs:
        if strict:
            finding = classify_strict(
                argv, cwd, workspace,
                routes.get("service_patterns") or ())
        else:
            finding = classify(argv, cwd, workspace)
        if finding is not None:
            current[signature(finding)] = finding
    previous = load_state()
    lines = []
    episodes = {}
    disp_dirty = False
    for sig, finding in current.items():
        if sig in previous:
            episodes[sig] = previous[sig]
            continue
        episodes[sig] = {"first_seen": at, "runner": finding["runner"],
                         "cwd": finding["cwd"], "argv": finding["argv"]}
        route = route_for(finding["cwd"], workspace, routes)
        label = (route or {}).get("label", "unmapped")
        programme = defects.repo_segment(finding["cwd"], workspace)
        line, dirty = episodes_mod.handle_first_sighting({
            "finding": finding, "sig": sig, "at": at,
            "defects": defects, "dispositions": dispositions,
            "ledger_lookup": ledger_lookup,
            "item_poster": item_poster, "routes": routes,
            "sender": sender, "route": route, "label": label,
            "programme": programme, "mode": mode,
            "strict": strict, "live_count": live_count,
            "load": load})
        lines.append(line)
        disp_dirty = disp_dirty or dirty
    save_state(episodes)
    if disp_dirty:
        defects.save_dispositions(DISPOSITIONS, dispositions)
    return 0, lines


def disposition_main(argv):
    """The disposition verb: `disposition <sig> --reason
    <text> --actor <handle>` — the one act that closes a
    defect episode, writing the reason into the record
    and marking the attention item done when the store
    seam is configured. Exit 0 = recorded; 2 = refused
    (unknown signature, empty reason or actor)."""
    import argparse

    parser = argparse.ArgumentParser(prog="local_test_watch disposition")
    parser.add_argument("signature")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--ledger-op", type=int, default=None,
                        help="scheduler ledger op id cited as "
                             "clearance evidence; stored with "
                             "the disposition")
    args = parser.parse_args(argv)
    at = now()
    citation = None
    if args.ledger_op is not None:
        citation = ledger.op_citation(args.ledger_op)
        if citation is None:
            print("DISPOSITION REFUSED: ledger op %d does not "
                  "resolve" % args.ledger_op)
            return 2
    ok, detail = defects.record_disposition(
        DISPOSITIONS, args.signature, args.reason, args.actor, at)
    if not ok:
        print("DISPOSITION REFUSED: " + detail)
        return 2
    if citation is not None:
        record = defects.load_dispositions(DISPOSITIONS)
        entry = (record.get("dispositions") or {}).get(args.signature)
        if entry is not None and entry.get("disposition"):
            entry["disposition"]["ledger_op"] = citation
            defects.save_dispositions(DISPOSITIONS, record)
    resolver = defects.default_item_resolver(REPO)
    item = "unconfigured"
    if resolver is not None:
        item = "done" if resolver(args.signature) else "unresolved"
    print("DISPOSITION RECORDED: %s reason=%r actor=%s at=%s "
          "item=%s" % (detail, args.reason.strip(), args.actor.strip(),
                       at, item))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["disposition"]:
        return disposition_main(argv[1:])
    sender = default_sender()
    code, lines = run(
        PROC_ROOT, WORKSPACE, sender=sender,
        item_poster=defects.default_item_poster(REPO))
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
