"""The argv-idioms component: the idiom shapes it
fails on (the membership value take, the index
extraction, known-args forwarding, argparse left at
its abbreviation default on a census entry point, the
single-$1 shell flag test, the JS membership/index
forms), the forms it must not flag (the unified
implementations themselves, equals-form argparse with
abbreviations disabled, ordinary membership tests that
are not flag-shaped), the census discipline (an
unmigrated census entry's findings are notes, never
failures, with no stale discipline; a migrated one is
judged in full), the declared-seam discipline (a
declared file's findings are notes; a declaration with
no matching pattern is itself a finding), and the scan
over a fixture tree. Specimen sources are written at
runtime into scratch trees so no tracked file carries
a violating idiom for the scan to find."""
import os
import shutil
import tempfile
import unittest

from gate import argvidioms as ai


def kinds(findings):
    return [(lineno, kind) for lineno, kind in findings]


class PythonIdiomTests(unittest.TestCase):
    def test_membership_value_take_is_a_finding(self):
        src = ("def main(argv):\n"
               "    if \"--caller\" in argv:\n"
               "        caller = argv[argv.index(\"--caller\") + 1]\n")
        self.assertEqual(
            kinds(ai.scan_python_source(src)),
            [(2, "membership-flag-test"),
             (3, "index-flag-extraction")])

    def test_membership_boolean_scan_is_a_finding(self):
        src = "dry_run = \"--dry-run\" in sys.argv[1:]\n"
        self.assertEqual(
            kinds(ai.scan_python_source(src)),
            [(1, "membership-flag-test")])

    def test_parse_known_args_is_a_finding(self):
        src = ("def main():\n"
               "    args, rest = parser.parse_known_args()\n")
        self.assertEqual(
            kinds(ai.scan_python_source(src)),
            [(2, "known-args-forwarding")])

    def test_plain_membership_is_fine(self):
        src = ("def main(argv):\n"
               "    if \"verbose\" in argv:\n"
               "        pass\n")
        self.assertEqual(ai.scan_python_source(src), [])

    def test_index_on_a_non_argv_expression_is_fine(self):
        src = ("def find(items, wanted):\n"
               "    return items.index(wanted)\n")
        self.assertEqual(ai.scan_python_source(src), [])

    def test_membership_against_a_list_literal_is_fine(self):
        src = "ok = \"--x\" in [\"--x\", \"--y\"]\n"
        self.assertEqual(ai.scan_python_source(src), [])

    def test_argparse_abbreviations_judged_only_for_census(self):
        src = ("import argparse\n"
               "parser = argparse.ArgumentParser()\n")
        self.assertEqual(ai.scan_python_source(src), [])
        self.assertEqual(
            kinds(ai.scan_python_for(src, is_census=True)),
            [(2, "argparse-abbreviations")])

    def test_argparse_with_abbreviations_disabled_is_fine(self):
        src = ("import argparse\n"
               "parser = argparse.ArgumentParser(allow_abbrev=False)\n")
        self.assertEqual(ai.scan_python_for(src, is_census=True), [])


class ShellAndJsIdiomTests(unittest.TestCase):
    def test_single_dollar1_flag_test_is_a_finding(self):
        src = ("#!/usr/bin/env bash\n"
               "if [ \"${1:-}\" = \"--dry-run\" ]; then\n"
               "  echo dry\n"
               "fi\n")
        self.assertEqual(
            kinds(ai.scan_shell_source(src)),
            [(2, "single-dollar1-flag-test")])

    def test_dollar1_verb_dispatch_is_fine(self):
        src = ("case \"${1:-}\" in\n"
               "  start) echo go ;;\n"
               "esac\n")
        self.assertEqual(ai.scan_shell_source(src), [])

    def test_js_membership_and_index_are_findings(self):
        src = ("const verbose = process.argv.includes(\"--verbose\");\n"
               "const at = process.argv.indexOf(\"--port\");\n")
        self.assertEqual(
            kinds(ai.scan_js_source(src)),
            [(1, "argv-membership"), (2, "argv-index")])

    def test_js_bare_argv_variable_is_a_finding(self):
        src = "if (argv.includes(\"--force\")) go();\n"
        self.assertEqual(kinds(ai.scan_js_source(src)),
                         [(1, "argv-membership")])

    def test_js_served_data_argv_field_is_not_a_finding(self):
        src = ("check(entry.run.argv.includes(\"progress-check\"));\n"
               "const n = entry.run.argv.indexOf(\"x\");\n")
        self.assertEqual(ai.scan_js_source(src), [])


class HomeTests(unittest.TestCase):
    SPECIMEN = "x = \"--caller\" in argv\n"

    def test_homes_are_never_scanned(self):
        for home in ("pipeline/platform/argv.py", "argv.py"):
            rows, failures = ai.evaluate({home: self.SPECIMEN}, [])
            self.assertEqual(rows, [])
            self.assertEqual(failures, [])


class CensusDisciplineTests(unittest.TestCase):
    SPECIMEN = "x = \"--caller\" in argv\n"

    def test_unmigrated_census_entry_is_a_note(self):
        census = {"pkg/tool.py": False}
        rows, failures = ai.evaluate(
            {"pkg/tool.py": self.SPECIMEN}, [], census=census)
        self.assertEqual(failures, [])
        self.assertEqual(
            rows, [("pkg/tool.py", 1, "membership-flag-test",
                    "census entry — migration pending")])

    def test_migrated_census_entry_is_judged_in_full(self):
        census = {"pkg/tool.py": True}
        rows, failures = ai.evaluate(
            {"pkg/tool.py": self.SPECIMEN}, [], census=census)
        self.assertEqual(
            failures, [("pkg/tool.py", 1,
                        "membership-flag-test", None)])

    def test_clean_unmigrated_census_entry_is_not_stale(self):
        census = {"pkg/tool.py": False}
        rows, failures = ai.evaluate(
            {"pkg/tool.py": "import argparse\n"}, [], census=census)
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])


class ExceptionDisciplineTests(unittest.TestCase):
    SPECIMEN = "x = \"--caller\" in argv\n"

    def test_declared_seam_is_a_note_not_a_failure(self):
        decl = [{"path": "pkg/legacy.py", "kind": "named seam"}]
        rows, failures = ai.evaluate({"pkg/legacy.py": self.SPECIMEN}, decl)
        self.assertEqual(failures, [])
        self.assertEqual(
            rows, [("pkg/legacy.py", 1, "membership-flag-test",
                    "named seam")])

    def test_stale_exception_is_itself_a_finding(self):
        decl = [{"path": "pkg/clean.py", "kind": "named seam"}]
        rows, failures = ai.evaluate({"pkg/clean.py": "x = 1\n"}, decl)
        self.assertEqual(
            failures, [("pkg/clean.py", 0, "stale-exception",
                        "named seam")])

    def test_exception_outside_the_scan_is_not_judged(self):
        decl = [{"path": "other/pkg.py", "kind": "named seam"}]
        rows, failures = ai.evaluate({"pkg/clean.py": "x = 1\n"}, decl)
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])


def _fixture_tree(files):
    root = tempfile.mkdtemp(prefix="gate-argvidioms-")
    for relpath, source in files.items():
        full = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(source)
    return root


class FixtureTreeScanTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        root = _fixture_tree({
            "tool.py": (
                "import argparse\n"
                "parser = argparse.ArgumentParser(allow_abbrev=False)\n"),
            "run.sh": "#!/usr/bin/env bash\necho go\n",
        })
        self.addCleanup(shutil.rmtree, root, True)
        rows, failures, scanned = ai.scan(root, root)
        self.assertEqual(failures, [])
        self.assertEqual(scanned, 2)
        self.assertEqual(
            ai.render(rows, failures, scanned),
            ["argv-idioms: ok (2 files scanned)"])

    def test_specimen_fails_by_name_content_never_printed(self):
        root = _fixture_tree({
            "tool.py": "caller = \"--caller\" in argv\n",
        })
        self.addCleanup(shutil.rmtree, root, True)
        rows, failures, scanned = ai.scan(root, root)
        self.assertEqual(
            failures, [("tool.py", 1, "membership-flag-test", None)])
        rendered = "\n".join(ai.render(rows, failures, scanned))
        self.assertIn("tool.py:1", rendered)
        self.assertIn("membership-flag-test", rendered)
        self.assertNotIn("--caller", rendered)

    def test_seeded_idiom_is_flagged_while_unified_forms_pass(self):
        # The plan's seeded-idiom proof: a hand-rolled
        # take planted in a scratch tree fails; a file
        # consuming the unified module passes.
        root = _fixture_tree({
            "legacy.py": (
                "def main(argv):\n"
                "    return argv[argv.index(\"--max\") + 1]\n"),
            "unified.py": (
                "from platform import argv as uargv\n"
                "def main(argv):\n"
                "    return uargv.parse_only(DECL, argv)\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        rows, failures, scanned = ai.scan(root, root)
        self.assertEqual(
            failures, [("legacy.py", 2, "index-flag-extraction", None)])


if __name__ == "__main__":
    unittest.main()
