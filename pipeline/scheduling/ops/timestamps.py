#!/usr/bin/env python3
"""Scheduling ops' shared clock: the one Z-stamp provider.

Every ops watch and driver stamps its records with the
same UTC second form — ``YYYY-MM-DDTHH:MM:SSZ`` — and the
stamp had a private copy in each watch module. This module
is the home (one owner per helper): watches bind it by path
through the same spec-load seam they use for ``ops/paths``,
and the served form never changes here without every
consumer moving at once.
"""

import time


def zstamp_now() -> str:
    """Now as a UTC Z-stamp, second precision."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
