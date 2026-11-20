"""sched exec argv handling (cli.ops_cmds.cmd_exec): the
client's own flags live before the "--" separator; everything
after it is the delivered argv and must pass verbatim.
Regression for the 2026-11-13 defect: a whole-argv flag scan
stripped a discrete "--caller <value>" pair belonging to the
inner command (runner fires lost their caller and the runner
refused the manifest's unregistered fallback). Ported from
the original scheduler repo's tests/test_sched_exec_argv.py;
the harness patches cli.ops_cmds._ops_post instead of loading
bin/sched."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cli import ops_cmds  # noqa: E402

OK = {"ok": True, "stdout_tail": "", "stderr_tail": "", "exit_code": 0}


class ExecArgvTests(unittest.TestCase):
    def run_exec(self, argv, env_caller="test-caller"):
        captured = {}

        def fake_post(req, http_timeout=30):
            captured.update(req)
            captured["http_timeout"] = http_timeout
            return dict(OK)

        with mock.patch.object(ops_cmds, "_ops_post", fake_post), \
                mock.patch.dict(os.environ, {"SCHED_CALLER": env_caller}):
            code = ops_cmds.cmd_exec(list(argv))
        return code, captured

    def test_inner_caller_pair_delivered_verbatim(self):
        code, req = self.run_exec(
            ["--", "echo", "--caller", "monitor", "hello"])
        self.assertEqual(code, 0)
        self.assertEqual(req["argv"],
                         ["echo", "--caller", "monitor", "hello"])
        self.assertEqual(req["caller"], "test-caller")

    def test_head_caller_is_attribution_inner_pair_intact(self):
        code, req = self.run_exec(
            ["--caller", "ops-caller", "--",
             "echo", "--caller", "monitor", "hello"])
        self.assertEqual(code, 0)
        self.assertEqual(req["caller"], "ops-caller")
        self.assertEqual(req["argv"],
                         ["echo", "--caller", "monitor", "hello"])

    def test_inner_timeout_and_cwd_pairs_not_stolen(self):
        code, req = self.run_exec(
            ["--timeout", "60", "--",
             "prog", "--timeout", "5", "--cwd", "/inner"])
        self.assertEqual(code, 0)
        self.assertEqual(req["timeout"], 60)
        self.assertEqual(req["argv"],
                         ["prog", "--timeout", "5", "--cwd", "/inner"])
        self.assertNotIn("cwd", req)

    def test_head_cwd_and_timeout_still_apply(self):
        code, req = self.run_exec(
            ["--cwd", "/somewhere", "--timeout", "15", "--", "true"])
        self.assertEqual(code, 0)
        self.assertEqual(req["cwd"], "/somewhere")
        self.assertEqual(req["timeout"], 15)
        self.assertEqual(req["argv"], ["true"])

    def test_missing_separator_is_usage_error_no_request(self):
        code, req = self.run_exec(["echo", "hello"])
        self.assertEqual(code, 2)
        self.assertEqual(req, {})

    def test_empty_command_is_usage_error_no_request(self):
        code, req = self.run_exec(["--"])
        self.assertEqual(code, 2)
        self.assertEqual(req, {})


if __name__ == "__main__":
    sys.exit(unittest.main())
