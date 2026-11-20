"""The ops token mechanism (§10.1; contracts 01 + 04): the
client token home's resolution order, and the mint/re-issue
semantics against the connector registry — re-issue rotates
and the old token stops verifying. Fixture tokens only, in
temp homes; no live config or token home is touched.

The verb's store mirror is pinned end-to-end in
MintStoreMirrorTest: a mint or revoke — by the /ops path
or the bootstrap path — leaves the unified registry
store's token_callers equal to the written config's
connector.callers, and a store that cannot be updated
fails the verb loudly. Config, token home, and store all
live in temp dirs, re-pointed through the standing env
seams; no live state is touched."""
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import connector_token, ops_client  # noqa: E402
from cli.connector_token import apply_mint, apply_revoke  # noqa: E402
from server.serving import connector  # noqa: E402

# The registry package's store-path env seam (its config
# contract, PIPELINE_REGISTRY_STORE): the mirror resolves
# the store through it, so tests re-point the store here.
STORE_ENV = "PIPELINE_REGISTRY_STORE"


class TokenHomeResolutionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env_dir = os.path.join(self._tmp.name, "env-home")
        self.default_dir = os.path.join(self._tmp.name, "default-home")
        os.makedirs(self.env_dir)
        os.makedirs(self.default_dir)

    def _write(self, directory, caller, text):
        with open(os.path.join(directory, f"{caller}.token"), "w") as fh:
            fh.write(text)

    def test_env_home_beats_default_home(self):
        self._write(self.env_dir, "ops", "tok-env\n")
        self._write(self.default_dir, "ops", "tok-default\n")
        with mock.patch.object(ops_client._paths, "OPS_TOKEN_DIR", self.default_dir):
            env = {ops_client.TOKEN_DIR_ENV: self.env_dir}
            self.assertEqual(ops_client.resolve_ops_token("ops", env=env), "tok-env")
            self.assertEqual(ops_client.resolve_ops_token("ops", env={}), "tok-default")

    def test_resolution_is_per_caller(self):
        self._write(self.env_dir, "ops", "tok-ops\n")
        env = {ops_client.TOKEN_DIR_ENV: self.env_dir}
        self.assertIsNone(ops_client.resolve_ops_token("other", env=env))

    def test_missing_and_empty_files_resolve_to_none(self):
        env = {ops_client.TOKEN_DIR_ENV: self.env_dir}
        self.assertIsNone(ops_client.resolve_ops_token("ghost", env=env))
        self._write(self.env_dir, "blank", "  \n")
        self.assertIsNone(ops_client.resolve_ops_token("blank", env=env))

    def test_store_round_trips_at_0600(self):
        env = {ops_client.TOKEN_DIR_ENV: self.env_dir}
        path = ops_client.store_ops_token("ops", "tok-stored", env=env)
        self.assertEqual(ops_client.resolve_ops_token("ops", env=env), "tok-stored")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class MintReissueTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = self._tmp.name
        self.config = {}
        self.values = {"home": self.home}

    def _flush(self):
        with open(os.path.join(self.home, "config.json"), "w") as fh:
            json.dump(self.config, fh)

    def test_reissue_rotates_and_the_old_token_stops_verifying(self):
        first = apply_mint(self.config, "ops", ["write-state", "exec"])
        self._flush()
        self.assertEqual(connector.authenticate(self.values, first),
                         ("ops", ["write-state", "exec"]))
        second = apply_mint(self.config, "ops", ["write-state", "exec"])
        self._flush()
        self.assertNotEqual(first, second)
        self.assertIsNone(connector.authenticate(self.values, first))
        self.assertEqual(connector.authenticate(self.values, second),
                         ("ops", ["write-state", "exec"]))

    def test_registry_stores_hashes_only(self):
        token = apply_mint(self.config, "ops", ["exec"])
        entry = self.config["connector"]["callers"]["ops"]
        self.assertNotIn(token, json.dumps(self.config))
        self.assertEqual(len(entry["token_sha256"]), 64)

    def test_revoke_removes_and_reports_absence(self):
        token = apply_mint(self.config, "ops", ["exec"])
        self._flush()
        self.assertTrue(apply_revoke(self.config, "ops"))
        self._flush()
        self.assertIsNone(connector.authenticate(self.values, token))
        self.assertFalse(apply_revoke(self.config, "ops"))

    def test_exec_scope_survives_registry_loading(self):
        # The registry loader drops unknown scopes; `exec` is a
        # contract 01 scope and must survive, while a bogus
        # scope is still dropped.
        import hashlib
        digest = hashlib.sha256(b"tok-x").hexdigest()
        self.config = {"connector": {"callers": {
            "ops": {"token_sha256": digest, "scopes": ["exec", "bogus"]}}}}
        self._flush()
        self.assertEqual(connector.authenticate(self.values, "tok-x"),
                         ("ops", ["exec"]))


class MintStoreMirrorTest(unittest.TestCase):
    """The verb driven whole, against temp state: the
    config under a patched ROOT, the token home and the
    registry store re-pointed by their env seams, and the
    /ops POST faked (the write's server half is the
    endpoint's own contract, pinned elsewhere)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = self._tmp.name
        self.home = os.path.join(base, "sched")
        self.token_home = os.path.join(base, "token-home")
        self.store_path = os.path.join(base, "store", "registry.json")
        os.makedirs(self.home)
        os.makedirs(self.token_home)
        self.config_path = os.path.join(self.home, "config.json")
        self.posts = []

    # -- fixture plumbing ---------------------------------

    def _write_config(self, callers):
        with open(self.config_path, "w") as fh:
            json.dump({"connector": {"callers": callers}}, fh)

    def _write_store(self, token_callers, handlers=None):
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, "w") as fh:
            json.dump({
                "version": 1,
                "thread_callers": {"callers": [], "active": []},
                "token_callers": token_callers,
                "handlers": handlers or [],
                "programmes": [],
            }, fh)

    def _read_store(self):
        with open(self.store_path) as fh:
            return json.load(fh)

    def _run(self, argv, post_result):
        def fake_post(req, http_timeout):
            self.posts.append(req)
            return post_result

        env = {ops_client.TOKEN_DIR_ENV: self.token_home,
               STORE_ENV: self.store_path}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(connector_token, "ROOT", self.home), \
                mock.patch.object(connector_token, "_ops_post", fake_post), \
                mock.patch.dict(os.environ, env), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            rc = connector_token.cmd_connector_token(argv)
        return rc, out.getvalue(), err.getvalue()

    def _posted_config(self):
        self.assertEqual(len(self.posts), 1)
        return json.loads(self.posts[0]["content"])

    @staticmethod
    def _printed_token(out):
        lines = out.splitlines()
        idx = next(i for i, line in enumerate(lines)
                   if "shown once" in line)
        return lines[idx + 1].strip()

    # -- the mirror lands ---------------------------------

    def test_mint_via_ops_mirrors_the_store_wholesale(self):
        self._write_config({})
        self._write_store(
            {"stale-caller": {"token_sha256": "0" * 64,
                              "scopes": ["read"]}},
            handlers=[{"handle": "seed-handler"}])
        rc, out, _err = self._run(
            ["--caller", "test-actor", "new-caller",
             "--scopes", "read,exec", "--save-client"],
            {"ok": True})
        self.assertEqual(rc, 0)
        written = self._posted_config()
        store = self._read_store()
        # Wholesale equality: the minted caller is in, the
        # store's stale caller is out — never a merge.
        self.assertEqual(store["token_callers"],
                         written["connector"]["callers"])
        self.assertNotIn("stale-caller", store["token_callers"])
        # The mirror touches its own section only.
        self.assertEqual(store["handlers"], [{"handle": "seed-handler"}])
        # The printed token is the minted caller's, and the
        # token-home save carries the same token.
        token = self._printed_token(out)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self.assertEqual(
            store["token_callers"]["new-caller"]["token_sha256"], digest)
        with open(os.path.join(self.token_home, "new-caller.token")) as fh:
            self.assertEqual(fh.read().strip(), token)

    def test_mint_via_bootstrap_mirrors_the_store(self):
        self._write_config({})
        rc, out, _err = self._run(
            ["--caller", "test-actor", "boot-caller",
             "--scopes", "send"],
            None)  # server unreachable: the bootstrap path
        self.assertEqual(rc, 0)
        self.assertIn("wrote the live config directly", out)
        with open(self.config_path) as fh:
            written = json.load(fh)
        store = self._read_store()
        self.assertEqual(store["token_callers"],
                         written["connector"]["callers"])
        self.assertIn("boot-caller", store["token_callers"])

    def test_revoke_mirrors_the_store(self):
        entry = {"token_sha256": "1" * 64, "scopes": ["read"]}
        self._write_config({"doomed": entry})
        self._write_store({"doomed": entry})
        rc, _out, _err = self._run(
            ["--caller", "test-actor", "doomed", "--revoke"],
            {"ok": True})
        self.assertEqual(rc, 0)
        self.assertEqual(self._read_store()["token_callers"], {})

    # -- the mirror fails: the verb fails loudly ----------

    def _block_the_store(self):
        blocker = os.path.join(self._tmp.name, "blocker")
        with open(blocker, "w") as fh:
            fh.write("a file, not a directory")
        self.store_path = os.path.join(blocker, "registry.json")

    def test_store_failure_fails_the_mint_after_config_lands(self):
        self._write_config({})
        self._block_the_store()
        rc, out, err = self._run(
            ["--caller", "test-actor", "new-caller",
             "--scopes", "read"],
            None)  # bootstrap: the config write is a real file
        self.assertEqual(rc, 1)
        self.assertIn("OUT OF SYNC", err)
        # The config landed — the failure is the mirror's,
        # and no success (or token) was ever reported.
        with open(self.config_path) as fh:
            self.assertIn("new-caller",
                          json.load(fh)["connector"]["callers"])
        self.assertNotIn("shown once", out)

    def test_store_failure_fails_the_mint_on_the_ops_path(self):
        self._write_config({})
        self._block_the_store()
        rc, out, err = self._run(
            ["--caller", "test-actor", "new-caller",
             "--scopes", "read"],
            {"ok": True})
        self.assertEqual(rc, 1)
        self.assertIn("OUT OF SYNC", err)
        self.assertNotIn("shown once", out)
        # The write was performed (the endpoint said ok);
        # the verb still refused to call it success.
        self.assertIn("new-caller",
                      self._posted_config()["connector"]["callers"])


if __name__ == "__main__":
    unittest.main()
