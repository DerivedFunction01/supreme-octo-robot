"""The segment feed (math adoption): the pure segmenter
over a fixture document, and the entry_segments feed
over a fixture registry — fixtures only, never live
files. The fixture document is fictional field-note
content in the math study's form: prose with inline
math, a numbered display equation, a malformed pair,
prices the inline heuristic must keep literal, a code
span and a fence the scanner must not reach into.

The feed half runs in a fresh interpreter (the payload
suite's pattern: the server package reads its config
at import, so the fixture config must be installed
before the import). Run in-process, its import of
server.feeds bound the package's config to this
fixture for every later suite in the process — under
full discovery test_server_feeds then swept the dead
fixture root and failed in setUpClass.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lib.derived import segments as segments_mod

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

FIXTURE_DOCUMENT = """# Field note — residual diagnostics

For each observation $i$ we record the residual $r_i = y_i - \\hat{y}_i$, the gap
between the measured value and the fitted value. The fit is accepted when the
residuals stay small relative to $\\sigma / \\sqrt{n}$.

$$R^2 = 1 - \\frac{\\sum_{i=1}^{n} r_i^2}{\\sum_{i=1}^{n} (y_i - \\bar{y})^2}$$ (1)

## Checks

- The prices $5 and $10 in the log are currency, not math.
- Inline code like `$\\alpha$` stays literal inside backticks.
- A broken draft term $\\frac{1}{2$ is missing its closing brace.

The normal equations collect the moments:

$$\\mathbf{X}^{\\top} \\mathbf{X} \\, \\boldsymbol{\\beta} = \\mathbf{X}^{\\top} \\mathbf{y}$$

A broken display term from the draft:

$$\\frac{\\sum_{i=1}^{n} x_i}{n$$

```text
Segments never reach inside a fence: $x^2$ stays text here.
```
"""


def _math_nodes(blocks):
    out = []
    for block in blocks:
        if block["kind"] == "math":
            out.append(block)
        for run in block.get("runs", []):
            if run["type"] == "math":
                out.append(run)
        for item in block.get("items", []):
            for run in item:
                if run["type"] == "math":
                    out.append(run)
    return out


class SegmenterTest(unittest.TestCase):

    def setUp(self):
        self.blocks = segments_mod.segment_document(
            FIXTURE_DOCUMENT)

    def test_block_kinds_in_order(self):
        kinds = [b["kind"] for b in self.blocks]
        self.assertEqual(
            kinds,
            ["heading", "paragraph", "math", "heading",
             "list", "paragraph", "math", "paragraph",
             "math", "code"])

    def test_inline_math_nodes_carry_the_served_shape(self):
        para = self.blocks[1]
        nodes = [r for r in para["runs"]
                 if r["type"] == "math"]
        self.assertEqual(len(nodes), 3)
        for node in nodes:
            self.assertEqual(
                set(node),
                {"type", "source", "display", "valid"})
            self.assertFalse(node["display"])
            self.assertTrue(node["valid"])
        self.assertEqual(nodes[0]["source"], "i")
        self.assertEqual(nodes[1]["source"],
                         r"r_i = y_i - \hat{y}_i")

    def test_display_block_carries_its_equation_number(self):
        block = self.blocks[2]
        self.assertEqual(block["kind"], "math")
        self.assertTrue(block["display"])
        self.assertTrue(block["valid"])
        self.assertEqual(block["number"], "(1)")
        self.assertTrue(
            block["source"].startswith("R^2 = 1"))

    def test_unnumbered_display_block(self):
        block = self.blocks[6]
        self.assertEqual(block["kind"], "math")
        self.assertTrue(block["valid"])
        self.assertNotIn("number", block)

    def test_malformed_pair_is_served_invalid(self):
        nodes = _math_nodes(self.blocks)
        invalid = [n for n in nodes if not n["valid"]]
        self.assertEqual(len(invalid), 2)
        inline = [n for n in invalid if not n["display"]]
        display = [n for n in invalid if n["display"]]
        self.assertEqual(len(inline), 1)
        self.assertEqual(inline[0]["source"], r"\frac{1}{2")
        self.assertEqual(len(display), 1)
        self.assertTrue(
            display[0]["source"].startswith(r"\frac{\sum"))

    def test_prices_stay_literal_text(self):
        items = self.blocks[4]["items"]
        text = "".join(
            r["text"] for r in items[0]
            if r["type"] == "text")
        self.assertIn("$5 and $10", text)
        self.assertEqual(
            [r for r in items[0] if r["type"] == "math"],
            [])

    def test_code_span_is_protected_and_typed(self):
        items = self.blocks[4]["items"]
        codes = [r for r in items[1]
                 if r["type"] == "code"]
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0]["text"], r"$\alpha$")
        self.assertEqual(
            [r for r in items[1] if r["type"] == "math"],
            [])

    def test_fence_is_a_code_block_untouched(self):
        block = self.blocks[-1]
        self.assertEqual(block["kind"], "code")
        self.assertEqual(block["language"], "text")
        self.assertIn("$x^2$", block["text"])

    def test_escaped_dollar_is_literal(self):
        runs = segments_mod.segment_runs(
            r"The fee is \$5 flat.")
        self.assertEqual(
            runs, [{"type": "text",
                    "text": "The fee is $5 flat."}])

    def test_validity_rule(self):
        v = segments_mod.tex_valid
        self.assertTrue(v(r"\frac{1}{2}"))
        self.assertTrue(v(r"\frac12"))
        self.assertTrue(v(r"\sqrt{x}"))
        self.assertTrue(v(r"\sqrt[3]{x}"))
        self.assertTrue(
            v(r"\begin{aligned} a &= b \end{aligned}"))
        self.assertFalse(v(""))
        self.assertFalse(v(r"\frac{1}{2"))
        self.assertFalse(v(r"\frac{1}"))
        self.assertFalse(v(r"\frac"))
        self.assertFalse(v(r"\sqrt"))
        self.assertFalse(v(r"\begin{aligned} a"))
        self.assertFalse(
            v(r"\begin{aligned} a \end{matrix}"))
        self.assertFalse(v("}"))


DRIVER = r'''
import json
import os
import sys
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws
from tests.server.test_segments import FIXTURE_DOCUMENT

cfg = fixture_ws.fixture_config(base, base / "state-test")
os.environ["WB_VIEWER_CONFIG"] = str(cfg)

from lib import registry as reg
from lib.writes import files as files_mod
from server import feeds

db = base / "registry.db"
reg.init_registry(db)
layout = (base / "entries", base / "archive")
doc = reg.add_entry(
    db, layout, "field-note",
    title="Field Note", kind="storyboard",
    main_file="note.md")
(Path(doc["entry_dir"]) / "note.md").write_text(
    FIXTURE_DOCUMENT, encoding="utf-8")
page = reg.add_entry(
    db, layout, "tile", title="Tile",
    kind="mockup", main_file="mock.html")
(Path(page["entry_dir"]) / "mock.html").write_text(
    "<h1>Tile</h1>\n", encoding="utf-8")
reg.add_entry(
    db, layout, "held-note", title="Held",
    kind="storyboard", source_kind="external",
    source_ref="docs/held.md")

result = {}
result["field_note"] = feeds.entry_segments(
    db, "field-note")
for key, entry_id in (("tile", "tile"),
                      ("held_note", "held-note")):
    try:
        feeds.entry_segments(db, entry_id)
        result[key] = {"error": None}
    except files_mod.FileError_ as exc:
        result[key] = {"error": "FileError_",
                       "status": exc.status}
try:
    feeds.entry_segments(db, "nope")
    result["unknown"] = {"error": None}
except reg.RegistryError:
    result["unknown"] = {"error": "RegistryError"}

print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _run_driver(driver):
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    proc = subprocess.run(
        [_python(), "-c", driver, str(base),
         str(WORKRECORD_ROOT)],
        capture_output=True, text=True, timeout=280)
    if proc.returncode != 0:
        raise AssertionError(
            f"driver failed:\n{proc.stdout}\n"
            f"{proc.stderr}")
    result = json.loads(
        proc.stdout.strip().splitlines()[-1])
    return tmp, result


class EntrySegmentsFeedTest(unittest.TestCase):
    """The feed over a fixture registry built through
    the registry's own writer (reg.add_entry), in a temp
    dir — the same construction fixture_ws uses. The
    probes run in the driver above: a fresh interpreter
    with the fixture config installed before the server
    import, so no config binding leaks into this
    process."""

    @classmethod
    def setUpClass(cls):
        cls._tmp, cls.result = _run_driver(DRIVER)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_feed_serves_the_segmented_document(self):
        payload = self.result["field_note"]
        self.assertEqual(payload["entry_id"], "field-note")
        self.assertEqual(payload["main_file"], "note.md")
        self.assertEqual(
            payload["blocks"],
            segments_mod.segment_document(FIXTURE_DOCUMENT))

    def test_rendered_page_main_refuses_415(self):
        self.assertEqual(self.result["tile"],
                         {"error": "FileError_",
                          "status": 415})

    def test_held_by_reference_refuses_400(self):
        self.assertEqual(self.result["held_note"],
                         {"error": "FileError_",
                          "status": 400})

    def test_unknown_entry_is_a_registry_error(self):
        self.assertEqual(self.result["unknown"],
                         {"error": "RegistryError"})


if __name__ == "__main__":
    unittest.main()
