"""The paths-discipline component: the climb forms it
fails on, the discipline's own forms it must not flag
(paths modules, the bootstrap, module-relative reads),
the declared-exception form, and the look-alikes that are
not derivations (path validation, prose)."""
import unittest

from gate import pathdiscipline as pd


class ClimbTests(unittest.TestCase):
    def test_nested_dirname_climb(self):
        rows, failures = pd.evaluate(
            {"pkg/mod.py": "ROOT = os.path.dirname("
             "os.path.dirname(os.path.abspath(__file__)))\n"}, [])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][2], "root-climb")

    def test_parents_climb(self):
        rows, failures = pd.evaluate(
            {"pkg/mod.py": "R = Path(__file__).resolve().parents[2]\n"}, [])
        self.assertEqual(len(failures), 1)

    def test_parent_chain_climb(self):
        rows, failures = pd.evaluate(
            {"pkg/mod.py": "R = Path(__file__).parent.parent\n"}, [])
        self.assertEqual(len(failures), 1)

    def test_join_segment_climb_multiline(self):
        src = ("path = os.path.normpath(os.path.join(\n"
               "    os.path.dirname(os.path.abspath(__file__)),\n"
               "    \"..\", \"platform\", \"writer.py\"))\n")
        rows, failures = pd.evaluate({"pkg/mod.py": src}, [])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][2], "root-climb")

    def test_cwd_root(self):
        rows, failures = pd.evaluate(
            {"pkg/mod.py": "ROOT = os.getcwd()\n"}, [])
        self.assertEqual(failures[0][2], "cwd-root")

    def test_hardcoded_root(self):
        rows, failures = pd.evaluate(
            {"pkg/mod.py": "ROOT = \"/ho" "me/x/workspace\"\n"}, [])
        self.assertEqual(failures[0][2], "hardcoded-root")


class SanctionedFormTests(unittest.TestCase):
    def test_paths_module_is_the_home(self):
        src = ("ROOT = os.path.dirname(os.path.dirname("
               "os.path.abspath(__file__)))\n")
        rows, failures = pd.evaluate({"pkg/paths.py": src}, [])
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])

    def test_bootstrap_loading_the_spine(self):
        src = ("_spec = importlib.util.spec_from_file_location(\n"
               "    \"scheduling_paths\",\n"
               "    os.path.normpath(os.path.join(\n"
               "        os.path.dirname(os.path.abspath(__file__)), "
               "\"..\", \"paths.py\")))\n")
        rows, failures = pd.evaluate({"pkg/bin/tool": src}, [])
        self.assertEqual(failures, [])

    def test_module_relative_resource_read(self):
        src = ("SEEDS = os.path.join(\n"
               "    os.path.dirname(os.path.abspath(__file__)),\n"
               "    \"seeds.json\")\n"
               "HERE = Path(__file__).resolve().parent\n")
        rows, failures = pd.evaluate({"pkg/mod.py": src}, [])
        self.assertEqual(failures, [])

    def test_validation_and_prose_are_not_derivations(self):
        src = ("if rel.startswith(\"/\") or \"..\" in rel.split(\"/\"):\n"
               "    raise ValueError(\"...\")\n")
        rows, failures = pd.evaluate({"pkg/mod.py": src}, [])
        self.assertEqual(failures, [])


class DeclarationTests(unittest.TestCase):
    SRC = "ROOT = os.path.dirname(os.path.dirname(" \
          "os.path.abspath(__file__)))\n"

    def test_exact_declaration_marks_and_passes(self):
        exc = [{"path": "pkg/bin/harness",
                "kind": "single-file client"}]
        rows, failures = pd.evaluate({"pkg/bin/harness": self.SRC}, exc)
        self.assertEqual(failures, [])
        self.assertEqual(rows[0][3], "single-file client")

    def test_subtree_declaration(self):
        exc = [{"path": "pkg/tests/**", "kind": "test fixture location"}]
        rows, failures = pd.evaluate({"pkg/tests/test_x.py": self.SRC}, exc)
        self.assertEqual(failures, [])
        self.assertEqual(rows[0][3], "test fixture location")

    def test_undeclared_twin_still_fails(self):
        exc = [{"path": "pkg/tests/**", "kind": "test fixture location"}]
        rows, failures = pd.evaluate(
            {"pkg/tests/test_x.py": self.SRC, "pkg/mod.py": self.SRC}, exc)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "pkg/mod.py")


if __name__ == "__main__":
    unittest.main()
