"""This package's settings under the unified config
contract (plan §4.4, contract 04).

Every live config is an untracked file seeded from a
tracked fictional example, resolved env > live > defaults,
with per-key source reporting — and no live value ever
enters a tracked file. The registry's own settings are
two paths: where the store lives, and where the claims
journal lives. The tracked example is
`config.example.json` beside this module (fictional
values); the live file is `config.json` in the same
place, untracked.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import paths as _paths

_HERE = Path(_paths.PACKAGE_DIR)

# key -> (default, env name). Defaults are package-relative
# (the store and journal live under the package's var/).
_KEYS = {
    "store_path": ("var/registry.json", "PIPELINE_REGISTRY_STORE"),
    "claims_journal": ("var/caller-claims.jsonl",
                       "PIPELINE_REGISTRY_CLAIMS"),
}


def live_path() -> Path:
    return _HERE / "config.json"


def resolve_config(live=None, env=None) -> tuple:
    """Resolve the registry's settings. Returns (values,
    sources): values maps each key to its resolved value
    (paths absolute, anchored at this package); sources
    maps each key to where its value came from — "env",
    "live", or "default" (contract 04's per-key source
    reporting)."""
    env = os.environ if env is None else env
    live_values = {}
    if live is None:
        try:
            with open(live_path(), "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                live_values = loaded
        except (OSError, ValueError):
            live_values = {}
    elif isinstance(live, dict):
        live_values = live
    values, sources = {}, {}
    for key, (default, env_name) in _KEYS.items():
        if env.get(env_name):
            raw, source = env[env_name], "env"
        elif isinstance(live_values.get(key), str) and live_values[key]:
            raw, source = live_values[key], "live"
        else:
            raw, source = default, "default"
        path = Path(raw)
        values[key] = path if path.is_absolute() else _HERE / path
        sources[key] = source
    return values, sources
