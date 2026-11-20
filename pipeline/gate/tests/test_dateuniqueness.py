"""The date-uniqueness component: the copy shapes it
fails on (one per family — parse, normalize, epoch, now
in both its forms, format), the forms it must not flag
(a consumer's larger computation, a composition over a
home, a delegation to a home), the declaration
discipline (a copy in its family's homed module is a
note; a sanctioned copy is a note with its reason; a
sanction or leg exception whose file no longer carries
a matching pattern is itself a finding), the
out-of-scope file classes (test, deployed), and the
scan over a fixture tree — a clean tree passes,
specimens fail by name, and the finding line names
file + family, never content. All specimens are fixture
sources and fixture data, written at runtime into
scratch trees; the live tree's state is never read.
"""
import os
import shutil
import tempfile
import unittest

from gate import dateuniqueness as du

PARSE_COPY = (
    "def parse_iso(text):\n"
    "    if not text:\n"
    "        return None\n"
    "    try:\n"
    "        return datetime.fromisoformat(\n"
    "            text.replace('Z', '+00:00'))\n"
    "    except ValueError:\n"
    "        return None\n")

NORMALIZE_COPY = (
    "def _as_dt(value):\n"
    "    if isinstance(value, datetime):\n"
    "        return value\n"
    "    try:\n"
    "        return datetime.fromisoformat(value)\n"
    "    except ValueError:\n"
    "        return None\n")

EPOCH_COPY = (
    "def _epoch(text):\n"
    "    try:\n"
    "        return datetime.fromisoformat(text).timestamp()\n"
    "    except ValueError:\n"
    "        return None\n")

NOW_COPY = (
    "def now_iso():\n"
    "    return datetime.now(timezone.utc).isoformat()\n")

NOW_GMTIME_COPY = (
    "def now():\n"
    "    return time.strftime('%Y-%m-%dT%H:%M:%SZ',\n"
    "                         time.gmtime())\n")

FORMAT_COPY = (
    "def iso(dt):\n"
    "    return dt.astimezone(timezone.utc).isoformat()\n")

FIXTURE_DATA = {
    "families": {
        "parse": {"homes": [
            {"path": "pkg/dates.py",
             "cluster": "fixture cluster",
             "exports": ["parse_iso"]}]},
    },
    "sanctioned_copies": [
        {"path": "pkg/proof.py", "function": "parse_iso",
         "family": "parse", "kind": "fixture dialect"}],
    "out_of_scope": [],
}


def shapes(findings):
    return [(lineno, family)
            for lineno, family, _qual, _name in findings]


class ShapeTests(unittest.TestCase):
    def test_parse_copy_is_a_finding(self):
        self.assertEqual(
            shapes(du.scan_source(PARSE_COPY)), [(1, "parse")])

    def test_normalize_copy_is_a_finding(self):
        self.assertEqual(
            shapes(du.scan_source(NORMALIZE_COPY)),
            [(1, "normalize")])

    def test_epoch_copy_is_a_finding(self):
        self.assertEqual(
            shapes(du.scan_source(EPOCH_COPY)), [(1, "epoch")])

    def test_now_copy_is_a_finding(self):
        self.assertEqual(
            shapes(du.scan_source(NOW_COPY)), [(1, "now")])

    def test_now_gmtime_copy_is_a_finding(self):
        self.assertEqual(
            shapes(du.scan_source(NOW_GMTIME_COPY)), [(1, "now")])

    def test_format_copy_is_a_finding(self):
        self.assertEqual(
            shapes(du.scan_source(FORMAT_COPY)), [(1, "format")])

    def test_method_and_nested_copies_are_findings(self):
        src = ("class Store:\n"
               "    def parse(self, text):\n"
               "        return datetime.fromisoformat(text)\n")
        self.assertEqual(
            shapes(du.scan_source(src)), [(2, "parse")])


class ConsumerTests(unittest.TestCase):
    def test_larger_computation_is_a_consumer(self):
        src = ("def sort_key(record):\n"
               "    parsed = datetime.fromisoformat(record['at'])\n"
               "    return (parsed, len(record['name']),\n"
               "            record['id'].lower())\n")
        self.assertEqual(du.scan_source(src), [])

    def test_composition_over_a_home_is_a_consumer(self):
        src = ("def now_iso():\n"
               "    return iso(datetime.now(timezone.utc))\n")
        self.assertEqual(du.scan_source(src), [])

    def test_delegation_to_a_home_is_a_consumer(self):
        src = ("def _parse(at):\n"
               "    try:\n"
               "        return foundation.parse_dt(str(at))\n"
               "    except (TypeError, ValueError):\n"
               "        return None\n")
        self.assertEqual(du.scan_source(src), [])

    def test_unparseable_file_yields_no_findings(self):
        self.assertEqual(du.scan_source("def broken(:\n"), [])


class DeclarationTests(unittest.TestCase):
    def test_copy_in_its_home_is_a_note(self):
        rows, failures = du.evaluate(
            {"pkg/dates.py": PARSE_COPY}, [], FIXTURE_DATA)
        self.assertEqual(failures, [])
        self.assertEqual(
            rows, [("pkg/dates.py", 1, "parse-copy",
                    "home: fixture cluster")])

    def test_copy_outside_its_home_is_a_failure(self):
        rows, failures = du.evaluate(
            {"pkg/store.py": PARSE_COPY}, [], FIXTURE_DATA)
        self.assertEqual(
            failures, [("pkg/store.py", 1, "parse-copy", None)])

    def test_other_family_copy_in_a_home_still_fails(self):
        rows, failures = du.evaluate(
            {"pkg/dates.py": FORMAT_COPY}, [], FIXTURE_DATA)
        self.assertEqual(
            failures, [("pkg/dates.py", 1, "format-copy", None)])

    def test_sanctioned_copy_is_a_note_with_its_reason(self):
        rows, failures = du.evaluate(
            {"pkg/proof.py": PARSE_COPY}, [], FIXTURE_DATA)
        self.assertEqual(failures, [])
        self.assertEqual(
            rows, [("pkg/proof.py", 1, "parse-copy",
                    "fixture dialect")])

    def test_stale_sanction_is_itself_a_finding(self):
        rows, failures = du.evaluate(
            {"pkg/proof.py": "x = 1\n"}, [], FIXTURE_DATA)
        self.assertEqual(
            failures, [("pkg/proof.py", 0, "stale-exception",
                        "fixture dialect")])

    def test_sanction_outside_the_scan_is_not_judged(self):
        rows, failures = du.evaluate(
            {"pkg/clean.py": "x = 1\n"}, [], FIXTURE_DATA)
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])

    def test_leg_exception_is_a_note(self):
        decl = [{"path": "pkg/store.py",
                 "kind": "named lane's in-flight copy"}]
        rows, failures = du.evaluate(
            {"pkg/store.py": PARSE_COPY}, decl, FIXTURE_DATA)
        self.assertEqual(failures, [])
        self.assertEqual(
            rows, [("pkg/store.py", 1, "parse-copy",
                    "named lane's in-flight copy")])

    def test_stale_leg_exception_is_itself_a_finding(self):
        decl = [{"path": "pkg/clean.py",
                 "kind": "named lane's in-flight copy"}]
        rows, failures = du.evaluate(
            {"pkg/clean.py": "import os\n"}, decl, FIXTURE_DATA)
        self.assertEqual(
            failures, [("pkg/clean.py", 0, "stale-exception",
                        "named lane's in-flight copy")])


class ScopeClassTests(unittest.TestCase):
    def test_test_class_files_are_out_of_scope(self):
        rows, failures = du.evaluate(
            {"pkg/tests/test_store.py": PARSE_COPY,
             "pkg/test_store.py": PARSE_COPY}, [], FIXTURE_DATA)
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])

    def test_deployed_class_files_are_out_of_scope(self):
        rows, failures = du.evaluate(
            {"pipeline/venue/adapters/colab/snippets/x.py":
             PARSE_COPY}, [], FIXTURE_DATA)
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])


def _fixture_tree(files):
    """A scratch package tree: {relpath: source} written
    at runtime. Not a git tree — the enumeration's walk
    fallback is the form the scan takes there."""
    root = tempfile.mkdtemp(prefix="gate-dateuniqueness-")
    for relpath, source in files.items():
        full = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(source)
    return root


class FixtureTreeScanTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        root = _fixture_tree({
            "store.py": (
                "def sort_key(record):\n"
                "    parsed = datetime.fromisoformat("
                "record['at'])\n"
                "    return (parsed, len(record['name']))\n"),
            "report.py": (
                "def emit(path, text):\n"
                "    with open(path, 'w') as fh:\n"
                "        fh.write(text)\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        rows, failures, scanned = du.scan(root, root)
        self.assertEqual(failures, [])
        self.assertEqual(scanned, 2)
        self.assertEqual(
            du.render(rows, failures, scanned),
            ["date-uniqueness: ok (2 files scanned)"])

    def test_specimen_fails_by_name_content_never_printed(self):
        root = _fixture_tree({"store.py": PARSE_COPY})
        self.addCleanup(shutil.rmtree, root, True)
        rows, failures, scanned = du.scan(root, root)
        self.assertEqual(
            failures, [("store.py", 1, "parse-copy", None)])
        rendered = "\n".join(du.render(rows, failures, scanned))
        self.assertIn("store.py:1", rendered)
        self.assertIn("parse-copy", rendered)
        self.assertNotIn("fromisoformat", rendered)


class DataMapTests(unittest.TestCase):
    def test_map_names_every_family_and_its_homes(self):
        for family in ("normalize", "parse", "epoch", "now",
                       "format"):
            self.assertIn(family, du.DATA["families"])
            self.assertTrue(
                du.DATA["families"][family]["homes"])

    def test_sanctions_name_known_families(self):
        for entry in du.DATA["sanctioned_copies"]:
            self.assertIn(entry["family"], du.DATA["families"])


if __name__ == "__main__":
    unittest.main()
