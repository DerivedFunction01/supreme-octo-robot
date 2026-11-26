"""State-store commands: ack (the outbox) and the logs
family (the ledger store) — stats, prune, export, verify.
Each logs verb's surface is a unified-argv
declaration: both value forms parse identically, a flag
in last position is a usage refusal, never a traceback."""
import os

from server import config as config_mod

from cli.ops_client import parse_decl
from dispatch.ledger import Ledger
from dispatch.outbox import Outbox
from dispatch.stateio import StateError

LOGS_DECLS = {
    "stats": {"name": "sched logs stats",
              "summary": "the log store at a glance"},
    "prune": {"name": "sched logs prune",
              "summary": "delete events past retention, vacuum, "
                         "report",
              "flags": {"days": {"takes_value": True,
                                 "help": "retention in days "
                                         "(default: the config's)"}}},
    "export": {"name": "sched logs export",
               "summary": "write events to disk as JSONL",
               "flags": {"job": {"takes_value": True,
                                 "help": "export one job's events"},
                         "all": {"help": "export every event"},
                         "out": {"takes_value": True,
                                 "help": "output path"}}},
    "verify": {"name": "sched logs verify",
               "summary": "integrity check on the log store"},
}


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
    decl = LOGS_DECLS.get(sub)
    if decl is None:
        print(f"unknown logs command: {sub}")
        return 2
    result, code = parse_decl(decl, argv[1:])
    if result is None:
        return code
    flags = result["flags"]
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
        if flags.get("days") is not None:
            try:
                days = int(flags["days"])
            except ValueError:
                print(f"sched logs prune: --days must be an int: "
                      f"{flags['days']}")
                return 2
        before = ledger.stats()["db_bytes"]
        dropped = ledger.prune(days)
        after = ledger.stats()["db_bytes"]
        print(f"pruned {dropped} events past {days} days;"
              f" store {before} -> {after} bytes")
        if dropped:
            ledger.record("ledger_pruned", dropped=dropped)
        return 0
    if sub == "export":
        job_id = flags.get("job")
        if job_id is None and not flags.get("all"):
            print("usage: sched logs export (--job <id> | --all) [--out <path>]")
            return 2
        if flags.get("out"):
            out_path = flags["out"]
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
    return 2
