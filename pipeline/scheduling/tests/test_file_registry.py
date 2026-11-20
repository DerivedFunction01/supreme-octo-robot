import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ops.watches import file_registry as reg

SPECIMEN = """
roots:
  workspace: {WS}
  kit-repo: {REPO}
files:
  - path: spec/route-coverage.md
    root: kit-repo
    presence: non-empty
    restore:
      class: tracked
    owner: fixture-owner
  - path: var/kit-readiness.json
    root: kit-repo
    presence: non-empty
    restore:
      class: generated
      generator:
        argv:
          - python3
          - tools/rebuild.py
        root: kit-repo
    owner: fixture-owner
  - path: var/operator-notes.md
    root: workspace
    presence: non-empty
    restore:
      class: backup
      backup: backups/operator-notes.md
    owner: fixture-owner
  - path: var/field-log.md
    root: workspace
    presence: exists
    restore:
      class: flag-only
    owner: fixture-owner
"""


def manifest_text(files_yaml, roots):
    lines = ["roots:"]
    for name, path in roots.items():
        lines.append(f"  {name}: {path}")
    lines.append("files:")
    lines.append(files_yaml)
    return "\n".join(lines) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = os.path.join(self.tmp, "ws")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.ws)
        os.makedirs(self.repo)
        self.roots = {"workspace": self.ws, "kit-repo": self.repo}
        self.old_state = reg.STATE
        reg.STATE = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        reg.STATE = self.old_state

    def write(self, base, rel, data):
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(path, mode) as fh:
            fh.write(data)
        return path

    def evaluate(self, files):
        data = reg.parse_manifest(manifest_text(files, self.roots))
        roots, entries = reg.validate_manifest(data)
        return reg.evaluate(roots, entries)


class ParserCase(Base):
    def test_specimen_parses_and_validates(self):
        text = SPECIMEN.replace("{WS}", self.ws).replace("{REPO}", self.repo)
        data = reg.parse_manifest(text)
        self.assertEqual(set(data["roots"]), {"workspace", "kit-repo"})
        roots, files = reg.validate_manifest(data)
        self.assertEqual(len(files), 4)
        classes = [f["restore"]["class"] for f in files]
        self.assertEqual(classes,
                         ["tracked", "generated", "backup", "flag-only"])
        gen = files[1]["restore"]["generator"]
        self.assertEqual(gen["argv"], ["python3", "tools/rebuild.py"])

    def test_validation_refusals(self):
        bad = manifest_text(
            "  - path: x.txt\n    root: workspace\n"
            "    presence: non-empty\n", self.roots)
        with self.assertRaises(reg.ManifestError):
            reg.validate_manifest(reg.parse_manifest(bad))
        bad2 = manifest_text(
            "  - path: x.txt\n    root: nowhere\n"
            "    presence: exists\n    owner: o\n", self.roots)
        with self.assertRaises(reg.ManifestError):
            reg.validate_manifest(reg.parse_manifest(bad2))


class PresenceCase(Base):
    def test_matrix(self):
        entry = {"presence": "exists"}
        missing = os.path.join(self.ws, "nope")
        self.assertFalse(reg.check_presence(missing, entry)[0])
        empty = self.write(self.ws, "e.txt", "")
        self.assertTrue(reg.check_presence(empty, entry)[0])
        self.assertFalse(
            reg.check_presence(empty, {"presence": "non-empty"})[0])
        self.assertFalse(reg.check_presence(
            empty, {"presence": "sha256", "sha256": "0" * 64})[0])
        full = self.write(self.ws, "f.txt", "abc")
        digest = hashlib.sha256(b"abc").hexdigest()
        self.assertTrue(reg.check_presence(
            full, {"presence": "sha256", "sha256": digest})[0])
        self.assertFalse(reg.check_presence(
            full, {"presence": "sha256", "sha256": "0" * 64})[0])


class RestoreCase(Base):
    def test_flag_only_never_writes(self):
        flagged, restored, passed = self.evaluate(
            "  - path: gone.txt\n    root: workspace\n"
            "    presence: exists\n    restore:\n"
            "      class: flag-only\n    owner: fixture-owner\n")
        self.assertEqual(len(flagged), 1)
        self.assertIn("fixture-owner", flagged[0])
        self.assertEqual(restored, [])
        self.assertFalse(os.path.exists(os.path.join(self.ws, "gone.txt")))

    def test_backup_restore_and_backup_failure(self):
        self.write(self.ws, "backups/notes.md", "real notes")
        flagged, restored, _passed = self.evaluate(
            "  - path: var/notes.md\n    root: workspace\n"
            "    presence: non-empty\n    restore:\n"
            "      class: backup\n      backup: backups/notes.md\n"
            "    owner: fixture-owner\n")
        self.assertEqual(flagged, [])
        self.assertEqual(len(restored), 1)
        with open(os.path.join(self.ws, "var/notes.md")) as fh:
            self.assertEqual(fh.read(), "real notes")
        # A backup that itself fails presence flags, never chains.
        self.write(self.ws, "backups/notes.md", "")
        os.remove(os.path.join(self.ws, "var/notes.md"))
        flagged, restored, _p = self.evaluate(
            "  - path: var/notes.md\n    root: workspace\n"
            "    presence: non-empty\n    restore:\n"
            "      class: backup\n      backup: backups/notes.md\n"
            "    owner: fixture-owner\n")
        self.assertEqual(restored, [])
        self.assertEqual(len(flagged), 1)
        self.assertIn("backup source fails presence", flagged[0])

    def test_generated_restore_and_still_fails(self):
        self.write(self.repo, "tools/rebuild.py",
                   "open('var/out.txt', 'w').write('fresh')\n")
        os.makedirs(os.path.join(self.repo, "var"))
        flagged, restored, _p = self.evaluate(
            "  - path: var/out.txt\n    root: kit-repo\n"
            "    presence: non-empty\n    restore:\n"
            "      class: generated\n      generator:\n"
            "        argv:\n          - python3\n"
            "          - tools/rebuild.py\n        root: kit-repo\n"
            "    owner: fixture-owner\n")
        self.assertEqual(flagged, [])
        self.assertEqual(len(restored), 1)
        self.write(self.repo, "tools/rebuild.py",
                   "open('var/out.txt', 'w').write('')\n")
        os.remove(os.path.join(self.repo, "var/out.txt"))
        flagged, restored, _p = self.evaluate(
            "  - path: var/out.txt\n    root: kit-repo\n"
            "    presence: non-empty\n    restore:\n"
            "      class: generated\n      generator:\n"
            "        argv:\n          - python3\n"
            "          - tools/rebuild.py\n        root: kit-repo\n"
            "    owner: fixture-owner\n")
        self.assertEqual(restored, [])
        self.assertTrue(any("still fails" in f for f in flagged))

    def test_tracked_restore_from_git_head(self):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME=self.tmp)
        target = self.write(self.repo, "spec/keep.md", "committed bytes")
        for args in (["git", "init", "-q"],
                     ["git", "-c", "user.email=a@b.c", "-c",
                      "user.name=fixture", "add", "spec/keep.md"],
                     ["git", "-c", "user.email=a@b.c", "-c",
                      "user.name=fixture", "commit", "-qm", "seed"]):
            subprocess.run(args, cwd=self.repo, env=env, check=True)
        os.remove(target)
        flagged, restored, _p = self.evaluate(
            "  - path: spec/keep.md\n    root: kit-repo\n"
            "    presence: non-empty\n    restore:\n"
            "      class: tracked\n    owner: fixture-owner\n")
        self.assertEqual(flagged, [])
        self.assertEqual(len(restored), 1)
        with open(target) as fh:
            self.assertEqual(fh.read(), "committed bytes")


class GlobCase(Base):
    def test_glob_rules(self):
        self.write(self.ws, "todos/a.md", "x")
        self.write(self.ws, "todos/b.md", "")
        flagged, _r, passed = self.evaluate(
            "  - path: todos/*.md\n    root: workspace\n"
            "    presence: non-empty\n    restore:\n"
            "      class: flag-only\n    owner: fixture-owner\n")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(passed, 0)
        flagged, _r, passed = self.evaluate(
            "  - path: nothing/*.md\n    root: workspace\n"
            "    presence: non-empty\n    optional: true\n"
            "    restore:\n      class: flag-only\n"
            "    owner: fixture-owner\n")
        self.assertEqual((flagged, passed), ([], 1))
        flagged, _r, _p = self.evaluate(
            "  - path: nothing/*.md\n    root: workspace\n"
            "    presence: non-empty\n    restore:\n"
            "      class: flag-only\n    owner: fixture-owner\n")
        self.assertTrue(any("glob matched nothing" in f for f in flagged))


class RunCase(Base):
    def _setup(self, files_yaml):
        mpath = self.write(self.tmp, "manifest.yaml",
                           manifest_text(files_yaml, self.roots))
        bpath = self.write(self.tmp, "boot_id", "boot-1\n")
        return mpath, bpath

    def test_report_discipline(self):
        mpath, bpath = self._setup(
            "  - path: gone.txt\n    root: workspace\n"
            "    presence: exists\n    restore:\n"
            "      class: flag-only\n    owner: fixture-owner\n")
        code, report = reg.run(mpath, bpath, at="T1")
        self.assertEqual(code, 0)
        self.assertIn("FLAGGED", report)
        code, report = reg.run(mpath, bpath, at="T2")
        self.assertIsNone(report)
        self.write(self.tmp, "boot_id", "boot-2\n")
        code, report = reg.run(mpath, bpath, at="T3")
        self.assertIn("boot=changed", report)
        code, report = reg.run(mpath, bpath, report_always=True, at="T4")
        self.assertIn("FLAGGED", report)

    def test_clean_pass_is_silent(self):
        self.write(self.ws, "ok.txt", "x")
        mpath, bpath = self._setup(
            "  - path: ok.txt\n    root: workspace\n"
            "    presence: non-empty\n    restore:\n"
            "      class: flag-only\n    owner: fixture-owner\n")
        code, report = reg.run(mpath, bpath, at="T1")
        self.assertEqual((code, report), (0, None))

    def test_loud_failures(self):
        _m, bpath = self._setup("")
        code, report = reg.run(os.path.join(self.tmp, "absent.yaml"),
                               bpath, at="T1")
        self.assertEqual(code, 3)
        mpath, _b = self._setup("")
        code, report = reg.run(mpath, os.path.join(self.tmp, "noboot"),
                               at="T1")
        self.assertEqual(code, 3)
        self.assertIn("boot-id source unreadable", report)


class StagedWriteCase(Base):
    """The staged write delegates to the platform writer
    (contract 15) via the paths spine; standalone, the same
    protocol runs inline. Behavior pinned on both paths:
    exact bytes, the standing file's mode carried, parent
    dirs created, and a failed write leaves the original
    byte-identical with no staging litter."""

    def test_writer_is_reachable_in_tree(self):
        self.assertIsNotNone(reg._load_writer())

    def test_delegated_write_bytes_mode_and_parents(self):
        target = self.write(self.ws, "var/keep.bin", b"old")
        os.chmod(target, 0o640)
        reg._staged_write(target, b"new-bytes")
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"new-bytes")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o640)
        deep = os.path.join(self.ws, "a", "b", "fresh.bin")
        reg._staged_write(deep, b"fresh")
        with open(deep, "rb") as fh:
            self.assertEqual(fh.read(), b"fresh")
        litter = [n for n in os.listdir(os.path.dirname(target))
                  if "sched-tmp" in n or n.endswith(".tmp-registry")]
        self.assertEqual(litter, [])

    def test_save_state_rides_the_staged_write(self):
        reg.save_state({"boot_id": "b1", "signature": "s"})
        with open(reg.STATE, encoding="utf-8") as fh:
            self.assertEqual(
                fh.read(),
                '{\n "boot_id": "b1",\n "signature": "s"\n}')
        self.assertEqual(reg.load_state(),
                         {"boot_id": "b1", "signature": "s"})

    def test_standalone_fallback_writes(self):
        missing = os.path.join(self.tmp, "no-writer.py")
        with mock.patch.object(reg.paths, "PLATFORM_WRITER", missing):
            self.assertIsNone(reg._load_writer())
            target = os.path.join(self.ws, "var", "fb.bin")
            reg._staged_write(target, b"fallback-bytes")
            reg.save_state({"boot_id": "b2"})
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"fallback-bytes")
        self.assertEqual(reg.load_state(), {"boot_id": "b2"})

    def test_torn_write_leaves_original_and_no_litter(self):
        target = self.write(self.ws, "var/keep.bin", b"standing")
        missing = os.path.join(self.tmp, "no-writer.py")
        with mock.patch.object(reg.paths, "PLATFORM_WRITER", missing), \
                mock.patch.object(reg.os, "replace",
                                  side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                reg._staged_write(target, b"torn")
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"standing")
        self.assertEqual(os.listdir(os.path.dirname(target)),
                         ["keep.bin"])

    def test_delegated_failure_leaves_original(self):
        blocker = self.write(self.ws, "blocker", b"standing")
        target = os.path.join(blocker, "state.json")
        with self.assertRaises(OSError):
            reg._staged_write(target, b"torn")
        with open(blocker, "rb") as fh:
            self.assertEqual(fh.read(), b"standing")


if __name__ == "__main__":
    unittest.main()
