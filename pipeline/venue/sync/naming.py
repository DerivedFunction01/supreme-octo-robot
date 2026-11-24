#!/usr/bin/env python3
"""Generated session names (profile-retirement plan, sentinel 1).

A lease's session name is generated at creation in the GitHub
style — an adjective, a noun, and a two-digit number
(`amber-otter-42`) — legible in the panel, the logs, and approval
cards, and never reused: the caller supplies every name already
taken (live sessions, lease records, the claims and spend
journals), and a candidate that collides is discarded. The word
lists are tracked, fictional-safe data; no workload, caller, or
shape is ever named by them — the name is an identifier, nothing
more.

This module is pure: it knows nothing of the lease's state files.
sync/lease/ assembles the taken set and owns the journals.
"""

import random
import re

ADJECTIVES = (
    "amber", "azure", "brisk", "calm", "cedar", "coral", "cozy", "crisp",
    "dawn", "dusk", "ember", "fern", "flint", "frost", "golden", "hazel",
    "ivory", "jade", "juniper", "keen", "lilac", "lunar", "maple", "marble",
    "misty", "noble", "oak", "olive", "onyx", "opal", "pearl", "pine",
    "quiet", "rapid", "river", "ruby", "russet", "sable", "sage", "sandy",
    "scarlet", "silver", "solar", "spruce", "stone", "storm", "sunny", "swift",
    "teal", "topaz", "velvet", "walnut", "willow", "zephyr",
)

NOUNS = (
    "anchor", "arrow", "atlas", "beacon", "birch", "breeze", "brook", "canyon",
    "castle", "clover", "comet", "compass", "cove", "creek", "crown", "delta",
    "dune", "falcon", "fjord", "forest", "garnet", "glacier", "grove", "heron",
    "island", "kettle", "lagoon", "lantern", "laurel", "ledge", "linen", "lotus",
    "lynx", "magnet", "mesa", "meteor", "mosaic", "nectar", "newt", "oasis",
    "orbit", "osprey", "otter", "panda", "pebble", "petal", "pilot", "pony",
    "quarry", "quest", "quill", "raven", "reef", "ridge", "robin", "rocket",
    "saddle", "sail", "scout", "shell", "shore", "summit", "talon", "temple",
    "tide", "timber", "tower", "trail", "tulip", "valley", "vault", "voyage",
    "wave", "wren",
)

MAX_ATTEMPTS = 200


_RENEWAL_SUFFIX = re.compile(r"-r\d+$")


def lineage(session: str) -> str:
    """The lease family a session name belongs to: the generated
    name with every renewal generation suffix (-r<epoch>)
    stripped — the derivation renewal mints a window's children
    by (sync/lease/sessions/renewal.py), so a name and all its
    renewed successors share one lineage, and a pin written
    against one generation names the family."""
    base = session
    while _RENEWAL_SUFFIX.search(base):
        base = _RENEWAL_SUFFIX.sub("", base)
    return base


def generate_name(taken, rng: random.Random | None = None) -> str:
    """One generated name outside `taken` (a set of names already
    spoken for). Raises RuntimeError after MAX_ATTEMPTS collisions
    — with ~400k names in the space, that is a defect signal (a
    taken set swollen with garbage), never an expected outcome."""
    rng = rng or random.SystemRandom()
    for _ in range(MAX_ATTEMPTS):
        name = f"{rng.choice(ADJECTIVES)}-{rng.choice(NOUNS)}-{rng.randrange(100):02d}"
        if name not in taken:
            return name
    raise RuntimeError("generated-name space exhausted against the taken set")
