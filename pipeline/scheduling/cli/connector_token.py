"""The connector-token command: mint, re-issue, or revoke a
token caller — one registry (contract 01) serving both
authenticated surfaces, /tools and /ops (§10.1). The raw
token prints once here; only its SHA-256 reaches the live
config, written through the /ops endpoint and read fresh
per call, so changes are immediate. Re-issuing a name mints
a fresh token and replaces its hash — the old token stops
verifying the moment the write lands.

Bootstrap: the write that creates the FIRST token cannot
itself be authenticated. When the acting caller holds no
token and the server refuses the write as unauthenticated
(or is unreachable — the quiesced freeze state), this verb
falls back to a direct staged write of the live config it
already read from disk, through the platform writer. A
refusal presented WITH a token never falls back: an
authenticated refusal is an answer, not a bootstrap.

Store mirror: the unified registry store (pipeline/
registry) carries the same token-caller map as one of its
sections, and other consumers authenticate against the
store. After a write lands — by either path — this verb
mirrors the config's connector.callers into the store's
token_callers through the store's own staged writer, and
reports success only once the mirror lands. A mirror
failure fails the verb: the config has landed, the store
is out of sync, and the message says so — provisioning
never completes half-synced in silence."""
import copy
import hashlib
import importlib.util
import json
import os
import secrets as _secrets
import sys

from cli import paths as _paths
from cli.common import ROOT
from cli.ops_client import (
    _ops_caller, _ops_post, _ops_report, _take_flag,
    resolve_ops_token, store_ops_token)

VALID_SCOPES = ("read", "write-state", "send", "bridge", "exec")


def apply_mint(config, name, scopes):
    """Mint (or re-issue) one caller in a live-config dict:
    replaces the caller's entry with a fresh token's hash.
    Returns the raw token — shown once, never stored here."""
    token = _secrets.token_urlsafe(32)
    section = config.setdefault("connector", {})
    callers = section.setdefault("callers", {})
    callers[name] = {
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "scopes": list(scopes),
    }
    return token


def apply_revoke(config, name):
    """Remove one caller from a live-config dict. Returns
    False when the caller is absent."""
    callers = (config.get("connector") or {}).get("callers") or {}
    if name not in callers:
        return False
    del callers[name]
    return True


def _direct_write(config_path, config):
    """The bootstrap write: the platform writer's staged
    protocol, in this process, used only when no token could
    authenticate the /ops write. Returns 0 on success."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", _paths.PLATFORM_WRITER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.staged_write(
            config_path, (json.dumps(config, indent=2) + "\n").encode("utf-8"))
    except module.WriterError as exc:
        print(f"connector-token: bootstrap write failed: {exc.name}: {exc.detail}",
              file=sys.stderr)
        return 1
    print("connector-token: wrote the live config directly "
          "(bootstrap — no token could authenticate the /ops write)")
    return 0


def _load_registry():
    """Load the unified registry package (pipeline/registry)
    by path under a private package name — the tree's
    standing cross-package seam, with no collision against
    any `registry` name the embedding already holds.
    Returns the package's (config, store) modules."""
    pkg_dir = os.path.join(_paths.PIPELINE_ROOT, "registry")
    name = "pipeline_registry"
    pkg = sys.modules.get(name)
    if pkg is None:
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(pkg_dir, "__init__.py"),
            submodule_search_locations=[pkg_dir])
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[name] = pkg
        spec.loader.exec_module(pkg)
    return (importlib.import_module(f"{name}.config"),
            importlib.import_module(f"{name}.store"))


def _sync_registry_store(config):
    """Mirror a just-written live config's connector
    callers into the unified registry store's token_callers
    section — wholesale equality, through the store's own
    staged writer (Registry.save). Returns 0 on success;
    on any failure, prints the out-of-sync warning and
    returns 1: the config has landed, the store has not,
    and the verb must not report success over that gap."""
    try:
        reg_config, reg_store = _load_registry()
        values, _sources = reg_config.resolve_config()
        store_path = values["store_path"]
        registry = reg_store.Registry.load(store_path)
        callers = (config.get("connector") or {}).get("callers") or {}
        registry.data["token_callers"] = copy.deepcopy(callers)
        registry.save(store_path)
    except Exception as exc:  # noqa: BLE001 - every failure is the same verdict
        print(f"connector-token: the live config was written, but the "
              f"unified registry store could not be updated ({exc}) — "
              "the store is OUT OF SYNC with the live config; re-run "
              "this command or back-fill the store's token_callers "
              "from the config's connector.callers",
              file=sys.stderr)
        return 1
    return 0


def cmd_connector_token(argv):
    """Mint, re-issue, or revoke a token caller
    (server/serving/connector.py): the raw token prints once here;
    only its SHA-256 reaches the live config, read fresh per
    call, so changes are immediate."""
    revoke = "--revoke" in argv
    argv = [a for a in argv if a != "--revoke"]
    save_client = "--save-client" in argv
    argv = [a for a in argv if a != "--save-client"]
    scopes = []
    if "--scopes" in argv:
        i = argv.index("--scopes")
        scopes = [s for s in argv[i + 1].split(",") if s]
        argv = argv[:i] + argv[i + 2:]
    caller = _ops_caller(argv)
    _c, argv = _take_flag(argv, "--caller")
    if not argv:
        print("usage: sched connector-token [--caller X] <name> "
              "--scopes a,b [--save-client] | --revoke")
        return 2
    name = argv[0]
    config_path = os.path.join(ROOT, "config.json")
    try:
        with open(config_path, encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, ValueError):
        config = {}
    if revoke:
        if not apply_revoke(config, name):
            print(f"connector-token: no such caller: {name}")
            return 1
        token = None
    else:
        if not scopes or not set(scopes) <= set(VALID_SCOPES):
            print(f"connector-token: --scopes must name some of "
                  f"{sorted(VALID_SCOPES)}")
            return 2
        token = apply_mint(config, name, scopes)
    payload = {"caller": caller, "op": "write", "path": config_path,
               "content": json.dumps(config, indent=2) + "\n"}
    result = _ops_post(payload, http_timeout=30)
    report = _ops_report("write", result)
    if report != 0:
        # Bootstrap only when the acting caller could not
        # authenticate at all: unreachable server, or an
        # unauthenticated refusal while holding no token.
        unauthenticated = (
            result is None
            or (isinstance(result, dict)
                and result.get("error") == "unauthenticated"))
        if unauthenticated and resolve_ops_token(caller) is None:
            report = _direct_write(config_path, config)
        if report != 0:
            return report
    # The config has landed, by either path. The token-home
    # save rides next, then the registry store mirror;
    # success is reported only once the mirror lands, so a
    # mint or revoke never completes half-synced.
    saved_path = None
    if not revoke and save_client:
        saved_path = store_ops_token(name, token)
    if _sync_registry_store(config) != 0:
        return 1
    if revoke:
        print(f"revoked connector caller: {name} (effective immediately)")
    else:
        print(f"connector caller {name} (scopes: {', '.join(scopes)}) "
              "— token, shown once:")
        print(token)
        if saved_path is not None:
            print(f"saved to this client's token home: {saved_path}")
        print("deliver it through the secure route; the server keeps only its hash")
    return 0
