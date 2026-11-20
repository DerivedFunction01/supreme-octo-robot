"""Server-half tests (S8): the ported feeds over the
fixture workspace (tests/server/fixture_ws), the armed
feed, the status vocabulary, and the assembly document
the live adapter consumes.

The fixture config is installed through WB_VIEWER_CONFIG
before the server package imports — the package reads
its config at import, exactly as the pinned server did.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.server import fixture_ws

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = REPO_ROOT / "contracts"


class ServerFeedsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name) / "fx"
        cls.info = fixture_ws.build_fixture_workspace(
            cls.base)
        cfg = fixture_ws.fixture_config(
            cls.base, cls.base / "state-test")
        cls._saved = {
            k: os.environ.get(k) for k in
            ("WB_VIEWER_CONFIG", "WB_ATTENTION_ARMED_DIR")}
        os.environ["WB_VIEWER_CONFIG"] = str(cfg)
        os.environ["WB_ATTENTION_ARMED_DIR"] = str(
            cls.info["armed_dir"])
        from server import assemble, common, feeds
        from server import messages_api
        cls.assemble = assemble
        cls.common = common
        cls.feeds = feeds
        cls.messages_api = messages_api
        sweep = common.get_sweep()
        cls.alpha = sweep.by_slug("alpha")
        cls.beta = sweep.by_slug("beta")
        assert cls.alpha is not None
        assert cls.beta is not None

    @classmethod
    def tearDownClass(cls):
        for key, value in cls._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls._tmp.cleanup()

    # -- home + sweep summary --------------------------------

    def test_home_rows(self):
        home = self.feeds.home_feed()
        slugs = [p["slug"] for p in home["projects"]]
        self.assertEqual(slugs, ["alpha", "beta"])
        alpha = home["projects"][0]
        self.assertEqual(alpha["todos"]["counts"],
                         {"todo": 1, "doing": 1,
                          "blocked": 1, "done": 3})
        self.assertEqual(alpha["todos"]["total"], 6)
        self.assertEqual(alpha["review"]["triage_count"], 2)
        # Beta is manifest-only (its declared stores do
        # not exist): honest absence, not degradation.
        beta = home["projects"][1]
        self.assertFalse(beta["degraded"])
        self.assertEqual(beta["todos"],
                         {"available": False, "counts": {},
                          "total": 0, "source": "files"})

    def test_summary_covers_the_same_projects(self):
        summary = self.common.get_sweep().summary()
        self.assertEqual(
            {p["slug"] for p in summary["projects"]},
            {"alpha", "beta"})

    # -- per-project feeds ------------------------------------

    def test_todos_feed_from_files(self):
        feed = self.feeds.todos_feed(self.alpha)
        self.assertEqual(feed["source"], "files")
        counts = {}
        for t in feed["todos"]:
            counts[t["status"]] = counts.get(
                t["status"], 0) + 1
        self.assertEqual(counts,
                         {"todo": 1, "doing": 1,
                          "blocked": 1, "done": 3})
        doing = next(t for t in feed["todos"]
                     if t["id"] == self.info["doing_todo"])
        self.assertEqual(doing["progress_check"], "30m")
        self.assertTrue(doing["progress_armed"].startswith(
            "2026-10-25T11:00"))

    def test_classification_derivation(self):
        feed = self.feeds.classification_feed(self.alpha)
        armed = feed["progress"]["armed"]
        self.assertEqual(len(armed), 1)
        block = armed[0]
        self.assertEqual(block["id"],
                         self.info["doing_todo"])
        self.assertEqual(block["interval_seconds"], 1800)
        # armed 2026-10-25, last checkpoint that day: by
        # any later run this is far past the stall line
        self.assertTrue(block["stalled"])
        self.assertGreaterEqual(block["missed_checks"], 2)
        self.assertEqual(feed["progress"]["summary"],
                         {"armed": 1, "stalled": 1})

    def test_board_portions(self):
        board = self.feeds.board_project_feed(self.alpha)
        self.assertEqual(
            set(board),
            {"slug", "name", "degraded", "captured_at",
             "todos", "plans", "review_queue", "counts",
             "done_page", "errors"})
        self.assertEqual(
            {r["id"] for r in board["review_queue"]},
            {"tile-a", "tile-b"})
        lanes = board["todos"]
        self.assertEqual(
            [c["title"] for c in lanes["todo"]],
            ["Open thing"])
        self.assertEqual(
            [c["title"] for c in lanes["doing"]],
            ["Doing thing"])
        self.assertEqual(
            [c["title"] for c in lanes["blocked"]],
            ["Blocked thing"])
        self.assertEqual(board["counts"]["todos"],
                         {"todo": 1, "doing": 1,
                          "blocked": 1, "done": 3})
        for lane in ("todo", "doing", "blocked", "done"):
            for card in lanes[lane]:
                for banned in ("body", "markdown",
                               "fields", "derived"):
                    self.assertNotIn(banned, card)
        plan = board["plans"]["doing"][0]
        self.assertEqual(plan["bundle"],
                         "2026-10-25-fixture-work")
        self.assertEqual(plan["step_count"], 2)

    def test_entries_and_detail(self):
        feed = self.feeds.entries_feed(self.alpha,
                                       archived=False)
        ids = {e["id"] for e in feed["entries"]}
        self.assertEqual(ids, {"tile-a", "tile-b",
                               "spec-doc"})
        db = self.alpha.manifest.registry
        detail = self.feeds.entry_detail(db, "tile-b")
        review = detail["latest_review"]
        self.assertEqual(review["verb"], "review")
        self.assertEqual(
            json.loads(review["new"])["disposition"],
            "needs-changes")

    def test_plans_feed_bundles_carry_the_plan(self):
        feed = self.feeds.plans_feed(self.alpha)
        # Loose plans: none — plans live inside bundles,
        # and ride the bundles array with their summaries.
        self.assertEqual(feed["plans"], [])
        bundle = feed["bundles"][0]
        self.assertEqual(bundle["id"],
                         "2026-10-25-fixture-work")
        self.assertEqual(bundle["plan"]["status_bucket"],
                         "doing")
        self.assertEqual(bundle["plan"]["title"],
                         "Fixture plan for the feeds")

    # -- armed feed + vocabulary ------------------------------

    def test_armed_feed_round_trip_and_schema(self):
        from server import armed as armed_mod
        feed = armed_mod.armed_feed()
        self.assertEqual(feed["skipped"], 0)
        self.assertEqual(len(feed["rows"]), 1)
        row = feed["rows"][0]
        schema = json.loads((CONTRACTS / "schemas"
                             / "armed-row.schema.json")
                            .read_text(encoding="utf-8"))
        for key in schema["required"]:
            self.assertIn(key, row)
        classes = schema["properties"]["source"][
            "properties"]["source_class"]["enum"]
        self.assertIn(row["source"]["source_class"],
                      classes)
        self.assertEqual(row["project"], "alpha")
        self.assertEqual(row["todo"],
                         self.info["doing_todo"])
        self.assertEqual(row["handle"],
                         self.info["doing_todo"])
        self.assertEqual(row["cadence"], "30m")
        self.assertEqual(row["cadence_minutes"], 30)
        self.assertEqual(row["status"], "doing")
        self.assertEqual(row["armed_at"],
                         "2026-10-25T11:00:00+00:00")
        self.assertEqual(row["source"]["writer"],
                         "workbench-harness")
        self.assertEqual(row["source"]["source_class"],
                         "fixture")

    def test_armed_feed_skips_unusable_rows(self):
        from server import armed as armed_mod
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "wb-armed-broken.json").write_text(
                "{not json", encoding="utf-8")
            (d / "wb-armed-alpha-x.json").write_text(
                json.dumps({"todo": "t-x"}),
                encoding="utf-8")
            (d / "unrelated.txt").write_text(
                "ignored", encoding="utf-8")
            feed = armed_mod.armed_feed(d)
        self.assertEqual(feed["rows"], [])
        self.assertEqual(feed["skipped"], 2)

    def test_status_vocabulary_matches_contract(self):
        vocab = self.assemble.status_vocabulary()
        fixture = json.loads(
            (CONTRACTS / "fixtures"
             / "attention-status-codes.json")
            .read_text(encoding="utf-8"))
        expected = fixture if isinstance(fixture, list) \
            else fixture.get("codes", fixture)
        self.assertEqual(len(vocab), 8)
        self.assertEqual(vocab, expected)

    # -- messages ---------------------------------------------

    def test_messages_carry_anchor_context(self):
        feed = self.messages_api.messages_list({})
        by_id = {m["id"]: m for m in feed["messages"]}
        note = by_id[self.info["annotation_id"]]
        self.assertIn("anchor_context", note)
        self.assertEqual(
            note["anchor_context"]["status"], "located")
        self.assertEqual(note["state"], "acknowledged")
        done = next(m for m in feed["messages"]
                    if m["body"] == "Handled already.")
        self.assertEqual(done["state"], "done")

    def test_outbox_events_and_drafts(self):
        # The outbox route is the watcher's event stream
        # (spec section 15.1); drafts surface through the
        # messages list's state filter.
        feed = self.messages_api.outbox_feed({})
        self.assertTrue(feed["events"])
        self.assertEqual(feed["last_id"],
                         feed["events"][-1]["id"])
        drafts = self.messages_api.messages_list(
            {"state": "draft"})
        self.assertEqual(
            [m["state"] for m in drafts["messages"]],
            ["draft"])

    # -- the assembly document --------------------------------

    def test_assemble_document(self):
        doc = self.assemble.build_feeds()
        for key in ("config", "home", "projects",
                    "projectFeeds", "repos", "repoDetails",
                    "messages", "outbox", "settings",
                    "armedRows", "armedSkipped",
                    "statusVocabulary", "goals",
                    "goalsSource"):
            self.assertIn(key, doc)
        # No pipeline goal-record store exists yet; the
        # document says so on its face instead of serving
        # invented records.
        self.assertEqual(doc["goals"], [])
        self.assertIn("goal", doc["goalsSource"].lower())
        alpha = doc["projectFeeds"]["alpha"]
        for key in ("entries", "plans", "todos",
                    "classification", "board",
                    "worktrees"):
            self.assertIn(key, alpha)
        plan_doc = alpha["planDocs"][
            "2026-10-25-fixture-work/plan.md"]
        self.assertEqual(plan_doc["step_count"], 2)
        self.assertEqual(plan_doc["fields"]["Executor"],
                         "fixture-lane")
        summary = {p["slug"]: p
                   for p in doc["projects"]["projects"]}
        manifest = summary["alpha"]["manifest"]
        self.assertEqual(manifest["registry"],
                         "workbench/registry.db")
        self.assertEqual(manifest["catalog"],
                         {"origin": "machine",
                          "generality":
                              "deployment-specific",
                          "use_case": "work-tracking"})
        # Detail scope (W4, cured at leg 7a):
        # delta-repo is a plain census repo (no
        # manifest), not project-linked — but it is a
        # top-level main checkout, so the document
        # carries its full repo document alongside its
        # summary. Its dataset also still serves
        # through the dataset derivation the pinned
        # dataset routes use on demand.
        summaries = {s["id"] for s in doc["repos"]["repos"]}
        self.assertIn("delta-repo", summaries)
        self.assertIn("delta-repo", doc["repoDetails"])
        self.assertIn("data/filings.csv",
                      doc["repoDetails"]["delta-repo"]
                      ["datasets"])
        from evaluation import datasets as datasets_mod
        dataset = datasets_mod.dataset_rows(
            str(self.info["delta"]), "data/filings.csv")
        self.assertEqual(len(dataset["rows"]), 2)
        self.assertIn("columns", dataset)
        self.assertEqual(len(doc["armedRows"]), 1)


if __name__ == "__main__":
    unittest.main()
