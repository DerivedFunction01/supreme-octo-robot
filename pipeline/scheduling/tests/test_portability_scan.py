"""Portability scanner tests. Every violating string is
built by concatenation, so this tracked file never carries
the literals it tests for — the scanner scans it too."""
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "portability_scan", os.path.join(ROOT, "tools", "portability_scan.py")
)
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)

HOME_PATH = "/ho" + "me/someone/x"      # an absolute home path
TILDE_PATH = "~" + "/somewhere/x"       # a home-anchored path
FAKE_LITERAL = "QZX-FAKE-LITERAL-9911"  # synthetic denylist entry
MARKER = "portability" + "-exception:"  # the directive marker, split


def _rules(findings):
    return sorted({rule for rule, _, _ in findings})


class GenericLegsTests(unittest.TestCase):
    def run_scan(self, files):
        tmp = tempfile.mkdtemp()
        relpaths = []
        for name, text in files.items():
            path = os.path.join(tmp, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            relpaths.append(name)
        return scan.scan_generic(tmp, relpaths)

    def test_anchors_and_bare_plan_dirs_do_not_fire(self):
        text = (
            "argv: ${REPO}/examples/x.sh, ${WS}/y, ${HOME}/z\n"
            "plans live in .plans/ and archive to .plans/finished/\n"
        )
        self.assertEqual(self.run_scan({"a.md": text}), [])

    def test_absolute_and_tilde_paths_fire(self):
        findings = self.run_scan({"a.md": f"{HOME_PATH}\n{TILDE_PATH}\n"})
        self.assertIn("portability/abs-path", _rules(findings))
        self.assertIn("portability/home-path", _rules(findings))

    def test_specific_plan_file_fires(self):
        plan_ref = ".pla" + "ns/2026-01-01-x.md"  # split: see class note
        findings = self.run_scan({"a.md": f"see {plan_ref}\n"})
        self.assertIn("portability/untracked-ref", _rules(findings))


class ExceptionTests(unittest.TestCase):
    def test_directive_in_non_registry_file_is_a_finding(self):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "a.md"), "w", encoding="utf-8") as fh:
            fh.write(f"{MARKER} {HOME_PATH} — a reason\n")
        findings = scan.scan_generic(tmp, ["a.md"])
        self.assertIn("portability/exception-misuse", _rules(findings))

    def test_declared_exception_exempts_exact_string_only(self):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "a.md"), "w", encoding="utf-8") as fh:
            fh.write(f"{MARKER} {HOME_PATH} — a reason\n{HOME_PATH}\n")
        with mock.patch.object(scan, "EXCEPTION_FILES", ("a.md",)):
            findings = scan.scan_generic(tmp, ["a.md"])
        self.assertEqual(findings, [])


class DenylistTests(unittest.TestCase):
    def _root_with(self, tmp, text):
        with open(os.path.join(tmp, "a.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        return tmp

    def test_absent_denylist_is_a_notice_not_a_failure(self):
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {}, clear=True):
            findings, notice, provisioned = scan.scan_denylist(tmp, ["a.md"])
        self.assertEqual(findings, [])
        self.assertFalse(provisioned)
        self.assertIn("NOTICE", notice)

    def test_unreadable_env_path_notices_without_fallback(self):
        tmp = tempfile.mkdtemp()
        env = {"STARTER_DENYLIST_FILE": os.path.join(tmp, "missing.txt")}
        with mock.patch.dict(os.environ, env, clear=True):
            findings, notice, provisioned = scan.scan_denylist(tmp, ["a.md"])
        self.assertEqual(findings, [])
        self.assertFalse(provisioned)
        self.assertIn("unreadable", notice)

    def test_provisioned_denylist_flags_without_content(self):
        tmp = tempfile.mkdtemp()
        self._root_with(tmp, f"first line\ncarries {FAKE_LITERAL} here\n")
        list_path = os.path.join(tmp, "list.txt")
        with open(list_path, "w", encoding="utf-8") as fh:
            fh.write(FAKE_LITERAL + "\n")
        env = {"STARTER_DENYLIST_FILE": list_path}
        with mock.patch.dict(os.environ, env, clear=True):
            findings, notice, provisioned = scan.scan_denylist(tmp, ["a.md"])
        self.assertTrue(provisioned)
        self.assertEqual(len(findings), 1)
        rule, relpath, lineno = findings[0]
        self.assertEqual((rule, relpath, lineno),
                         ("denylist/personal-literal", "a.md", 2))

    def test_denylist_matching_is_case_insensitive(self):
        # Personal literals are names and identifiers: a
        # provisioned literal fires in any case it appears.
        tmp = tempfile.mkdtemp()
        self._root_with(tmp, f"shouted {FAKE_LITERAL.lower()} here\n")
        list_path = os.path.join(tmp, "list.txt")
        with open(list_path, "w", encoding="utf-8") as fh:
            fh.write(FAKE_LITERAL + "\n")
        env = {"STARTER_DENYLIST_FILE": list_path}
        with mock.patch.dict(os.environ, env, clear=True):
            findings, _notice, provisioned = scan.scan_denylist(tmp, ["a.md"])
        self.assertTrue(provisioned)
        self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()
