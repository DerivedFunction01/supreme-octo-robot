"""The writer-uniqueness component: the write forms it
fails on (a truncate-write of a state-shaped path; a
duplicate staged-write implementation, full and partial),
the forms it must not flag (reads, non-state writes,
writes riding the writer seam, staging temps), the
declared-seam discipline (a declared file's findings are
notes; a declaration with no matching pattern is itself
a finding), and the scan over a fixture tree — a clean
tree passes, specimens fail by name, and the finding line
names file + kind, never content. Specimen sources are
written at runtime into scratch trees so no tracked file
carries a violating write for the scan to find."""
import os
import shutil
import tempfile
import unittest

from gate import writeruniqueness as wu


def kinds(findings):
    return [(lineno, kind) for lineno, kind in findings]


class TruncateWriteTests(unittest.TestCase):
    def test_open_write_under_var_is_a_finding(self):
        src = ("def save(path):\n"
               "    with open('var/attention-state.json', "
               "'w') as fh:\n"
               "        fh.write('{}')\n")
        self.assertEqual(
            kinds(wu.scan_source(src)), [(2, "truncate-write")])

    def test_open_write_under_state_segment_is_a_finding(self):
        src = ("target = os.path.join(root, 'state', "
               "'config.json')\n"
               "with open(target, 'w') as fh:\n"
               "    fh.write('x')\n")
        self.assertEqual(
            kinds(wu.scan_source(src)), [(2, "truncate-write")])

    def test_write_text_on_a_jsonl_store_is_a_finding(self):
        src = ("from pathlib import Path\n"
               "Path('state/releases.jsonl').write_text('x')\n")
        self.assertEqual(
            kinds(wu.scan_source(src)), [(2, "truncate-write")])

    def test_state_constant_target_is_a_finding(self):
        src = ("STATE = os.path.join(BASE, 'store.json')\n"
               "def save(data):\n"
               "    with open(STATE, 'wb') as fh:\n"
               "        fh.write(data)\n")
        self.assertEqual(
            kinds(wu.scan_source(src)), [(3, "truncate-write")])

    def test_state_dir_reference_is_a_finding(self):
        src = ("def save(paths, data):\n"
               "    target = os.path.join(paths.STATE_DIR, "
               "'x.json')\n"
               "    with open(target, 'w') as fh:\n"
               "        fh.write(data)\n")
        self.assertEqual(
            kinds(wu.scan_source(src)), [(3, "truncate-write")])

    def test_read_open_of_a_state_path_is_fine(self):
        src = ("with open('var/attention-state.json') as fh:\n"
               "    data = fh.read()\n")
        self.assertEqual(wu.scan_source(src), [])

    def test_write_to_a_non_state_path_is_fine(self):
        src = ("def report(path, text):\n"
               "    with open(path, 'w') as fh:\n"
               "        fh.write(text)\n")
        self.assertEqual(wu.scan_source(src), [])

    def test_write_riding_the_writer_seam_is_fine(self):
        src = ("def save(writer, path, data):\n"
               "    writer.staged_write(path, data)\n")
        self.assertEqual(wu.scan_source(src), [])

    def test_variable_mode_is_the_stated_limit(self):
        src = ("def save(path, mode):\n"
               "    with open(path, mode) as fh:\n"
               "        fh.write('x')\n")
        self.assertEqual(wu.scan_source(src), [])


class StagedWriteTests(unittest.TestCase):
    def test_full_protocol_copy_is_a_finding(self):
        src = ("def save(path, data):\n"
               "    tmp = path + '.tmp'\n"
               "    with open(tmp, 'wb') as fh:\n"
               "        fh.write(data)\n"
               "        fh.flush()\n"
               "        os.fsync(fh.fileno())\n"
               "    os.replace(tmp, path)\n")
        self.assertEqual(
            kinds(wu.scan_source(src)),
            [(7, "duplicate-staged-write")])

    def test_partial_copy_without_fsync_is_a_finding(self):
        src = ("def save(path, data):\n"
               "    staging = f'{path}.staging-1'\n"
               "    with open(staging, 'w') as fh:\n"
               "        fh.write(data)\n"
               "    os.replace(staging, path)\n")
        self.assertEqual(
            kinds(wu.scan_source(src)),
            [(5, "partial-staged-write")])

    def test_staging_write_is_not_a_truncate_write(self):
        # The staged target sits under var/ — state-shaped
        # — but it is renamed over the target in the same
        # scope: the staged-write check's jurisdiction.
        src = ("def save(data):\n"
               "    tmp = 'var/.state.json.tmp'\n"
               "    with open(tmp, 'w') as fh:\n"
               "        fh.write(data)\n"
               "    os.replace(tmp, 'var/state.json')\n")
        found = kinds(wu.scan_source(src))
        self.assertEqual(found, [(5, "partial-staged-write")])

    def test_pathlib_rename_form_is_a_finding(self):
        src = ("def save(path, data):\n"
               "    tmp = path.with_name('.tmp')\n"
               "    tmp.write_bytes(data)\n"
               "    tmp.replace(path)\n")
        self.assertEqual(
            kinds(wu.scan_source(src)),
            [(4, "partial-staged-write")])

    def test_unrelated_replace_is_fine(self):
        src = ("def clean(text):\n"
               "    return text.replace('a', 'b')\n")
        self.assertEqual(wu.scan_source(src), [])

    def test_writer_home_is_never_scanned(self):
        src = ("def staged_write(path, data):\n"
               "    tmp = path + '.tmp'\n"
               "    with open(tmp, 'wb') as fh:\n"
               "        fh.write(data)\n"
               "        os.fsync(fh.fileno())\n"
               "    os.replace(tmp, path)\n")
        rows, failures = wu.evaluate(
            {"pipeline/platform/writer.py": src}, [])
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])


class ExceptionDisciplineTests(unittest.TestCase):
    SPECIMEN = (
        "def save(path, data):\n"
        "    tmp = path + '.tmp'\n"
        "    with open(tmp, 'wb') as fh:\n"
        "        fh.write(data)\n"
        "        os.fsync(fh.fileno())\n"
        "    os.replace(tmp, path)\n")

    def test_declared_seam_is_a_note_not_a_failure(self):
        decl = [{"path": "pkg/fallback.py",
                 "kind": "standalone fallback seam"}]
        rows, failures = wu.evaluate(
            {"pkg/fallback.py": self.SPECIMEN}, decl)
        self.assertEqual(failures, [])
        self.assertEqual(
            rows, [("pkg/fallback.py", 6,
                    "duplicate-staged-write",
                    "standalone fallback seam")])

    def test_undeclared_reliance_is_an_ordinary_finding(self):
        rows, failures = wu.evaluate(
            {"pkg/store.py": self.SPECIMEN}, [])
        self.assertEqual(
            failures, [("pkg/store.py", 6,
                        "duplicate-staged-write", None)])

    def test_stale_exception_is_itself_a_finding(self):
        decl = [{"path": "pkg/clean.py",
                 "kind": "standalone fallback seam"}]
        rows, failures = wu.evaluate(
            {"pkg/clean.py": "import os\n"}, decl)
        self.assertEqual(
            failures, [("pkg/clean.py", 0, "stale-exception",
                        "standalone fallback seam")])

    def test_exception_outside_the_scan_is_not_judged(self):
        decl = [{"path": "other/pkg.py",
                 "kind": "standalone fallback seam"}]
        rows, failures = wu.evaluate({"pkg/clean.py": "x = 1\n"},
                                     decl)
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])


def _fixture_tree(files):
    """A scratch package tree: {relpath: source} written
    at runtime. Not a git tree — the enumeration's walk
    fallback is the form the scan takes there."""
    root = tempfile.mkdtemp(prefix="gate-writeruniqueness-")
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
                "def save(writer, path, data):\n"
                "    writer.staged_write(path, data)\n"),
            "report.py": (
                "def emit(path, text):\n"
                "    with open(path, 'w') as fh:\n"
                "        fh.write(text)\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        rows, failures, scanned = wu.scan(root, root)
        self.assertEqual(failures, [])
        self.assertEqual(scanned, 2)
        self.assertEqual(
            wu.render(rows, failures, scanned),
            ["writer-uniqueness: ok (2 files scanned)"])

    def test_specimen_fails_by_name_content_never_printed(self):
        root = _fixture_tree({
            "store.py": (
                "def save(data):\n"
                "    with open('var/state.json', 'w') as fh:\n"
                "        fh.write(data)\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        rows, failures, scanned = wu.scan(root, root)
        self.assertEqual(
            failures, [("store.py", 2, "truncate-write", None)])
        rendered = "\n".join(wu.render(rows, failures, scanned))
        self.assertIn("store.py:2", rendered)
        self.assertIn("truncate-write", rendered)
        self.assertNotIn("state.json", rendered)


if __name__ == "__main__":
    unittest.main()
