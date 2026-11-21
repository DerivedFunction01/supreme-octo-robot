"""The feeds assembly itself: the section timer and the
one assembly pass — split from assemble.py along the
compute seam; server.assemble re-exports this surface.
The store is passed in by the package __init__ (the
singleton's owner).
"""

import json
import sys
import time

from lib.util import fan_out

from .. import armed as armed_mod
from .. import config as cfgmod
from .. import feeds, messages_api
from .. import goals as goals_feed_mod
from ..common import CFG, get_sweep

from .documents import (
    _project_document,
    _projects_document,
    status_vocabulary,
)
from .persist import _persist_document, _reclaim

class _AssemblyTimer:
    """Section timings for one assembly, printed to
    stderr as each section closes (`workbench-viewer:
    feeds assembly: <section> took <n>s`, plus a total
    line). The server log is where a slow assembly
    gets diagnosed: the cold assembly's cost was
    estimated blind through three cure rounds, so the
    sections are measured where they run, permanently
    (see the timing note at the top of this module)."""

    def __init__(self):
        self._started = time.monotonic()
        self._last = self._started

    def section(self, name: str) -> None:
        now = time.monotonic()
        print(f"workbench-viewer: feeds assembly: "
              f"{name} took {now - self._last:.2f}s",
              file=sys.stderr)
        self._last = now

    def total(self) -> None:
        print(f"workbench-viewer: feeds assembly: "
              f"total "
              f"{time.monotonic() - self._started:.2f}s",
              file=sys.stderr)



def build_feeds_compute(store) -> dict:
    """The assembly itself: every payload, built once
    over the configured stores. Each section times
    itself to stderr as it closes (see _AssemblyTimer),
    and a successful assembly persists itself for the
    next process's prime (see _persist_document) and
    stores its one serialization in the document
    store (see _store_payload). The projects index
    comes from projects_feed, which reads the repos
    feed's shared cached census — the same enumeration
    every other consumer reads, refreshed on the
    census cache's own TTL; the assembly never walks
    the workspace itself."""
    timer = _AssemblyTimer()
    sweep = get_sweep()
    projects = dict(fan_out(
        lambda p: (p.slug, _project_document(p)),
        sweep.projects,
        workers=CFG["feed_pool_workers"]))
    projects_doc = _projects_document(sweep)
    timer.section("sweep + project documents")
    # The unified project index (SPEC §21): the census
    # summaries join the sweep into canonical project
    # rows. The document carries NO repo detail any
    # more — Code detail (status, files, peeks,
    # datasets, history) is served on demand by the
    # project-scoped Code routes, which is what retires
    # the eager repoDetails assembly and its payload
    # budget machinery wholesale.
    from .. import projects_feed
    projects_index = projects_feed.projects_index_feed()
    timer.section("projects index")
    _reclaim()
    home = feeds.home_feed()
    timer.section("home")
    messages = messages_api.messages_list({})
    timer.section("messages")
    outbox = messages_api.outbox_feed({})
    timer.section("outbox")
    settings = messages_api.effective_settings()
    vocabulary = status_vocabulary()
    armed = armed_mod.armed_feed()
    timer.section("armed")
    goals_block = goals_feed_mod.goals_feed()
    timer.section("goals")
    document = {
        "config": {
            "config": CFG,
            "config_hash": cfgmod.config_hash(CFG),
            "config_file": str(cfgmod.config_path()),
        },
        "home": home,
        "projects": projects_doc,
        "projectFeeds": projects,
        "projectsIndex": projects_index,
        "messages": messages,
        "outbox": outbox,
        "settings": settings,
        "armedRows": armed["rows"],
        "armedSkipped": armed["skipped"],
        "statusVocabulary": vocabulary,
        "goals": goals_block["goals"],
        "goalsSource": goals_block["goalsSource"],
    }
    timer.total()
    # One serialization, to bytes: the holder stores
    # these bytes and the persist writes them — the
    # dumps string dies with the encode, and no second
    # encoded copy stands beside the first at the
    # peak (see the footprint note at the top).
    payload = json.dumps(
        document, ensure_ascii=False).encode("utf-8")
    store.store_payload(payload)
    _persist_document(payload)
    _reclaim()
    return document
