"""The seed/export step (contract 01; plan §4.1, §9.1).

The merged registry's live store is seeded, never
hand-copied:

- `seed-capture` builds the store from the S1 overlay
  capture (docs/overlay/holding/) — the consolidation's
  seed source. Live registries are re-seeded from the
  capture only (S7 done-evidence), never from the tracked
  examples.
- `seed-examples` builds it from the tracked fictional
  examples (contracts/fixtures/) — the fresh-deployment
  form of contract 04's seed/example pattern.
- `export` writes the store back out as the per-form
  files: the thread-caller file form, the connector
  token-caller map, the three routing tables in their
  native forms, and — new at this step — handlers.json
  and programmes.json, the tracked seed/export form
  attention's registries have never had.

Secrets discipline: the token section carries hashes
only, exactly as captured; raw tokens exist nowhere in
this flow. The bridge token is not part of this registry
at all — it stays a raw-token live-config file on the
client side only (contract 01).

Run from the pipeline root:
  python3 -m registry.seed seed-capture --holding DIR --to PATH
  python3 -m registry.seed seed-examples --fixtures DIR --to PATH
  python3 -m registry.seed export --from PATH --out DIR
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

from . import paths as _paths
from . import store as store_mod


def _load_yaml_parser():
    """The strict YAML-subset parser is the scheduling
    registry module's (it froze the format); loaded by
    path from the registry paths module."""
    path = _paths.SCHEDULING_REGISTRY
    spec = importlib.util.spec_from_file_location(
        "pipeline_scheduling_registry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_yaml


def _load_platform_writer():
    path = _paths.PLATFORM_WRITER
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_yaml(path):
    with open(path, "r", encoding="utf-8") as fh:
        return _load_yaml_parser()(fh.read(), where=os.fspath(path))


# -- seeding ---------------------------------------------------

def seed_from_capture(holding) -> dict:
    """Build the merged store data from the S1 overlay
    capture (docs/overlay/holding/). Every section's
    source is a held live registry, verbatim."""
    holding = os.fspath(holding)
    data = store_mod.empty_data()

    callers = _read_json(os.path.join(
        holding, "colab-runner", "config", "callers.json"))
    data["thread_callers"] = {
        "callers": list(callers.get("callers") or []),
        "active": list(callers.get("active") or []),
    }

    sched_config = _read_json(os.path.join(
        holding, "scheduler", "config.json"))
    connector = sched_config.get("connector") or {}
    data["token_callers"] = dict(connector.get("callers") or {})

    wake = _read_yaml(os.path.join(
        holding, "scheduler", "bodies", "bridge-wake-owners.yaml"))
    data["routing"]["bridge_wake_owners"] = {
        "version": wake.get("version", 1),
        "owners": dict(wake.get("owners") or {}),
    }
    if isinstance(wake.get("drain"), dict):
        data["routing"]["bridge_wake_owners"]["drain"] = wake["drain"]

    notify = _read_json(os.path.join(
        holding, "colab-runner", "config", "notify-routes.json"))
    data["routing"]["notify_routes"] = {
        "main": notify.get("main"),
        "routes": dict(notify.get("routes") or {}),
    }

    restart = _read_yaml(os.path.join(
        holding, "scheduler", "bodies",
        "restart-reconcile-owners.yaml"))
    data["routing"]["restart_owners"] = {
        "owners": dict(restart.get("owners") or {}),
        "namespaces": dict(restart.get("namespaces") or {}),
        "prefixes": dict(restart.get("prefixes") or {}),
    }

    state = _read_json(os.path.join(
        holding, "owner-attention", "var", "data", "state.json"))
    data["handlers"] = list(state.get("handlers") or [])
    data["programmes"] = list(state.get("programmes") or [])
    return data


def seed_from_examples(fixtures) -> dict:
    """Build the store from the tracked fictional examples
    — the fresh-deployment seed (contract 04). Fictional
    values only; a deployment replaces them with its own
    live seed, as the capture seeded this consolidation."""
    fixtures = os.fspath(fixtures)
    data = store_mod.empty_data()
    callers = _read_json(os.path.join(fixtures, "callers.example.json"))
    data["thread_callers"] = {
        "callers": list(callers.get("callers") or []),
        "active": list(callers.get("active") or []),
    }
    notify = _read_json(os.path.join(fixtures,
                                     "notify-routes.example.json"))
    data["routing"]["notify_routes"] = {
        "main": notify.get("main"),
        "routes": dict(notify.get("routes") or {}),
    }
    wake = _read_yaml(os.path.join(
        fixtures, "bridge-wake-owners.example.yaml"))
    data["routing"]["bridge_wake_owners"] = {
        "version": wake.get("version", 1),
        "owners": dict(wake.get("owners") or {}),
    }
    handler = _read_json(os.path.join(fixtures, "attention-handler.json"))
    data["handlers"] = [handler]
    programme = _read_json(os.path.join(fixtures,
                                        "attention-programme.json"))
    data["programmes"] = [programme]
    return data


# -- export ------------------------------------------------------

def _emit_chat_table(sections) -> str:
    """Emit the owners-table YAML form: top-level sections
    of caller -> {chat: "..."} maps, two-space nesting,
    values double-quoted (the held files' form)."""
    lines = []
    for name, rows in sections:
        lines.append(f"{name}:")
        for key in sorted(rows):
            chat = rows[key].get("chat") if isinstance(rows[key], dict) \
                else rows[key]
            lines.append(f"  {key}:")
            lines.append(f'    chat: "{chat}"')
    return "\n".join(lines) + "\n"


def _write(path, text):
    _writer.staged_write(os.fspath(path), text.encode("utf-8"))


def export_forms(registry, out_dir) -> list:
    """Write the store out as the per-form files. Returns
    the file names written. The token section exports as
    the connector map (hashes only — that is all the store
    has ever held)."""
    os.makedirs(out_dir, exist_ok=True)
    written = []

    def put(name, text):
        _write(os.path.join(out_dir, name), text)
        written.append(name)

    put("callers.json", json.dumps(registry.thread_callers(),
                                   indent=2, sort_keys=True) + "\n")
    put("connector-callers.json",
        json.dumps(registry.token_callers(), indent=2,
                   sort_keys=True) + "\n")
    wake = registry.routing().get("bridge_wake_owners") or {}
    if isinstance(wake.get("drain"), dict):
        # drain is a single {chat} map, not a caller map;
        # it emits in its held shape, ahead of owners.
        drain_lines = f'drain:\n  chat: "{wake["drain"].get("chat")}"\n'
    else:
        drain_lines = ""
    owners_lines = _emit_chat_table(
        [("owners", wake.get("owners") or {})])
    put("bridge-wake-owners.yaml",
        f"version: {wake.get('version', 1)}\n"
        f"{drain_lines}{owners_lines}")
    notify = registry.routing().get("notify_routes") or {}
    put("notify-routes.json", json.dumps(
        {"main": notify.get("main"),
         "routes": notify.get("routes") or {}},
        indent=2, sort_keys=True) + "\n")
    restart = registry.routing().get("restart_owners") or {}
    put("restart-reconcile-owners.yaml", _emit_chat_table([
        ("owners", restart.get("owners") or {}),
        ("namespaces", restart.get("namespaces") or {}),
        ("prefixes", restart.get("prefixes") or {}),
    ]))
    put("handlers.json", json.dumps(registry.handlers(), indent=2,
                                    sort_keys=True) + "\n")
    put("programmes.json", json.dumps(registry.programmes(), indent=2,
                                      sort_keys=True) + "\n")
    return written


# -- CLI ---------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="registry.seed")
    sub = parser.add_subparsers(dest="verb", required=True)
    cap = sub.add_parser("seed-capture")
    cap.add_argument("--holding", required=True)
    cap.add_argument("--to", required=True)
    ex = sub.add_parser("seed-examples")
    ex.add_argument("--fixtures", required=True)
    ex.add_argument("--to", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--from", dest="source", required=True)
    exp.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.verb == "seed-capture":
        registry = store_mod.Registry(seed_from_capture(args.holding))
        registry.save(args.to)
        print(f"seeded {args.to} from capture {args.holding}")
    elif args.verb == "seed-examples":
        registry = store_mod.Registry(seed_from_examples(args.fixtures))
        registry.save(args.to)
        print(f"seeded {args.to} from examples {args.fixtures}")
    elif args.verb == "export":
        registry = store_mod.Registry.load(args.source)
        written = export_forms(registry, args.out)
        print(f"exported {len(written)} forms to {args.out}: "
              f"{', '.join(written)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
