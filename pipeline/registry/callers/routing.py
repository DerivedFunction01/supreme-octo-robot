"""Caller→chat routing (contract 01; SCH8's table half).

The resolution rule itself — destination chat is data
inside a record; the wake address is a separate routing
decision — is contract 05's. This module is the tables it
resolves against, folded into the one registry store:

- bridge-wake owners: which owning thread a bridged read
  tool's result belongs to. A caller with no entry leaves
  its items unresolved — the minter names them and leaves
  them queued rather than guessing a thread.
- notify routes: the liveness escalation's destinations.
  Machinery and unknown callers fall back to `main`.
- restart-reconcile owners: the runner-caller→chat table
  the restart reconcile resolves by its own grammar —
  exact caller, else the caller's namespace (the segment
  before its first colon), else a caller prefix. A caller
  with no entry in any of the three is UNRESOLVED,
  reported to the main chat, never guessed.
"""

from __future__ import annotations


def _table(registry, name) -> dict:
    table = registry.routing().get(name)
    return table if isinstance(table, dict) else {}


# -- bridge-wake owners --------------------------------------

def wake_owner(registry, caller) -> str | None:
    """The owning chat for a caller's bridged read tools,
    or None when the caller has no entry (unresolved —
    never guessed)."""
    owners = _table(registry, "bridge_wake_owners").get("owners")
    if isinstance(owners, dict):
        row = owners.get(caller)
        if isinstance(row, dict) and isinstance(row.get("chat"), str):
            return row["chat"]
    return None


def wake_drain(registry) -> str | None:
    """The bridge-drain episode's chat, when the table
    carries one."""
    drain = _table(registry, "bridge_wake_owners").get("drain")
    if isinstance(drain, dict) and isinstance(drain.get("chat"), str):
        return drain["chat"]
    return None


# -- notify routes -------------------------------------------

def notify_route(registry, caller) -> str | None:
    """The escalation chat for a caller: its own route when
    routed, else the table's `main`. None only when the
    table itself carries no main."""
    table = _table(registry, "notify_routes")
    routes = table.get("routes")
    if isinstance(routes, dict) and isinstance(routes.get(caller), str):
        return routes[caller]
    main = table.get("main")
    return main if isinstance(main, str) else None


# -- restart-reconcile owners --------------------------------

def restart_owner(registry, caller) -> str | None:
    """Resolve a runner caller to its owning chat by the
    table's grammar: an exact caller under owners first,
    else the caller's namespace under namespaces, else a
    caller prefix under prefixes. None is UNRESOLVED —
    reported to the main chat, never guessed."""
    table = _table(registry, "restart_owners")
    if not isinstance(caller, str) or not caller:
        return None
    for key in ("owners", "namespaces", "prefixes"):
        rows = table.get(key)
        if not isinstance(rows, dict):
            continue
        if key == "owners":
            probe = caller
        elif key == "namespaces":
            probe = caller.partition(":")[0]
        else:
            probe = None
        if key == "prefixes":
            for prefix, row in rows.items():
                if isinstance(prefix, str) and caller.startswith(prefix) \
                        and isinstance(row, dict) \
                        and isinstance(row.get("chat"), str):
                    return row["chat"]
            continue
        row = rows.get(probe)
        if isinstance(row, dict) and isinstance(row.get("chat"), str):
            return row["chat"]
    return None
