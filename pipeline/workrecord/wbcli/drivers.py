"""The driver-facing verbs: the active-plan
declaration, the doctor, and the progress/goal
stall-verdict reads the scheduler entries run."""
import os
from pathlib import Path

from lib.derived import active as active_mod  # noqa: E402
from lib.writes import goals as goals_mod  # noqa: E402
from lib import progress as progress_mod  # noqa: E402
from lib.progress import attention as \
    attention_mod  # noqa: E402
from lib.progress import schedule as \
    progress_schedule_mod  # noqa: E402
from lib.discovery.manifest import load_manifest  # noqa: E402
from lib.plans import bundles as bundle_parser  # noqa: E402
from lib.plans import commissions as commissions_mod  # noqa: E402
from lib.discovery.sweep import sweep  # noqa: E402
from wbcli.context import PlansCtx  # noqa: E402
from wbcli.context import REPO_ROOT  # noqa: E402
from wbcli.context import _doctor_mod  # noqa: E402
from wbcli.context import _print  # noqa: E402
from wbcli.context import _sweep_roots  # noqa: E402

# Portability exception (gate component directive):
# portability-exception: .plans/active.yaml — the harness's standing active-plan declaration file, the data contract of the activate verb documented below, not a reference to a specific plan
def cmd_activate(args):
    """Active-plan declaration (repo-home spec §17.2 step
    1): set/clear/show `.plans/active.yaml` in the resolved
    project's plans dir. Run inside a worktree, this is
    THAT worktree's declaration — activeness is
    per-worktree and the plans dir resolves from the cwd's
    own workbench.yaml."""
    ctx = PlansCtx(args)
    if args.clear:
        _print(active_mod.clear_active(ctx.plans_dir))
        return 0
    if args.bundle:
        result = active_mod.set_active(
            ctx.plans_dir, args.bundle, plan=args.plan,
            since=args.since)
        _print(result)
        return 0
    branch = None
    try:
        import subprocess
        out = subprocess.run(
            ["git", "-C", str(ctx.root), "rev-parse",
             "--abbrev-ref", "HEAD"], capture_output=True,
            text=True, timeout=5)
        name = out.stdout.strip()
        branch = name if name and name != "HEAD" else None
    except Exception:
        branch = None
    resolution = active_mod.resolve_active(
        ctx.plans_dir, branch=branch)
    resolution["branch"] = branch
    resolution["plans_dir"] = str(ctx.plans_dir)
    _print(resolution)
    return 0


def cmd_doctor(args):
    """Read-only consistency checks over every swept
    project (wb-doctor plan): broken todos, plans not
    archived, conflicting status — all derived by the
    evaluation package's doctor from the same functions
    the feeds use. --post diffs against the previous
    run's state and posts one digest through
    dispatch.messages when the finding set changed. The
    --post state and message-store paths resolve under
    this service's own state dir, overridable by the
    WB_DOCTOR_STATE_PATH / WB_MESSAGES_DB_PATH seams."""
    doctor_mod = _doctor_mod()
    roots = _sweep_roots(args)
    result = sweep(roots)
    findings = doctor_mod.run_checks(result.projects)
    for f in findings:
        print(f"[{f['project']}] {f['check']} — "
              f"{f['subject']}: {f['detail']}")
    if findings:
        print(f"wb doctor: {len(findings)} finding(s) "
              f"across {len(result.projects)} project(s)")
    else:
        print("wb doctor: clean")
    if args.post:
        own = load_manifest(REPO_ROOT / "workbench.yaml")
        state_path = Path(os.environ.get(
            "WB_DOCTOR_STATE_PATH",
            REPO_ROOT / "state" / "doctor-findings.json"))
        messages_db = Path(os.environ.get(
            "WB_MESSAGES_DB_PATH",
            REPO_ROOT / "state" / "messages.db"))
        summary = doctor_mod.run_post(
            result.projects, findings=findings,
            state_path=state_path,
            messages_db=messages_db,
            harness_slug=own.slug)
        if summary["posted"]:
            print(f"wb doctor: digest posted "
                  f"(message {summary['message_id']}) — "
                  f"{len(summary['new'])} new, "
                  f"{len(summary['resolved'])} resolved")
        else:
            print("wb doctor: finding set unchanged — "
                  "no digest posted")
    return 1 if findings else 0


def cmd_progress(args):
    """The progress driver's single read: every swept
    project's armed todos with their derived stall
    verdicts (lib/progress.py), as JSON. Read-only —
    acting on a verdict (checkpointing through
    `wb todo set --note`, nudging, surfacing) is the
    driver's business. The schedules themselves are
    the harness's own mechanism now: arming a todo
    writes its attention armed row in the same call
    (lib/progress/attention.py), and `--sync-entries`
    deletes every wb-progress scheduler entry — the
    scheduler-entry rendering is retired (Step 6),
    so the sync is the retirement sweep now, run only
    at the coordinated cutover. Sweep roots resolve
    through the same seam as the doctor's."""
    roots = _sweep_roots(args)
    result = sweep(roots)
    if args.sync_entries:
        _print({"sync": progress_schedule_mod.sync_all(
                    result.projects),
                "sync_attention":
                    attention_mod.sync_all(
                        result.projects)})
        return 0
    projects = []
    for project in result.projects:
        plans_dir = project.manifest.plans
        if plans_dir is None:
            continue
        report = progress_mod.project_progress(plans_dir)
        projects.append({"slug": project.slug, **report})
    _print({"projects": projects})
    return 0


def cmd_progress_check(args):
    """One armed todo's stall verdict, for the scheduler
    entry the harness wrote when the todo armed: exit 0
    on track / disarmed / gone, exit 3 with a STALLED
    line when the derivation says it stalled — the
    entry's failure report carries the line as a ping.
    A root that no longer exists is the gone case, not
    a crash: the project (or a fixture's tempdir) went
    away, so the check exits 0 and the doctor flags the
    orphaned entry.

    Context rule: a todo id names one project's store
    only, so a verdict is only ever read from a pinned
    context. The harness's own entries pin --root; a
    reader who resolves the context ambiently (the cwd
    walk-up) and finds the id absent has learned
    nothing — the id may live in any other project —
    so an ambient miss fails loud (exit 2, naming the
    resolved project) instead of returning the pinned
    path's quiet orphan line. A pinned miss keeps the
    quiet zero: there the absence is a fact about that
    project, and the doctor reconciles the orphan. An
    ambient HIT is a true read and verdicts normally."""
    root_arg = getattr(args, "root", None)
    if root_arg and not Path(root_arg).is_dir():
        print(f"{args.id}: project root gone — "
              f"entry orphaned (the doctor reconciles)")
        return 0
    ctx = PlansCtx(args)
    code, line = progress_schedule_mod.check_todo(
        ctx.plans_dir, args.id)
    pinned = bool(root_arg or getattr(args, "project",
                                      None)
                  or getattr(args, "db", None))
    found = any(t.get("id") == args.id
                for t in bundle_parser.list_todos(
                    ctx.plans_dir))
    if not pinned and not found:
        slug = ctx.project_meta["slug"] \
            if ctx.project_meta else "?"
        print(f"{args.id}: not found in project "
              f"{slug} — the context came from the "
              f"working directory, and a todo id names "
              f"one project's store only; pin the "
              f"programme context (--root or --project) "
              f"for a verdict")
        return 2
    print(line)
    return code


def cmd_commission_check(args):
    """One claimed commission's verdict against the
    record (channel-indistinguishability cure):
    exit 0 with a COMMISSION line when the
    cited todo is a commission of record (provenance
    planted through the writers' plant_commission),
    exit 3 with a NOT A COMMISSION line when the record
    holds no such entry or the entry carries no
    provenance — a claim carried only by a chat channel
    is not a commission, however often repeated.

    Context rule, mirroring progress-check's: a todo id
    names one project's store only, so an ambient
    (cwd-resolved) miss fails loud (exit 2, naming the
    resolved project) instead of ruling — the id may
    live in any other project. A pinned miss is a fact
    about that project and rules not-a-commission. A
    pinned root that no longer exists holds no record,
    so nothing in it can verify: exit 3."""
    root_arg = getattr(args, "root", None)
    if root_arg and not Path(root_arg).is_dir():
        print(f"{args.id}: NOT A COMMISSION — the "
              f"pinned project root is gone, so no record "
              f"entry can resolve this claim")
        return 3
    ctx = PlansCtx(args)
    block = commissions_mod.verify_commission(
        ctx.plans_dir, args.id)
    pinned = bool(root_arg or getattr(args, "project",
                                      None)
                  or getattr(args, "db", None))
    if not pinned and block["title"] is None \
            and block["path"] is None:
        slug = ctx.project_meta["slug"] \
            if ctx.project_meta else "?"
        print(f"{args.id}: not found in project "
              f"{slug} — the context came from the "
              f"working directory, and a todo id names "
              f"one project's store only; pin the "
              f"programme context (--root or --project) "
              f"for a verdict")
        return 2
    if block["verdict"] == "commission":
        print(f"{args.id}: COMMISSION — "
              f"{block['title']!r}, commissioned by "
              f"{block['commissioned_by']} at "
              f"{block['commissioned_at']} "
              f"(status: {block['status']})")
        return 0
    print(f"{args.id}: NOT A COMMISSION — "
          f"{block['reason']}")
    return 3


def cmd_plan_check(args):
    """One plan file's syntax gate (coding_plan
    skill): exit 0 with the frontier adoption will
    arm when the plan's step blocks, prerequisites,
    estimates, and question sentinels all parse and
    agree; exit 3 with one finding per violation when
    refused; exit 2 when the named file cannot be
    read as a plan at all. The check itself is
    lib/plans/plan_check — the parser's grammar,
    composed, never re-read here. The file names its
    own context: its .plans dir is the project scope
    its prerequisites resolve against, the way the
    other check verbs resolve against their pinned
    project."""
    from lib.plans import plan_check as plan_check_mod
    path = Path(args.plan)
    if not path.is_file():
        print(f"plan-check: no such plan file: "
              f"{args.plan}")
        return 2
    if path.suffix != ".md":
        print(f"plan-check: not a plan file "
              f"(expected a .md plan): {args.plan}")
        return 2
    try:
        result = plan_check_mod.check_plan_file(path)
    except (OSError, UnicodeDecodeError) as e:
        print(f"plan-check: cannot read {args.plan}: {e}")
        return 2
    findings = result["findings"]
    if findings:
        for f in findings:
            print(f"{path.name}: {f}")
        print(f"wb plan-check: {path.name} — "
              f"{len(findings)} finding(s), plan refused")
        return 3
    print(f"wb plan-check: {path.name} — clean")
    print("frontier (adoption arms):")
    for entry in result["frontier"]:
        todos = "|".join(entry["todos"])
        suffix = " (serial)" if entry["serial"] else ""
        print(f"  step {entry['step']} — {todos}{suffix}")
    return 0


def cmd_goal_check(args):
    """One goal record's stall verdict, for the scheduler
    entry the record armed about itself (contract 11):
    exit 0 on track / retired / gone, exit 3 with a
    STALLED line when the derivation says it stalled —
    the entry's failure report carries the line as a
    ping. The store is the service's own (lib/goals'
    default path, WB_GOALS_FILE when named), never a
    project store: a goal slug names one record in the
    one goal store, so no context pinning applies."""
    store = goals_mod.GoalStore()
    code, line = goals_mod.check_goal(store, args.slug)
    print(line)
    return code


def cmd_print_schedule(args):
    print("# Staleness check for one project — run by hand or")
    print("# hand this definition to the platform scheduler.")
    print("# (Scheduling itself is a platform concern; the")
    print("# harness builds the tool, not the schedule.)")
    print()
    print("[systemd timer]")
    print("OnCalendar=daily")
    print(f"ExecStart={REPO_ROOT}/.venv/bin/python "
          f"{REPO_ROOT}/wb --project <slug> stale")
    print()
    print("[cron]")
    print(f"17 6 * * * {REPO_ROOT}/.venv/bin/python "
          f"{REPO_ROOT}/wb --project <slug> stale")
    return 0
