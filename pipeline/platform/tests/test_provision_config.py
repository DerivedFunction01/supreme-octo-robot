"""Pins for the cutover config provisioning write path
(commission 14): provision_config.py's writes ride the
unified state writer (contract 15) — the gate's
writer-uniqueness leg found its local _atomic_write a
partial staged-write copy (stage + replace, no fsync, no
read-back), and the cure re-pointed the script at
pipeline/platform/writer.py's staged_write in the
platform seam form, deleting the local implementation.

The homes here are scratch fixtures: a scheduling home
is a temp dir carrying a config.example.json and a stub
`server` package whose config loader stands in for the
real home's (provision validates through the home's own
loader by subprocess; the stub parses the JSON and
resolves port/home from it). Nothing touches a live
config.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PLATFORM = Path(__file__).resolve().parent.parent
PROVISION_PATH = PLATFORM / "ops" / "cutover" / "provision_config.py"
WRITER_PATH = PLATFORM / "writer.py"

_STUB_INIT = ""
_STUB_CONFIG = '''\
import json


def require_live_config(path):
    with open(path, encoding="utf-8") as fh:
        json.load(fh)


def resolve(path):
    with open(path, encoding="utf-8") as fh:
        values = json.load(fh)
    return {"port": values["port"], "home": values["home"]}, None
'''


def _load_provision():
    spec = importlib.util.spec_from_file_location(
        "provision_config_under_test", PROVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provision = _load_provision()


class _RecordingWriter:
    """Delegates to the real writer, recording calls —
    the pin that the write rode the seam, with the exact
    bytes it carried."""

    def __init__(self, real):
        self._real = real
        self.WriterError = real.WriterError
        self.calls = []

    def staged_write(self, path, data, mode=None):
        self.calls.append((path, data))
        return self._real.staged_write(path, data, mode=mode)


class TestProvisionConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "sched-home")
        os.makedirs(os.path.join(self.home, "server"))
        with open(os.path.join(self.home, "server", "__init__.py"),
                  "w", encoding="utf-8") as fh:
            fh.write(_STUB_INIT)
        with open(os.path.join(self.home, "server", "config.py"),
                  "w", encoding="utf-8") as fh:
            fh.write(_STUB_CONFIG)
        self.example = {"home": self.home, "port": 8796}
        with open(os.path.join(self.home, "config.example.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(self.example, fh)
        self.config_path = os.path.join(self.home, "config.json")

    def _run(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = provision.main(argv)
        return code, out.getvalue()

    def _summary(self, output):
        line = output.strip().splitlines()[-1]
        self.assertTrue(line.startswith("SUMMARY "))
        return json.loads(line[len("SUMMARY "):])

    def _rendered(self, merged):
        return json.dumps(merged, indent=2, sort_keys=True) + "\n"

    def test_writer_seam_resolves_to_the_one_writer(self):
        self.assertEqual(
            os.path.realpath(provision._writer.__file__),
            os.path.realpath(WRITER_PATH))

    def test_fresh_provision_lands_exact_content_via_writer(self):
        recorder = _RecordingWriter(provision._writer)
        with mock.patch.object(provision, "_writer",
                                        recorder):
            code, out = self._run(["--sched-home", self.home])
        self.assertEqual(code, 0)
        expected = self._rendered(self.example)
        with open(self.config_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), expected)
        self.assertEqual(
            recorder.calls,
            [(self.config_path, expected.encode("utf-8"))])
        # no staging litter remains in the home
        self.assertEqual(
            sorted(os.listdir(self.home)),
            ["config.example.json", "config.json", "server"])
        summary = self._summary(out)
        self.assertTrue(summary["provisioned"])
        self.assertEqual(summary["resolved"]["port"], 8796)

    def test_carried_values_merge_over_existing_config(self):
        existing = {"home": self.home, "port": 1, "extra": "keep"}
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh)
        values_path = os.path.join(self.tmp.name, "values.json")
        with open(values_path, "w", encoding="utf-8") as fh:
            json.dump({"port": 9999}, fh)
        recorder = _RecordingWriter(provision._writer)
        with mock.patch.object(provision, "_writer",
                                        recorder):
            code, out = self._run(
                ["--sched-home", self.home,
                 "--values", values_path])
        self.assertEqual(code, 0)
        merged = {"home": self.home, "port": 9999, "extra": "keep"}
        expected = self._rendered(merged)
        with open(self.config_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), expected)
        self.assertEqual(
            recorder.calls,
            [(self.config_path, expected.encode("utf-8"))])
        summary = self._summary(out)
        self.assertFalse(summary["provisioned"])
        self.assertEqual(summary["carried_keys"], ["port"])
        self.assertEqual(summary["resolved"]["port"], 9999)

    def test_no_provision_no_carried_no_write(self):
        existing = {"home": self.home, "port": 5}
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh)
        recorder = _RecordingWriter(provision._writer)
        with mock.patch.object(provision, "_writer",
                                        recorder):
            code, _out = self._run(["--sched-home", self.home])
        self.assertEqual(code, 0)
        self.assertEqual(recorder.calls, [])
        with open(self.config_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), existing)

    def test_writer_failure_surfaces_as_fail_line_target_untouched(self):
        # Occupy the writer's own staging path with a
        # directory: the staged open fails inside the real
        # writer before any byte can land (the failed-stage
        # pin's form, test_writer.py), and the failure must
        # surface in the script's FAIL form with the
        # writer's error name, exit 1, no SUMMARY, and no
        # config left behind.
        staging = os.path.join(
            self.home,
            ".%s.sched-tmp-%d-%d" % ("config.json", os.getpid(),
                                     threading.get_ident()))
        os.mkdir(staging)
        code, out = self._run(["--sched-home", self.home])
        self.assertEqual(code, 1)
        self.assertIn("FAIL config write: io_error", out)
        self.assertNotIn("SUMMARY", out)
        self.assertFalse(os.path.exists(self.config_path))


if __name__ == "__main__":
    unittest.main()
