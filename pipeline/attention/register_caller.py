#!/usr/bin/env python3
"""Caller registration, step one: record this venue's caller
name in untracked local state. The token itself never passes
through this script — it is issued per caller at the host and
delivered through the secure store (docs/connector-setup.md).
"""

import importlib.util
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "attention_paths", Path(__file__).resolve().parent / "paths.py"
)
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)

_argv_spec = importlib.util.spec_from_file_location(
    "platform_argv", Path(_paths.PIPELINE_ROOT) / "platform" / "argv.py"
)
_argv = importlib.util.module_from_spec(_argv_spec)
_argv_spec.loader.exec_module(_argv)

ROOT = _paths.ATTENTION_HOME
RECORD = ROOT / "var" / "connector" / "caller.json"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

DECL = {
    "name": "register_caller.py",
    "summary": "Record this venue's caller name in untracked local state.",
    "flags": {},
    "positionals": [
        {
            "name": "caller-name",
            "required": True,
            "help": "a slug from the host's caller registry",
        }
    ],
}

_USAGE = (
    "usage: register_caller.py <caller-name>\n"
    "the name is a slug from the host's caller registry"
)


def main(argv: list[str]) -> int:
    """Record the caller name, or refuse with the reason."""
    try:
        parsed = _argv.parse(DECL, argv[1:])
    except _argv.UsageError as err:
        print(err)
        print(_USAGE)
        return 2
    if "help" in parsed:
        print(parsed["help"])
        return 0
    name = parsed["positionals"]["caller-name"]
    if not SLUG.match(name):
        print(_USAGE)
        return 2
    if RECORD.is_file():
        current = json.loads(RECORD.read_text(encoding="utf-8"))
        if current.get("caller") != name:
            print(
                f"refused: this venue is registered as "
                f"{current.get('caller')}; delete {RECORD} to "
                f"re-register under a different name",
            )
            return 1
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(
            {"caller": name, "registered_at": date.today().isoformat()},
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    # The unified writer's protocol (contract 15), performed
    # inline: this script runs on a venue host, outside the
    # pipeline tree the writer lives in — the protocol, not
    # the module, is the invariant. Stage to a fresh sibling,
    # fsync, read back and compare, rename over, so a denied
    # or torn write leaves the standing record byte-identical.
    tmp = RECORD.parent / (RECORD.name + ".tmp-register")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if tmp.read_bytes() != data:
            raise OSError("read-back mismatch on staged write")
        os.replace(tmp, RECORD)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    dir_fd = os.open(RECORD.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    print(f"caller recorded: {name} ({RECORD})")
    print("next: the host issues this caller's token; it reaches")
    print("this venue through the secure store and is injected at")
    print("runtime as HARNESS_CONNECTOR_TOKEN — never written to a")
    print("tracked file, a notebook, or a chat. Set HARNESS_CALLER")
    print(f"to {name} and HARNESS_CONNECTOR_URL to the host's")
    print("loopback/tailnet address, then make a read call:")
    print("  python3 connector/client.py chat-list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
