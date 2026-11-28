"""The classified schedule catalog: loading, the serializer
round-trip, adoption rendering, literal refusal, and drift.

Fixtures are self-contained: the shipped layer is read for the
load and round-trip checks (it is tracked, so a bare clone has
it); adoption and drift expectations are built in the test,
never read from the live overlay registry.
"""

import copy
import os
import shutil
import tempfile
import unittest

from server import registry
from server.entries import catalog

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYER = os.path.join(REPO, "examples", "registry")

TONIGHTS_PARAMS = {
    "title": "Storage watch — one report per free-space threshold crossing (home + /tmp)",
    "owner": "none",
    "owner_reason": "owner-commissioned fleet tripwire (2026-11-08)",
    "timezone": "America/New_York",
}


class LoadCase(unittest.TestCase):
    def test_shipped_catalog_is_consistent(self):
        cat, errors = catalog.load_catalog(REPO)
        self.assertEqual(errors, [])
        self.assertEqual(cat["version"], 1)
        self.assertEqual(len(cat["rows"]), 21)
        self.assertEqual(len(cat["entries"]), 14)
        config_rows = [r for r in cat["rows"].values() if r["class"] == "config-example"]
        self.assertEqual(len(config_rows), 7)
        for row in config_rows:
            self.assertEqual(row["companion_of"], "example-sweeper-nudge-check")

    def test_unclassified_layer_file_is_an_error(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        layer = os.path.join(tmp, "examples", "registry")
        os.makedirs(layer)
        with open(os.path.join(layer, "catalog.yaml"), "w") as fh:
            fh.write("version: 1\nentries:\n  example-one:\n"
                     "    file: example-one.yaml\n    class: entry\n"
                     "    origin: hand\n    generality: generalized\n"
                     "    use_case: demo\n")
        with open(os.path.join(layer, "example-one.yaml"), "w") as fh:
            fh.write("id: example-one\ncatalog:\n  origin: hand\n"
                     "  generality: generalized\n  use_case: demo\n")
        with open(os.path.join(layer, "stray.yaml"), "w") as fh:
            fh.write("id: stray\n")
        _cat, errors = catalog.load_catalog(tmp)
        self.assertTrue(any("not classified" in e for e in errors), errors)


class RoundTripCase(unittest.TestCase):
    def test_every_layer_file_round_trips(self):
        for name in sorted(os.listdir(LAYER)):
            if not name.endswith(".yaml"):
                continue
            with open(os.path.join(LAYER, name), encoding="utf-8") as fh:
                data = registry.parse_yaml(fh.read(), where=name)
            again = registry.parse_yaml(catalog.serialize_yaml(data), where=name)
            self.assertEqual(again, data, name)


class RenderCase(unittest.TestCase):
    def setUp(self):
        cat, errors = catalog.load_catalog(REPO)
        self.assertEqual(errors, [])
        self.example = cat["entries"]["example-storage-watch"]

    def test_render_matches_the_specimen_shape(self):
        live, errors = catalog.render_adoption(
            "example-storage-watch", self.example, TONIGHTS_PARAMS, 1)
        self.assertEqual(errors, [])
        self.assertEqual(live["id"], "storage-watch")
        self.assertEqual(live["title"], TONIGHTS_PARAMS["title"])
        self.assertEqual(live["owner"], "none")
        self.assertEqual(live["owner_reason"], TONIGHTS_PARAMS["owner_reason"])
        self.assertEqual(live["timezone"], "America/New_York")
        self.assertEqual(live["cadence"], {"type": "interval", "every": "15m"})
        # No admission field exists in the target format
        # (amendment 3): the render carries none of the family.
        for field in ("migrated", "migrated_at", "migration_note",
                      "proof_pending"):
            self.assertNotIn(field, live)
        self.assertNotIn("catalog", live)
        self.assertEqual(live["source"]["catalog"], "example-storage-watch")
        self.assertEqual(live["source"]["catalog_version"], 1)
        self.assertEqual(live["source"]["parameters"]["cadence_every"], "15m")
        # The render validates as a live entry.
        registry.validate("storage-watch", copy.deepcopy(live), REPO)

    def test_declared_parameter_overrides_default(self):
        params = dict(TONIGHTS_PARAMS, cadence_every="30m")
        live, errors = catalog.render_adoption(
            "example-storage-watch", self.example, params, 1)
        self.assertEqual(errors, [])
        self.assertEqual(live["cadence"]["every"], "30m")

    def test_owner_is_required_and_undeclared_params_refused(self):
        _live, errors = catalog.render_adoption(
            "example-storage-watch", self.example, {}, 1)
        self.assertTrue(any("owner" in e for e in errors))
        _live, errors = catalog.render_adoption(
            "example-storage-watch", self.example,
            dict(TONIGHTS_PARAMS, bogus="x"), 1)
        self.assertTrue(any("undeclared" in e for e in errors))

    def test_machine_literals_refused(self):
        data = {"state_paths": [os.path.join("/", "home", "someone", "state")], "run": {"argv": ["bash", "x"]}}
        self.assertTrue(catalog.machine_literals(data))
        ok = {"state_paths": ["${REPO}/state/x"], "run": {"argv": ["bash", "${REPO}/x.sh"]}}
        self.assertEqual(catalog.machine_literals(ok), [])


class SetupCase(unittest.TestCase):
    def setUp(self):
        cat, errors = catalog.load_catalog(REPO)
        self.assertEqual(errors, [])
        self.cat = cat

    def test_sweeper_setup_is_the_worked_specimen(self):
        actions = catalog.setup_actions(self.cat["entries"]["example-sweeper-nudge-check"])
        kinds = [a[0] for a in actions]
        self.assertEqual(kinds.count("mkdir"), 1)
        self.assertIn(("mkdir", "${WS}/approval-sweeper"), actions)
        stores = [a for a in actions if a[0] == "store"]
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0][2], "${WS}/approval-sweeper/nudge-ledger.sqlite")
        self.assertIn("nudge_ledger.py", stores[0][3][1])
        files = [a for a in actions if a[0] == "file"]
        self.assertEqual(len(files), 7)
        self.assertTrue(all(a[3] is None for a in files))  # verify-only
        docs = [a for a in actions if a[0] == "doc"]
        self.assertEqual(docs, [("doc", "example-sweeper-nudge-check.setup.md")])

    def test_missing_setup_doc_is_a_catalog_error(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        layer = os.path.join(tmp, "examples", "registry")
        os.makedirs(layer)
        with open(os.path.join(layer, "catalog.yaml"), "w") as fh:
            fh.write("version: 1\nentries:\n  example-one:\n"
                     "    file: example-one.yaml\n    class: entry\n"
                     "    origin: hand\n    generality: generalized\n"
                     "    use_case: demo\n")
        with open(os.path.join(layer, "example-one.yaml"), "w") as fh:
            fh.write("id: example-one\ncatalog:\n  origin: hand\n"
                     "  generality: generalized\n  use_case: demo\n"
                     "  setup:\n    docs:\n      - absent.setup.md\n")
        _cat, errors = catalog.load_catalog(tmp)
        self.assertTrue(any("setup doc missing" in e for e in errors), errors)

    def test_storage_setup_is_one_state_dir(self):
        actions = catalog.setup_actions(self.cat["entries"]["example-storage-watch"])
        self.assertEqual(actions, [("mkdir", "${REPO}/state/storage-watch")])

    def test_uncovered_state_path_is_a_catalog_error(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        layer = os.path.join(tmp, "examples", "registry")
        os.makedirs(layer)
        with open(os.path.join(layer, "catalog.yaml"), "w") as fh:
            fh.write("version: 1\nentries:\n  example-one:\n"
                     "    file: example-one.yaml\n    class: entry\n"
                     "    origin: hand\n    generality: generalized\n"
                     "    use_case: demo\n")
        with open(os.path.join(layer, "example-one.yaml"), "w") as fh:
            fh.write("id: example-one\nstate_paths:\n  - ${REPO}/state/x\n"
                     "catalog:\n  origin: hand\n"
                     "  generality: generalized\n  use_case: demo\n")
        _cat, errors = catalog.load_catalog(tmp)
        self.assertTrue(any("not covered" in e for e in errors), errors)

    def test_bad_setup_shape_fails_validation(self):
        cat, errors = catalog.load_catalog(REPO)
        data = copy.deepcopy(cat["entries"]["example-storage-watch"])
        data["catalog"]["setup"] = {"teleporters": []}
        with self.assertRaises(registry.EntryError):
            registry.validate("example-storage-watch", data, REPO)


class MachineStampDriftCase(unittest.TestCase):
    def test_machine_form_source_counts_as_machine_not_adopted(self):
        cat, errors = catalog.load_catalog(REPO)
        self.assertEqual(errors, [])
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        jobs = os.path.join(tmp, "jobs")
        os.makedirs(jobs)
        with open(os.path.join(jobs, "wb-progress-demo-t-1.yaml"), "w") as fh:
            fh.write("id: wb-progress-demo-t-1\n"
                     "catalog:\n  origin: machine\n"
                     "  generality: deployment-specific\n"
                     "  use_case: work-tracking\n"
                     "source:\n  writer: workbench-harness\n"
                     "  project: demo\n  todo: t-1\n"
                     "  source_class: project\n")
        lines, problems = catalog.drift(tmp, cat)
        self.assertEqual(problems, 0)
        self.assertTrue(any("1 machine-written" in ln for ln in lines), lines)
        self.assertFalse(any("wb-progress-demo" in ln for ln in lines), lines)


class DriftCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.jobs = os.path.join(self.tmp, "jobs")
        os.makedirs(self.jobs)
        cat, errors = catalog.load_catalog(REPO)
        self.assertEqual(errors, [])
        self.cat = cat
        live, errors = catalog.render_adoption(
            "example-storage-watch", cat["entries"]["example-storage-watch"],
            TONIGHTS_PARAMS, 1)
        self.assertEqual(errors, [])
        self.live = live

    def write_live(self, data, name="storage-watch.yaml"):
        with open(os.path.join(self.jobs, name), "w") as fh:
            fh.write(catalog.serialize_yaml(data))

    def test_adopted_and_current(self):
        self.write_live(self.live)
        with open(os.path.join(self.jobs, "wb-progress-x.yaml"), "w") as fh:
            fh.write("id: wb-progress-x\n")
        lines, problems = catalog.drift(self.tmp, self.cat)
        self.assertEqual(problems, 0)
        self.assertTrue(any("adopted-and-current" in ln for ln in lines))
        self.assertTrue(any("1 machine-written" in ln for ln in lines))

    def test_field_drift_is_named(self):
        tampered = copy.deepcopy(self.live)
        tampered["timeout_secs"] = 999
        self.write_live(tampered)
        lines, problems = catalog.drift(self.tmp, self.cat)
        self.assertEqual(problems, 1)
        self.assertTrue(any("timeout_secs" in ln for ln in lines))


if __name__ == "__main__":
    unittest.main()
