"""The unified argv parser: protocol tests at the home.

The contract stated in pipeline/platform/argv.py is
proven here in the writer's test form: the shared
fixture corpus (argv_fixtures.json — argv vectors with
expected outcomes over two sample declarations, a verb
tool and a mode tool) runs green against all three
implementations of the contract: the Python module
(parse_only), the bash adapter (argv.sh, driven through
its canonical dump), and the JS adapter (tools/argv.mjs,
in its corpus mode). A clause present in one
implementation and missing in another fails here before
it ships. The dummy battery drives parse-only across
each sample declaration's whole surface. The census
test pins the audited entry-point list: every record's
path exists in the tree.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
REPO_ROOT = PLATFORM.parents[1]
sys.path.insert(0, str(PLATFORM))

import argv as uargv  # noqa: E402

FIXTURES = json.loads(
    (PLATFORM / "argv_fixtures.json").read_text(encoding="utf-8"))
CENSUS = json.loads(
    (PLATFORM / "argv_census.json").read_text(encoding="utf-8"))


def canon(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, list):
        return ",".join(canon(item) for item in value)
    return str(value)


def canon_lines(outcome):
    """The shared canonical form the bash adapter's
    argv_canon prints: sorted fact lines, or the single
    line 'error' / 'help'."""
    if not outcome["ok"]:
        return ["error"]
    if "help" in outcome:
        return ["help"]
    result = outcome["result"]
    lines = [f"verb={result['verb'] or '-'}"]
    lines += [f"flag:{name}={canon(value)}"
              for name, value in result["flags"].items()]
    lines += [f"pos:{name}={canon(value)}"
              for name, value in result["positionals"].items()]
    return sorted(lines)


class CorpusPythonTests(unittest.TestCase):
    def test_every_vector_matches(self):
        for idx, vector in enumerate(FIXTURES["vectors"]):
            decl = FIXTURES["declarations"][vector["decl"]]
            outcome = uargv.parse_only(decl, vector["argv"])
            expect = vector["expect"]
            with self.subTest(vector=idx, argv=vector["argv"]):
                if not expect["ok"]:
                    self.assertFalse(outcome["ok"])
                    self.assertEqual(outcome["exit_code"], 2)
                elif expect.get("help"):
                    self.assertTrue(outcome["ok"])
                    self.assertIn("help", outcome)
                else:
                    self.assertTrue(outcome["ok"], outcome)
                    result = outcome["result"]
                    self.assertEqual(result["verb"], expect["verb"])
                    self.assertEqual(result["flags"], expect["flags"])
                    self.assertEqual(
                        result["positionals"], expect["positionals"])

    def test_corpus_covers_the_clauses(self):
        # The corpus is the drift control: it must keep a
        # vector for every clause family, named by the
        # forms it exercises.
        argvs = [tuple(v["argv"]) for v in FIXTURES["vectors"]]
        joined = [" ".join(a) for a in argvs]
        self.assertTrue(any("=" in a for a in joined))  # equals form
        self.assertTrue(any("--bogus" in a for a in argvs))  # unknown
        self.assertTrue(any("--dry-run=x" in a for a in argvs))  # safety
        self.assertTrue(any("--shap" in a for a in argvs))  # abbreviation
        self.assertTrue(any("--" in a for a in argvs))  # separator
        decls = set(v["decl"] for v in FIXTURES["vectors"])
        self.assertEqual(decls, {"verb_tool", "mode_tool"})


class DeclarationTests(unittest.TestCase):
    def test_divergent_flag_shape_across_verbs_is_refused(self):
        decl = {"name": "x", "verbs": {
            "a": {"flags": {"f": {"takes_value": True}}},
            "b": {"flags": {"f": {}}}}}
        with self.assertRaises(uargv.DeclarationError):
            uargv.validate_declaration(decl)

    def test_variadic_must_be_last(self):
        decl = {"name": "x", "positionals": [
            {"name": "rest", "variadic": True}, {"name": "after"}]}
        with self.assertRaises(uargv.DeclarationError):
            uargv.validate_declaration(decl)

    def test_mode_group_names_declared_booleans_only(self):
        decl = {"name": "x", "flags": {"v": {"takes_value": True}},
                "mode_groups": [{"name": "m", "flags": ["v"]}]}
        with self.assertRaises(uargv.DeclarationError):
            uargv.validate_declaration(decl)

    def test_usage_error_is_exit_2_never_a_traceback(self):
        decl = FIXTURES["declarations"]["mode_tool"]
        outcome = uargv.parse_only(decl, ["--session"])
        self.assertEqual(
            outcome["exit_code"], 2)
        self.assertIn("usage:", outcome["usage"])


class HelpTests(unittest.TestCase):
    def test_help_is_generated_from_the_declaration(self):
        decl = FIXTURES["declarations"]["verb_tool"]
        text = uargv.help_text(decl)
        self.assertIn("usage: sample-verbs", text)
        self.assertIn("--shape VALUE", text)
        self.assertIn("acquire", text)
        verb_text = uargv.help_text(decl, "acquire")
        self.assertIn("usage: sample-verbs acquire", verb_text)

    def test_help_short_circuits_even_with_a_verb(self):
        decl = FIXTURES["declarations"]["verb_tool"]
        outcome = uargv.parse_only(decl, ["status", "--help"])
        self.assertTrue(outcome["ok"])
        self.assertIn("help", outcome)


class DummyTests(unittest.TestCase):
    def test_dummy_battery_matches_on_both_samples(self):
        for name, decl in FIXTURES["declarations"].items():
            cases = uargv.dummy(decl)
            self.assertTrue(cases, name)
            bad = [c for c in cases if not c["matched"]]
            self.assertEqual(bad, [], f"{name}: {bad[:2]}")

    def test_dummy_base_case_satisfies_choices(self):
        decl = {"name": "proof", "flags": {
            "channel": {"takes_value": True, "required": True,
                        "choices": ["http", "bridge", "static"]},
            "slug": {"takes_value": True, "required": True}}}
        cases = uargv.dummy(decl)
        bad = [c for c in cases if not c["matched"]]
        self.assertEqual(bad, [], f"{bad[:2]}")

    def test_dummy_covers_every_verb_and_flag(self):
        decl = FIXTURES["declarations"]["verb_tool"]
        cases = uargv.dummy(decl)
        verbs = {c["verb"] for c in cases}
        self.assertEqual(verbs, {None, "acquire", "release", "status"})
        argvs = [" ".join(c["argv"]) for c in cases]
        self.assertTrue(any("--shape=gpu" in a or "--shape=y" in a
                            for a in argvs))


BASH_DRIVER = """#!/usr/bin/env bash
source "$1"
shift
argv_parse "$@" >/dev/null 2>&1 || { echo error; exit 0; }
argv_canon
"""


def bash_decl_source(decl):
    """The corpus declaration in the bash adapter's
    declaration calls — the same data, in the adapter's
    own form (the conversion the migration lanes make
    per tool, here over the corpus samples)."""
    lines = [f'source "{PLATFORM / "argv.sh"}"',
             f'argv_tool {decl["name"]} "{decl.get("summary", "")}"']

    def flag(scope_fn, name, spec):
        kind = "value" if spec.get("takes_value") else "bool"
        attrs = [scope_fn, name, kind]
        if spec.get("required"):
            attrs.append("required")
        if spec.get("repeatable"):
            attrs.append("repeatable")
        if spec.get("safety"):
            attrs.append("safety")
        if "default" in spec:
            attrs.append(f'default={spec["default"]}')
        if spec.get("short"):
            attrs.append(f'short={spec["short"]}')
        if spec.get("choices"):
            attrs.append("choices=" + ",".join(spec["choices"]))
        lines.append(" ".join(attrs))

    def positional(scope_fn, spec):
        attrs = [scope_fn, spec["name"]]
        if spec.get("required"):
            attrs.append("required")
        if spec.get("variadic"):
            attrs.append("variadic")
        lines.append(" ".join(attrs))

    for name, spec in decl.get("flags", {}).items():
        flag("argv_global_flag", name, spec)
    for spec in decl.get("positionals", []):
        positional("argv_global_positional", spec)
    for group in decl.get("mode_groups", []):
        bits = ["argv_global_mode_group", group["name"],
                ",".join(group["flags"])]
        if group.get("required"):
            bits.append("required")
        lines.append(" ".join(bits))
    for verb, vspec in decl.get("verbs", {}).items():
        lines.append(f'argv_verb {verb} "{vspec.get("summary", "")}"')
        for name, spec in vspec.get("flags", {}).items():
            flag("argv_flag", name, spec)
        for spec in vspec.get("positionals", []):
            positional("argv_positional", spec)
        for group in vspec.get("mode_groups", []):
            bits = ["argv_mode_group", group["name"],
                    ",".join(group["flags"])]
            if group.get("required"):
                bits.append("required")
            lines.append(" ".join(bits))
        lines.append("argv_end_verb")
    return "\n".join(lines) + "\n"


class CorpusBashTests(unittest.TestCase):
    def test_every_vector_matches_under_bash(self):
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("no bash runtime present")
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "driver.sh"
            driver.write_text(BASH_DRIVER, encoding="utf-8")
            decl_files = {}
            for name, decl in FIXTURES["declarations"].items():
                path = Path(tmp) / f"{name}.sh"
                path.write_text(bash_decl_source(decl), encoding="utf-8")
                decl_files[name] = path
            for idx, vector in enumerate(FIXTURES["vectors"]):
                decl = FIXTURES["declarations"][vector["decl"]]
                outcome = uargv.parse_only(decl, vector["argv"])
                expected = canon_lines(outcome)
                proc = subprocess.run(
                    [bash, str(driver), str(decl_files[vector["decl"]]),
                     *vector["argv"]],
                    capture_output=True, text=True, timeout=30)
                got = sorted(
                    line for line in proc.stdout.splitlines() if line)
                with self.subTest(vector=idx, argv=vector["argv"]):
                    self.assertEqual(got, expected,
                                     proc.stderr[-400:])


class CorpusJsTests(unittest.TestCase):
    def test_every_vector_matches_under_js(self):
        runtime = shutil.which("node") or shutil.which("bun")
        if runtime is None:
            self.skipTest("no JS runtime present")
        proc = subprocess.run(
            [runtime, str(REPO_ROOT / "tools" / "argv.mjs"), "corpus",
             str(PLATFORM / "argv_fixtures.json")],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertIn("vectors matched", proc.stdout)


class CensusTests(unittest.TestCase):
    def test_census_records_are_well_formed(self):
        seen = set()
        for entry in CENSUS["entries"]:
            self.assertEqual(set(entry), {"path", "family", "migrated"})
            self.assertIsInstance(entry["migrated"], bool)
            self.assertNotIn(entry["path"], seen)
            seen.add(entry["path"])

    def test_every_census_path_exists(self):
        missing = [entry["path"] for entry in CENSUS["entries"]
                   if not (REPO_ROOT / entry["path"]).is_file()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
