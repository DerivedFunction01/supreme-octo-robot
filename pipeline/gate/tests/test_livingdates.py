"""The living-dates component: the surfaces it fails on
(a dated Python comment and docstring, a dated doc line,
a date parenthetical, a dated script comment, dated
config comments), the forms it must not flag (dates held
as data — string literals in code and scripts, fixture
specimens, config values, a hash inside a quoted value
or a gitignore pattern, code spans and fenced blocks in
a document), the archive directory conventions, the
tracked population (an untracked file is not scanned; a
staged one is), and the leg's wiring (declared once in
the gate package's declaration, a scanner leg kind, and
dispatched by the runner over the repo root). All
specimens are fixture sources and fixture data, written
at runtime into scratch trees; the live tree's state is
never read.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gate import livingdates as ld
from gate import runner

ISO = "2026" + "-11" + "-23"

# A finished-plan fixture path, built from its parts: a
# contiguous literal in this file would itself read as a
# specific plan-file reference to the portability leg.
FINISHED_PLAN = "/".join((".plans", "finished", "old-plan.md"))


def _fixture_tree(files):
    """A scratch tree: {relpath: text} written at runtime.
    Not a git tree — the enumeration's walk fallback is
    the form the scan takes there."""
    root = tempfile.mkdtemp(prefix="gate-livingdates-")
    for relpath, text in files.items():
        full = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
    return root


def _rules(rows):
    return sorted({rule for rule, _relpath, _lineno in rows})


class SurfaceTests(unittest.TestCase):
    def scan_tree(self, files):
        root = _fixture_tree(files)
        self.addCleanup(shutil.rmtree, root, True)
        return ld.scan(root)

    def test_dated_python_comment_fails(self):
        rows, failures, _scanned = self.scan_tree(
            {"mod.py": f"# cache warmed on {ISO}\nx = 1\n"})
        self.assertEqual(_rules(rows), ["living-dates/iso-date"])
        self.assertEqual(rows[0][2], 1)
        self.assertEqual(failures, rows)

    def test_dated_docstring_fails(self):
        text = f'"""Behaviour as of {ISO}."""\n\nx = 1\n'
        rows, _failures, _scanned = self.scan_tree({"mod.py": text})
        self.assertEqual(_rules(rows), ["living-dates/iso-date"])

    def test_dated_doc_line_fails(self):
        rows, _failures, _scanned = self.scan_tree(
            {"note.md": "Shipped in November 2026.\n"})
        self.assertEqual(_rules(rows), ["living-dates/month-date"])

    def test_date_parenthetical_fails(self):
        rows, _failures, _scanned = self.scan_tree(
            {"note.md": "the old behaviour (2026) is gone\n"})
        self.assertEqual(
            _rules(rows), ["living-dates/date-parenthetical"])

    def test_dated_script_comment_fails(self):
        files = {"app.ts": f"// warmed on {ISO}\nexport const x = 1\n"}
        rows, _failures, _scanned = self.scan_tree(files)
        self.assertEqual(_rules(rows), ["living-dates/iso-date"])

    def test_date_string_literal_in_code_passes(self):
        text = f'STAMP = "{ISO}"\n\n\ndef stamp():\n    return STAMP\n'
        rows, failures, _scanned = self.scan_tree({"mod.py": text})
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])

    def test_date_string_literal_in_script_passes(self):
        rows, _failures, _scanned = self.scan_tree(
            {"app.ts": f'export const STAMP = "{ISO}"\n'})
        self.assertEqual(rows, [])

    def test_fixture_specimen_date_passes(self):
        files = {
            "fixtures/specimen.py":
                f'ROWS = [{{"day": "{ISO}", "amount": 3}}]\n',
            "fixtures/specimens.json": f'{{"day": "{ISO}"}}\n',
        }
        rows, _failures, _scanned = self.scan_tree(files)
        self.assertEqual(rows, [])

    def test_archive_paths_pass(self):
        files = {
            FINISHED_PLAN: f"ruled on {ISO}\n",
            "run-logs/gate.md": f"gate ran {ISO}\n",
            f"logs/{ISO}/run.md": f"run of {ISO}\n",
        }
        rows, _failures, _scanned = self.scan_tree(files)
        self.assertEqual(rows, [])

    def test_clean_tree_passes(self):
        files = {
            "note.md": "the cache warms before the gate reads it\n",
            "mod.py": "# the cache warms first\nx = 1\n",
            "app.ts": "/* the cache warms first */\nexport const x = 1\n",
        }
        rows, failures, scanned = self.scan_tree(files)
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])
        self.assertEqual(
            ld.render(rows, failures, scanned),
            ["living-dates: ok (3 files scanned)"])

    def test_findings_never_print_matched_content(self):
        rows, failures, scanned = self.scan_tree(
            {"note.md": f"shipped {ISO}\n"})
        self.assertTrue(rows)
        rendered = "\n".join(ld.render(rows, failures, scanned))
        self.assertIn("note.md:1", rendered)
        self.assertNotIn(ISO, rendered)

    def test_date_in_doc_code_span_passes(self):
        text = f"Run `report --day {ISO}` to rebuild.\n"
        rows, _failures, _scanned = self.scan_tree({"note.md": text})
        self.assertEqual(rows, [])

    def test_date_in_fenced_block_passes(self):
        files = {
            "note.md": f"Example:\n\n```\nreport --day {ISO}\n```\n",
            "guide.md": f"Example:\n\n~~~\nreport --day {ISO}\n~~~\n",
        }
        rows, _failures, _scanned = self.scan_tree(files)
        self.assertEqual(rows, [])

    def test_date_in_prose_beside_code_span_fails(self):
        text = f"Shipped {ISO}; run `report` to check.\n"
        rows, _failures, _scanned = self.scan_tree({"note.md": text})
        self.assertEqual(_rules(rows), ["living-dates/iso-date"])
        self.assertEqual(rows[0][2], 1)

    def test_dated_gitignore_comment_fails(self):
        files = {".gitignore": f"# bundle corpus; retired {ISO}\n*.log\n"}
        rows, _failures, _scanned = self.scan_tree(files)
        self.assertEqual(_rules(rows), ["living-dates/iso-date"])
        self.assertEqual(rows[0][2], 1)

    def test_gitignore_hash_inside_pattern_passes(self):
        rows, _failures, _scanned = self.scan_tree(
            {".gitignore": f"build#{ISO}/\n"})
        self.assertEqual(rows, [])

    def test_dated_toml_comment_fails(self):
        files = {"pyproject.toml": f"# floor raised {ISO}\n[project]\n"}
        rows, _failures, _scanned = self.scan_tree(files)
        self.assertEqual(_rules(rows), ["living-dates/iso-date"])
        self.assertEqual(rows[0][2], 1)

    def test_date_in_toml_string_value_passes(self):
        rows, _failures, _scanned = self.scan_tree(
            {"pyproject.toml": f'day = "{ISO}"\n'})
        self.assertEqual(rows, [])

    def test_date_in_yaml_string_value_passes(self):
        rows, _failures, _scanned = self.scan_tree(
            {"config.yaml": f'day: "{ISO}"\n'})
        self.assertEqual(rows, [])

    def test_hash_in_quoted_yaml_value_starts_no_comment(self):
        rows, _failures, _scanned = self.scan_tree(
            {"config.yaml": f'note: "release #{ISO} build"\n'})
        self.assertEqual(rows, [])

    def test_date_in_yaml_trailing_comment_fails(self):
        rows, _failures, _scanned = self.scan_tree(
            {"config.yaml": f"day: today # verified {ISO}\n"})
        self.assertEqual(_rules(rows), ["living-dates/iso-date"])
        self.assertEqual(rows[0][2], 1)


def _git(root, *args):
    subprocess.run(
        ["git", "-C", str(root),
         "-c", "user.email=test@example.com",
         "-c", "user.name=Test", *args],
        check=True, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("git"), "git not on PATH")
class TrackedPopulationTests(unittest.TestCase):
    def test_only_tracked_files_are_scanned(self):
        dated = f"shipped {ISO}\n"
        root = _fixture_tree({})
        self.addCleanup(shutil.rmtree, root, True)
        _git(root, "init", "-q")
        Path(root, "tracked.md").write_text(dated, encoding="utf-8")
        _git(root, "add", "tracked.md")
        _git(root, "commit", "-q", "-m", "seed")
        Path(root, "untracked.md").write_text(dated, encoding="utf-8")
        rows, _failures, _scanned = ld.scan(root)
        self.assertEqual({relpath for _rule, relpath, _n in rows},
                         {"tracked.md"})
        _git(root, "add", "untracked.md")
        rows, _failures, _scanned = ld.scan(root)
        self.assertEqual({relpath for _rule, relpath, _n in rows},
                         {"tracked.md", "untracked.md"})


class WiringTests(unittest.TestCase):
    def test_declared_once_in_the_gate_package(self):
        gate_json = Path(__file__).resolve().parents[1] / "gate.json"
        decl = json.loads(gate_json.read_text(encoding="utf-8"))
        legs = [leg for leg in decl["legs"]
                if leg.get("leg") == "livingdates"]
        self.assertEqual(len(legs), 1)

    def test_a_scanner_leg_kind(self):
        self.assertIn("livingdates", runner.SCANNER_LEG_KINDS)

    def test_runner_dispatch_scans_the_repo_root(self):
        root = _fixture_tree(
            {"note.md": "the cache warms before the gate reads it\n"})
        self.addCleanup(shutil.rmtree, root, True)
        pkg = runner.Package(
            name="gate", root=Path(root), decl={}, source=Path(root))
        leg = {"leg": "livingdates", "name": "repo living dates"}
        outcome = runner.run_leg(pkg, leg, repo_root=Path(root))
        self.assertTrue(outcome.ok)
        Path(root, "note.md").write_text(
            f"shipped {ISO}\n", encoding="utf-8")
        outcome = runner.run_leg(pkg, leg, repo_root=Path(root))
        self.assertFalse(outcome.ok)


if __name__ == "__main__":
    unittest.main()
