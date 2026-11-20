import json
import os
import tempfile
import unittest

from ops.flap import flap_series

SAMPLE = {"at": "2026-11-09T05:00:00Z", "verdict": "down",
          "exit": 0, "mechanisms": {}, "core_denied": []}


class FlapSeriesCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "series.jsonl")

    def test_append_and_tail_round_trip(self):
        self.assertIsNone(flap_series.append_line(
            self.path, json.dumps(SAMPLE)))
        line = flap_series.tail_line(self.path)
        self.assertEqual(json.loads(line)["verdict"], "down")

    def test_append_rejects_non_sample(self):
        self.assertIsNotNone(flap_series.append_line(self.path, "nope"))
        self.assertIsNotNone(flap_series.append_line(
            self.path, json.dumps({"verdict": "down"})))
        self.assertIsNone(flap_series.tail_line(self.path))

    def test_tail_missing_file_is_none(self):
        self.assertIsNone(flap_series.tail_line(self.path))

    def test_appends_accumulate_in_order(self):
        for verdict in ("down", "mixed", "down"):
            sample = dict(SAMPLE, verdict=verdict)
            self.assertIsNone(flap_series.append_line(
                self.path, json.dumps(sample)))
        with open(self.path, encoding="utf-8") as fh:
            verdicts = [json.loads(ln)["verdict"] for ln in fh if ln.strip()]
        self.assertEqual(verdicts, ["down", "mixed", "down"])

    def test_main_verbs(self):
        self.assertEqual(flap_series.main(
            ["--file", self.path, "append", json.dumps(SAMPLE)]), 0)
        self.assertEqual(flap_series.main(["--file", self.path, "tail"]), 0)
        self.assertEqual(flap_series.main(["--file", self.path, "bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
