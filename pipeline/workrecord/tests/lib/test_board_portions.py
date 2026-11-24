"""Board portion gate tests: the board's per-project
portion contract, driven through the server package in a
subprocess against two fixture projects (heavy-feed
batching; re-expressed at S8 — the pinned
test drove the same assertions over real HTTP through
run.py; the moved tree's serving process is S11's, so
the portions are computed through the feeds module the
process will serve, in a subprocess so the config loads
exactly as it does at serve time).

Proves: one portion per project instead of a board
monolith; card projections carry only the fields the
board cards render (no bodies, raw markdown, or step
lists — those stay in the section feeds); the done lanes
are paginated with their totals riding along while the
open lanes serve whole; one project's portion never
carries another project's cards; and the feeds module
exposes no monolith board producer.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from lib.writes import bundles as bundle_mod
from lib import registry as reg

REPO = Path(__file__).resolve().parent.parent.parent
PY = REPO / ".venv" / "bin" / "python"
DRIVER = REPO / "tests" / "server" / "board_driver.py"

MOCK = ('<style>:root{--ink:#111}</style>'
        '<h1 style="color:var(--ink)">A</h1>\n')

DONE_COUNT = 60


def make_project(ws: Path, slug: str, name: str,
                 done_history: bool) -> Path:
    root = ws / slug
    (root / "workbench").mkdir(parents=True)
    (root / ".plans").mkdir()
    (root / "workbench.yaml").write_text(
        f"name: {name}\n"
        "registry: workbench/registry.db\n"
        "plans: .plans\n"
        "mockups: workbench/entries\n"
        "archive: workbench/archive\n", encoding="utf-8")
    db = root / "workbench" / "registry.db"
    reg.init_registry(db)
    layout = (root / "workbench" / "entries",
              root / "workbench" / "archive")
    entry = reg.add_entry(db, layout, "tile-a", title="Tile A")
    main = Path(entry["entry_dir"]) / "mock.html"
    main.write_text(MOCK, encoding="utf-8")
    reg.verify_entry(db, "tile-a", accept_drift=True)
    plans = root / ".plans"
    bundle_mod.create_bundle(plans, "fixture-work",
                             today="2026-10-25")
    bundle_mod.create_todo(plans, "fixture-work",
                           "Do the thing")
    bundle_mod.create_todo(plans, "fixture-work",
                           "Blocked thing", status="blocked")
    bundle_mod.create_bundle(plans, "fixture-planned",
                             plan=True, today="2026-10-25")
    if done_history:
        bundle_mod.create_bundle(plans, "done-history",
                                 today="2026-10-25")
        for i in range(DONE_COUNT):
            bundle_mod.create_todo(
                plans, "done-history", f"Done thing {i:02d}",
                status="done", body="history " * 40)
    return root


class BoardPortionCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="wb-board-"))
        ws = cls.tmp / "ws"
        ws.mkdir()
        cls.alpha = make_project(ws, "alpha", "Alpha", True)
        cls.beta = make_project(ws, "beta", "Beta", False)
        cfg = {"workspace_root": str(ws),
               "sweep_roots": [str(ws)],
               "state_dir": str(cls.tmp / "state"),
               "file_editing_enabled": False,
               "sweep_ttl_s": 1}
        cls.cfg_path = cls.tmp / "config.json"
        cls.cfg_path.write_text(json.dumps(cfg),
                                encoding="utf-8")
        out_path = cls.tmp / "portions.json"
        env = {**os.environ,
               "WB_VIEWER_CONFIG": str(cls.cfg_path),
               "PYTHONPATH": str(REPO)}
        proc = subprocess.run(
            [str(PY), str(DRIVER), str(out_path)],
            env=env, capture_output=True, text=True,
            timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(
                "board driver failed: "
                + proc.stderr[-2000:])
        cls.out = json.loads(out_path.read_text(
            encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_portion_shape_counts_and_review(self):
        p = self.out["alpha_board"]
        self.assertEqual(p["slug"], "alpha")
        self.assertEqual(p["counts"]["todos"]["todo"], 1)
        self.assertEqual(p["counts"]["todos"]["blocked"], 1)
        self.assertEqual(p["counts"]["todos"]["done"],
                         DONE_COUNT)
        self.assertEqual(p["counts"]["plans"]["todo"], 1)
        self.assertEqual(p["counts"]["review_queue"], 1)
        self.assertEqual(p["review_queue"][0]["id"], "tile-a")
        self.assertEqual(p["review_queue"][0]["kind"],
                         "mockup")
        todo_titles = [t["title"] for t in p["todos"]["todo"]]
        self.assertEqual(todo_titles, ["Do the thing"])
        blocked = [t["title"] for t in p["todos"]["blocked"]]
        self.assertEqual(blocked, ["Blocked thing"])

    def test_cards_are_projections(self):
        p = self.out["alpha_board"]
        cards = (p["todos"]["todo"] + p["todos"]["blocked"]
                 + p["todos"]["done"])
        self.assertTrue(cards)
        for card in cards:
            for heavy in ("body", "markdown",
                          "content_sha256", "fields",
                          "derived"):
                self.assertNotIn(heavy, card)
            self.assertEqual(card["project"], "alpha")
            self.assertEqual(card["project_name"], "Alpha")
            self.assertTrue(card["id"])
            self.assertTrue(card["path"])
        for plan in p["plans"]["todo"]:
            self.assertNotIn("steps", plan)
            self.assertIn("step_count", plan)
            self.assertEqual(plan["bundle"],
                             "2026-10-25-fixture-planned")
        # the section feed still serves the full rows —
        # projection is a board-portion property only
        feed = self.out["alpha_todos"]
        done_rows = [t for t in feed["todos"]
                     if t["status"] == "done"]
        self.assertTrue(done_rows)
        self.assertIn("body", done_rows[0])

    def test_done_lanes_paginate_with_totals(self):
        p = self.out["alpha_board"]
        # default page = board_done_page (50)
        self.assertEqual(len(p["todos"]["done"]), 50)
        self.assertEqual(p["done_page"],
                         {"offset": 0, "limit": 50})
        first_ids = {t["id"] for t in p["todos"]["done"]}
        p2 = self.out["alpha_board_offset50"]
        self.assertEqual(len(p2["todos"]["done"]),
                         DONE_COUNT - 50)
        second_ids = {t["id"] for t in p2["todos"]["done"]}
        self.assertFalse(first_ids & second_ids)
        # totals do not move with the page
        self.assertEqual(p2["counts"]["todos"]["done"],
                         DONE_COUNT)
        p3 = self.out["alpha_board_limit5"]
        self.assertEqual(len(p3["todos"]["done"]), 5)
        self.assertEqual(p3["done_page"]["limit"], 5)
        # junk paging args degrade to the defaults
        p4 = self.out["alpha_board_junk"]
        self.assertEqual(p4["done_page"]["offset"], 0)
        self.assertEqual(p4["done_page"]["limit"], 50)

    def test_portions_are_per_project(self):
        p = self.out["beta_board"]
        self.assertEqual(p["slug"], "beta")
        self.assertEqual(p["counts"]["todos"]["done"], 0)
        self.assertEqual(p["todos"]["done"], [])
        for lane in p["todos"].values():
            for card in lane:
                self.assertEqual(card["project"], "beta")

    def test_board_monolith_is_gone(self):
        # The legacy board monolith was dropped (threadpool
        # plan, step 6): portions are the only board
        # surface the feeds module exposes.
        self.assertEqual(self.out["board_functions"],
                         ["board_project_feed"])


if __name__ == "__main__":
    unittest.main()
