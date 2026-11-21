"""Staffing row builders (spec §1.11): the fleet-
independent defect classes — phantom stops, blocked
states, unrouted defects, serial plans, owner-waiting —
and, from Step 2 of the supervision plan, the venue
family-concurrency rows and the plan-frontier
shortfall rows the registry contracts declare.

The implementation is split by measure family —
staffing_common (the row shape and shared helpers),
staffing_blocked, staffing_waits, and staffing_venue —
and this module re-exports the whole surface, so
existing imports of
attention.services.measure.staffing_rows are unchanged.
"""

from __future__ import annotations

import re  # noqa: F401
from datetime import UTC, datetime  # noqa: F401

from attention.services import programmes  # noqa: F401
from attention.services.measure import registry, venue  # noqa: F401
from attention.services.reads import digest as digest_mod  # noqa: F401
from attention.services.reads import model  # noqa: F401

from .staffing_blocked import (  # noqa: F401
    _CITATION_RE,
    _CLAIM_RE,
    _blocked_rows,
    _blocked_todos,
    _claims_owner_order,
    _find_citation,
    _phantom_rows,
    _unrouted_rows,
)
from .staffing_common import (  # noqa: F401
    KIND_LABELS,
    OWNER_THREADS,
    WORKHORSE_TERMS,
    _as_dt,
    _names_workhorse,
    _row,
)
from .staffing_venue import (  # noqa: F401
    _family_rows,
    _frontier_rows,
    _orphan_rows,
    _programme_armed,
    _terminal_rows,
)
from .staffing_waits import (  # noqa: F401
    _armed_rows,
    _latest_lane_stamp,
    _owner_waiting_rows,
    _record_rows,
    _worktree_rows,
)
