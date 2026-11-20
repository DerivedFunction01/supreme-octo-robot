"""State-store commands: ack (the outbox) and the logs
family (the ledger store) — stats, prune, export, verify,
import-jsonl."""
import os

from server import config as config_mod

from dispatch.ledger import Ledger
from dispatch.outbox import Outbox
from dispatch.stateio import StateError


def cmd_ack(ping_id):
    values, _sources = config_mod.resolve()
    state_dir = os.path.join(values["home"], "state")
    ledger = Ledger(state_dir)
    try:
        outbox = Outbox(state_dir, ledger)
    except StateError as exc:
        print(f"ack failed: {exc}")
        return 1
    ping = outbox.ack(ping_id)
    if ping is None:
        print(f"no such ping: {ping_id}")
        return 1
    print(f"ping {ping_id} ({ping['job_id']}): {ping['state']}")
    return 0


def _ledger():
    values, _sources = config_mod.resolve()
    return values, Ledger(os.path.join(values["home"], "state"))


def cmd_logs(argv):
    sub = argv[0] if argv else ""
    values, ledger = _ledger()
    if sub == "stats":
        stats = ledger.stats()
        print(f"store: sqlite {stats['db_path']} ({stats['db_bytes']} bytes)")
        print(f"events: {stats['events']}  oldest: {stats['oldest']}"
              f"  newest: {stats['newest']}")
        print(f"retention: {values['ledger_retention_days']} days")
        for job_id in sorted(stats["per_job"]):
            print(f"  {job_id}: {stats['per_job'][job_id]}")
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(stats["per_kind"].items()))
        print(f"kinds: {kinds}")
        return 0
    if sub == "prune":
        days = values["ledger_retention_days"]
        if "--days" in argv:
            days = int(argv[argv.index("--days") + 1])
        before = ledger.stats()["db_bytes"]
        dropped = ledger.prune(days)
        after = ledger.stats()["db_bytes"]
        print(f"pruned {dropped} events past {days} days;"
              f" store {before} -> {after} bytes")
        if dropped:
            ledger.record("ledger_pruned", dropped=dropped)
        return 0
    if sub == "export":
        job_id = None
        if "--job" in argv:
            job_id = argv[argv.index("--job") + 1]
        elif "--all" not in argv:
            print("usage: sched logs export (--job <id> | --all) [--out <path>]")
            return 2
        if "--out" in argv:
            out_path = argv[argv.index("--out") + 1]
        else:
            from datetime import datetime, timezone
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            scope = job_id or "all"
            out_path = os.path.join(values["home"], "state", "exports",
                                    f"logs-{scope}-{stamp}.jsonl")
        result = ledger.export_to(out_path, job_id=job_id)
        print(f"exported {result['rows']} events to {result['path']}")
        print(f"sha256: {result['sha256']}")
        return 0
    if sub == "verify":
        result = ledger.verify()
        print(f"integrity: {result['integrity']}  events: {result['events']}")
        return 0 if result["ok"] else 1
    if sub == "import-jsonl":
        if len(argv) < 2:
            print("usage: sched logs import-jsonl <path>")
            return 2
        try:
            imported, source_hash = ledger.import_jsonl(argv[1])
        except (ValueError, OSError) as exc:
            print(f"import failed: {exc}")
            return 1
        import hashlib
        lines = ledger.export_lines()
        blob = "".join(line + "\n" for line in lines).encode("utf-8")
        export_hash = hashlib.sha256(blob).hexdigest()
        print(f"imported {imported} events from {argv[1]}")
        print(f"source canonical sha256: {source_hash}")
        print(f"export check: {len(lines)} rows, sha256 {export_hash}")
        ok = len(lines) == imported and export_hash == source_hash
        print("PROOF:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    print(f"unknown logs command: {sub}")
    return 2
