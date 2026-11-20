"""The serve split (owner ruling, 2026-11-15: process
boundaries follow coupling): run.py's `serve` assembles
exactly the two coupled surfaces (scheduling, attention)
and never loads the split surfaces' mounts;
`serve-workbench` runs the workbench's own standalone
entry and `serve-venue` the lease panel's, each loading
nothing else's mount.

The builders are stubbed at run.py's own seams (the
module loaders and the surfaces' build_mount functions),
so the pin is composition — which mounts, on which
ports, with which workers — not the surfaces' internals.
"""

import importlib.util
import inspect
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_MODULE_KEYS = ("server", "server.serving",
                "server.serving.http", "attention",
                "attention.server", "workrecord_server",
                "workrecord_server.serving")


def _load_run():
    spec = importlib.util.spec_from_file_location(
        "workhorse_run", REPO_ROOT / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


class _FakeListener:
    def __init__(self, mount, host, port):
        self.mount = mount
        self.host = host
        self.port = port
        self.server_address = (host, port)


class _SplitCase(unittest.TestCase):
    def setUp(self):
        self.run = _load_run()
        self._saved = {name: sys.modules.get(name)
                       for name in _MODULE_KEYS}
        self.addCleanup(self._restore_modules)

    def _restore_modules(self):
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class CoupledServeCompositionTests(_SplitCase):
    def test_assemble_mounts_exactly_the_coupled_pair(self):
        sched_http = _module(
            "server.serving.http",
            build_mount=lambda engine, values, sources:
                "sched-mount")
        sched_serving = _module("server.serving",
                                http=sched_http)
        sys.modules["server"] = _module(
            "server", serving=sched_serving, __path__=[])
        sys.modules["server.serving"] = sched_serving
        sys.modules["server.serving.http"] = sched_http

        att_server = _module(
            "attention.server",
            build_mount=lambda settings, store: (
                "att-mount",
                {"attention-loop": lambda stop: None}))
        sys.modules["attention"] = _module(
            "attention", server=att_server, __path__=[])
        sys.modules["attention.server"] = att_server

        split_loads = []

        def forbidden_load(name):
            def load():
                split_loads.append(name)
                raise AssertionError(
                    f"the coupled serve loaded the {name}")
            return load

        self.run._load_workrecord_server = forbidden_load(
            "workbench")
        self.run._load_venue_ui = forbidden_load("venue")

        fake_serving = types.SimpleNamespace(
            Listener=_FakeListener)
        listeners, workers = self.run._assemble(
            fake_serving, engine=object(),
            values={"host": "127.0.0.1", "port": 8796,
                    "tick_secs": 30},
            sources={},
            att_settings=types.SimpleNamespace(
                host="127.0.0.1", port=8797),
            att_store=object())

        self.assertEqual([l.mount for l in listeners],
                         ["sched-mount", "att-mount"])
        self.assertEqual([l.port for l in listeners],
                         [8796, 8797])
        self.assertEqual(set(workers),
                         {"scheduler-tick", "attention-loop"})
        self.assertEqual(split_loads, [])

    def test_assemble_source_names_no_split_surface(self):
        source = inspect.getsource(self.run._assemble)
        self.assertNotIn("workrecord", source)
        self.assertNotIn("venue_ui", source)


class ServeWorkbenchTests(_SplitCase):
    def _install_workbench(self):
        self.main_calls = []

        def fake_main():
            self.main_calls.append(())
            return 7

        wr_serving = _module("workrecord_server.serving",
                             main=fake_main)
        wr_package = _module("workrecord_server",
                             serving=wr_serving, __path__=[])

        def fake_load():
            sys.modules["workrecord_server"] = wr_package
            sys.modules["workrecord_server.serving"] = \
                wr_serving
            return wr_package

        self.run._load_workrecord_server = fake_load

    def test_runs_only_the_workbench_entry(self):
        self._install_workbench()
        before = set(sys.modules)
        self.assertEqual(self.run.cmd_serve_workbench([]), 7)
        self.assertEqual(self.main_calls, [()])
        loaded = set(sys.modules) - before
        self.assertEqual(
            loaded & {"server", "server.config",
                      "server.serving.http", "attention",
                      "attention.server"},
            set())

    def test_rejects_arguments_without_loading(self):
        self._install_workbench()
        self.assertEqual(
            self.run.cmd_serve_workbench(["--config", "x"]),
            2)
        self.assertEqual(self.main_calls, [])

    def test_main_dispatches_serve_workbench(self):
        self._install_workbench()
        self.assertEqual(
            self.run.main(["serve-workbench"]), 7)
        self.assertEqual(self.main_calls, [()])


class ServeVenueTests(_SplitCase):
    def _install_venue(self):
        self.main_calls = []

        def fake_main(argv):
            self.main_calls.append(argv)
            return 9

        venue_ui = _module("venue_ui_fake", main=fake_main)

        def fake_load():
            return venue_ui

        self.run._load_venue_ui = fake_load

    def test_runs_only_the_venue_entry(self):
        self._install_venue()
        before = set(sys.modules)
        self.assertEqual(self.run.cmd_serve_venue([]), 9)
        self.assertEqual(self.main_calls, [[]])
        loaded = set(sys.modules) - before
        self.assertEqual(
            loaded & {"server", "server.config",
                      "server.serving.http", "attention",
                      "attention.server", "workrecord_server",
                      "workrecord_server.serving"},
            set())

    def test_rejects_arguments_without_loading(self):
        loads = []

        def fake_load():
            loads.append(1)
            raise AssertionError(
                "serve-venue loaded the panel for bad argv")

        self.run._load_venue_ui = fake_load
        self.assertEqual(
            self.run.cmd_serve_venue(["--port", "8793"]), 2)
        self.assertEqual(loads, [])

    def test_main_dispatches_serve_venue(self):
        self._install_venue()
        self.assertEqual(self.run.main(["serve-venue"]), 9)
        self.assertEqual(self.main_calls, [[]])


if __name__ == "__main__":
    unittest.main()
