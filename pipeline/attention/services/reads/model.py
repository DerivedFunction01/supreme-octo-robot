"""The model builders: one function per API section.

Every derivation and label is made here, display-ready;
presence filters here, server-side (API.md principles 2–4).

The implementation is split by builder family — labels
(the label registries and read helpers), verbs (the
verb derivation and staleness), items (the item view
and the open-item sets), and sections (the per-section
builders) — and this module re-exports the whole
surface, so existing imports of
attention.services.reads.model are unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta  # noqa: F401

from attention.domain import attention as dom  # noqa: F401
from attention.services.dispatch import dispatch as dispatch_mod  # noqa: F401
from attention.services.waits import basis, engine, fulfillment  # noqa: F401
from attention.services.waits import facts as facts_mod  # noqa: F401
from attention.settings import Settings  # noqa: F401

from .items import *  # noqa: F401,F403
from .items import _live_items  # noqa: F401
from .labels import *  # noqa: F401,F403
from .labels import _iso, _kind_label  # noqa: F401
from .sections import *  # noqa: F401,F403
from .verbs import *  # noqa: F401,F403
from .verbs import _shadow_hint, _verb_entry  # noqa: F401
