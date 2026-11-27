"""bin/venue-run's _record_target resolution chain: the
target a record carries, else its shape's binding, else the
venue's only target.

The defect specimen is the rename shape: a record written
before its target was renamed carries the old id ("local"
against a config keyed "msi-hx18"); its poll died with "no
local venue target resolves for this run" although the
record's shape binding resolves. The chain's legs are
stubbed at the local_venue seam — venue_target and
shape_target keep their own specimens — so these pins hold
_record_target's fall-through alone.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

CARRIED = {"host": "carried.invalid", "user": "agent"}
BOUND = {"host": "bound.invalid", "user": "agent"}
SOLE = {"host": "sole.invalid", "user": "agent"}


class FakeVenue:
    """venue_target resolves only the ids in `targets` (a
    no-id call serves the sole fallback); shape_target
    serves `bound` for the shape id "local"."""

    def __init__(self, targets, bound):
        self.targets = targets
        self.bound = bound
        self.shape_calls = []

    def venue_target(self, repo, target_id=None):
        if target_id is None:
            return SOLE if len(self.targets) == 1 else None
        return self.targets.get(target_id)

    def shape_target(self, repo, shape_id):
        self.shape_calls.append(shape_id)
        if self.bound is not None and shape_id == "local":
            return ({"id": "local"}, "msi-hx18", self.bound)
        return (None, None, None)


def load(monkeypatch, targets, bound):
    mod = load_module("venue_run_record_target_unit", REPO / "bin" / "venue-run")
    fake = FakeVenue(targets, bound)
    monkeypatch.setattr(mod, "local_venue", fake)
    return mod, fake


def test_carried_target_resolves_directly(monkeypatch):
    mod, fake = load(monkeypatch, {"msi-hx18": CARRIED}, BOUND)
    rec = {"target": "msi-hx18", "shape": "local"}
    assert mod._record_target(rec) is CARRIED
    assert fake.shape_calls == []


def test_unresolvable_carried_id_falls_through_to_shape_binding(monkeypatch):
    mod, _fake = load(monkeypatch, {"msi-hx18": CARRIED}, BOUND)
    rec = {"target": "local", "shape": "local"}
    assert mod._record_target(rec) is BOUND


def test_unresolvable_carried_id_falls_through_to_sole_target(monkeypatch):
    mod, _fake = load(monkeypatch, {"msi-hx18": SOLE}, None)
    rec = {"target": "local", "shape": "retired-shape"}
    assert mod._record_target(rec) is SOLE


def test_record_without_target_uses_shape_binding(monkeypatch):
    mod, _fake = load(monkeypatch, {"msi-hx18": CARRIED}, BOUND)
    assert mod._record_target({"shape": "local"}) is BOUND


def test_nothing_resolvable_returns_none(monkeypatch):
    mod, _fake = load(monkeypatch, {"a": CARRIED, "b": BOUND}, None)
    rec = {"target": "local", "shape": "retired-shape"}
    assert mod._record_target(rec) is None
