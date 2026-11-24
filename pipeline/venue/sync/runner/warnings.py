"""Output-name risk warnings at launch, extracted from
main() along the function's own seam (it was a closure over
the launch locals; main.py sits in the line-cap creep band
and the launch-lock wiring needed the room —
the band doctrine is decompose, not route around).
"""

import sys

from .pull import output_name_overlaps
from .records import save_record


def name_warnings(rec: dict, session: str, run_id: str, outputs: list) -> list:
    # Output-name risk, named at launch while a rename
    # is still cheap: a declared basename a live run on
    # this session also declares is safe in the per-run
    # out dirs, but two payloads writing it cwd-relative
    # share the session root and interleave silently
    # (defect routed). Advisory only — it
    # blocks nothing; finalize's contention guard is
    # the backstop. The computation is guarded at every
    # level: a warning that can raise is a gate.
    try:
        found = output_name_overlaps(session, run_id, outputs)
    except Exception:  # noqa: BLE001
        return []
    if found:
        rec["output_name_warnings"] = found
        save_record(rec)
        for warning in found:
            print(f"warning: output name {warning['name']!r} is also declared by live run {warning['shared_with']} on {session} — if both payloads write it cwd-relative, the root copy is unattributable and finalize will flag it contended rather than collect it", file=sys.stderr)
    return found
