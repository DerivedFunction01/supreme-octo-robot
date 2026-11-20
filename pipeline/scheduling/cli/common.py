"""Shared context for the sched CLI modules: the tree root,
the registry directory, and the one registry load every
registry-reading command goes through."""
import os

from cli import paths as _paths
from server import config as config_mod
from server import registry

ROOT = _paths.ROOT
JOBS_DIR = _paths.JOBS_DIR


def _load():
    values, _sources = config_mod.resolve()
    return registry.load_dir(JOBS_DIR, ROOT, anchors=config_mod.anchors(values))
