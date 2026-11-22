import unittest


class StandaloneLoadCase(unittest.TestCase):
    def test_ledger_loads_in_a_clean_interpreter(self):
        # The job runs the watch as a bare script; the
        # suite's own package context masked a loader
        # failure there once (2026-11-22: the ledger's
        # util load died on util's relative import and
        # the watch job failed at startup while the
        # package gate stood green). This pin loads the
        # ledger exactly as the job's context does — a
        # clean interpreter, a flat spec load by path.
        import subprocess
        import sys
        from pathlib import Path

        ledger_path = (
            Path(__file__).resolve().parent.parent
            / "ops" / "watches" / "local_test_ledger.py")
        code = (
            "import importlib.util, sys;"
            "spec = importlib.util.spec_from_file_location("
            "'local_test_ledger', sys.argv[1]);"
            "m = importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(m);"
            "assert m._epoch('2026-11-22T00:00:00Z') is not None;"
            "print('standalone-load-ok')")
        proc = subprocess.run(
            [sys.executable, "-c", code, str(ledger_path)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("standalone-load-ok", proc.stdout)




if __name__ == "__main__":
    unittest.main()
