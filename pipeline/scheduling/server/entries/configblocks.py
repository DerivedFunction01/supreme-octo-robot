"""Entry config blocks (contract 09, as amended):
the serving projection and the guarded save behind them.

The block rides the entry record (the registry entry form,
map-shaped — see registry.py); this module projects it to
the schema's array form for serving and writes value edits
back through the one writer path:

- writer-validated: every presented value is type- and
  range-checked and every constraint re-checked against the
  merged values; any violation refuses the whole save and
  the entry file is left byte-identical;
- stale-stamp refusal (the CAS form): a save presents the
  block version it loaded; when the store's stamp has moved
  the save is refused `no_match` (the platform writer's
  version_conflict at this surface) and writes nothing;
- every applied knob change is ledgered as an `op` event.

A save whose values change nothing applies nothing: no
write, no ledger events, and the version stamp does not
move. Refusals are never ledgered.

Fire-time seam: a knob may declare `env`, the variable the
engine sets to the knob's value when the entry fires
(`registry.config_env`, applied by the executor). The
served view carries the name beside the value; the mapping
lives on the knob — beside this serving contract — never
in a per-job table in the engine.
"""

import copy
import hashlib
import importlib.util
import os

from . import catalog as catalog_mod
from .. import config as config_mod
from .. import paths as _paths
from .. import registry
from ..registry import EntryError

_STATUS = {"bad_request": 400, "not_found": 404, "no_match": 409,
           "io_error": 500}


def _load_platform_writer():
    """The platform writer (contract 15), loaded the way
    server/serving/ops.py loads it — same seam, same module."""
    path = _paths.PLATFORM_WRITER
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fmt_num(num):
    if isinstance(num, float) and num.is_integer():
        return str(int(num))
    return str(num)


# ------------------------------------------------------------ serving


def view_of(entry):
    """The served configView for an entry, or None when the
    entry carries no config block. The entry form's knobs and
    constraints are maps keyed by name; the served form is the
    schema's arrays, in entry order, keys injected."""
    block = entry.get("config")
    if not isinstance(block, dict):
        return None
    knobs = []
    for key, knob in (block.get("knobs") or {}).items():
        served = {
            "key": key,
            "label": knob["label"],
            "type": knob["type"],
            "unit": knob["unit"],
            "value": registry.config_number(knob["value"], knob["type"]),
            "min": registry.config_number(knob["min"], knob["type"]),
            "max": registry.config_number(knob["max"], knob["type"]),
        }
        # The fire-time mapping is part of this serving
        # contract: a knob declaring `env` serves the name
        # beside its value, so a consumer can see which
        # variable the saved value reaches at fire time.
        if knob.get("env"):
            served["env"] = knob["env"]
        knobs.append(served)
    constraints = [
        {"kind": con["kind"], "left": con["left"], "right": con["right"],
         "message": con["message"]}
        for con in (block.get("constraints") or {}).values()
    ]
    return {"version": block["version"], "knobs": knobs,
            "constraints": constraints}


# ------------------------------------------------------------ the save


def _refuse(name, detail):
    return _STATUS[name], {"ok": False, "error": name, "detail": detail}


def _render_block(block):
    """The block's entry-form text (YAML subset, map-shaped)."""
    fmt = catalog_mod._fmt_scalar
    out = ["config:", f"  version: {block['version']}", "  knobs:"]
    for key, knob in block["knobs"].items():
        out.append(f"    {key}:")
        for field in ("label", "type", "unit", "value", "min", "max", "env"):
            if field in knob:
                out.append(f"      {field}: {fmt(knob[field])}")
    if block.get("constraints"):
        out.append("  constraints:")
        for name, con in block["constraints"].items():
            out.append(f"    {name}:")
            for field in ("kind", "left", "right", "message"):
                out.append(f"      {field}: {fmt(con[field])}")
    return out


def _replace_block(text, block):
    """Swap the top-level `config:` region of the entry text
    for the new block's rendering; every other byte of the
    file — comments included — is preserved."""
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("config:") and line.strip() == "config:":
            start = i
            break
    if start is None:
        raise EntryError("entry carries no config block to replace")
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line and line[0] in " \t":
            end += 1
        elif line == "" and end + 1 < len(lines) \
                and lines[end + 1][:1] in (" ", "\t"):
            end += 1  # a blank line inside the block's own span
        else:
            break
    return "\n".join(lines[:start] + _render_block(block) + lines[end:])


def save_config(engine, job_id, version, values, caller):
    """The guarded config save. Returns (status, payload):
    ok carries the new version and the served view; refusals
    carry the error name and a detail naming the cause."""
    if job_id not in engine.entries:
        return _refuse("not_found", f"no such job: {job_id}")
    if not isinstance(values, dict):
        return _refuse("bad_request", "values must be a map of knob values")
    path = os.path.join(engine.jobs_dir, f"{job_id}.yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return _refuse("io_error", f"entry file unreadable: {exc}")
    stamp_before = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        data = registry.parse_yaml(text)
        registry.validate(job_id, data, home=engine.home, where=path,
                          anchors=config_mod.anchors(engine.values))
    except EntryError as exc:
        return _refuse("bad_request", f"entry record invalid: {exc}")
    block = data.get("config")
    if block is None:
        return _refuse("bad_request", f"{job_id} carries no editable config.")
    if version != block["version"]:
        return _refuse(
            "no_match",
            f"{job_id} config changed since it was loaded "
            f"(now version {block['version']}) — reload and re-apply.")
    knobs = block["knobs"]
    current = {key: registry.config_number(knob["value"], knob["type"])
               for key, knob in knobs.items()}
    merged = dict(current)
    for key, raw in values.items():
        knob = knobs.get(key)
        if knob is None:
            return _refuse("bad_request", f"Unknown knob {key}.")
        num = registry.config_number(raw, knob["type"])
        if num is None:
            whole = knob["type"] == "integer"
            return _refuse(
                "bad_request",
                f"{knob['label']} must be "
                f"{'a whole number' if whole else 'a number'}"
                f"{f' ({knob['unit']})' if whole else ''}.")
        lo = registry.config_number(knob["min"], knob["type"])
        hi = registry.config_number(knob["max"], knob["type"])
        if not lo <= num <= hi:
            return _refuse(
                "bad_request",
                f"{knob['label']} must be between {_fmt_num(lo)} and "
                f"{_fmt_num(hi)} {knob['unit']}.")
        merged[key] = num
    for con in (block.get("constraints") or {}).values():
        if con["kind"] == "lt" and not merged[con["left"]] < merged[con["right"]]:
            return _refuse("bad_request", con["message"])
    changed = [key for key in merged if merged[key] != current[key]]
    if not changed:
        return 200, {"ok": True, "version": block["version"],
                     "config": view_of(engine.entries[job_id])}
    new_block = copy.deepcopy(block)
    for key in changed:
        knob = new_block["knobs"][key]
        knob["value"] = merged[key] if knob["type"] == "integer" \
            else float(merged[key])
    new_block["version"] = block["version"] + 1
    try:
        new_text = _replace_block(text, new_block)
    except EntryError as exc:
        return _refuse("io_error", str(exc))
    writer = _load_platform_writer()
    try:
        moved = writer.stamp_of(path) != stamp_before
    except (OSError, writer.WriterError):
        moved = True
    if moved:
        return _refuse(
            "no_match",
            f"{job_id} changed on disk during the save — "
            "reload and re-apply.")
    try:
        writer.staged_write(path, new_text.encode("utf-8"))
    except (OSError, writer.WriterError) as exc:
        return _refuse("io_error", f"entry write failed: {exc}")
    for key in changed:
        engine.ledger.record(
            "op", op="config", caller=caller, target=job_id,
            job_id=job_id, knob=key, label=knobs[key]["label"],
            old=current[key], new=merged[key], unit=knobs[key]["unit"],
            status="ok")
    engine._rescan(engine.now_fn())
    served = engine.entries.get(job_id)
    return 200, {"ok": True, "version": new_block["version"],
                 "config": view_of(served) if served is not None else None}
