"""Catalog commands: adopt (a catalog entry into the live
overlay, with its admission back half) and catalog-drift
(adopted live entries diffed against their catalog
renders)."""
import os
import sys

from server.entries import catalog as catalog_mod
from server import registry

from cli.common import JOBS_DIR, ROOT, _load
from cli.ops_client import _ops_caller, _ops_do, _take_flag


def cmd_adopt(argv):
    caller = _ops_caller(argv)
    _c, argv = _take_flag(argv, "--caller")
    dry_run = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    params, positional = {}, []
    i = 0
    while i < len(argv):
        if argv[i] == "--param" and i + 1 < len(argv):
            key, _, value = argv[i + 1].partition("=")
            params[key] = value
            i += 2
        else:
            positional.append(argv[i])
            i += 1
    if len(positional) != 1:
        print("usage: sched adopt <example-id> [--param k=v]... [--dry-run]")
        return 2
    example_id = positional[0]
    catalog, errors = catalog_mod.load_catalog(ROOT)
    if errors:
        for err in errors:
            print(f"INVALID: {err}")
        return 1
    row = catalog["rows"].get(example_id)
    if row is None:
        print(f"sched adopt: no catalog row: {example_id}", file=sys.stderr)
        return 1
    if row.get("class") != "entry":
        print(f"sched adopt: {example_id} is a config-example — it rides with "
              f"{row.get('companion_of')}, never adopted standalone", file=sys.stderr)
        return 1
    if row.get("generality") == "deployment-specific":
        print(f"sched adopt: {example_id} is classified deployment-specific — "
              "no copy is offered", file=sys.stderr)
        return 1
    example = catalog["entries"][example_id]
    live, errors = catalog_mod.render_adoption(
        example_id, example, params, catalog["version"])
    if errors:
        for err in errors:
            print(f"sched adopt: {err}", file=sys.stderr)
        return 1
    literals = catalog_mod.machine_literals(live)
    if literals:
        for lit in literals:
            print(f"sched adopt: refused — {lit}", file=sys.stderr)
        return 1
    live_id = live["id"]
    if dry_run:
        sys.stdout.write(catalog_mod.serialize_yaml(live))
        for action in catalog_mod.setup_actions(example):
            print(f"# setup: {' '.join(str(a) for a in action)}")
        return 0
    target = os.path.join(JOBS_DIR, f"{live_id}.yaml")
    if os.path.exists(target):
        print(f"sched adopt: live entry already exists: jobs/{live_id}.yaml "
              "(retire it first — re-adoption is a fresh adopt act)",
              file=sys.stderr)
        return 1

    def write(path, content):
        code, _payload = _ops_do(
            {"caller": caller, "op": "write", "path": path, "content": content},
            "adopt")
        return code

    staged = dict(live)
    staged["status"] = "suspended"
    staged["suspend_reason"] = "adoption in progress: proof run pending"
    if write(target, catalog_mod.serialize_yaml(staged)) != 0:
        return 4
    layer = os.path.join(ROOT, catalog_mod.EXAMPLES_DIR)
    for sibling, rel in catalog_mod.adoption_files(example, live_id):
        with open(os.path.join(layer, sibling), encoding="utf-8") as fh:
            if write(os.path.join(ROOT, rel), fh.read()) != 0:
                return 4

    def ops_exec(argv, timeout=60):
        code, payload = _ops_do(
            {"caller": caller, "op": "exec", "argv": argv,
             "cwd": ROOT, "timeout": timeout},
            "adopt", http_timeout=timeout + 30)
        return code, payload

    # Setup: establish or verify everything the adoption needs
    # beyond the entry itself, before the proof run. A failed
    # item leaves the entry suspended (not admitted) and names
    # itself.
    anchors = registry.derive_anchors(ROOT)

    def expand(value):
        return registry.expand_anchors(value, anchors)

    copied, registrations, docs_recorded = [], [], []
    for action in catalog_mod.setup_actions(example):
        kind = action[0]
        if kind == "mkdir":
            code, _p = ops_exec(["mkdir", "-p", expand(action[1])])
            if code != 0:
                return code
        elif kind == "file":
            _k, name, target_rel, from_catalog = action
            if os.path.isfile(os.path.join(ROOT, target_rel)):
                continue
            if not from_catalog:
                print(f"sched adopt: setup file missing and no specimen "
                      f"to copy: {target_rel} ({name}); left "
                      "suspended (not admitted)", file=sys.stderr)
                return 1
            src = os.path.join(layer, catalog["rows"][from_catalog]["file"])
            with open(src, encoding="utf-8") as fh:
                if write(os.path.join(ROOT, target_rel), fh.read()) != 0:
                    return 4
            copied.append(target_rel)
        elif kind == "store":
            _k, name, path, init = action
            if os.path.exists(expand(path)):
                continue
            if not init:
                print(f"sched adopt: setup store missing and no init "
                      f"declared: {path} ({name}); left "
                      "suspended (not admitted)", file=sys.stderr)
                return 1
            code, _p = ops_exec([expand(a) for a in init], timeout=120)
            if code != 0:
                return code
            if not os.path.exists(expand(path)):
                print(f"sched adopt: setup store init ran but the store "
                      f"is still missing: {path} ({name}); left "
                      "suspended (not admitted)", file=sys.stderr)
                return 1
        elif kind == "companion":
            comp = action[1]
            default_live = comp[len("example-"):] if comp.startswith("example-") else comp
            found = os.path.isfile(os.path.join(JOBS_DIR, f"{default_live}.yaml"))
            if not found:
                for other in sorted(os.listdir(JOBS_DIR)):
                    if not other.endswith(".yaml"):
                        continue
                    try:
                        data = registry.parse_yaml(
                            open(os.path.join(JOBS_DIR, other),
                                 encoding="utf-8").read(), where=other)
                    except Exception:  # noqa: BLE001 - a bad file is not a match
                        continue
                    if (data.get("source") or {}).get("catalog") == comp:
                        found = True
                        break
            if not found:
                print(f"sched adopt: companion entry not adopted: {comp}; "
                      "left suspended (not admitted)", file=sys.stderr)
                return 1
        elif kind == "registration":
            registrations.append(action[1])
        elif kind == "doc":
            # A setup doc is recorded with the adoption, never
            # performed: the amendments it describes are the
            # operator's separate, recorded act.
            record_dir = os.path.join(ROOT, "state", "adoptions", live_id)
            code, _p = ops_exec(["mkdir", "-p", record_dir])
            if code != 0:
                return code
            with open(os.path.join(layer, action[1]), encoding="utf-8") as fh:
                if write(os.path.join(record_dir, action[1]), fh.read()) != 0:
                    return 4
            docs_recorded.append(action[1])
    exclude_path = os.path.join(ROOT, ".git", "info", "exclude")
    lines = []
    if os.path.isfile(exclude_path):
        with open(exclude_path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    wanted = [f"jobs/{live_id}.yaml"] + [
        rel for _s, rel in catalog_mod.adoption_files(example, live_id)] + copied
    if any(w not in lines for w in wanted):
        content = "\n".join(lines + [w for w in wanted if w not in lines]) + "\n"
        if write(exclude_path, content) != 0:
            return 4
    entries, errors = _load()
    if errors or live_id not in entries:
        for err in errors:
            print(f"INVALID: {err}")
        print(f"sched adopt: {live_id} written but the registry does not "
              "validate it; left suspended (not admitted)", file=sys.stderr)
        return 1
    code, payload = _ops_do(
        {"caller": caller, "op": "exec",
         "argv": ["python3", os.path.join(ROOT, "ops", "proof", "proof_run.py"), live_id],
         "cwd": ROOT, "timeout": 300},
        "adopt", http_timeout=330)
    if code != 0:
        return code
    proof_line = (payload or {}).get("stdout_tail", "")
    if f"status=ok" not in proof_line:
        print(f"sched adopt: proof run did not pass for {live_id}: "
              f"{proof_line.strip()}; left suspended (not admitted)",
              file=sys.stderr)
        return 1
    # The admitting write: the entry goes into the registry at
    # its rendered status only now, after validate + proof —
    # presence through this writer path is admission
    # (contract 02, amendment 3). The proof outcome is the
    # admission evidence; no field on the entry records it.
    if write(target, catalog_mod.serialize_yaml(live)) != 0:
        return 4
    print(f"adopted {example_id} as {live_id} (catalog v{catalog['version']}); "
          "proof run ok; admitted by the write")
    for reg in registrations:
        print(f"declared setup — manual registration to confirm: {reg}")
    for doc_name in docs_recorded:
        print(f"declared setup — documentation recorded at "
              f"state/adoptions/{live_id}/{doc_name}: it describes "
              "documentation amendments this adoption requires; "
              "adopting did not perform them")
    return 0


def cmd_catalog_drift():
    catalog, errors = catalog_mod.load_catalog(ROOT)
    if errors:
        for err in errors:
            print(f"INVALID: {err}")
        return 1
    lines, problems = catalog_mod.drift(ROOT, catalog)
    for line in lines:
        print(line)
    print(f"catalog-drift: {problems} problem(s)")
    return 1 if problems else 0
