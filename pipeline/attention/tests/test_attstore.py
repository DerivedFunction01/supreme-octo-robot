"""The attention store migration proof (contract 01's
seed/export step; plan §4.15's S7 re-point).

The migrated store — ATT1's discipline with the writer
wrapper-mediated — is rehearsed against a committed
synthetic fixture carrying the S1 captured copy's shape
at its exact registry counts: it loads with counts
identical to the S1 validation, it saves through the
unified writer, and the saved file loads again with the
same counts. (The suite once read the captured copy
itself from untracked holding material and errored in
a bare clone; tests seed their own fixtures — the
fixture's rows are synthetic, its counts are the S1
table below.) The final leg loads both the fixture and
the migrated save through the PINNED attention code's
own store loader; it runs when ATTENTION_PIN_ROOT names
the pinned checkout (the proof is a migration rehearsal
against the pin, executed at this step — the loader lives
in the source repo, which no tracked file may name).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from attention.infra import attstore

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "held-state.json"

# The S1 validation table (docs/overlay/attention.md):
# counts raw, and identical through the pinned loader.
S1_CENSUS = {
    "handlers": 10,
    "programmes": 3,
    "sends": 47,
    "items": 53,
    "rules": 8,
    "templates": 18,
    "status_codes": 8,
    "fields": 12,
    "wait_classes": 16,
    "item_kinds": 11,
    "action_rules": 7,
    "waits": 0,
    "armed_rows": 2,
    "owner_actions": 26,
    "dispatch_failures": 442,
}


def census(state) -> dict:
    return {key: len(state.get(key) or []) for key in S1_CENSUS}


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="registry-attstore-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.copy = self.tmp / "state.json"
        shutil.copyfile(FIXTURE, self.copy)

    def test_fixture_copy_loads_with_s1_counts(self):
        state = attstore.AttentionStateStore(self.copy).load_state()
        self.assertEqual(census(state), S1_CENSUS)
        self.assertEqual(state["presence"]["mode"], "away")
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for key in raw:
            self.assertIn(key, state)

    def test_writer_mediated_save_round_trips(self):
        store = attstore.AttentionStateStore(self.copy)
        state = store.load_state()
        out = self.tmp / "migrated" / "state.json"
        attstore.AttentionStateStore(out).save_state(state)
        # The writer's protocol leaves no staging sibling
        # behind, and the saved file is the pinned encoder's
        # form (indent=2 JSON of the same state).
        self.assertEqual([p.name for p in out.parent.iterdir()], ["state.json"])
        reloaded = attstore.AttentionStateStore(out).load_state()
        self.assertEqual(census(reloaded), S1_CENSUS)
        self.assertEqual(reloaded["presence"]["mode"], "away")

    def test_backfill_appends_missing_seeds_never_overwrites(self):
        raw = json.loads(self.copy.read_text(encoding="utf-8"))
        dropped = raw["templates"][0]["kind"]
        raw["templates"] = [t for t in raw["templates"] if t["kind"] != dropped]
        sentinel = raw["templates"][0]
        sentinel["sentinel"] = "kept"
        marked = self.tmp / "marked.json"
        marked.write_text(json.dumps(raw), encoding="utf-8")
        state = attstore.AttentionStateStore(marked).load_state()
        kinds = {t["kind"] for t in state["templates"]}
        self.assertIn(dropped, kinds)
        self.assertEqual(len(state["templates"]), 18)
        row = next(t for t in state["templates"] if t.get("sentinel") == "kept")
        self.assertEqual(row["kind"], sentinel["kind"])


@unittest.skipUnless(
    os.environ.get("ATTENTION_PIN_ROOT"),
    "ATTENTION_PIN_ROOT not set (the pinned loader's checkout)",
)
class PinnedLoaderTests(unittest.TestCase):
    """The done-evidence leg: the migrated store loads
    through the pinned attention code's own store loader
    with registry counts identical to the S1 validation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="registry-pinned-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        root = os.environ["ATTENTION_PIN_ROOT"]
        if root not in sys.path:
            sys.path.insert(0, root)
        from backend.infra.store import JsonFileStore

        self.JsonFileStore = JsonFileStore

    def test_pinned_loader_reads_fixture_copy_at_s1_counts(self):
        held = self.tmp / "held.json"
        shutil.copyfile(FIXTURE, held)
        state = self.JsonFileStore(held).load_state()
        self.assertEqual(census(state), S1_CENSUS)
        self.assertEqual(state["presence"]["mode"], "away")

    def test_pinned_loader_reads_the_migrated_save(self):
        migrated = self.tmp / "migrated.json"
        store = attstore.AttentionStateStore(FIXTURE)
        attstore.AttentionStateStore(migrated).save_state(store.load_state())
        state = self.JsonFileStore(migrated).load_state()
        self.assertEqual(census(state), S1_CENSUS)
        self.assertEqual(state["presence"]["mode"], "away")


if __name__ == "__main__":
    unittest.main()
