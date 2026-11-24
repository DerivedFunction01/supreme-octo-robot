#!/usr/bin/env python3
"""Ledger consult for the local-test watch.

The watch samples processes; its argv/cwd signature cannot
distinguish a scheduler-server child from a shell run — agent
work routed through the server's ops channel executes ON this
box, as the server's children, and flags as local execution.
Three flags (a full-gate cluster and two repo-leg runs)
all proved ops-route executions on manual ledger
verification, and their dispositions had to be recalibrated
by hand. The scheduler ledger (state/scheduler.db, events
kind 'op') is the discriminating record: an op's record
carries its caller and its full command target.

Locator, pinned (Edgar coordinator's Instance 14
disposition): the discriminating store is
state/scheduler.db, table events — the state/ledger.db
beside it is a 0-byte stub that answers nothing, and a
check pointed there reads empty and misreads as
no-covering-op. Three probes found the right store
once; this note is so no check pays that again.

This module is the consult: given a finding (argv + cwd) and
the sighting instant, it answers whether a ledger op covers
the sampled process — the op started inside the window
before the sighting, its target names the finding's cwd, and
every distinctive argv token (a path or a script filename)
appears in the target. The match is deliberately strict: a
loose match would clear real violations. Any failure to read
the ledger — missing file, locked, schema drift — answers
None, leaving the warning standing (fail-safe).

Stdlib only; the database opens read-only, in the same form
as the sibling census watch.
"""

import importlib.util as _importlib_util
import json
import os
import sqlite3
import sys as _sys
import types as _types

WINDOW_BEFORE_S = 1200
WINDOW_AFTER_S = 120

# The parse intent's home for this cluster is the
# workrecord lib's util (the date-family map: scheduling
# ops bind it by derived path) — the tolerant instant
# parse lives there, never copied here. util is a package
# module (it imports its sibling paths relatively), so it
# is loaded under a synthetic package rooted at the lib
# dir: a flat standalone load gives its relative import
# no parent and the watch dies at startup in the job's
# own context (the package gate's context masked it;
# the job runs this file as a bare script).
_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(_HERE))),
    "workrecord", "lib")
if "workrecord_lib" not in _sys.modules:
    _pkg = _types.ModuleType("workrecord_lib")
    _pkg.__path__ = [_LIB_DIR]
    _sys.modules["workrecord_lib"] = _pkg
_util_spec = _importlib_util.spec_from_file_location(
    "workrecord_lib.util", os.path.join(_LIB_DIR, "util.py"))
_util = _importlib_util.module_from_spec(_util_spec)
_sys.modules["workrecord_lib.util"] = _util
_util_spec.loader.exec_module(_util)


def ledger_path(state_dir=None):
    # scheduler.db is the ledger of record; the
    # ledger.db stub beside it answers nothing (see
    # the module docstring's locator note).
    if state_dir is None:
        state_dir = os.path.join(
            os.path.dirname(os.path.dirname(_HERE)), "state")
    return os.path.join(state_dir, "scheduler.db")


def _epoch(at):
    if isinstance(at, (int, float)):
        return float(at)
    parsed = _util.parse_instant(at)
    return parsed.timestamp() if parsed is not None else None


def _distinctive_tokens(argv):
    return [a for a in argv
            if "/" in a or a.endswith((".py", ".sh", ".mjs"))]


def _connect(db_path):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def covered_by_op(finding, at, db_path=None):
    """The covering op's citation {op_id, caller, ts}, or
    None — no op covers the finding, or the ledger could not
    be read (the warning then stands)."""
    epoch = _epoch(at)
    tokens = _distinctive_tokens(finding.get("argv") or [])
    cwd = finding.get("cwd") or ""
    if epoch is None or not tokens or not cwd:
        return None
    db_path = db_path or ledger_path()
    try:
        con = _connect(db_path)
        try:
            rows = con.execute(
                "SELECT id, ts, ts_epoch, record FROM events "
                "WHERE kind = 'op' AND ts_epoch BETWEEN ? AND ? "
                "ORDER BY ts_epoch DESC",
                (epoch - WINDOW_BEFORE_S, epoch + WINDOW_AFTER_S),
            ).fetchall()
        finally:
            con.close()
    except Exception:
        return None
    for op_id, ts, _ts_epoch, raw in rows:
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            continue
        target = record.get("target") or ""
        if cwd in target and all(t in target for t in tokens):
            return {"op_id": op_id, "caller": record.get("caller"),
                    "ts": ts}
    return None


def op_citation(op_id, db_path=None):
    """One op's citation by id, for the disposition verb: a
    cited op that does not resolve must not close an episode,
    so an unknown id answers None."""
    db_path = db_path or ledger_path()
    try:
        con = _connect(db_path)
        try:
            row = con.execute(
                "SELECT id, ts, record FROM events "
                "WHERE kind = 'op' AND id = ?", (op_id,),
            ).fetchone()
        finally:
            con.close()
    except Exception:
        return None
    if row is None:
        return None
    try:
        record = json.loads(row[2])
    except (TypeError, ValueError):
        record = {}
    return {"op_id": row[0], "caller": record.get("caller"),
            "ts": row[1]}
