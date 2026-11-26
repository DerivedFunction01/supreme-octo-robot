#!/usr/bin/env python3
"""Mint/re-issue the ops + connector tokens over the live
caller set, and deliver each raw token to its client home
(freeze step 7's OI-2 residue, scripted).

Rides the mega home's own `bin/sched connector-token` —
one registry, hashes only server-side; the raw token is
shown once by that verb, so this driver captures the
verb's stdout and NEVER prints it. What it records per
caller: name, scopes, the delivered token file, and its
mode. A mint whose token file does not land at 0600 in the
token home fails the run.

Sequencing (two phases, both rehearsed): the acting
caller (the freeze operator's own caller) is minted first
— with the server quiesced that first mint bootstraps by
the direct staged write the OI-2 build provides. Once the
acting caller holds a token, the direct-write fallback no
longer applies, so the remaining mints ride /ops: the
runbook starts the mega server standalone for the mint
run (at step 7 the ports are already free — the originals
stopped at step 2), this driver mints the rest, and the
server stops again before step 8 raises it as the unit.
Scopes ride contract 01/04: write-state and exec for ops
callers; read/send/bridge for tool callers.

With --probe-dir and the mega server running (its config
in the target home), an authenticated round-trip runs per
ops caller class: an exec caller must run /bin/true
through /ops; a write-state caller must land a probe file
through /ops. A refused probe fails the run.

Manifest (JSON): [{"caller": name, "scopes": [...]}, ...]
"""

import json
import os
import stat
import subprocess
import sys


def _run(home, env, argv):
    return subprocess.run(argv, cwd=home, env=env,
                          capture_output=True, text=True)


def _mint(home, env, sched, acting, entry):
    argv = [sys.executable, sched, "connector-token",
            "--caller", acting, entry["caller"],
            "--scopes", ",".join(entry["scopes"]),
            "--save-client"]
    proc = _run(home, env, argv)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        return {"caller": entry["caller"], "ok": False,
                "error": tail[-1] if tail else
                f"connector-token exited {proc.returncode}"}
    token_file = os.path.join(env["SCHED_OPS_TOKEN_DIR"],
                              entry["caller"] + ".token")
    if not os.path.isfile(token_file):
        return {"caller": entry["caller"], "ok": False,
                "error": "token file did not land in the "
                "client token home"}
    mode = stat.S_IMODE(os.stat(token_file).st_mode)
    if mode != 0o600:
        return {"caller": entry["caller"], "ok": False,
                "error": f"token file mode {oct(mode)}, "
                "expected 0o600"}
    return {"caller": entry["caller"], "ok": True,
            "scopes": entry["scopes"],
            "token_file": token_file}


def _probe(home, env, sched, entry, probe_dir):
    scopes = set(entry["scopes"])
    if "exec" in scopes:
        proc = _run(home, env, [sys.executable, sched, "exec",
                                "--caller", entry["caller"],
                                "--", "/bin/true"])
        if proc.returncode != 0:
            return {"caller": entry["caller"], "probe": "exec",
                    "ok": False}
        return {"caller": entry["caller"], "probe": "exec",
                "ok": True}
    if "write-state" in scopes:
        target = os.path.join(
            probe_dir, f"probe-{entry['caller']}.txt")
        proc = subprocess.run(
            [sys.executable, sched, "write", "--caller",
             entry["caller"], target],
            cwd=home, env=env, input="probe\n",
            capture_output=True, text=True)
        ok = proc.returncode == 0 and os.path.isfile(target)
        return {"caller": entry["caller"], "probe": "write",
                "ok": ok}
    return {"caller": entry["caller"], "probe": "none",
            "ok": True}


import importlib.util  # noqa: E402


def _load_paths():
    """The platform paths spine, loaded by path (the
    package's standing bootstrap form)."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_paths",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "paths.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_argv():
    """The unified argv module, located through the
    paths spine and loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_argv", _load_paths().ARGV)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_platform_argv"] = module
    spec.loader.exec_module(module)
    return module


uargv = _load_argv()
from types import SimpleNamespace  # noqa: E402


# The declared surface, parsed by the unified argv
# module (pipeline/platform/argv.py): both value forms
# are one flag, unknown flags and surplus positionals
# refuse at exit 2, and help is generated from this
# declaration.
DECL = {
    "name": "mint-tokens",
    "flags": {
        "sched-home": {"takes_value": True, "required": True},
        "manifest": {"takes_value": True, "required": True},
        "acting": {"takes_value": True, "help": "the acting (operator) caller; default: the manifest's first entry"},
        "token-dir": {"takes_value": True, "help": "client token home (default: the home's ops-tokens/)"},
        "probe-dir": {"takes_value": True, "help": "if given, run the authenticated round-trip probes against the server the home's config names"},
    },
}

def _parse(argv):
    outcome = uargv.parse_only(
        DECL, sys.argv[1:] if argv is None else argv)
    if not outcome["ok"]:
        print(outcome["error"], file=sys.stderr)
        print(outcome["usage"], file=sys.stderr)
        raise SystemExit(uargv.USAGE_EXIT)
    if "help" in outcome:
        print(outcome["help"], end="")
        raise SystemExit(0)
    result = outcome["result"]
    merged = dict(result["flags"])
    merged.update(result["positionals"])
    return SimpleNamespace(
        **{key.replace("-", "_"): value
           for key, value in merged.items()})


def main(argv=None):
    args = _parse(argv)

    home = os.path.abspath(args.sched_home)
    sched = os.path.join(home, "bin", "sched")
    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not manifest:
        print("FAIL empty manifest")
        return 1
    acting = args.acting or manifest[0]["caller"]
    ordered = sorted(manifest,
                     key=lambda e: e["caller"] != acting)

    env = dict(os.environ)
    env["SCHED_OPS_TOKEN_DIR"] = os.path.abspath(
        args.token_dir or os.path.join(home, "ops-tokens"))
    os.makedirs(env["SCHED_OPS_TOKEN_DIR"], exist_ok=True)

    results, probes, failed = [], [], False
    for entry in ordered:
        result = _mint(home, env, sched, acting, entry)
        results.append(result)
        failed |= not result["ok"]
        if result["ok"] and args.probe_dir:
            probe = _probe(home, env, sched, entry,
                           args.probe_dir)
            probes.append(probe)
            failed |= not probe["ok"]
    print(f"SUMMARY {json.dumps({'minted': results, 'probes': probes}, sort_keys=True)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
