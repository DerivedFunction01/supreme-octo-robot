"""The registry-entry verbs: the entry lifecycle
(add/list/show/set/status/supersede/verify/archive),
reviews, state, and the project reports."""
import json
import sys
from pathlib import Path

from lib.registry import export as export_mod  # noqa: E402
from lib import registry as reg  # noqa: E402
from lib.derived import staleness as stale_mod  # noqa: E402
from lib import validators as val_mod  # noqa: E402
from lib.discovery.sweep import sweep  # noqa: E402
from wbcli.context import Ctx  # noqa: E402
from wbcli.context import WORKSPACE_ROOT  # noqa: E402
from wbcli.context import _latest_reviews  # noqa: E402
from wbcli.context import _print  # noqa: E402

def cmd_projects(args):
    roots = [Path(r) for r in args.root] \
        if args.root else [WORKSPACE_ROOT]
    result = sweep(roots)
    _print(result.summary())
    return 0


def cmd_init(args):
    ctx = Ctx(args)
    reg.init_registry(ctx.db_path)
    ctx.regenerate()
    print(f"wb: registry ready at {ctx.db_path}")
    return 0


def cmd_add(args):
    ctx = Ctx(args)
    schema = None
    if args.state_schema:
        schema = json.loads(Path(args.state_schema)
                            .read_text())
    entry = reg.add_entry(
        ctx.db_path, ctx.layout, args.slug, title=args.title,
        kind=args.kind, actor="cli", status=args.status,
        ruling=args.ruling, source_kind=args.source_kind,
        source_ref=args.source_ref, main_file=args.main_file,
        state_schema=schema,
        plan_ref=args.plan_ref,
        owner_thread=args.owner_thread,
        owner_label=args.owner_label,
        deploy_class=args.deploy_class)
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_list(args):
    ctx = Ctx(args)
    archived = None
    if args.archived:
        archived = True
    elif not args.all:
        archived = False
    entries = reg.list_entries(ctx.db_path, archived=archived)
    thresholds = stale_mod.load_thresholds(ctx.db_path)
    latest = _latest_reviews(ctx)
    rows = []
    for e in entries:
        derived = stale_mod.entry_staleness(
            e, thresholds=thresholds)
        row = {"id": e["id"], "title": e["title"],
               "kind": e["kind"], "status": e["status"],
               "archived": e["archived"],
               "stale": derived["stale"],
               "stale_reasons": derived["reasons"]}
        if args.stale and not derived["stale"]:
            continue
        if args.status and e["status"] != args.status:
            continue
        rows.append(row)
    for r in rows:
        badge = " [STALE: " + "; ".join(r["stale_reasons"]) + "]" \
            if r["stale"] else ""
        arch = " (archived)" if r["archived"] else ""
        print(f"{r['id']:<28} {r['status']:<12} "
              f"{r['kind']:<18} {r['title']}{arch}{badge}")
    if not rows:
        print("wb: no entries")
    return 0


def cmd_show(args):
    ctx = Ctx(args)
    entry = reg.get_entry(ctx.db_path, args.id)
    entry["derived"] = stale_mod.entry_staleness(
        entry, thresholds=stale_mod.load_thresholds(ctx.db_path))
    entry["approval"] = stale_mod.approval_coverage(
        entry, reg.latest_review(ctx.db_path, args.id))
    entry["history"] = reg.history_for(ctx.db_path, args.id)
    _print(entry)
    return 0


def cmd_set(args):
    ctx = Ctx(args)
    fields = {}
    for pair in args.pairs:
        if "=" not in pair:
            raise SystemExit(f"wb set: expected field=value, "
                             f"got {pair!r}")
        key, _, value = pair.partition("=")
        fields[key] = value
    entry = reg.set_fields(ctx.db_path, args.id, fields,
                           actor="cli",
                           expect_version=args.expect_version)
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_set_status(args):
    ctx = Ctx(args)
    entry = reg.set_status(
        ctx.db_path, args.id, args.status, actor="cli",
        ruling=args.ruling, gate=args.gate,
        expect_version=args.expect_version, layout=ctx.layout)
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_supersede(args):
    ctx = Ctx(args)
    entry = reg.supersede(ctx.db_path, args.old, args.new,
                          actor="cli", ruling=args.ruling)
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_verify(args):
    ctx = Ctx(args)
    entry = reg.verify_entry(ctx.db_path, args.id, actor="cli",
                             accept_drift=args.accept_drift)
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_archive(args):
    ctx = Ctx(args)
    entry = reg.archive_entry(ctx.db_path, ctx.layout, args.id,
                              actor="cli", resume=args.resume)
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_unarchive(args):
    ctx = Ctx(args)
    entry = reg.unarchive_entry(ctx.db_path, ctx.layout,
                                args.id, actor="cli")
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_stale(args):
    ctx = Ctx(args)
    entries = reg.list_entries(ctx.db_path, archived=False)
    report = stale_mod.project_report(
        entries, _latest_reviews(ctx),
        thresholds=stale_mod.load_thresholds(ctx.db_path))
    _print(report)
    summary = (f"stale-check: {report['summary']['stale']} of "
               f"{report['summary']['total']} entries flagged")
    reg.record_stale_check(ctx.db_path, summary)
    ctx.regenerate()
    print(summary)
    return 0


def cmd_validate(args):
    ctx = Ctx(args)
    findings = val_mod.validate_project(ctx.db_path, ctx.layout)
    for f in findings:
        print(f"[{f['validator']}] {f['entry']}: {f['message']}")
    if findings:
        print(f"wb validate: {len(findings)} finding(s)")
        return 1
    print("wb validate: clean")
    return 0


def cmd_export(args):
    ctx = Ctx(args)
    out = export_mod.regenerate(ctx.db_path,
                                project=ctx.project_meta)
    print(f"wb: export regenerated at {out}")
    return 0


def cmd_rebuild(args):
    ctx = Ctx(args)
    export_path = ctx.db_path.with_name("registry.json")
    if args.from_file:
        export_path = Path(args.from_file)
    data = export_mod.rebuild(ctx.db_path, export_path)
    print(f"wb: rebuilt {ctx.db_path} from {export_path} "
          f"({len(data.get('entries', []))} entries)")
    return 0


def cmd_set_state_schema(args):
    ctx = Ctx(args)
    schema = json.loads(Path(args.file).read_text())
    entry = reg.set_state_schema(ctx.db_path, args.id, schema,
                                 actor="cli")
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_set_state(args):
    ctx = Ctx(args)
    state = json.loads(args.json)
    entry = reg.set_state(ctx.db_path, args.id, state,
                          actor="cli",
                          expect_version=args.expect_version)
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_review(args):
    ctx = Ctx(args)
    entry = reg.review_entry(ctx.db_path, args.id,
                             args.disposition, actor="cli",
                             comment=args.comment,
                             layout=ctx.layout)
    ctx.regenerate()
    _print(entry)
    return 0
