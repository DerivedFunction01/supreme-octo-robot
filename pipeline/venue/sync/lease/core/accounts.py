"""Accounts and per-account budgets (venue rework).

Caps are tied per (venue, account) — there are no flat,
venue-level cap keys:

- `accounts` block: {venue: [{"id", "label"?, "token_file"?}]}.
  The first entry is the venue's default account. Absent the
  block, the venue has one account — the primary, id "primary" —
  whose credential is the funnel's live token.
- `budgets` block: {venue: {account: {"daily", "monthly",
  "standing_daily"}}} in the served caps key names. Resolution
  for (venue, account), per key: the budgets entry, then None
  (no cap). Every venue inherits this one generic budget shape:
  an account whose caps are all None is unlimited, and a venue
  kind can be budget-less by nature (below) — those are the
  shape's two states, not separate mechanisms.

A non-default account is brought in by naming it in `accounts`
and placing its credential file at `token_file` (relative to
var/). This layer reads only the file's presence, never its
contents — the stored credential stays under the auth guard's
rules (docs/auth.md). Dialing a non-primary account (its balance,
minting under its credential) needs account-scoped funnel
invocation and is a separate adapter build; until then such an
account is fully addressable — budgets, spend attribution, the
guard, the editor — with its balance served as null.

Budgets are per venue and per account, never one mass (FU-2):
the served budget set spans every venue the config names. A
venue kind can also be budget-less by nature: a local machine
venue is the operator's own hardware — nothing is metered,
there is no balance and nothing to throttle — so it has NO
budget at all, and the served set says so with a null budget
rather than zero or fabricated figures.
"""

from pathlib import Path

from . import foundation

PRIMARY_ACCOUNT = "primary"


def venue_accounts(cfg: dict, venue: str) -> list[dict]:
    """The venue's configured accounts, in config order. Absent
    or malformed config yields the single primary account."""
    block = cfg.get("accounts")
    entries = block.get(venue) if isinstance(block, dict) else None
    out = []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]:
                out.append({
                    "id": entry["id"],
                    "label": entry.get("label") if isinstance(entry.get("label"), str) else entry["id"],
                    "token_file": entry.get("token_file") if isinstance(entry.get("token_file"), str) else None,
                })
    if not out:
        out = [{"id": PRIMARY_ACCOUNT, "label": PRIMARY_ACCOUNT, "token_file": None}]
    return out


def default_account(cfg: dict, venue: str) -> str:
    """The venue's default account id: the first configured
    account, or the primary when none is configured."""
    return venue_accounts(cfg, venue)[0]["id"]


def caps_for(cfg: dict, venue: str, account: str) -> dict:
    """The served caps for one (venue, account): the budgets
    block's entry, per key, or None (no cap) where the entry or
    the key is absent. Caps exist only per (venue, account) —
    no flat key is consulted for any venue or account. The
    shape is grants._served_caps' shape, unchanged:
    {"daily", "monthly", "standing_daily"}, each a
    non-negative number or None (no cap)."""
    block = cfg.get("budgets")
    entry = None
    if isinstance(block, dict):
        per_venue = block.get(venue)
        if isinstance(per_venue, dict) and isinstance(per_venue.get(account), dict):
            entry = per_venue[account]
    out = {}
    for key in ("daily", "monthly", "standing_daily"):
        out[key] = entry[key] if entry is not None and key in entry else None
    return out


# Venue kinds with no budget by nature: a local machine venue
# is unmetered and unlimited, so no balance, spend, or caps
# exist for it — the served budget set carries the venue with
# a null budget (honest absence), never zero figures.
NO_BUDGET_VENUES = frozenset({"local"})


def venue_budgetless(venue: str) -> bool:
    """Whether the venue kind carries no budget at all (a local
    machine venue). A budget-less venue has no accounts in the
    budget set and no caps to edit."""
    return venue in NO_BUDGET_VENUES


def configured_venues(cfg: dict) -> list[str]:
    """Every venue the config names, in config order: the
    `accounts` block's venues first, then any venue named only
    in `budgets`. The budget set spans exactly these venues
    plus the home venue the caller adds."""
    out: list[str] = []
    for block_name in ("accounts", "budgets"):
        block = cfg.get(block_name)
        if isinstance(block, dict):
            for venue in block:
                if isinstance(venue, str) and venue and venue not in out:
                    out.append(venue)
    return out


def credential_status(repo: Path, cfg: dict, venue: str, account: str) -> str:
    """Whether the account's credential is in place: "live" for
    the primary account (the funnel's own stored token),
    "credential-present" when a configured token file exists
    under var/, "not-brought-in" otherwise. Presence only —
    contents are never read here."""
    if account == PRIMARY_ACCOUNT:
        return "live"
    for entry in venue_accounts(cfg, venue):
        if entry["id"] == account:
            token_file = entry.get("token_file")
            if token_file and (foundation.var_dir(repo) / token_file).is_file():
                return "credential-present"
            return "not-brought-in"
    return "not-brought-in"
