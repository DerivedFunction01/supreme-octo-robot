"""The import-isolation component: the import forms it
fails on (every statement form whose top-level root names
a sibling surface), the forms it must not flag (relative
imports, the package's own root, stdlib and third-party
roots), its stated limit (dynamic imports), and the scan
over a fixture tree — a clean attention-shaped tree passes,
a specimen importing a sibling fails by name, and the
finding line names file + imported root, never content.
The exception mechanism's fixture cases: a declaration in
the fixture's own gate.json (the bootstrap form) turns its
import into a note and the leg passes; a declaration whose
file carries no matching import fails as a stale
exception; an undeclared import beside the exception still
fails; a declaration naming a different root than the file
imports does not suppress the finding; a declaration for a
file outside the scan is not judged. Specimen sources are
written at runtime into scratch trees so no tracked file
carries a sibling import for the scan to find."""
import os
import shutil
import tempfile
import unittest

from gate import importisolation as ii

SIBLINGS = [
    "dispatch", "evaluation", "gate", "platform",
    "registry", "scheduling", "venue", "workrecord",
]


class StatementFormTests(unittest.TestCase):
    def test_plain_import_of_sibling(self):
        findings = ii.evaluate(
            {"pkg/mod.py": "import registry\n"}, SIBLINGS)
        self.assertEqual(findings, [("pkg/mod.py", 1, "registry")])

    def test_dotted_import_of_sibling(self):
        findings = ii.evaluate(
            {"pkg/mod.py": "import scheduling.server.serving\n"},
            SIBLINGS)
        self.assertEqual(findings[0][2], "scheduling")

    def test_from_import_of_sibling(self):
        src = "from registry.attention.directory import upsert_handler\n"
        findings = ii.evaluate({"pkg/mod.py": src}, SIBLINGS)
        self.assertEqual(findings, [("pkg/mod.py", 1, "registry")])

    def test_aliased_import_of_sibling(self):
        findings = ii.evaluate(
            {"pkg/mod.py": "import gate as g\n"}, SIBLINGS)
        self.assertEqual(findings[0][2], "gate")

    def test_function_level_import_of_sibling(self):
        src = ("def load():\n"
               "    from venue.sync import transfer\n"
               "    return transfer\n")
        findings = ii.evaluate({"pkg/mod.py": src}, SIBLINGS)
        self.assertEqual(findings, [("pkg/mod.py", 2, "venue")])

    def test_conditional_import_of_sibling(self):
        src = ("try:\n"
               "    import dispatch\n"
               "except ImportError:\n"
               "    dispatch = None\n")
        findings = ii.evaluate({"pkg/mod.py": src}, SIBLINGS)
        self.assertEqual(findings[0][2], "dispatch")


class SanctionedFormTests(unittest.TestCase):
    def test_relative_imports_are_internal(self):
        src = ("from . import settings\n"
               "from ..services import waits\n"
               "from .infra.store import Store\n")
        findings = ii.evaluate({"pkg/mod.py": src}, SIBLINGS)
        self.assertEqual(findings, [])

    def test_own_root_is_fine(self):
        src = ("import attention\n"
               "from attention.services import waits\n")
        findings = ii.evaluate(
            {"attention/mod.py": src}, SIBLINGS)
        self.assertEqual(findings, [])

    def test_stdlib_and_third_party_are_fine(self):
        src = ("import os\n"
               "import sys\n"
               "from pathlib import Path\n"
               "from datetime import datetime\n")
        findings = ii.evaluate({"pkg/mod.py": src}, SIBLINGS)
        self.assertEqual(findings, [])

    def test_dynamic_import_is_the_stated_limit(self):
        # Not an import statement: visible to review, not
        # to this leg (the component's documented limit).
        src = ("import importlib\n"
               "mod = importlib.import_module("
               "\"registry.attention.directory\")\n")
        findings = ii.evaluate({"pkg/mod.py": src}, SIBLINGS)
        self.assertEqual(findings, [])

    def test_unparseable_file_yields_no_findings(self):
        findings = ii.evaluate(
            {"pkg/mod.py": "def broken(:\n"}, SIBLINGS)
        self.assertEqual(findings, [])


def _fixture_tree(files):
    """A scratch package tree: {relpath: source} written
    at runtime. Not a git tree — the enumeration's walk
    fallback is the form the scan takes there."""
    root = tempfile.mkdtemp(prefix="gate-importisolation-")
    for relpath, source in files.items():
        full = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(source)
    return root


class FixtureTreeScanTests(unittest.TestCase):
    def test_clean_attention_shaped_tree_passes(self):
        root = _fixture_tree({
            "__init__.py": "",
            "settings.py": "import os\n",
            "infra/store.py": (
                "from attention.settings import VALUES\n"
                "from ..errors import Problem\n"),
            "services/waits.py": (
                "from pathlib import Path\n"
                "from attention.domain import Wait\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        findings, scanned = ii.scan(root, root, SIBLINGS)
        self.assertEqual(findings, [])
        self.assertEqual(scanned, 4)
        lines = ii.render(findings, scanned)
        self.assertEqual(
            lines, ["import-isolation: ok (4 files scanned)"])

    def test_specimen_fails_by_name_content_never_printed(self):
        root = _fixture_tree({
            "__init__.py": "",
            "infra/store.py": (
                "from registry.attention.directory import "
                "upsert_handler\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        findings, scanned = ii.scan(root, root, SIBLINGS)
        self.assertEqual(
            findings, [("infra/store.py", 1, "registry")])
        rendered = "\n".join(ii.render(findings, scanned))
        self.assertIn("infra/store.py:1", rendered)
        self.assertIn("'registry'", rendered)
        self.assertNotIn("upsert_handler", rendered)


class ExceptionFixtureTests(unittest.TestCase):
    # The fixture package's own gate.json, carrying the
    # bootstrap declaration in the component's schema:
    # package-relative path, the covered root, the kind.
    GATE_JSON = (
        '{"package": "attention", "legs": [{"leg": '
        '"importisolation", "exceptions": [{"path": '
        '"init_venv.py", "root": "gate", "kind": '
        '"bootstrap"}]}]}')

    def test_declared_exception_passes_as_a_note(self):
        root = _fixture_tree({
            "gate.json": self.GATE_JSON,
            "init_venv.py": (
                "from gate.venvbuild import build_venv\n"),
            "settings.py": "import os\n",
        })
        self.addCleanup(shutil.rmtree, root, True)
        findings, scanned = ii.scan(root, root, SIBLINGS)
        self.assertEqual(findings, [])
        self.assertEqual(
            findings.notes,
            [("init_venv.py", 1, "gate", "bootstrap")])
        rendered = "\n".join(ii.render(findings, scanned))
        self.assertIn("note - init_venv.py:1", rendered)
        self.assertIn("exceptioned: bootstrap", rendered)
        self.assertIn(
            "import-isolation: ok (2 files scanned)", rendered)

    def test_declaration_without_the_import_is_stale(self):
        root = _fixture_tree({
            "gate.json": self.GATE_JSON,
            "init_venv.py": "import os\n",
        })
        self.addCleanup(shutil.rmtree, root, True)
        findings, scanned = ii.scan(root, root, SIBLINGS)
        self.assertEqual(findings, [("init_venv.py", 0, "gate")])
        rendered = "\n".join(ii.render(findings, scanned))
        self.assertIn("stale exception", rendered)
        self.assertIn("declared: bootstrap", rendered)
        self.assertIn("'gate'", rendered)

    def test_undeclared_import_beside_the_exception_fails(self):
        root = _fixture_tree({
            "gate.json": self.GATE_JSON,
            "init_venv.py": (
                "from gate.venvbuild import build_venv\n"),
            "infra/store.py": (
                "from registry.attention.directory import "
                "upsert_handler\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        findings, scanned = ii.scan(root, root, SIBLINGS)
        self.assertEqual(
            findings, [("infra/store.py", 1, "registry")])
        self.assertEqual(
            findings.notes,
            [("init_venv.py", 1, "gate", "bootstrap")])
        rendered = "\n".join(ii.render(findings, scanned))
        self.assertIn("IMPORT-ISOLATION: infra/store.py:1",
                      rendered)
        self.assertNotIn("upsert_handler", rendered)

    def test_declaration_for_another_root_does_not_suppress(self):
        root = _fixture_tree({
            "gate.json": self.GATE_JSON,
            "init_venv.py": (
                "from registry.attention.directory import "
                "upsert_handler\n"),
        })
        self.addCleanup(shutil.rmtree, root, True)
        findings, scanned = ii.scan(root, root, SIBLINGS)
        # The registry import is an ordinary failure, and
        # the gate declaration — its file scanned, its
        # root never imported — is stale. Both ways.
        self.assertEqual(
            findings,
            [("init_venv.py", 0, "gate"),
             ("init_venv.py", 1, "registry")])
        self.assertEqual(findings.notes, [])
        rendered = "\n".join(ii.render(findings, scanned))
        self.assertIn("IMPORT-ISOLATION: init_venv.py:1",
                      rendered)
        self.assertIn("stale exception", rendered)

    def test_declaration_for_an_unscanned_file_is_not_judged(self):
        root = _fixture_tree({
            "gate.json": (
                '{"package": "attention", "legs": [{"leg": '
                '"importisolation", "exceptions": [{"path": '
                '"absent.py", "root": "gate", "kind": '
                '"bootstrap"}]}]}'),
            "settings.py": "import os\n",
        })
        self.addCleanup(shutil.rmtree, root, True)
        findings, scanned = ii.scan(root, root, SIBLINGS)
        self.assertEqual(findings, [])
        self.assertEqual(findings.notes, [])


class DerivationTests(unittest.TestCase):
    def test_siblings_derive_from_composed_declarations(self):
        parent = tempfile.mkdtemp(prefix="gate-importisolation-")
        self.addCleanup(shutil.rmtree, parent, True)
        for name in ("attention", "registry", "venue"):
            pkg = os.path.join(parent, name)
            os.makedirs(pkg)
            with open(os.path.join(pkg, "gate.json"), "w",
                      encoding="utf-8") as fh:
                fh.write('{"package": "%s", "legs": []}' % name)
        package, siblings = ii.composed_siblings(
            os.path.join(parent, "attention"))
        self.assertEqual(package, "attention")
        self.assertEqual(sorted(siblings), ["registry", "venue"])


if __name__ == "__main__":
    unittest.main()
