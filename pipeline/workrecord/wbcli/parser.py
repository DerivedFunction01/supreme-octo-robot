"""The argument parser: every verb and flag the
CLI exposes, wired to its command function."""
import argparse

from lib.writes import bundles as bundle_mod  # noqa: E402
from lib import registry as reg  # noqa: E402
from wbcli.artifacts import cmd_artifact_build  # noqa: E402
from wbcli.artifacts import cmd_artifact_new  # noqa: E402
from wbcli.artifacts import cmd_set_class  # noqa: E402
from wbcli.artifacts import cmd_set_owner  # noqa: E402
from wbcli.bundles import cmd_bundle_contract  # noqa: E402
from wbcli.bundles import cmd_bundle_new  # noqa: E402
from wbcli.bundles import cmd_todo_file_list  # noqa: E402
from wbcli.bundles import cmd_todo_file_set  # noqa: E402
from wbcli.bundles import cmd_todo_import_db  # noqa: E402
from wbcli.bundles import cmd_todo_migrate_names  # noqa: E402
from wbcli.bundles import cmd_todo_new  # noqa: E402
from wbcli.drivers import cmd_activate  # noqa: E402
from wbcli.drivers import cmd_doctor  # noqa: E402
from wbcli.drivers import cmd_goal_check  # noqa: E402
from wbcli.drivers import cmd_print_schedule  # noqa: E402
from wbcli.drivers import cmd_progress  # noqa: E402
from wbcli.drivers import cmd_commission_check  # noqa: E402
from wbcli.drivers import cmd_plan_check  # noqa: E402
from wbcli.drivers import cmd_progress_check  # noqa: E402
from wbcli.entries import cmd_add  # noqa: E402
from wbcli.entries import cmd_archive  # noqa: E402
from wbcli.entries import cmd_export  # noqa: E402
from wbcli.entries import cmd_init  # noqa: E402
from wbcli.entries import cmd_list  # noqa: E402
from wbcli.entries import cmd_projects  # noqa: E402
from wbcli.entries import cmd_rebuild  # noqa: E402
from wbcli.entries import cmd_review  # noqa: E402
from wbcli.entries import cmd_set  # noqa: E402
from wbcli.entries import cmd_set_state  # noqa: E402
from wbcli.entries import cmd_set_state_schema  # noqa: E402
from wbcli.entries import cmd_set_status  # noqa: E402
from wbcli.entries import cmd_show  # noqa: E402
from wbcli.entries import cmd_stale  # noqa: E402
from wbcli.entries import cmd_supersede  # noqa: E402
from wbcli.entries import cmd_unarchive  # noqa: E402
from wbcli.entries import cmd_validate  # noqa: E402
from wbcli.entries import cmd_verify  # noqa: E402

_GLOBAL_SELECTORS = (
    ("--project", "project slug (sweep)"),
    ("--root", "project root with workbench.yaml"),
    ("--db", "registry DB path (direct)"),
)


def _apply_argv_contract(p):
    """The unified argv contract over the whole parser
    tree: abbreviations off at every level (BT9), and
    the global selectors declared on every verb as well
    as before it — a selector is a declared flag
    wherever it stands, so `wb add <slug> --project x`
    parses (the selector is a declaration, not a
    positional guess). A verb that already declares a
    selector (the sweep verbs' repeatable --root) keeps
    its own declaration."""
    tree = []
    stack = [p]
    while stack:
        parser = stack.pop()
        parser.allow_abbrev = False
        tree.append(parser)
        for action in parser._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                stack.extend(choices.values())
    for parser in tree[1:]:
        declared = {s for a in parser._actions
                    for s in a.option_strings}
        for flag, helptext in _GLOBAL_SELECTORS:
            if flag not in declared:
                parser.add_argument(
                    flag, default=argparse.SUPPRESS,
                    help=helptext)
    return p


def build_parser():
    p = argparse.ArgumentParser(
        prog="wb", description="Workbench harness CLI "
        "(thin caller over lib/ — one mutation path).",
        allow_abbrev=False)
    p.add_argument("--project", help="project slug (sweep)")
    p.add_argument("--root", help="project root with "
                                  "workbench.yaml")
    p.add_argument("--db", help="registry DB path (direct)")
    sub = p.add_subparsers(dest="verb", required=True)

    sp = sub.add_parser("projects")
    sp.add_argument("--root", action="append",
                    help="sweep root (repeatable)")
    sp.set_defaults(fn=cmd_projects)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    sp = sub.add_parser("add")
    sp.add_argument("slug")
    sp.add_argument("--title")
    sp.add_argument("--kind", default="mockup")
    sp.add_argument("--status", default="unexplored")
    sp.add_argument("--ruling")
    sp.add_argument("--source-kind", default="entry-dir")
    sp.add_argument("--source-ref")
    sp.add_argument("--main-file", default="mock.html")
    sp.add_argument("--state-schema",
                    help="path to a JSON state-schema file")
    sp.add_argument("--owner-thread",
                    help="owning chat id (attribution)")
    sp.add_argument("--owner-label",
                    help="owning thread title (display)")
    sp.add_argument("--plan", dest="plan_ref",
                    help="plan/bundle this entry was made "
                         "for (attribution anchor)")
    sp.add_argument("--class", dest="deploy_class",
                    default="standard",
                    help="deploy class: standard | deployed")
    sp.set_defaults(fn=cmd_add)

    sp = sub.add_parser("list")
    sp.add_argument("--status")
    sp.add_argument("--stale", action="store_true")
    sp.add_argument("--archived", action="store_true")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("show")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser("set")
    sp.add_argument("id")
    sp.add_argument("pairs", nargs="+")
    sp.add_argument("--expect-version", type=int)
    sp.set_defaults(fn=cmd_set)

    sp = sub.add_parser("set-status")
    sp.add_argument("id")
    sp.add_argument("status")
    sp.add_argument("--ruling")
    sp.add_argument("--gate")
    sp.add_argument("--expect-version", type=int)
    sp.set_defaults(fn=cmd_set_status)

    sp = sub.add_parser("set-owner")
    sp.add_argument("id")
    sp.add_argument("--thread",
                    help="owning chat id")
    sp.add_argument("--label",
                    help="owning thread title (display)")
    sp.add_argument("--clear", action="store_true",
                    help="clear the attribution")
    sp.set_defaults(fn=cmd_set_owner)

    sp = sub.add_parser("set-class")
    sp.add_argument("id")
    sp.add_argument("deploy_class",
                    help="standard | deployed")
    sp.set_defaults(fn=cmd_set_class)

    sp = sub.add_parser("supersede")
    sp.add_argument("old")
    sp.add_argument("new")
    sp.add_argument("--ruling")
    sp.set_defaults(fn=cmd_supersede)

    sp = sub.add_parser("verify")
    sp.add_argument("id")
    sp.add_argument("--accept-drift", action="store_true")
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser("archive")
    sp.add_argument("id")
    sp.add_argument("--resume", action="store_true")
    sp.set_defaults(fn=cmd_archive)

    sp = sub.add_parser("unarchive")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_unarchive)

    sub.add_parser("stale").set_defaults(fn=cmd_stale)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)
    sub.add_parser("export").set_defaults(fn=cmd_export)

    sp = sub.add_parser("rebuild")
    sp.add_argument("--from-file")
    sp.set_defaults(fn=cmd_rebuild)

    sp = sub.add_parser("set-state-schema")
    sp.add_argument("id")
    sp.add_argument("file")
    sp.set_defaults(fn=cmd_set_state_schema)

    sp = sub.add_parser("set-state")
    sp.add_argument("id")
    sp.add_argument("json")
    sp.add_argument("--expect-version", type=int)
    sp.set_defaults(fn=cmd_set_state)

    sp = sub.add_parser("review")
    sp.add_argument("id")
    sp.add_argument("disposition",
                    choices=list(reg.REVIEW_DISPOSITIONS))
    sp.add_argument("--comment")
    sp.set_defaults(fn=cmd_review)

    sp = sub.add_parser(
        "artifact",
        help="choice-kit study artifacts: stamp one out "
             "from templates/choice-kit, re-render after "
             "spec edits")
    asub = sp.add_subparsers(dest="artifact_verb",
                             required=True)
    na = asub.add_parser(
        "new",
        help="register a kit artifact entry and render "
             "its page from the demo spec (or --spec)")
    na.add_argument("slug")
    na.add_argument("--title")
    na.add_argument("--spec",
                    help="path to a spec JSON file "
                         "(default: the demo scaffold)")
    na.add_argument("--owner-thread",
                    help="owning chat id (attribution)")
    na.add_argument("--owner-label",
                    help="owning thread title (display)")
    na.add_argument("--plan", dest="plan_ref",
                    help="plan/bundle this entry was made "
                         "for (attribution anchor)")
    na.add_argument("--class", dest="deploy_class",
                    default="standard",
                    help="deploy class: standard | deployed")
    na.set_defaults(fn=cmd_artifact_new)
    ba = asub.add_parser(
        "build",
        help="re-render an entry's index.html from its "
             "spec.json and restamp its content hash")
    ba.add_argument("slug")
    ba.set_defaults(fn=cmd_artifact_build)

    sp = sub.add_parser(
        "bundle", help="plan bundles (spec §3.4)")
    bsub = sp.add_subparsers(dest="bundle_verb",
                             required=True)
    nb = bsub.add_parser("new")
    nb.add_argument("slug")
    nb.add_argument("--plan", action="store_true",
                    help="also write a plan.md skeleton")
    nb.add_argument("--feature")
    nb.add_argument("--date",
                    help="bundle date prefix (default: today)")
    nb.set_defaults(fn=cmd_bundle_new)

    cb = bsub.add_parser(
        "contract",
        help="show or set a bundle's goal contract")
    cb.add_argument("bundle")
    cb.add_argument("--programme")
    cb.add_argument("--objective")
    cb.add_argument("--complete-when", dest="complete_when")
    cb.add_argument("--work-record", dest="work_record")
    cb.set_defaults(fn=cmd_bundle_contract)

    sp = sub.add_parser(
        "todo", help="file todos in bundles (spec §3.4)")
    tsub = sp.add_subparsers(dest="todo_verb", required=True)
    nt = tsub.add_parser("new")
    nt.add_argument("bundle")
    nt.add_argument("title")
    nt.add_argument("--name",
                    help="the todo's name (a GitHub-like "
                         "slug, unique project-wide); "
                         "default: derived from the title")
    nt.add_argument("--step", type=int)
    nt.add_argument("--worktree")
    nt.add_argument("--plan")
    nt.add_argument("--feature")
    nt.add_argument("--body")
    nt.add_argument("--progress",
                    help="arm a progress schedule with "
                         "this cadence (e.g. 30m)")
    nt.add_argument("--no-progress",
                    action="store_true",
                    help="record the explicit opt-out: "
                         "this todo is never monitored")
    nt.set_defaults(fn=cmd_todo_new)

    st = tsub.add_parser("set")
    st.add_argument("id")
    st.add_argument("status",
                    choices=list(bundle_mod.TODO_STATUSES))
    st.add_argument("--note",
                    help="appended to the todo body "
                         "(blocker reason / deploy record)")
    st.add_argument("--progress",
                    help="arm or re-arm the progress "
                         "schedule with this cadence "
                         "(e.g. 30m), overriding the "
                         "automatic 15m arm on a move to "
                         "doing; a move to done or "
                         "blocked disarms it")
    st.add_argument("--no-progress",
                    action="store_true",
                    help="record the explicit opt-out "
                         "instead: progress_check off, "
                         "no schedule, never monitored")
    st.add_argument("--worktree",
                    help="the acting worktree this move "
                         "runs in: stamped on the todo's "
                         "worktree field and carried on "
                         "the move's transition line "
                         "(timing ledger — the activation "
                         "move names it)")
    st.set_defaults(fn=cmd_todo_file_set)

    lt = tsub.add_parser("list")
    lt.add_argument("--bundle")
    lt.add_argument("--status",
                    choices=list(bundle_mod.TODO_STATUSES))
    lt.set_defaults(fn=cmd_todo_file_list)

    mt = tsub.add_parser(
        "migrate-names",
        help="rename legacy t-<token> todo ids to "
             "GitHub-like names derived from their "
             "titles (the 2026-11-14 naming ruling); "
             "dry-run unless --apply")
    mt.add_argument("--apply", action="store_true",
                    help="perform the rename (default: "
                         "report the plan only)")
    mt.set_defaults(fn=cmd_todo_migrate_names)

    it = tsub.add_parser(
        "import-db",
        help="import registry-DB todos into a starter "
             "bundle of file todos (spec §3.7)")
    it.add_argument("import_project", nargs="?",
                    help="project slug (sweep); default: "
                         "the selected project")
    it.add_argument("--bundle", default="project-zero-starter",
                    help="starter bundle slug")
    it.add_argument("--date",
                    help="bundle date prefix (default: today)")
    it.set_defaults(fn=cmd_todo_import_db)

    sp = sub.add_parser(
        "activate",
        help="active-plan declaration for this worktree "
             "(repo-home spec §17): set, clear, or show")
    sp.add_argument("bundle", nargs="?",
                    help="bundle id or slug to declare "
                         "active (omit to show the current "
                         "resolution)")
    sp.add_argument("--plan",
                    help="plan path within the bundle "
                         "(default: the bundle's plan)")
    sp.add_argument("--since",
                    help="declaration date (default: today)")
    sp.add_argument("--clear", action="store_true",
                    help="remove the declaration")
    sp.set_defaults(fn=cmd_activate)

    sp = sub.add_parser(
        "doctor",
        help="read-only consistency checks over every "
             "swept project")
    sp.add_argument("--post", action="store_true",
                    help="diff against the previous run "
                         "and post a digest message when "
                         "the finding set changed")
    sp.add_argument("--root", action="append",
                    help="sweep root (repeatable); "
                         "default: the server config's "
                         "sweep roots")
    sp.set_defaults(fn=cmd_doctor)

    sp = sub.add_parser(
        "progress",
        help="armed progress schedules with derived "
             "stall verdicts, as JSON (the progress "
             "driver's read)")
    sp.add_argument("--root", action="append",
                    help="sweep root (repeatable); "
                         "default: the server config's "
                         "sweep roots")
    sp.add_argument("--sync-entries",
                    action="store_true",
                    help="delete every wb-progress "
                         "scheduler entry (the retired "
                         "rendering's retirement sweep) "
                         "instead of reporting")
    sp.set_defaults(fn=cmd_progress)

    sp = sub.add_parser(
        "progress-check",
        help="one armed todo's stall verdict: exit 0 on "
             "track, exit 3 with a STALLED line when "
             "stalled (run by the todo's scheduler "
             "entry, which pins --root); an unpinned "
             "invocation whose id is absent from the "
             "ambient project fails loud (exit 2) — a "
             "todo id names one project's store only")
    sp.add_argument("id", help="the todo id")
    sp.set_defaults(fn=cmd_progress_check)

    sp = sub.add_parser(
        "commission-check",
        help="one claimed commission's verdict against "
             "the record: exit 0 with a COMMISSION line "
             "when the cited todo is a commission of "
             "record (provenance planted through the "
             "writers), exit 3 NOT A COMMISSION when no "
             "entry resolves or the entry carries no "
             "provenance — a chat-channel claim alone is "
             "not a commission; an unpinned invocation "
             "whose id is absent from the ambient "
             "project fails loud (exit 2)")
    sp.add_argument("id", help="the todo id the claim cites")
    sp.set_defaults(fn=cmd_commission_check)

    sp = sub.add_parser(
        "plan-check",
        help="one plan file's syntax gate (coding-plan "
             "skill): exit 0 with the frontier adoption "
             "will arm when the plan's step blocks, "
             "prerequisites, estimates, and question "
             "sentinels all parse and agree; exit 3 with "
             "one finding per violation when refused "
             "(prose-only steps, undeclared or dangling "
             "prerequisites, requires cycles, steps "
             "with no fan-out or serial exception); "
             "exit 2 when the file cannot be read as "
             "a plan")
    sp.add_argument("plan",
                    help="path to the plan .md file")
    sp.set_defaults(fn=cmd_plan_check)

    sp = sub.add_parser(
        "goal-check",
        help="one goal record's stall verdict: exit 0 on "
             "track, retired, or gone, exit 3 with a "
             "STALLED line when stalled (run by the goal "
             "ping entry the record armed about itself, "
             "contract 11)")
    sp.add_argument("slug", help="the goal slug")
    sp.set_defaults(fn=cmd_goal_check)

    sub.add_parser("print-schedule").set_defaults(
        fn=cmd_print_schedule)
    return _apply_argv_contract(p)
