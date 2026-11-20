#!/usr/bin/env python3
"""`attn` — the lane's CLI over the api/1 posting contract
(API.md). Posts are caller-attributed; idempotency keys
are generated here so a lane never hand-rolls one."""

import argparse
import json
import sys
import uuid
from pathlib import Path

try:
    from attention import client
except ImportError:  # direct-file execution, not -m
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "attention_paths", Path(__file__).resolve().parent / "paths.py"
    )
    _paths = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_paths)
    sys.path.insert(0, str(_paths.PIPELINE_ROOT))
    from attention import client


def _emit(result: dict) -> int:
    print(json.dumps(result, indent=2))
    return 0


_HANDLES: list | None = None


def _posting_handle() -> str:
    """The caller's handle in its registered form: a
    bare caller name resolves to its registered @ form
    (and back) instead of being refused."""
    global _HANDLES
    caller = client.caller_name()
    if _HANDLES is None:
        try:
            _HANDLES = [
                h["handle"] for h in client.get_registries().get("handlers", [])
            ]
        except (client.AttentionError, OSError):
            _HANDLES = []
    if caller in _HANDLES:
        return caller
    if "@" + caller in _HANDLES:
        return "@" + caller
    if caller.startswith("@") and caller[1:] in _HANDLES:
        return caller[1:]
    return caller


def _on_behalf(args, payload) -> dict:
    """The post's handle: the caller's own, unless a
    producer posts on a lane's behalf — then the lane is
    the handle and the caller is stamped as posted_by."""
    own = _posting_handle()
    payload["handle"] = args.handle or own
    if args.handle and args.handle != own:
        payload["posted_by"] = own
    return payload


def _parse_option(raw: str) -> dict:
    """One --option value: <id>=<label>, or with the
    effect segment <id>=<label>=<effect> (options shape
    v2 — the effect states what picking the option
    dispatches; when it is absent the server defaults
    it to the verdict-send statement). A bare <id>
    labels itself, as before."""
    parts = raw.split("=")
    opt_id = parts[0]
    if len(parts) >= 3:
        return {
            "id": opt_id,
            "label": "=".join(parts[1:-1]) or opt_id,
            "effect": parts[-1],
        }
    if len(parts) == 2:
        return {"id": opt_id, "label": parts[1] or opt_id}
    return {"id": opt_id, "label": opt_id}


def _post_item(args) -> int:
    payload = {
        "source_ref": args.source_ref,
        "kind": args.kind,
        "title": args.title,
        "status_code": args.status,
        "due_at": args.due_at,
        "source_url": args.source_url or "",
        "clears_at_source": not args.no_clears,
    }
    if args.provenance:
        payload["provenance"] = args.provenance
    if args.option:
        payload["options"] = [_parse_option(raw) for raw in args.option]
    if args.mode:
        payload["mode"] = args.mode
    if args.result_preserving:
        payload["result_preserving"] = True
    if args.repo:
        payload["repo"] = args.repo
    if args.workhorse:
        payload["routing"] = {
            "workhorse": args.workhorse,
            "thread": args.notify_thread or "",
            "evidence": args.evidence or "",
        }
    return _emit(client.post_item(_on_behalf(args, payload)))


def _post_wait(args) -> int:
    payload = {
        "wait_class": args.wait_class,
        "summary": args.summary,
        "program_approved": args.program_approved,
        "reversible": args.reversible,
        "in_budget": args.in_budget,
        "only_blocker": args.only_blocker,
        "idempotency_key": uuid.uuid4().hex,
    }
    return _emit(client.post_wait(_on_behalf(args, payload)))


def _poll_wait(args) -> int:
    return _emit(client.get_wait(args.wait_id))


def _resolve_item(args) -> int:
    payload = {
        "resolution": args.resolution,
        "idempotency_key": uuid.uuid4().hex,
    }
    return _emit(client.resolve_item(args.item_id, payload))


def _dispatch_list(args) -> int:
    return _emit(client.get_undispatched())


def _dispatch_claim(args) -> int:
    return _emit(client.claim_send(args.send_id, client.caller_name()))


def _dispatch_ack(args) -> int:
    return _emit(client.ack_send(args.send_id, client.caller_name(), args.delivery_ref))


def _verify_status(args) -> int:
    return _emit(
        client.verify_status(
            args.handle, args.verdict, args.note or "", client.caller_name()
        )
    )


def _dispatch_fail(args) -> int:
    return _emit(
        client.report_dispatch_failure(args.send_id, client.caller_name(), args.reason)
    )


def _dispatch_suppress(args) -> int:
    return _emit(client.suppress_send(args.send_id, args.reason))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="attn", description="Post to the owner-attention surface."
    )
    verbs = parser.add_subparsers(dest="verb", required=True)
    post = verbs.add_parser("post").add_subparsers(dest="noun", required=True)
    item = post.add_parser("item")
    item.add_argument("--source-ref", required=True)
    item.add_argument("--kind", required=True)
    item.add_argument("--title", required=True)
    item.add_argument("--status")
    item.add_argument("--due-at")
    item.add_argument("--source-url")
    item.add_argument("--no-clears", action="store_true")
    item.add_argument("--provenance", choices=("commission", "offer"))
    item.add_argument(
        "--option",
        action="append",
        help="attached choice, as <id>=<label> or <id>=<label>=<effect>",
    )
    item.add_argument(
        "--mode",
        choices=("single", "multi"),
        help="pick mode for the item's options (default single)",
    )
    item.add_argument("--result-preserving", action="store_true")
    item.add_argument("--repo")
    item.add_argument(
        "--workhorse",
        choices=("scheduler", "workbench", "colab"),
        help="route the item to a workhorse — requires --notify-thread",
    )
    item.add_argument(
        "--notify-thread",
        help="owning thread the routing notifies (required with --workhorse)",
    )
    item.add_argument("--evidence", help="evidence pointer (routing)")
    item.add_argument("--handle", help="post on this lane's behalf (producers)")
    item.set_defaults(run=_post_item)
    wait = post.add_parser("wait")
    wait.add_argument("--class", dest="wait_class", required=True)
    wait.add_argument("--summary", required=True)
    wait.add_argument("--program-approved", action="store_true")
    wait.add_argument("--reversible", action="store_true")
    wait.add_argument("--in-budget", action="store_true")
    wait.add_argument("--only-blocker", action="store_true")
    wait.add_argument("--handle", help="post on this lane's behalf (producers)")
    wait.set_defaults(run=_post_wait)
    verify = verbs.add_parser("verify").add_subparsers(dest="noun", required=True)
    verify_status = verify.add_parser("status")
    verify_status.add_argument("--handle", required=True)
    verify_status.add_argument("--verdict", choices=("verified", "void"), required=True)
    verify_status.add_argument("--note")
    verify_status.set_defaults(run=_verify_status)
    poll = verbs.add_parser("poll").add_subparsers(dest="noun", required=True)
    poll_wait = poll.add_parser("wait")
    poll_wait.add_argument("wait_id")
    poll_wait.set_defaults(run=_poll_wait)
    resolve = verbs.add_parser("resolve").add_subparsers(dest="noun", required=True)
    res_item = resolve.add_parser("item")
    res_item.add_argument("item_id")
    res_item.add_argument("--resolution", choices=("done", "withdrawn"), required=True)
    res_item.set_defaults(run=_resolve_item)
    dispatch = verbs.add_parser("dispatch").add_subparsers(dest="noun", required=True)
    dispatch_list = dispatch.add_parser("list")
    dispatch_list.set_defaults(run=_dispatch_list)
    dispatch_claim = dispatch.add_parser("claim")
    dispatch_claim.add_argument("send_id")
    dispatch_claim.set_defaults(run=_dispatch_claim)
    dispatch_ack = dispatch.add_parser("ack")
    dispatch_ack.add_argument("send_id")
    dispatch_ack.add_argument("--delivery-ref", required=True)
    dispatch_ack.set_defaults(run=_dispatch_ack)
    dispatch_fail = dispatch.add_parser("fail")
    dispatch_fail.add_argument("send_id")
    dispatch_fail.add_argument("--reason", required=True)
    dispatch_fail.set_defaults(run=_dispatch_fail)
    dispatch_suppress = dispatch.add_parser("suppress")
    dispatch_suppress.add_argument("send_id")
    dispatch_suppress.add_argument("--reason", required=True)
    dispatch_suppress.set_defaults(run=_dispatch_suppress)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except client.Refusal as err:
        print(f"attn: {err}", file=sys.stderr)
        return 2
    except client.ApiError as err:
        print(f"attn: {err}", file=sys.stderr)
        for field_error in err.problem.get("field_errors", []):
            print(
                f"attn:   {field_error.get('field')}: {field_error.get('message')}",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
