"""Programme contracts: the wb-carried goal contract is
the single source for a declaration's rule text and
cadence — the registry row points at the contract file
and the slow loop refreshes the sourced fields from it."""

from __future__ import annotations

import re
from pathlib import Path

_FIELDS = {
    "Programme": "programme",
    "Objective": "objective",
    "Complete when": "complete_when",
    "Blocked only when": "blocked_only_when",
    "Work record": "work_record",
    "Cadence": "cadence_text",
    "Continuation": "continuation_text",
}


def parse(text: str) -> dict:
    """The contract's fields, from its `- Key: value` lines."""
    fields: dict = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"-\s+([A-Za-z ]+):\s+(.*)", line.strip())
        if match and match.group(1) in _FIELDS:
            current = _FIELDS[match.group(1)]
            fields[current] = match.group(2).strip()
        elif current and line.strip():
            fields[current] = (fields[current] + " " + line.strip()).strip()
    cadence = re.search(r"every (\d+) minutes", fields.get("cadence_text", ""))
    if cadence:
        fields["cadence_minutes"] = int(cadence.group(1))
    return fields


def sync(state: dict) -> bool:
    """Refresh contract-sourced declaration fields in place."""
    changed = False
    for programme in state.get("programmes") or []:
        path = programme.get("contract_path")
        if not path:
            continue
        try:
            fields = parse(Path(path).read_text())
        except OSError:
            continue
        if not fields.get("objective"):
            continue
        if programme.get("rule_text") != fields["objective"]:
            programme["rule_text"] = fields["objective"]
            changed = True
        if (
            fields.get("cadence_minutes")
            and programme.get("cadence_minutes") != fields["cadence_minutes"]
        ):
            programme["cadence_minutes"] = fields["cadence_minutes"]
            changed = True
        if programme.get("contract") != fields:
            programme["contract"] = fields
            changed = True
    return changed
