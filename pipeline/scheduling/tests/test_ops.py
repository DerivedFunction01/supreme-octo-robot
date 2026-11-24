"""Unit tests for the delegated operations (server/serving/ops.py).

Every test runs against a fixture workspace in a temp dir; the
live tree and the live ledger are never touched. The audit is
checked against a fake ledger that only records.
"""

import hashlib
import os
import stat
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from server.serving import ops  # noqa: E402


class FakeLedger:
    def __init__(self):
        self.records = []

    def record(self, kind, **fields):
        rec = {"kind": kind}
        rec.update(fields)
        self.records.append(rec)
        return rec


class OpsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.values = {"workspace_root": self.root, "capture_cap_bytes": 65536}
        self.ledger = FakeLedger()

    def tearDown(self):
        self._tmp.cleanup()

    # The authenticated identity every pre-existing case rides
    # (§10.1: /ops is token-authenticated; the auth pins live
    # in the dedicated section below).
    AUTH = ("test", ["read", "write-state", "send", "bridge", "exec"])

    def perform(self, req, auth=AUTH):
        return ops.perform(self.ledger, self.values, req, auth=auth)

    # ---------------------------------------------------------- write

    def test_write_creates_file_and_reports_hash(self):
        code, payload = self.perform(
            {"caller": "test", "op": "write", "path": "a/b.txt", "content": "hello\n"}
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["path"], os.path.join("a", "b.txt"))
        self.assertEqual(payload["sha256"], hashlib.sha256(b"hello\n").hexdigest())
        with open(os.path.join(self.root, "a", "b.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "hello\n")

    def test_write_outside_scope_is_refused(self):
        code, payload = self.perform(
            {"caller": "test", "op": "write", "path": "../escape.txt", "content": "x"}
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "outside_scope")
        self.assertFalse(
            os.path.exists(os.path.join(os.path.dirname(self.root), "escape.txt"))
        )

    def test_write_absolute_path_inside_scope(self):
        target = os.path.join(self.root, "abs.txt")
        code, payload = self.perform(
            {"caller": "test", "op": "write", "path": target, "content": "abs"}
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])

    def test_write_mode_is_stamped(self):
        # The write form's mode extension (contract 15's
        # discipline through the endpoint): a credential-class
        # target performed through the service is stamped
        # server-side, never left at the umask default.
        target = os.path.join(self.root, "secret.json")
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "write",
                "path": target,
                "content": "{}",
                "mode": 0o600,
            }
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)

    def test_write_mode_restamps_a_recreated_file(self):
        target = self._seed("secret.json", "{}")
        os.chmod(target, 0o644)
        code, _payload = self.perform(
            {
                "caller": "test",
                "op": "write",
                "path": target,
                "content": "{}",
                "mode": 0o600,
            }
        )
        self.assertEqual(code, 200)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)

    def test_write_without_mode_carries_the_existing_mode(self):
        target = self._seed("carried.txt", "old")
        os.chmod(target, 0o640)
        code, _payload = self.perform(
            {"caller": "test", "op": "write", "path": target, "content": "new"}
        )
        self.assertEqual(code, 200)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o640)

    def test_write_bad_mode_is_rejected_and_writes_nothing(self):
        for bad in ("600", True, 0o10000, -1):
            target = os.path.join(self.root, "bad.txt")
            code, payload = self.perform(
                {
                    "caller": "test",
                    "op": "write",
                    "path": target,
                    "content": "x",
                    "mode": bad,
                }
            )
            self.assertEqual(code, 400, bad)
            self.assertEqual(payload["error"], "bad_request")
            self.assertFalse(os.path.exists(target))

    # ---------------------------------------------------------- patch

    def _seed(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_patch_replaces_single_match(self):
        self._seed("f.txt", "alpha beta gamma")
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "patch",
                "path": "f.txt",
                "old": "beta",
                "new": "BETA",
            }
        )
        self.assertEqual(code, 200)
        with open(os.path.join(self.root, "f.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "alpha BETA gamma")

    def test_patch_no_match(self):
        self._seed("f.txt", "alpha")
        code, payload = self.perform(
            {"caller": "test", "op": "patch", "path": "f.txt", "old": "zzz", "new": "q"}
        )
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "no_match")

    def test_patch_multi_match(self):
        self._seed("f.txt", "x x x")
        code, payload = self.perform(
            {"caller": "test", "op": "patch", "path": "f.txt", "old": "x", "new": "y"}
        )
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "multi_match")

    def test_patch_missing_file(self):
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "patch",
                "path": "nope.txt",
                "old": "a",
                "new": "b",
            }
        )
        self.assertEqual(code, 404)
        self.assertEqual(payload["error"], "not_found")

    # ---------------------------------------------------------- exec

    def test_exec_captures_output_and_exit(self):
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "exec",
                "argv": [sys.executable, "-c", "import sys; print('out'); sys.exit(3)"],
            }
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["exit_code"], 3)
        self.assertIn("out", payload["stdout_tail"])
        self.assertFalse(payload["timed_out"])

    def test_exec_cwd_inside_scope(self):
        os.makedirs(os.path.join(self.root, "sub"))
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "exec",
                "cwd": "sub",
                "argv": [
                    sys.executable,
                    "-c",
                    "import os; print(os.path.basename(os.getcwd()))",
                ],
            }
        )
        self.assertEqual(code, 200)
        self.assertIn("sub", payload["stdout_tail"])

    def test_exec_timeout(self):
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "exec",
                "timeout": 1,
                "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
            }
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["timed_out"])
        self.assertIsNone(payload["exit_code"])

    def test_exec_bad_argv(self):
        code, payload = self.perform({"caller": "test", "op": "exec", "argv": []})
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "bad_request")

    def test_exec_env_carries_pinned_ssh_when_configured(self):
        import unittest.mock as mock

        values = dict(self.values)
        values["git_ssh_identity_file"] = os.path.join(self.root, "id_test")
        values["git_ssh_known_hosts_file"] = os.path.join(self.root, "kh_test")
        with mock.patch.dict(os.environ):
            os.environ.pop("GIT_SSH_COMMAND", None)
            code, payload = ops.perform(
                self.ledger,
                values,
                {
                    "caller": "test",
                    "op": "exec",
                    "argv": [
                        sys.executable,
                        "-c",
                        "import os; print(os.environ.get('GIT_SSH_COMMAND'))",
                    ],
                },
                auth=self.AUTH,
            )
        self.assertEqual(code, 200)
        out = payload["stdout_tail"]
        self.assertIn("ssh -i " + values["git_ssh_identity_file"], out)
        self.assertIn("UserKnownHostsFile=" + values["git_ssh_known_hosts_file"], out)
        self.assertIn("StrictHostKeyChecking=yes", out)

    def test_exec_env_has_no_ssh_pin_by_default(self):
        import unittest.mock as mock

        with mock.patch.dict(os.environ):
            os.environ.pop("GIT_SSH_COMMAND", None)
            code, payload = self.perform(
                {
                    "caller": "test",
                    "op": "exec",
                    "argv": [
                        sys.executable,
                        "-c",
                        "import os; print(os.environ.get('GIT_SSH_COMMAND'))",
                    ],
                }
            )
        self.assertEqual(code, 200)
        self.assertEqual(payload["stdout_tail"].strip(), "None")

    def test_exec_env_half_configured_pins_nothing(self):
        import unittest.mock as mock

        values = dict(self.values)
        values["git_ssh_identity_file"] = os.path.join(self.root, "id_test")
        with mock.patch.dict(os.environ):
            os.environ.pop("GIT_SSH_COMMAND", None)
            code, payload = ops.perform(
                self.ledger,
                values,
                {
                    "caller": "test",
                    "op": "exec",
                    "argv": [
                        sys.executable,
                        "-c",
                        "import os; print(os.environ.get('GIT_SSH_COMMAND'))",
                    ],
                },
                auth=self.AUTH,
            )
        self.assertEqual(code, 200)
        self.assertEqual(payload["stdout_tail"].strip(), "None")

    # ---------------------------------------------------------- shape + audit

    def test_missing_caller_rejected(self):
        code, payload = self.perform({"op": "write", "path": "x.txt", "content": "y"})
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "bad_request")

    def test_unknown_op_rejected(self):
        code, payload = self.perform({"caller": "test", "op": "delete"})
        self.assertEqual(code, 400)

    # ---------------------------------------------------------- auth (§10.1)

    def test_unauthenticated_is_refused_and_performs_nothing(self):
        code, payload = self.perform(
            {"caller": "test", "op": "write", "path": "nope.txt", "content": "x"},
            auth=None,
        )
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "unauthenticated")
        self.assertFalse(os.path.exists(os.path.join(self.root, "nope.txt")))
        rec = self.ledger.records[-1]
        self.assertEqual(rec["status"], "refused")
        self.assertEqual(rec["caller"], "unknown")

    def test_write_requires_write_state_scope(self):
        code, payload = self.perform(
            {"caller": "test", "op": "write", "path": "nope.txt", "content": "x"},
            auth=("test", ["exec"]),
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "scope_refused")
        self.assertFalse(os.path.exists(os.path.join(self.root, "nope.txt")))

    def test_exec_requires_exec_scope(self):
        code, payload = self.perform(
            {"caller": "test", "op": "exec", "argv": [sys.executable, "-c", "pass"]},
            auth=("test", ["write-state"]),
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "scope_refused")

    def test_caller_label_must_match_the_authenticated_caller(self):
        code, payload = self.perform(
            {"caller": "test", "op": "write", "path": "nope.txt", "content": "x"},
            auth=("other", ["write-state", "exec"]),
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "caller_mismatch")
        self.assertFalse(os.path.exists(os.path.join(self.root, "nope.txt")))

    def test_every_attempt_is_audited(self):
        self.perform(
            {"caller": "test", "op": "write", "path": "ok.txt", "content": "1"}
        )
        self.perform(
            {"caller": "test", "op": "write", "path": "../no.txt", "content": "1"}
        )
        kinds = [
            (r["op"], r["status"]) for r in self.ledger.records if r["kind"] == "op"
        ]
        self.assertEqual(kinds, [("write", "ok"), ("write", "refused")])
        self.assertTrue(all(r["caller"] == "test" for r in self.ledger.records))


class OpsHttpAuthTest(unittest.TestCase):
    """POST /ops over real HTTP (§10.1): the bearer token is
    authenticated by the HTTP layer through the connector
    registry in the home's live config, read fresh per call."""

    TOKENS = {"writer": "tok-writer", "runner": "tok-runner"}

    def setUp(self):
        import hashlib
        import json
        import threading
        import urllib.error
        import urllib.request

        self._json, self._threading = json, threading
        self._urllib_error, self._urllib_request = urllib.error, urllib.request
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        home = os.path.join(self._tmp.name, "home")
        self.ws = os.path.join(self._tmp.name, "ws")
        os.makedirs(self.ws)
        from tests.helpers import make_home

        self.values, self.sources = make_home(home)
        self.values["workspace_root"] = self.ws
        callers = {
            "writer": {
                "token_sha256": hashlib.sha256(b"tok-writer").hexdigest(),
                "scopes": ["write-state"],
            },
            "runner": {
                "token_sha256": hashlib.sha256(b"tok-runner").hexdigest(),
                "scopes": ["exec"],
            },
        }
        with open(os.path.join(home, "config.json"), "w") as fh:
            json.dump({"connector": {"callers": callers}}, fh)
        from server.firing.engine import Engine
        from server.serving.http import make_server

        from tests.helpers import T0, Clock

        engine = Engine(self.values, now_fn=Clock(T0), inline=True)
        self.server = make_server(
            engine, self.values, self.sources, host="127.0.0.1", port=0
        )
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.shutdown)

    def post(self, req, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = self._urllib_request.Request(
            f"http://127.0.0.1:{self.port}/ops",
            data=self._json.dumps(req).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        try:
            with self._urllib_request.urlopen(request, timeout=10) as resp:
                return resp.status, self._json.loads(resp.read())
        except self._urllib_error.HTTPError as exc:
            return exc.code, self._json.loads(exc.read())

    def test_no_token_is_401(self):
        code, payload = self.post(
            {"caller": "writer", "op": "write", "path": "x.txt", "content": "y"}
        )
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "unauthenticated")
        self.assertFalse(os.path.exists(os.path.join(self.ws, "x.txt")))

    def test_write_state_token_writes(self):
        code, payload = self.post(
            {"caller": "writer", "op": "write", "path": "x.txt", "content": "y"},
            token=self.TOKENS["writer"],
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        with open(os.path.join(self.ws, "x.txt")) as fh:
            self.assertEqual(fh.read(), "y")

    def test_write_state_token_cannot_exec(self):
        code, payload = self.post(
            {"caller": "writer", "op": "exec", "argv": [sys.executable, "-c", "pass"]},
            token=self.TOKENS["writer"],
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "scope_refused")

    def test_exec_token_execs(self):
        code, payload = self.post(
            {
                "caller": "runner",
                "op": "exec",
                "argv": [sys.executable, "-c", "print('oi2-http')"],
            },
            token=self.TOKENS["runner"],
        )
        self.assertEqual(code, 200)
        self.assertIn("oi2-http", payload["stdout_tail"])


if __name__ == "__main__":
    unittest.main()


class ConfigSshKeysTest(unittest.TestCase):
    def test_git_ssh_keys_resolve_from_env(self):
        from server import config as config_mod

        values, sources = config_mod.resolve(
            path=os.path.join(tempfile.gettempdir(), "no-such-config.json"),
            env={
                "SCHEDULER_GIT_SSH_IDENTITY_FILE": "idp",
                "SCHEDULER_GIT_SSH_KNOWN_HOSTS_FILE": "khp",
            },
        )
        self.assertEqual(values["git_ssh_identity_file"], "idp")
        self.assertEqual(values["git_ssh_known_hosts_file"], "khp")
        self.assertEqual(sources["git_ssh_identity_file"], "env")

    def test_git_ssh_keys_default_unset(self):
        from server import config as config_mod

        values, _sources = config_mod.resolve(
            path=os.path.join(tempfile.gettempdir(), "no-such-config.json"), env={}
        )
        self.assertIsNone(values["git_ssh_identity_file"])
        self.assertIsNone(values["git_ssh_known_hosts_file"])


class ExtraRootOpsTest(unittest.TestCase):
    """The /ops endpoint's extra write roots (the writer-route
    cure): the server's config values name roots beside the
    workspace that write/patch may target — the venue
    funnel's credential directory is the standing entry — and
    nothing else widens: a path outside root + extra roots is
    refused, exec cwd is never widened, and a request field
    claiming to name a root is ignored."""

    AUTH = OpsTest.AUTH

    def setUp(self):
        self._ws = tempfile.TemporaryDirectory()
        self._cred = tempfile.TemporaryDirectory()
        self.root = self._ws.name
        self.cred = self._cred.name
        self.values = {
            "workspace_root": self.root,
            "capture_cap_bytes": 65536,
            "ops_extra_write_roots": [self.cred],
        }
        self.ledger = FakeLedger()

    def tearDown(self):
        self._ws.cleanup()
        self._cred.cleanup()

    def perform(self, req, auth=AUTH):
        return ops.perform(self.ledger, self.values, req, auth=auth)

    def test_write_under_a_configured_extra_root(self):
        target = os.path.join(self.cred, "token.json")
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "write",
                "path": target,
                "content": "{}",
                "mode": 0o600,
            }
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{}")
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
        # The audit target names the resolved path (it is not
        # workspace-relative).
        self.assertEqual(self.ledger.records[-1]["target"], target)

    def test_write_outside_root_and_extra_roots_is_refused(self):
        target = os.path.join(
            os.path.dirname(self.root), "escape-extra-root.txt")
        code, payload = self.perform(
            {"caller": "test", "op": "write", "path": target, "content": "x"}
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "outside_scope")
        self.assertFalse(os.path.exists(target))

    def test_exec_cwd_is_not_widened_by_extra_roots(self):
        code, payload = self.perform(
            {
                "caller": "test",
                "op": "exec",
                "argv": ["/bin/true"],
                "cwd": self.cred,
            }
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "outside_scope")

    def test_a_request_cannot_name_an_extra_root(self):
        target = os.path.join(self.cred, "token.json")
        values = {"workspace_root": self.root, "capture_cap_bytes": 65536}
        code, payload = ops.perform(
            self.ledger,
            values,
            {
                "caller": "test",
                "op": "write",
                "path": target,
                "content": "{}",
                "ops_extra_write_roots": [self.cred],
            },
            auth=self.AUTH,
        )
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "outside_scope")
        self.assertFalse(os.path.exists(target))

    def test_extra_roots_default_is_the_funnel_credential_dir(self):
        from server import config as config_mod

        values, sources = config_mod.resolve(
            path=os.path.join(tempfile.gettempdir(), "no-such-config.json"),
            env={},
        )
        expected = os.path.join(
            os.path.expanduser("~"), ".config", "colab-cli")
        self.assertEqual(values["ops_extra_write_roots"], [expected])
        self.assertEqual(sources["ops_extra_write_roots"], "default")
