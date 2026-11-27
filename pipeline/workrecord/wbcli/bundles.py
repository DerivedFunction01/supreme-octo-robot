"""The bundle and file-todo verbs (live-work-
tracking spec §3.4): bundle create/contract and
the file todos inside them."""
import sys

from lib.writes import bundles as bundle_mod  # noqa: E402
from lib.writes import todo_rename as todo_rename_mod  # noqa: E402
from lib.plans import bundles as bundle_parser  # noqa: E402
from lib.plans import timing as timing_mod  # noqa: E402
from wbcli.context import PlansCtx  # noqa: E402
from wbcli.context import _print  # noqa: E402

def cmd_bundle_new(args):
    ctx = PlansCtx(args)
    result = bundle_mod.create_bundle(
        ctx.plans_dir, args.slug, plan=args.plan,
        feature=args.feature, today=args.date)
    _print(result)
    return 0


def cmd_bundle_contract(args):
    ctx = PlansCtx(args)
    filled = (args.programme, args.objective,
              args.complete_when, args.work_record)
    if any(v is not None for v in filled):
        if not all(v is not None for v in filled):
            raise SystemExit(
                "wb bundle contract: setting a contract "
                "takes all four fields — --programme, "
                "--objective, --complete-when, "
                "--work-record")
        result = bundle_mod.set_bundle_contract(
            ctx.plans_dir, args.bundle,
            programme=args.programme,
            objective=args.objective,
            complete_when=args.complete_when,
            work_record=args.work_record)
        _print(result)
        return 0
    bundle_dir = bundle_mod.find_bundle_dir(
        ctx.plans_dir, args.bundle)
    if bundle_dir is None:
        raise SystemExit(
            f"wb bundle contract: unknown bundle: "
            f"{args.bundle!r}")
    _print({"bundle": bundle_dir.name,
            "contract": bundle_parser.parse_contract(
                bundle_dir)})
    return 0


def cmd_todo_new(args):
    ctx = PlansCtx(args)
    result = bundle_mod.create_todo(
        ctx.plans_dir, args.bundle, args.title,
        step=args.step, worktree=args.worktree,
        plan=args.plan, feature=args.feature,
        body=args.body or "", progress=args.progress,
        no_progress=args.no_progress, name=args.name)
    _print({k: result[k] for k in
            ("id", "title", "status", "feature", "plan",
             "plan_step", "est", "fanout_position",
             "worktree", "created", "updated",
             "progress_check", "progress_armed",
             "progress_entry", "attention_row",
             "bundle", "file")})
    return 0


def cmd_todo_file_set(args):
    ctx = PlansCtx(args)
    result = bundle_mod.set_todo_status(
        ctx.plans_dir, args.id, args.status, note=args.note,
        progress=args.progress,
        no_progress=args.no_progress,
        worktree=args.worktree)
    _print({k: result[k] for k in
            ("id", "title", "status", "worktree", "updated",
             "progress_check", "progress_armed",
             "progress_entry", "attention_row",
             "bundle", "file")})
    return 0


def cmd_todo_file_list(args):
    ctx = PlansCtx(args)
    todos = bundle_parser.list_todos(
        ctx.plans_dir, bundle=args.bundle,
        status=args.status)
    invalid = 0
    for t in todos:
        feature = f" [{t['feature']}]" if t["feature"] else ""
        bundle = f" ({t['bundle']})" if t.get("bundle") else ""
        flag = ""
        if not t["valid"]:
            invalid += 1
            flag = " [INVALID: " + "; ".join(t["errors"]) + "]"
        print(f"{t['id'] or '(no id)':<32} "
              f"{t['status'] or '?':<8} "
              f"{t['title'] or '(no title)'}{feature}"
              f"{bundle}{flag}")
    if not todos:
        print("wb: no file todos")
    if invalid:
        print(f"wb: {invalid} todo(s) with invalid "
              f"front-matter (see flags above)",
              file=sys.stderr)
    return 0


def cmd_todo_timing(args):
    """The timing report (timing-ledger Step 4):
    read-only. With a bundle, one plan's per-step
    estimate vs actual and its ruled wall-clock;
    without one, the project's price book across
    plans. Writes nothing."""
    ctx = PlansCtx(args)
    if args.bundle:
        try:
            report = timing_mod.plan_timing(
                ctx.plans_dir, args.bundle)
        except ValueError as e:
            raise SystemExit(f"wb todo timing: {e}")
        print(timing_mod.render_plan(report))
    else:
        print(timing_mod.render_book(
            timing_mod.price_book(ctx.plans_dir)))
    return 0


def cmd_todo_migrate_names(args):
    ctx = PlansCtx(args)
    result = todo_rename_mod.rename_todos(
        ctx.plans_dir, apply=args.apply)
    _print(result)
    return 0


def cmd_todo_import_db(args):
    ctx = PlansCtx(args,
                   project_slug=args.import_project)
    if ctx.db_path is None:
        raise SystemExit(
            "wb: project declares no registry — no DB "
            "todos to import")
    result = bundle_mod.import_db_todos(
        ctx.plans_dir, ctx.db_path, bundle_slug=args.bundle,
        today=args.date)
    _print(result)
    return 0
