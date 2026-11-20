"""Ownership/deploy-class attribution and the
choice-kit artifact verbs."""
from lib import kit as kit_mod  # noqa: E402
from lib import registry as reg  # noqa: E402
from wbcli.context import Ctx  # noqa: E402
from wbcli.context import REPO_ROOT  # noqa: E402
from wbcli.context import _print  # noqa: E402

KIT_TEMPLATE_DIR = REPO_ROOT / "templates" / "choice-kit"


def cmd_set_owner(args):
    ctx = Ctx(args)
    thread = None if args.clear else args.thread
    label = None if args.clear else args.label
    entry = reg.set_owner(
        ctx.db_path, args.id, thread, label, actor="cli")
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_set_class(args):
    ctx = Ctx(args)
    entry = reg.set_deploy_class(
        ctx.db_path, args.id, args.deploy_class, actor="cli")
    ctx.regenerate()
    _print(entry)
    return 0


def cmd_artifact_new(args):
    ctx = Ctx(args)
    spec = None
    if args.spec:
        spec = kit_mod.load_spec(args.spec)
    entry = kit_mod.create_kit(
        ctx.db_path, ctx.layout, args.slug,
        title=args.title, spec=spec,
        template_dir=KIT_TEMPLATE_DIR,
        plan_ref=args.plan_ref,
        owner_thread=args.owner_thread,
        owner_label=args.owner_label,
        deploy_class=args.deploy_class)
    ctx.regenerate()
    _print(entry)
    print()
    print("next steps:")
    print(f"  1. edit the study spec: "
          f"{entry['entry_dir']}/spec.json")
    print(f"  2. re-render the page: wb artifact build "
          f"{args.slug}")
    print(f"  3. publish {entry['entry_dir']}/index.html "
          f"as a static artifact (the agent's "
          f"artifact-tool step — wb never publishes)")
    return 0


def cmd_artifact_build(args):
    ctx = Ctx(args)
    result = kit_mod.build_kit(
        ctx.db_path, ctx.layout, args.slug,
        template_dir=KIT_TEMPLATE_DIR)
    ctx.regenerate()
    _print(result)
    return 0
