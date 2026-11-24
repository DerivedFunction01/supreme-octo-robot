"""The serve boot record (server/bootrecord.py): one
appended record per serve startup in the scheduler's
state home, the previous boot's record left intact, and
the ready stamp carrying the startup latency. The
specimens pin the outage cure's evidence form: after a
serve death, the record set itself must say when each
boot started, from what code, and whether it became
ready — no journal, no live process to interrogate.
All stamps are injected; nothing here reads the live
machine, a live home, or a live repo."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from server import bootrecord

UTC = timezone.utc
T0 = datetime(2026, 11, 24, 13, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 11, 24, 13, 0, 7, 250000, tzinfo=UTC)


class BootRecordCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, "state"))
        self.path = bootrecord.record_path(self.home)

    def open_boot(self, instance, **overrides):
        kwargs = {
            "entry": "run.py serve",
            "repo_root": self.tmp,
            "now": T0,
            "boot_id": "boot-aaaa",
            "instance": instance,
            "pid": 4242,
            "stamp": ("head-111", "tree-222"),
        }
        kwargs.update(overrides)
        return bootrecord.open_boot(self.path, **kwargs)

    def read_file(self):
        with open(self.path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_record_path_is_the_state_home_form(self):
        self.assertEqual(
            self.path,
            os.path.join(self.home, "state", "serve-boots.json"))

    def test_open_boot_writes_the_full_record(self):
        record = self.open_boot("inst-1")
        self.assertEqual(record["instance"], "inst-1")
        self.assertEqual(record["boot_id"], "boot-aaaa")
        self.assertEqual(record["entry"], "run.py serve")
        self.assertEqual(record["pid"], 4242)
        self.assertEqual(record["started_at"], T0.isoformat())
        self.assertEqual(record["head"], "head-111")
        self.assertEqual(record["tree"], "tree-222")
        self.assertIsNone(record["ready_at"])
        self.assertIsNone(record["startup_latency_s"])
        self.assertEqual(self.read_file(), {"boots": [record]})

    def test_second_boot_leaves_the_first_record_intact(self):
        first = self.open_boot("inst-1")
        second = self.open_boot(
            "inst-2", now=T1, boot_id="boot-aaaa",
            stamp=("head-333", "tree-444"))
        boots = self.read_file()["boots"]
        self.assertEqual(boots, [first, second])
        self.assertEqual(boots[0]["head"], "head-111")
        self.assertEqual(boots[1]["head"], "head-333")

    def test_stamp_ready_records_latency_from_process_start(self):
        self.open_boot("inst-1")
        stamped = bootrecord.stamp_ready(
            self.path, "inst-1", started_monotonic=100.0,
            now=T1, monotonic=107.25)
        self.assertTrue(stamped)
        record = self.read_file()["boots"][0]
        self.assertEqual(record["ready_at"], T1.isoformat())
        self.assertEqual(record["startup_latency_s"], 7.25)

    def test_stamp_ready_for_an_unknown_instance_writes_nothing(self):
        self.open_boot("inst-1")
        before = self.read_file()
        stamped = bootrecord.stamp_ready(
            self.path, "inst-absent", started_monotonic=100.0,
            now=T1, monotonic=107.25)
        self.assertFalse(stamped)
        self.assertEqual(self.read_file(), before)

    def test_an_unready_record_stays_unready(self):
        """A boot that died before health-ready is legible
        as exactly that: started_at stands, the ready
        fields stay None, and the next boot's record does
        not repair it."""
        self.open_boot("inst-1")
        self.open_boot("inst-2")
        boots = self.read_file()["boots"]
        self.assertIsNone(boots[0]["ready_at"])
        self.assertIsNone(boots[0]["startup_latency_s"])

    def test_corrupt_record_is_moved_aside_not_discarded(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        record = self.open_boot("inst-9")
        aside = f"{self.path}.corrupt-inst-9"
        with open(aside, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{not json")
        self.assertEqual(self.read_file(), {"boots": [record]})

    def test_kernel_boot_id_reads_the_file_and_tolerates_absence(self):
        boot_file = os.path.join(self.tmp, "boot_id")
        with open(boot_file, "w", encoding="utf-8") as fh:
            fh.write("boot-bbbb\n")
        self.assertEqual(
            bootrecord.kernel_boot_id(boot_file), "boot-bbbb")
        self.assertIsNone(bootrecord.kernel_boot_id(
            os.path.join(self.tmp, "no-such-file")))

    def test_code_stamp_of_a_non_repo_is_none_not_an_error(self):
        head, tree = bootrecord.code_stamp(self.tmp)
        self.assertIsNone(head)
        self.assertIsNone(tree)


if __name__ == "__main__":
    unittest.main()
