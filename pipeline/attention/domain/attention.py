"""Pure domain rules for owner-attention (spec/backend/02-domain).

Plain dicts in, plain values out; labels live in services.

The implementation is split along its seams — catalogs
(the shipped registries and staleness), fields_templates
(fields and post templates), rules (the rule set and the
verb vocabulary), logic (the condition grammar and
the decision engine), and stop_verdict (the stop
classifier over the catalogs' enumeration) — and this
module re-exports the whole surface, so existing
imports of attention.domain.attention are unchanged.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta  # noqa: F401

from .catalogs import *  # noqa: F401,F403
from .catalogs import _code  # noqa: F401
from .fields_templates import *  # noqa: F401,F403
from .fields_templates import _field, _template  # noqa: F401
from .logic import *  # noqa: F401,F403
from .logic import _where_classes  # noqa: F401
from .rules import *  # noqa: F401,F403
from .rules import _action_rule, _rule  # noqa: F401
from .stop_verdict import *  # noqa: F401,F403
