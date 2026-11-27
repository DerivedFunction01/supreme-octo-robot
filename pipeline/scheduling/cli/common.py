"""Shared context for the sched CLI modules: the tree root,
the registry directory, and the one registry load every
registry-reading command goes through."""
import os

from cli import paths as _paths
from server import config as config_mod
from server import registry

ROOT = _paths.ROOT
JOBS_DIR = _paths.JOBS_DIR


def _anchors():
    """The registry anchors from the server config — the one
    derivation every CLI registry read (and the adopt verb's
    setup expansion) goes through, so ${WS} resolves to the
    configured workspace root everywhere the CLI expands it."""
    values, _sources = config_mod.resolve()
    return config_mod.anchors(values)


def _load():
    return registry.load_dir(JOBS_DIR, ROOT, anchors=_anchors())
