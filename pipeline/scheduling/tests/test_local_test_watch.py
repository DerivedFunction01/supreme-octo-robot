import os
import tempfile
import unittest

from ops.watches import local_test_watch as watch

WS = "ws"
REPO = "ws/programme-b-wt-addressunit"


def classify(argv, cwd=REPO):
    return watch.classify(argv, cwd, WS)


class MatcherCase(unittest.TestCase):
    def test_acceptance_specimen_unfiltered_vitest_flags(self):
        # The live specimen: one file, NO name filter.
        finding = classify(["node", "opt/bin/npx", "vitest", "run",
                            "packages/services/src/booking-e2.test.ts",
                            "--pool=threads"])
        self.assertIsNotNone(finding)
        self.assertEqual(finding["runner"], "vitest")

    def test_filtered_single_file_vitest_is_exempt(self):
        self.assertIsNone(classify(
            ["npm", "exec", "vitest", "run",
             "packages/services/src/booking-e2.test.ts",
             "--pool=threads", "-t", "finds by email first"]))

    def test_three_file_suite_flags(self):
        self.assertIsNotNone(classify(
            ["pnpm", "vitest", "run",
             "packages/config/src/config.test.ts",
             "packages/services/src/customer-auth.test.ts",
             "packages/services/src/customer-sign-in.test.ts",
             "--pool=threads"]))

    def test_single_file_without_filter_flags(self):
        self.assertIsNotNone(classify(
            ["vitest", "run", "src/a.test.ts"]))

    def test_jest_narrow_and_broad(self):
        self.assertIsNone(classify(
            ["jest", "src/a.test.ts", "-t", "one case"]))
        self.assertIsNotNone(classify(["jest"]))

    def test_playwright(self):
        self.assertIsNone(classify(
            ["playwright", "test", "tests/a.spec.ts", "-g", "login"]))
        self.assertIsNotNone(classify(
            ["playwright", "test", "tests/a.spec.ts"]))

    def test_pytest_named_cases_exempt(self):
        self.assertIsNone(classify(
            ["python3", "-m", "pytest",
             "tests/test_a.py::test_one", "tests/test_a.py::test_two"]))
        self.assertIsNone(classify(
            ["pytest", "tests/test_a.py", "-k", "test_one"]))

    def test_pytest_broad_flags(self):
        self.assertIsNotNone(classify(["pytest", "tests/"]))
        self.assertIsNotNone(classify(
            ["pytest"] + ["tests/test_a.py::t%d" % i for i in range(6)]))
        self.assertIsNotNone(classify(
            ["pytest", "tests/test_a.py", "tests/test_b.py", "-k", "x"]))

    def test_check_py_flags(self):
        self.assertIsNotNone(classify(["python3", "check.py"]))
        self.assertIsNotNone(classify(["bash", "check.py", "--all"]))

    def test_package_test_flags(self):
        self.assertIsNotNone(classify(["pnpm", "test"]))
        self.assertIsNotNone(classify(["npm", "run", "test:unit"]))

    def test_non_tests_never_match(self):
        self.assertIsNone(classify(["pnpm", "add", "-Dw",
                                    "@axe-core/playwright@4.10.2"]))
        self.assertIsNone(classify(["pnpm", "biome", "format", "."]))
        self.assertIsNone(classify(["node", "server.js"]))
        self.assertIsNone(classify(["vim", "src/a.test.ts"]))

    def test_outside_workspace_never_matches(self):
        self.assertIsNone(classify(["pytest"], cwd="elsewhere/scratch"))
        self.assertIsNone(classify(["vitest", "run"], cwd="elsewhere/home"))

    def test_npm_exec_wrapped_vitest(self):
        self.assertIsNotNone(classify(
            ["npm", "exec", "vitest", "run", "src/a.test.ts",
             "src/b.test.ts"]))


class EpisodeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = watch.STATE
        watch.STATE = os.path.join(self.tmp, "state.json")
        self.old_disp = watch.DISPOSITIONS
        watch.DISPOSITIONS = os.path.join(self.tmp, "dispositions.json")

    def tearDown(self):
        watch.STATE = self.old
        watch.DISPOSITIONS = self.old_disp

    def procs(self):
        return [(["vitest", "run", "src/a.test.ts"], REPO)]

    def test_first_sighting_reports_then_silent(self):
        code, lines = watch.run("/proc", WS, procs=self.procs(),
                                load="1.0 2.0 3.0", at="T1", live_count=0)
        self.assertEqual((code, len(lines)), (0, 1))
        self.assertIn("LOCAL-TEST vitest", lines[0])
        self.assertIn("load=1.0 2.0 3.0", lines[0])
        code, lines = watch.run("/proc", WS, procs=self.procs(),
                                load="1.0 2.0 3.0", at="T2", live_count=0)
        self.assertEqual((code, lines), (0, []))

    def test_episode_closes_and_reopens(self):
        watch.run("/proc", WS, procs=self.procs(), load="1", at="T1", live_count=0)
        code, lines = watch.run("/proc", WS, procs=[], load="1", at="T2", live_count=0)
        self.assertEqual((code, lines), (0, []))
        code, lines = watch.run("/proc", WS, procs=self.procs(),
                                load="1", at="T3", live_count=0)
        self.assertEqual(len(lines), 1)

    def test_missing_state_reports_live_matches(self):
        self.assertFalse(os.path.exists(watch.STATE))
        _code, lines = watch.run("/proc", WS, procs=self.procs(),
                                 load="1", at="T1", live_count=0)
        self.assertEqual(len(lines), 1)


SCHED = "ws/scheduler"
ROUTES = {"threads": {SCHED: {"chat_id": "chat-x",
                              "label": "scheduler thread"}},
          "service_patterns": ["workbench-viewer/run.py"]}


class StrictMatcherCase(unittest.TestCase):
    def strict(self, argv, cwd=REPO, patterns=()):
        return watch.classify_strict(argv, cwd, WS, patterns)

    def test_exemption_suspended_in_strict_mode(self):
        # The specimen that is exempt in normal mode (one
        # file + name filter) flags when the fleet is live.
        argv = ["npm", "exec", "vitest", "run",
                "packages/services/src/booking-e2.test.ts",
                "--pool=threads", "-t", "finds by email first"]
        self.assertIsNone(classify(argv))
        finding = self.strict(argv)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["kind"], "test")

    def test_dev_server_flags(self):
        finding = self.strict(["python3", "run.py"])
        self.assertEqual((finding["kind"], finding["runner"]),
                         ("server", "run.py"))
        finding = self.strict(["uvicorn", "app:main"])
        self.assertEqual(finding["kind"], "server")
        finding = self.strict(["npm", "run", "dev"])
        self.assertEqual(finding["kind"], "server")

    def test_experiment_script_flags(self):
        finding = self.strict(["python3", "experiments/probe.py"])
        self.assertEqual((finding["kind"], finding["runner"]),
                         ("script", "script:probe.py"))
        finding = self.strict(["node", "tools/sweep.mjs"])
        self.assertEqual(finding["kind"], "script")

    def test_service_pattern_never_flags(self):
        self.assertIsNone(self.strict(
            ["/usr/bin/python3", "/x/workbench-viewer/run.py"],
            patterns=["workbench-viewer/run.py"]))

    def test_service_pattern_matches_resolved_relative_path(self):
        # The runner's seeding mechanic invoked relatively
        # from its own repo root: the raw argv carries no
        # repo segment, so the pattern can only match the
        # resolved path (the refire specimen).
        self.assertIsNone(self.strict(
            ["bash", "sync/make_snapshot_bundle.sh"],
            cwd="ws/colab-runner",
            patterns=["colab-runner/sync/"]))

    def test_service_pattern_resolved_elsewhere_still_flags(self):
        # The same relative shape from another repo resolves
        # outside the pattern's repo segment and still flags.
        finding = self.strict(
            ["bash", "sync/make_snapshot_bundle.sh"],
            cwd="ws/specimen-repo",
            patterns=["colab-runner/sync/"])
        self.assertIsNotNone(finding)
        self.assertEqual(finding["kind"], "script")

    def test_attention_status_transport_never_flags(self):
        # The false positives: a lane's
        # prescribed status posts (00:12:39Z / 00:12:46Z)
        # flagged as local execution while the fleet was
        # up. The status transport is supervision
        # machinery, not a check or code execution.
        argv = ["python3",
                "ws/specimen-repo/pipeline/attention/cli.py",
                "post", "status", "--code", "WORKING",
                "--summary", "lane status"]
        self.assertIsNone(self.strict(
            argv, cwd="ws/specimen-repo"))
        argv[3] = "item"
        self.assertIsNone(self.strict(
            argv, cwd="ws/specimen-repo"))

    def test_attention_cli_other_verbs_still_flag(self):
        # The exemption is the transport verb pair, not
        # the CLI: the same cli.py under another verb pair
        # is an ordinary script execution and flags.
        finding = self.strict(
            ["python3",
             "ws/specimen-repo/pipeline/attention/cli.py",
             "post", "close"],
            cwd="ws/specimen-repo")
        self.assertIsNotNone(finding)
        self.assertEqual(finding["kind"], "script")

    def test_other_packages_cli_post_status_still_flags(self):
        # Identity, not the verb pair alone: another
        # package's cli.py posting "status" is not the
        # attention transport.
        finding = self.strict(
            ["python3", "ws/other-repo/tools/cli.py",
             "post", "status"],
            cwd="ws/other-repo")
        self.assertIsNotNone(finding)
        self.assertEqual(finding["kind"], "script")

    def test_module_and_inline_runs_do_not_flag_as_scripts(self):
        self.assertIsNone(self.strict(["python3", "-c", "print(1)"]))
        self.assertIsNone(self.strict(["python3", "-m", "pip"]))


class StrictCycleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = watch.STATE
        watch.STATE = os.path.join(self.tmp, "state.json")
        self.old_disp = watch.DISPOSITIONS
        watch.DISPOSITIONS = os.path.join(self.tmp, "dispositions.json")
        self.old_ws = watch.WORKSPACE
        self.sent = []

    def tearDown(self):
        watch.STATE = self.old
        watch.DISPOSITIONS = self.old_disp
        watch.WORKSPACE = self.old_ws

    def sender(self, chat_id, text, envelope_id):
        self.sent.append((chat_id, text, envelope_id))
        return True

    def fake_workspace(self):
        """A seeded workspace mirroring the production shapes
        the cross-repo pins exercise: sibling repos carrying
        their ops/ surfaces and named service scripts, so
        identity resolution runs the same path without
        reading the live tree. (The real-tree version of
        these pins failed the venue gate: off the home
        machine the sibling repos do not exist, and the
        identity exemption requires real files. Suites seed
        their own fixtures.)"""
        ws = os.path.join(self.tmp, "ws")
        # _is_infra_path anchors at the module WORKSPACE, so
        # the fake tree must BE the watcher's workspace for
        # the pass (restored in tearDown).
        watch.WORKSPACE = ws
        for rel in (
                "workbench-viewer/ops/doctor.sh",
                "workbench-viewer/server/healthcheck.py",
                "workbench-viewer/server/autorepair.py",
                "workbench-viewer/server/linkprobe.py",
                "workbench-viewer/.venv/bin/python",
                "colab-runner/ops/mirror_transient.py",
                "colab-runner/ui/install-unit.sh",
                "colab-runner/ui/deploy.sh",
                "colab-runner/sync/make_snapshot_bundle.sh",
                "specimen-repo/check.py",
                "scheduler/ops/bridge/bridge_wake.py",
                "specimen-repo/pipeline/scheduling/ops/"
                "bridge/bridge_wake.py",
                "specimen-repo/pipeline/scheduling/ops/"
                "watches/local_test_watch.py"):
            path = os.path.join(ws, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# fixture\n")
        return ws

    def test_first_sighting_warns_and_routes(self):
        procs = [(["python3", "run.py"], SCHED)]
        code, lines = watch.run(
            "/proc", WS, procs=procs, load="1", at="T1",
            live_count=3, routes=ROUTES, sender=self.sender)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("LOCAL-EXEC WARNING", lines[0])
        self.assertIn("kind=server", lines[0])
        self.assertIn("sessions_live=3", lines[0])
        self.assertIn("thread=scheduler thread", lines[0])
        self.assertIn("routed=queued", lines[0])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], "chat-x")
        self.assertTrue(self.sent[0][2].startswith("local-test-watch-"))
        # A continuing episode stays silent and sends nothing.
        code, lines = watch.run(
            "/proc", WS, procs=procs, load="1", at="T2",
            live_count=3, routes=ROUTES, sender=self.sender)
        self.assertEqual((code, lines), (0, []))
        self.assertEqual(len(self.sent), 1)

    def test_unmapped_repo_warns_print_only(self):
        procs = [(["python3", "experiments/probe.py"], REPO)]
        _code, lines = watch.run(
            "/proc", WS, procs=procs, load="1", at="T1",
            live_count=2, routes=ROUTES, sender=self.sender)
        self.assertEqual(len(lines), 1)
        self.assertIn("thread=unmapped", lines[0])
        self.assertIn("routed=print-only", lines[0])
        self.assertEqual(self.sent, [])

    def test_failed_send_still_warns(self):
        def bad_sender(chat_id, text, envelope_id):
            raise RuntimeError("connector down")

        procs = [(["python3", "run.py"], SCHED)]
        code, lines = watch.run(
            "/proc", WS, procs=procs, load="1", at="T1",
            live_count=1, routes=ROUTES, sender=bad_sender)
        self.assertEqual(code, 0)
        self.assertIn("routed=failed", lines[0])

    def test_automation_surface_never_flags_in_strict_mode(self):
        # The scheduler system's own legs run scripts under
        # the repo's ops/ — infrastructure by job argv
        # (absolute) and by relative invocation from the
        # repo root alike (an agent running a leg by hand;
        # the self-flag of this watcher was the false
        # positive this pins). Seeded fake tree in
        # the mega shape — the scheduling package nested at
        # pipeline/scheduling inside its repo — because
        # resolution is by script identity on disk and the
        # identity rule is depth-independent: the mega
        # nesting is exactly what the pre-cure depth-2 rule
        # missed on the venue gate.
        ws = self.fake_workspace()
        sched = os.path.join(
            ws, "specimen-repo", "pipeline", "scheduling")
        for argv in (
                ["python3", sched + "/ops/bridge/bridge_wake.py",
                 "--live"],
                ["python3", "ops/bridge/bridge_wake.py", "--live"],
                ["python3", "ops/watches/local_test_watch.py"]):
            _code, lines = watch.run(
                "/proc", ws,
                procs=[(argv, sched)], load="1", at="T1",
                live_count=3, routes=ROUTES, sender=self.sender)
            self.assertEqual(lines, [], argv)

    def test_relative_ops_shape_outside_the_repo_still_flags(self):
        # The same relative shape from another repo is not
        # the surface: resolution lands outside ops/.
        procs = [(["python3", "ops/bridge_wake.py"], REPO)]
        _code, lines = watch.run(
            "/proc", WS, procs=procs, load="1", at="T1",
            live_count=3, routes=ROUTES, sender=self.sender)
        self.assertEqual(len(lines), 1)
        self.assertIn("kind=script", lines[0])

    def test_cross_repo_infrastructure_never_flags(self):
        # The scheduler's legs run other repos' automation
        # surfaces: another repo's ops/ script by absolute
        # path from the scheduler cwd (doctor.sh), another
        # repo's ops/ script by relative path from its own
        # repo root (mirror_transient.py), and a repo's
        # healthcheck surface outside ops/ (server/
        # healthcheck.py) — the false-positive class.
        # Seeded fake tree, resolved by identity.
        ws = self.fake_workspace()
        sched = os.path.join(ws, "scheduler")
        wbv = os.path.join(ws, "workbench-viewer")
        colab = os.path.join(ws, "colab-runner")
        for argv, cwd in (
                (["bash", wbv + "/ops/doctor.sh"], sched),
                (["python3", "ops/mirror_transient.py",
                  "restore"], colab),
                (["python3", colab + "/ops/mirror_transient.py",
                  "restore"], sched),
                ([wbv + "/.venv/bin/python",
                  wbv + "/server/healthcheck.py"], sched),
                # The viewer's watchdog execs its repair
                # surface: the exec'd argv shows only
                # server/autorepair.py from the scheduler
                # cwd.
                ([wbv + "/.venv/bin/python",
                  wbv + "/server/autorepair.py"], sched),
                # The healthcheck chain's link probe, same
                # server/ machinery family.
                ([wbv + "/.venv/bin/python",
                  wbv + "/server/linkprobe.py"], sched),
                # The panel's venue machinery: the systemd
                # unit installer with the absolute script
                # path from the ui cwd, the deploy script
                # likewise,
                # and the installer invoked relatively from
                # the repo root.
                (["bash", colab + "/ui/install-unit.sh"],
                 colab + "/ui"),
                (["bash", colab + "/ui/deploy.sh"],
                 colab + "/ui"),
                (["bash", "ui/install-unit.sh"], colab)):
            _code, lines = watch.run(
                "/proc", ws, procs=[(argv, cwd)],
                load="1", at="T1", live_count=3,
                routes=ROUTES, sender=self.sender)
            self.assertEqual(lines, [], argv)

    def test_cross_repo_task_script_still_flags(self):
        # The negative control: another repo's gate script
        # is task work, not infrastructure — the cross-repo
        # exemption covers ops//bin/ and the named health
        # surfaces only.
        ws = self.fake_workspace()
        spec_repo = os.path.join(ws, "specimen-repo")
        procs = [(["python3", spec_repo + "/check.py"], spec_repo)]
        _code, lines = watch.run(
            "/proc", ws, procs=procs, load="1", at="T1",
            live_count=3, routes=ROUTES, sender=self.sender)
        self.assertEqual(len(lines), 1)
        self.assertIn("kind=test", lines[0])

    def test_snapshot_bundle_relative_shape_never_flags(self):
        # Run-level pin of the 14:45 EST refire: the seeding
        # mechanic invoked relatively from the colab-runner
        # cwd, with the live routes pattern in force.
        ws = self.fake_workspace()
        colab = os.path.join(ws, "colab-runner")
        routes = dict(ROUTES)
        routes["service_patterns"] = ["colab-runner/sync/"]
        procs = [(["bash", "sync/make_snapshot_bundle.sh"],
                  colab)]
        _code, lines = watch.run(
            "/proc", ws, procs=procs, load="1", at="T1",
            live_count=3, routes=routes, sender=self.sender)
        self.assertEqual(lines, [])


class DerivedLocationCase(unittest.TestCase):
    """A sandbox process whose cwd link reads empty from
    the server's context is located from its argv."""

    def test_absolute_script_argv_locates_without_cwd(self):
        finding = watch.classify_strict(
            ["python3", "ws/specimen-repo/tools/probe.py"], None, WS)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["kind"], "script")
        self.assertTrue(finding["derived"])
        self.assertEqual(finding["cwd"], "ws/specimen-repo/tools")

    def test_relative_argv_without_cwd_stays_unlocated(self):
        self.assertIsNone(watch.classify_strict(
            ["python3", "probe.py"], None, WS))

    def test_normal_mode_also_derives(self):
        finding = watch.classify(
            ["python3", "ws/specimen-repo/check.py"], None, WS)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["runner"], "check.py")
        self.assertTrue(finding["derived"])


ROUTES_MAIN = {"threads": {SCHED: {"chat_id": "chat-x",
                                   "label": "scheduler thread"}},
               "service_patterns": [],
               "main": {"chat_id": "chat-main", "label": "main"}}


class DefectRoutingCase(unittest.TestCase):
    """The enforcement cure: a first sighting raises a
    defect item, copies main, and opens a disposition
    entry; a recorded disposition is the only clear."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = watch.STATE
        watch.STATE = os.path.join(self.tmp, "state.json")
        self.old_disp = watch.DISPOSITIONS
        self.disp_path = os.path.join(self.tmp, "dispositions.json")
        watch.DISPOSITIONS = self.disp_path
        self.sent = []
        self.items = []

    def tearDown(self):
        watch.STATE = self.old
        watch.DISPOSITIONS = self.old_disp

    def sender(self, chat_id, text, envelope_id):
        self.sent.append((chat_id, text, envelope_id))
        return True

    def poster(self, payload, at):
        self.items.append((payload, at))
        return True

    def cycle(self, procs, live_count=3, routes=ROUTES_MAIN,
              poster=None, at="2026-11-18T10:00:00Z"):
        return watch.run(
            "/proc", WS, procs=procs, load="1.5 2.0 3.0", at=at,
            live_count=live_count, routes=routes,
            sender=self.sender,
            item_poster=self.poster if poster is None else poster)

    def procs(self):
        return [(["python3", "run.py"], SCHED)]

    def sig(self):
        return watch.signature(
            {"cwd": SCHED, "argv": ["python3", "run.py"]})

    def test_defect_item_once_per_episode_with_fields(self):
        code, lines = self.cycle(self.procs())
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("item=posted", lines[0])
        self.assertIn("sig=" + self.sig(), lines[0])
        self.assertEqual(len(self.items), 1)
        payload, at = self.items[0]
        self.assertEqual(payload["kind"], "defect")
        self.assertEqual(payload["handle"], "main")
        self.assertEqual(payload["source_ref"],
                         "local-test-watch-" + self.sig())
        self.assertFalse(payload["clears_at_source"])
        self.assertEqual(payload["repo"], "scheduler")
        self.assertEqual(payload["routing"]["workhorse"], "scheduler")
        self.assertEqual(payload["routing"]["thread"],
                         "scheduler thread")
        title = payload["title"]
        for needle in ("scheduler", "server", "run.py",
                       "mode=strict", "sessions_live=3",
                       "load=1.5 2.0 3.0",
                       "first-seen=2026-11-18T10:00:00Z"):
            self.assertIn(needle, title)
        # The disposition entry is born open, with the
        # finding and every routing outcome.
        record = watch.defects.load_dispositions(self.disp_path)
        entry = record["dispositions"][self.sig()]
        self.assertEqual(entry["status"], "open")
        self.assertEqual(entry["finding"]["runner"], "run.py")
        self.assertEqual(entry["routing"],
                         {"thread": "queued", "main": "queued",
                          "item": "posted"})
        # A continuing episode raises nothing new.
        code, lines = self.cycle(self.procs(), at="2026-11-18T10:01:00Z")
        self.assertEqual((code, lines), (0, []))
        self.assertEqual(len(self.items), 1)

    def test_main_copy_routed_and_shown_when_unconfigured(self):
        _code, lines = self.cycle(self.procs())
        self.assertIn("main=queued", lines[0])
        main_sends = [s for s in self.sent if s[0] == "chat-main"]
        self.assertEqual(len(main_sends), 1)
        self.assertEqual(main_sends[0][2],
                         "local-test-watch-main-" + self.sig())
        # No main key in the routes: the copy degrades to
        # print-only, named on the line.
        self.tearDown()
        self.setUp()
        _code, lines = self.cycle(self.procs(), routes=ROUTES)
        self.assertIn("main=print-only", lines[0])
        self.assertEqual(
            [s for s in self.sent if s[0] == "chat-main"], [])

    def test_normal_mode_also_raises_item_and_main_copy(self):
        procs = [(["vitest", "run", "src/a.test.ts"], REPO)]
        _code, lines = self.cycle(procs, live_count=0)
        self.assertEqual(len(lines), 1)
        self.assertIn("LOCAL-TEST vitest", lines[0])
        self.assertIn("item=posted", lines[0])
        self.assertIn("main=queued", lines[0])
        payload, _at = self.items[0]
        self.assertIn("mode=normal", payload["title"])
        self.assertIn("sessions_live=0", payload["title"])

    def test_disposition_with_reason_suppresses_reraise(self):
        self.cycle(self.procs())
        self.cycle([], at="2026-11-18T10:05:00Z")  # episode closes
        ok, _detail = watch.defects.record_disposition(
            self.disp_path, self.sig(),
            "venue adapter fixture smoke; the script is the "
            "runner's own seeding mechanic", "lane-seat",
            "2026-11-18T10:06:00Z")
        self.assertTrue(ok)
        self.items.clear()
        self.sent.clear()
        _code, lines = self.cycle(
            self.procs(), at="2026-11-18T10:07:00Z")
        self.assertEqual(len(lines), 1)
        self.assertIn("LOCAL-EXEC EXPLAINED", lines[0])
        self.assertIn("disposition=closed-legitimate-tooling",
                      lines[0])
        self.assertEqual(self.items, [])
        self.assertEqual(self.sent, [])

    def test_undispositioned_reappearance_reraises(self):
        self.cycle(self.procs())
        self.cycle([], at="2026-11-18T10:05:00Z")
        self.items.clear()
        _code, lines = self.cycle(
            self.procs(), at="2026-11-18T10:07:00Z")
        self.assertEqual(len(lines), 1)
        self.assertIn("LOCAL-EXEC WARNING", lines[0])
        self.assertIn("item=posted", lines[0])
        self.assertEqual(len(self.items), 1)
        record = watch.defects.load_dispositions(self.disp_path)
        entry = record["dispositions"][self.sig()]
        self.assertEqual(entry["status"], "open")
        self.assertEqual(entry["last_raised_at"],
                         "2026-11-18T10:07:00Z")

    def test_failed_item_send_still_prints_line(self):
        def bad_poster(payload, at):
            raise RuntimeError("store unavailable")

        code, lines = self.cycle(self.procs(), poster=bad_poster)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("item=failed", lines[0])
        # The open entry records the failed outcome too.
        record = watch.defects.load_dispositions(self.disp_path)
        entry = record["dispositions"][self.sig()]
        self.assertEqual(entry["routing"]["item"], "failed")

    def test_unconfigured_item_poster_is_named_on_line(self):
        _code, lines = watch.run(
            "/proc", WS, procs=self.procs(), load="1",
            at="2026-11-18T10:00:00Z", live_count=3,
            routes=ROUTES_MAIN, sender=self.sender,
            item_poster=None)
        self.assertIn("item=unconfigured", lines[0])

    def test_record_disposition_refusals(self):
        ok, _ = watch.defects.record_disposition(
            self.disp_path, "deadbeefdeadbeef", "reason", "actor",
            "2026-11-18T10:00:00Z")
        self.assertFalse(ok)  # unknown signature
        self.cycle(self.procs())
        ok, _ = watch.defects.record_disposition(
            self.disp_path, self.sig(), "  ", "actor",
            "2026-11-18T10:01:00Z")
        self.assertFalse(ok)  # empty reason records nothing
        ok, _ = watch.defects.record_disposition(
            self.disp_path, self.sig(), "reason", "",
            "2026-11-18T10:01:00Z")
        self.assertFalse(ok)  # empty actor records nothing


class DefectStorePosterCase(unittest.TestCase):
    """The production poster seam over a scratch attention
    store: ingest validation, dedupe, and the disposition
    verb's resolve — never the live store."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmp, "attention.json")
        self.old_env = os.environ.get(
            watch.defects.ATTENTION_STATE_ENV)
        os.environ[watch.defects.ATTENTION_STATE_ENV] = \
            self.store_path
        # Seed the scratch store with the one registered
        # handler the poster posts under.
        attstore, _ingest = watch.defects._load_attention(watch.REPO)
        store = attstore.AttentionStateStore(self.store_path)
        state = store.load_state()
        state["handlers"] = [{"handle": "main"}]
        store.save_state(state)

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop(watch.defects.ATTENTION_STATE_ENV, None)
        else:
            os.environ[watch.defects.ATTENTION_STATE_ENV] = \
                self.old_env

    def payload(self):
        finding = {"kind": "server", "runner": "run.py",
                   "cwd": SCHED, "argv": ["python3", "run.py"]}
        return watch.defects.build_item_payload(
            "sig123", finding, "scheduler", "scheduler thread",
            "strict", 3, "1.0", "2026-11-18T10:00:00Z")

    def load_items(self):
        attstore, _ingest = watch.defects._load_attention(watch.REPO)
        store = attstore.AttentionStateStore(self.store_path)
        return store.load_state()["items"]

    def test_poster_posts_once_and_resolver_resolves(self):
        poster = watch.defects.default_item_poster(watch.REPO)
        self.assertIsNotNone(poster)
        self.assertTrue(poster(self.payload(),
                               "2026-11-18T10:00:00Z"))
        self.assertTrue(poster(self.payload(),
                               "2026-11-18T10:01:00Z"))
        items = [i for i in self.load_items()
                 if i["source_ref"] == "local-test-watch-sig123"]
        self.assertEqual(len(items), 1)  # ingest dedupe
        self.assertEqual(items[0]["kind"], "defect")
        self.assertEqual(items[0]["triage"], "open")
        resolver = watch.defects.default_item_resolver(watch.REPO)
        self.assertTrue(resolver("sig123"))
        items = [i for i in self.load_items()
                 if i["source_ref"] == "local-test-watch-sig123"]
        self.assertEqual(items[0]["triage"], "done")
        self.assertFalse(resolver("nosuchsig"))


if __name__ == "__main__":
    unittest.main()
