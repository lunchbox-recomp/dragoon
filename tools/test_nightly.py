from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import known_issues
import nightly
import nightly_report
import power
import route_compiles
import state_goldens
from frame_pair import side_by_side, write_png
from framediff import Image, read_png
from nightly_fakes import AC, BATTERY, FakePmset, FakeTree, booting, fake_frame, fake_image
from nightly_report import FAIL, NOT_RUN, PASS, SKIPPED_BATTERY, Check, Problem
from testengine import ENGINE_SHA, built_sha, set_plan
from testutil import temp_dir, write_file


class PowerTest(unittest.TestCase):
    def test_it_reads_the_source_off_the_first_line(self) -> None:
        self.assertEqual(power.source(AC), "AC Power")
        self.assertEqual(power.source(BATTERY), "Battery Power")
        with self.assertRaises(ValueError):
            power.source("nothing to see\n")

    def test_battery_raises_and_ac_returns(self) -> None:
        pmset = FakePmset(self)
        power.require_ac(pmset.command())
        pmset.now(BATTERY)
        with self.assertRaisesRegex(power.OnBattery, "Battery Power"):
            power.require_ac(pmset.command())


class FramesStepTest(unittest.TestCase):
    def test_matching_frames_and_state_pass_and_leave_no_dump(self) -> None:
        tree = FakeTree(self)
        checks = tree.by_id(tree.play("frames", tree.context()))
        self.assertEqual({c.status for c in checks.values()}, {PASS}, checks)
        self.assertEqual(sorted(checks), ["frames 16:9 menu", "frames 16:9 title", "frames 4:3 menu",
                                          "frames 4:3 title", "state 16:9 menu", "state 16:9 title",
                                          "state 4:3 menu", "state 4:3 title"])
        self.assertFalse((tree.report / "dumps").exists())
        self.assertEqual(tree.runs_left(), [])

    def test_a_changed_frame_keeps_its_dump_and_no_other(self) -> None:
        tree = FakeTree(self)
        set_plan(tree.root, tint={"120": 9})
        checks = tree.by_id(tree.play("frames", tree.context(routes=["title"])))
        frames = checks["frames 4:3 title"]
        self.assertEqual((frames.status, frames.kind), (FAIL, "drew differently"))
        self.assertEqual([p.where for p in frames.problems], ["frame 120"])
        self.assertEqual(frames.problems[0].dump, "dumps/4x3/title/frame_00120.png")
        self.assertEqual(checks["state 4:3 title"].status, PASS)
        kept = sorted(p.relative_to(tree.report).as_posix() for p in (tree.report / "dumps").rglob("*.png"))
        self.assertEqual(kept, ["dumps/16x9/title/frame_00120.png", "dumps/4x3/title/frame_00120.png"])
        self.assertEqual((tree.report / kept[0]).read_bytes(), fake_frame(120, 9))
        self.assertEqual(tree.runs_left(), [])

    def golden_build(self, tree: FakeTree) -> None:
        (tree.root / "build" / "nightly" / "golden-build").mkdir()
        write_file(tree.root / "build" / "nightly" / "golden-build", "dragoon", "a game")

    def test_a_golden_the_golden_build_draws_again_goes_beside_the_new_frame(self) -> None:
        tree = FakeTree(self)
        self.golden_build(tree)
        set_plan(tree.root, tint={"120": 9})
        checks = tree.by_id(tree.play("frames", tree.context(routes=["title"])))
        problem = checks["frames 4:3 title"].problems[0]
        self.assertEqual(problem.dump, "dumps/4x3/title/frame_00120-golden-left.png")
        pair = read_png(tree.report / problem.dump)
        self.assertEqual(pair, side_by_side(fake_image(120), fake_image(120, 9)))
        self.assertTrue((tree.report / "dumps/4x3/title/frame_00120.png").is_file())
        self.assertEqual(tree.games, 4)  # each aspect's route, and the golden build once for each
        self.assertEqual(tree.runs_left(), [])

    def test_no_pair_when_the_golden_build_draws_something_else(self) -> None:
        tree = FakeTree(self)
        self.golden_build(tree)
        set_plan(tree.root, tint={"120": 9}, bin_tint={"120": 4})
        checks = tree.by_id(tree.play("frames", tree.context(routes=["title"])))
        self.assertEqual(checks["frames 4:3 title"].problems[0].dump, "dumps/4x3/title/frame_00120.png")
        self.assertEqual(list((tree.report / "dumps").rglob("*golden-left.png")), [])
        self.assertEqual(tree.runs_left(), [])

    def test_a_different_screen_plays_differently_and_keeps_that_checkpoint(self) -> None:
        tree = FakeTree(self)
        set_plan(tree.root, events=[{"frame": 100, "do": [["screen", 5]]}])
        checks = tree.by_id(tree.play("frames", tree.context(routes=["title"])))
        state = checks["state 4:3 title"]
        self.assertEqual((state.status, state.kind), (FAIL, "played differently"))
        self.assertEqual([(p.where, p.what) for p in state.problems],
                         [("frame 120 scene.minor", "5 != golden 38")])
        self.assertEqual(state.problems[0].dump, "dumps/4x3/title/frame_00120.png")
        self.assertEqual(checks["frames 4:3 title"].status, PASS)  # it drew the same

    def test_a_missing_state_golden_fails_the_state_check_only(self) -> None:
        tree = FakeTree(self)
        (tree.root / "tests" / "hashes" / "state" / "menu.txt").unlink()
        checks = tree.by_id(tree.play("frames", tree.context(routes=["menu"])))
        self.assertEqual(checks["state 4:3 menu"].status, FAIL)
        self.assertIn("no state golden", checks["state 4:3 menu"].detail)
        self.assertEqual(checks["frames 4:3 menu"].status, PASS)

    def test_a_changed_hash_is_named_in_full(self) -> None:
        tree = FakeTree(self)
        set_plan(tree.root, tint={"120": 9})
        checks = tree.by_id(tree.play("frames", tree.context(routes=["title"])))
        new, golden = (hashlib.sha1(fake_frame(120, b)).hexdigest() for b in (9, 0))
        self.assertEqual(checks["frames 4:3 title"].problems[0].what, f"{new} != golden {golden}")

    def test_16x9_plays_against_the_same_state_golden(self) -> None:
        tree = FakeTree(self)
        set_plan(tree.root, events=[{"frame": 100, "do": [["screen", 5]]}])
        checks = tree.by_id(tree.play("frames", tree.context(routes=["title"])))
        self.assertEqual([(p.where, p.what) for p in checks["state 16:9 title"].problems],
                         [("frame 120 scene.minor", "5 != golden 38")])


class KnownIssueTest(unittest.TestCase):
    def play(self, known: str, **plan) -> dict[str, Check]:
        tree = FakeTree(self)
        tree.known(f"# a comment\n{known}\n")
        set_plan(tree.root, **plan)
        return tree.by_id(tree.play("frames", tree.context(routes=["title"])))

    def check(self, known: str, screen_at: int = 100, screen: int = 5) -> Check:
        """The 16:9 state check on the title route, whose screen turns SCREEN at frame SCREEN_AT."""
        return self.play(known, events=[{"frame": screen_at, "do": [["screen", screen]]}])["state 16:9 title"]

    def test_the_known_values_at_the_known_checkpoint_are_the_known_issue(self) -> None:
        checks = self.play("state title 16:9 120 scene.minor=5 the screen is 5 at 16:9",
                           events=[{"frame": 100, "do": [["screen", 5]]}])
        self.assertEqual((checks["state 16:9 title"].status, checks["state 16:9 title"].known),
                         (FAIL, "the screen is 5 at 16:9"))
        self.assertIsNone(checks["state 4:3 title"].known)  # the other aspect fails as any check does
        self.assertEqual([c.id for c in nightly_report.failing(list(checks.values()))], ["state 4:3 title"])

    def test_another_value_at_the_known_checkpoint_fails(self) -> None:
        c = self.check("state title 16:9 120 scene.minor=5 the screen is 5", screen=6)
        self.assertIsNone(c.known)
        self.assertIn("which isn't the known issue at 120", c.detail)

    def test_a_scene_change_in_a_field_the_issue_doesnt_name_fails(self) -> None:
        c = self.check("state title 16:9 120 players.count=0 player1.kind=0 only the riders are off")
        self.assertEqual((c.status, c.known, [p.where for p in c.problems]),
                         (FAIL, None, ["frame 120 scene.minor"]))

    def test_failing_first_at_an_earlier_checkpoint_fails(self) -> None:
        c = self.check("state title 16:9 120 scene.minor=5 the screen is 5 from 120", screen_at=30)
        self.assertEqual((c.known, [p.where for p in c.problems]),
                         (None, ["frame 60 scene.minor", "frame 120 scene.minor"]))

    def test_the_known_values_in_a_run_that_ended_early_fail(self) -> None:
        checks = self.play("state title 16:9 120 scene.minor=5 the screen is 5",
                           events=[{"frame": 100, "do": [["screen", 5]]}, {"frame": 150, "do": [["exit"]]}])
        c = checks["state 16:9 title"]
        self.assertIsNone(c.known)
        self.assertIn("the run ended on", c.problems[-1].what)

    def test_one_that_passes_is_marked_so_its_line_can_go(self) -> None:
        checks = self.play("state title 4:3 120 scene.minor=5 the screen is 5")
        self.assertEqual((checks["state 4:3 title"].status, checks["state 4:3 title"].known),
                         (PASS, "the screen is 5"))

    def test_the_repos_known_issues_read(self) -> None:
        issues = known_issues.read(nightly.ROOT / "tests" / "hashes")
        c2 = issues["state 16:9 air-ride-courses-2"]
        self.assertEqual((c2.checkpoint, len(c2.values), c2.values["player1.speed"]), (19400, 16, "26.0290222"))

    def test_a_bad_line_is_refused(self) -> None:
        for bad in ("state title 4:3 120 a bug with no values\n", "frames title 4:3 120 scene.minor=5 bug\n"):
            with self.subTest(bad):
                with self.assertRaisesRegex(ValueError, "line 1"):
                    known_issues.parse(bad)


class GoldenBuildTest(unittest.TestCase):
    def tree(self) -> FakeTree:
        tree = FakeTree(self)
        write_file(tree.root / "build", "dragoon", "the game")
        return tree

    def golden(self, tree: FakeTree) -> Path:
        return tree.root / "build" / "nightly" / "golden-build"

    def test_a_frames_step_that_passed_every_route_copies_the_game_and_its_commits(self) -> None:
        tree = self.tree()
        tree.play("frames", tree.context())
        self.assertEqual((self.golden(tree) / "dragoon").read_text(), "the game")
        self.assertEqual((self.golden(tree) / "commit.txt").read_text(), f"dragoon ?\nengine {built_sha(1)}\n")

    def test_only_some_routes_copy_nothing(self) -> None:
        tree = self.tree()
        tree.play("frames", tree.context(routes=["title", "menu"]))
        self.assertFalse(self.golden(tree).exists())

    def test_a_failure_copies_nothing_but_a_known_issue_does(self) -> None:
        tree = self.tree()
        set_plan(tree.root, tint={"120": 9})
        tree.play("frames", tree.context())
        self.assertFalse(self.golden(tree).exists())
        set_plan(tree.root, events=[{"frame": 100, "do": [["screen", 5]]}])
        tree.known("".join(f"state {r} {a} 120 scene.minor=5 bug\n" for r in ("menu", "title") for a in ("4:3", "16:9")))
        tree.play("frames", tree.context())
        self.assertTrue((self.golden(tree) / "dragoon").is_file())


class StateCompareTest(unittest.TestCase):
    def test_a_golden_reads_back_as_it_was_written(self) -> None:
        states = {60: booting(60), 4200: (4203, {"scene.minor": "18", "player1.x": "294.294342"})}
        self.assertEqual(state_goldens.parse_golden(state_goldens.format_golden("r", states)), states)

    def test_compare_names_each_field_and_frame(self) -> None:
        golden = {60: (60, {"scene.minor": "0", "players.count": "1"}), 120: (120, {"scene.minor": "2"}),
                  180: (181, {"scene.minor": "2"})}
        got = {60: (60, {"scene.minor": "0", "players.count": "4"}), 180: (182, {"scene.minor": "2"})}
        self.assertEqual(state_goldens.compare(golden, got), [
            (60, "players.count", "4 != golden 1"), (120, "frame", "not reached"),
            (180, "frame", "read at 182, golden at 181")])
        self.assertEqual(state_goldens.compare(golden, dict(golden)), [])


class BatteryTest(unittest.TestCase):
    def test_battery_before_a_game_skips_the_step_and_the_rest(self) -> None:
        tree = FakeTree(self)
        pmset = FakePmset(self)

        def before() -> None:
            power.require_ac(pmset.command())
            pmset.now(BATTERY)  # the cord comes out once the first game has started

        ctx = tree.context(before=before)
        checks, steps, stopped = nightly.run_steps(["frames", "audio"], tree.report,
                                                   lambda: power.require_ac(pmset.command()),
                                                   lambda step: nightly.play_step(step, ctx))
        self.assertEqual(tree.games, 1)  # one game played, and the second never started
        self.assertEqual([(c.id, c.status) for c in checks], [
            ("frames 4:3 title", PASS), ("state 4:3 title", PASS), ("frames", SKIPPED_BATTERY),
            ("audio", NOT_RUN)])
        self.assertIn("Battery Power", stopped)
        self.assertEqual(tree.runs_left(), [])
        code = nightly.finish(tree.report, checks, steps, stopped, 0.0, [1.0, 1.0], None, tree.root, lambda text: None)
        self.assertEqual(code, 2)
        summary = (tree.report / "summary.txt").read_text()
        self.assertIn("frames: skipped-battery", summary)
        self.assertIn("audio: not-run", summary)
        self.assertEqual(json.loads((tree.report / "report.json").read_text())["result"], "stopped on battery")

    def test_battery_at_the_start_plays_nothing(self) -> None:
        tree = FakeTree(self)
        pmset = FakePmset(self, BATTERY)
        checks, _, stopped = nightly.run_steps(["frames"], tree.report, lambda: power.require_ac(pmset.command()),
                                               lambda step: self.fail("a step ran on battery"))
        self.assertEqual([(c.id, c.status) for c in checks], [("frames", SKIPPED_BATTERY)])
        self.assertTrue(stopped)

    def test_a_pmset_that_cant_say_stops_the_run_with_a_report(self) -> None:
        def unreadable() -> None:
            raise ValueError("pmset -g batt: no power source on its first line, ''")
        checks, _, stopped = nightly.run_steps(["frames", "audio"], temp_dir(self), unreadable,
                                               lambda step: self.fail("a step ran with no power source"))
        self.assertEqual([(c.id, c.status) for c in checks], [("frames", SKIPPED_BATTERY), ("audio", NOT_RUN)])
        self.assertIn("no power source", stopped or "")


def check(id_: str, status: str = PASS, **kw) -> Check:
    return Check(id_, id_.split(" ")[0], status, **kw)


def timed(id_: str, value: float, status_value=None, status: str = PASS) -> Check:
    return check(id_, status, value=value, unit="ms", limit=8.0, status_value=status_value, timed=True,
                 load=[2.0, 3.0])


class ChangesTest(unittest.TestCase):
    def test_flips_both_ways_new_failures_and_old_ones(self) -> None:
        last = [check("frames a"), check("frames b", FAIL), check("frames c", FAIL), check("frames d")]
        now = [check("frames a", FAIL), check("frames b"), check("frames c", FAIL), check("frames d"),
               check("frames e", FAIL), check("frames f")]
        self.assertEqual(nightly_report.changes(now, last), {
            "frames a": ["flipped, pass last time"], "frames b": ["flipped, fail last time"],
            "frames c": ["same"], "frames e": ["new"]})

    def test_with_no_last_report_every_failure_is_new(self) -> None:
        self.assertEqual(nightly_report.changes([check("frames a", FAIL), check("frames b")], None),
                         {"frames a": ["new"]})

    def test_skipped_checks_are_never_flips(self) -> None:
        self.assertEqual(nightly_report.changes([check("soak a", SKIPPED_BATTERY)], [check("soak a")]), {})


class SlowerTest(unittest.TestCase):
    def test_more_than_ten_percent_slower_than_last_or_status_is_a_regression(self) -> None:
        last = [timed("timed a", 4.0), timed("timed b", 4.0), timed("timed c", 4.0)]
        now = [timed("timed a", 4.41), timed("timed b", 4.4), timed("timed c", 4.0, status_value=3.6)]
        self.assertEqual(nightly_report.changes(now, last), {
            "timed a": ["10% slower than last's 4"], "timed c": ["11% slower than status.md's 3.6"]})

    def test_a_small_number_must_also_be_more_than_the_floor_slower(self) -> None:
        self.assertEqual(nightly_report.FLOOR, 0.25)
        now = [timed("timed a", 1.25), timed("timed b", 1.26)]  # 25% and 26% slower than 1.0
        self.assertEqual(nightly_report.changes(now, [timed("timed a", 1.0), timed("timed b", 1.0)]),
                         {"timed b": ["26% slower than last's 1"]})

    def test_faster_is_no_regression_and_far_enough_under_status_is_improved(self) -> None:
        now = [timed("timed a", 2.25, status_value=4.2), timed("timed b", 0.6, status_value=0.722),
               timed("timed c", 3.8, status_value=4.2)]
        self.assertEqual(nightly_report.changes(now, [timed("timed a", 4.0)]), {})
        self.assertEqual([nightly_report.improved(c) for c in now],
                         ["46% under status.md's 4.2, update status.md", None, "10% under status.md's 4.2, update status.md"])
        self.assertIsNone(nightly_report.improved(timed("timed d", 3.83, status_value=4.2)))

    def test_a_count_isnt_held_to_ten_percent(self) -> None:
        now = [check("timed n", value=3.0)]
        self.assertEqual(nightly_report.changes(now, [check("timed n", value=1.0)]), {})

    def test_the_summary_shows_the_load_beside_the_number(self) -> None:
        line = nightly_report.line(timed("timed a", 4.41), ["10% slower than last's 4"])
        self.assertEqual(line, "  timed a: 4.41 ms (bar 8), load 2.0 to 3.0 [10% slower than last's 4]")


class SummaryTest(unittest.TestCase):
    def test_regressions_then_old_failures_then_passes_then_skips(self) -> None:
        last = [check("frames 4:3 a"), check("frames 4:3 b", FAIL), timed("timed x", 4.0)]
        now = [check("soak s", SKIPPED_BATTERY), check("frames 4:3 c"),
               check("frames 4:3 b", FAIL, kind="drew differently",
                     problems=[Problem("frame 60", "1 != golden 2", "dumps/4x3/b/frame_00060.png")]),
               timed("timed x", 5.0),
               check("frames 4:3 a", FAIL, kind="drew differently",
                     problems=[Problem("frame 120", "3 != golden 4", "dumps/4x3/a/frame_00120.png"),
                               Problem("frame 180", "not reached")])]
        lines = nightly_report.summary(["head"], now, last).splitlines()
        self.assertEqual(lines, [
            "head",
            "Regressions (2)",
            "  timed x: 5.00 ms (bar 8), load 2.0 to 3.0 [25% slower than last's 4]",
            "  frames 4:3 a: drew differently, frame 120 3 != golden 4, and 1 more -> "
            "dumps/4x3/a/frame_00120.png [flipped, pass last time]",
            "Failing as last time (1)",
            "  frames 4:3 b: drew differently, frame 60 1 != golden 2 -> dumps/4x3/b/frame_00060.png",
            "Passes",
            "  frames: 1 of 3 checks pass (1 frames)",  # timed x passed its bar, but it's listed above
            "Skipped",
            "  soak: skipped-battery (1 checks)"])

    def test_known_issues_and_improved_numbers_have_their_own_headings(self) -> None:
        now = [check("state 16:9 r", FAIL, kind="played differently", known="bug 1",
                     problems=[Problem("frame 9 speed", "1 != golden 2")]),
               check("frames 4:3 r", known="bug 2"), timed("timed x", 2.0, status_value=4.0), check("frames 4:3 s")]
        lines = nightly_report.summary(["head"], now, [check("state 16:9 r")]).splitlines()
        self.assertEqual(lines, [
            "head",
            "Known issues (2)",
            "  state 16:9 r: played differently, frame 9 speed 1 != golden 2 [known: bug 1]",
            "  frames 4:3 r: passes now, so its line in known-issues.txt can go [known: bug 2]",
            "Improved (1)",
            "  timed x: 2.00 ms (bar 8), load 2.0 to 3.0 [50% under status.md's 4, update status.md]",
            "Passes",
            "  frames: 2 of 2 checks pass (2 frames)"])

    def test_a_long_list_is_cut_to_fit_one_screen(self) -> None:
        now = [check(f"frames 4:3 r{i}", FAIL) for i in range(100)]
        lines = nightly_report.summary([], now, None).splitlines()
        self.assertLessEqual(len(lines), nightly_report.LINES + 5)
        self.assertEqual(lines[-1], f"  and 60 more in {nightly_report.REPORT}")

    def test_last_report_is_the_newest_earlier_one(self) -> None:
        nightly_dir = temp_dir(self)
        for name in ("2026-11-16-0130", "2026-11-17-0130", "2026-11-19-0130"):
            (nightly_dir / name).mkdir()
            write_file(nightly_dir / name, nightly_report.REPORT, "{}")
        (nightly_dir / "2026-11-17-1200").mkdir()  # no report in it
        self.assertEqual(nightly_report.last_report(nightly_dir, nightly_dir / "2026-11-18-0130"),
                         nightly_dir / "2026-11-17-0130" / nightly_report.REPORT)


class FinishTest(unittest.TestCase):
    def report(self) -> Path:
        report = temp_dir(self)
        for d in ("logs", "work"):
            (report / d).mkdir()
        for name in ("4p.log", "menu.log"):
            write_file(report / "logs", name, "x")
        return report

    def test_logs_go_when_every_check_passed(self) -> None:
        report = self.report()
        checks = [check("timed a", value=1.0, dump="logs/4p.log"), check("timed b", value=1.0, dump="logs/menu.log")]
        self.assertEqual(nightly.finish(report, checks, {}, None, 0.0, [1.0, 1.0], None, report, lambda text: None), 0)
        self.assertFalse((report / "logs").exists())
        self.assertFalse((report / "work").exists())

    def test_a_failed_checks_log_stays(self) -> None:
        report = self.report()
        checks = [check("timed a", value=1.0, dump="logs/4p.log"),
                  check("timed b", FAIL, value=1.0, dump="logs/menu.log")]
        self.assertEqual(nightly.finish(report, checks, {}, None, 0.0, [1.0, 1.0], None, report, lambda text: None), 1)
        self.assertEqual(sorted(p.name for p in (report / "logs").iterdir()), ["menu.log"])

    def last(self, checks: list[Check]) -> Path:
        return write_file(temp_dir(self), nightly_report.REPORT, json.dumps({"checks": nightly_report.to_json(checks)}))

    def test_a_slower_checks_log_stays_though_it_passed_its_bar(self) -> None:
        report = self.report()
        checks = [timed("timed a", 5.0, status_value=4.0), timed("timed b", 4.0)]
        checks[0].dump, checks[1].dump = "logs/4p.log", "logs/menu.log"
        last = self.last([timed("timed a", 4.0), timed("timed b", 4.0)])
        self.assertEqual(nightly.finish(report, checks, {}, None, 0.0, [1.0, 1.0], last, report, lambda text: None), 1)
        self.assertEqual(sorted(p.name for p in (report / "logs").iterdir()), ["4p.log"])

    def test_a_faster_number_and_a_known_issue_fail_nothing(self) -> None:
        report = self.report()
        checks = [timed("timed a", 2.0, status_value=4.0), check("state 16:9 r", FAIL, known="a bug")]
        self.assertEqual(nightly.finish(report, checks, {}, None, 0.0, [1.0, 1.0], None, report, lambda text: None), 0)
        self.assertIn("Result: pass, 0 regressions, 0 failing", (report / nightly_report.SUMMARY).read_text())

    def test_the_built_engine_heads_the_report(self) -> None:
        report = self.report()
        steps = {"frames": {"seconds": 60, "built": ENGINE_SHA + "-dirty"}}
        nightly.finish(report, [check("frames 4:3 r")], steps, None, 0.0, [1.0, 1.0], None, report, lambda text: None)
        self.assertIn("gcn-recomp built 0123456-dirty, ", (report / nightly_report.SUMMARY).read_text())


class LastReportTest(unittest.TestCase):
    def test_a_report_that_wont_read_is_none_with_why(self) -> None:
        d = temp_dir(self)
        cases = {"missing": d / "nowhere", "a directory with no report": d,
                 "not json": write_file(d, "a.json", "{"), "no checks": write_file(d, "b.json", "{}"),
                 "a row that isn't a check": write_file(d, "c.json", '{"checks": [{"step": "x"}]}')}
        for what, path in cases.items():
            with self.subTest(what):
                got, why = nightly_report.readable(path)
                self.assertIsNone(got)
                self.assertIn("isn't a report", why or "")

    def test_an_older_or_newer_report_reads_with_its_odd_fields_dropped(self) -> None:
        row = {**nightly_report.to_json([check("frames 4:3 r")])[0], "moved": True}
        del row["known"]
        path = write_file(temp_dir(self), nightly_report.REPORT, json.dumps({"checks": [row]}))
        self.assertEqual(nightly_report.readable(path.parent), (path, None))
        self.assertEqual(nightly_report.read(path), [check("frames 4:3 r")])

    def test_the_summary_says_why_nothing_was_compared(self) -> None:
        report = FinishTest.report(self)
        nightly.finish(report, [], {}, None, 0.0, [1.0, 1.0], None, report, lambda text: None,
                       last_note="x isn't a report")
        self.assertIn("Last: x isn't a report", (report / nightly_report.SUMMARY).read_text())


class FramePairTest(unittest.TestCase):
    def test_golden_left_gap_new_right(self) -> None:
        golden = Image(1, 2, 4, bytes([1, 2, 3, 255, 4, 5, 6, 255]))
        new = Image(2, 1, 3, bytes([7, 8, 9, 10, 11, 12]))
        pair = side_by_side(golden, new, gap=1)
        self.assertEqual((pair.width, pair.height, pair.channels), (4, 2, 3))
        self.assertEqual(pair.pixels, bytes([1, 2, 3, 0, 0, 0, 7, 8, 9, 10, 11, 12,
                                             4, 5, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0]))
        path = write_file(temp_dir(self), "pair.png", write_png(pair))
        self.assertEqual(read_png(path), pair)


class RouteCompilesTest(unittest.TestCase):
    LOG = ("[ft] f99 guest   16.67ms  draws  10/  10 verts 100 idx 100 \n[rt] f100 render  1.00ms\n"
           "[shaders] compiled program 7 in 2.5 ms\n[shaders] compiled program 8 in 1.5 ms\n"
           "[ft] f100 guest   16.67ms  draws  10/  10 verts 100 idx 100 \n[rt] f101 render  9.00ms\n")

    def test_each_compile_is_counted_at_its_frame(self) -> None:
        c = route_compiles.read_log(self.LOG, 101)
        self.assertEqual((c.frames, c.reached, c.ok), ([101, 101], 101, False))
        self.assertEqual(route_compiles.describe(c), "compiled 2 at frames 101, 101")

    def test_a_run_short_of_its_frame_fails_with_no_compile(self) -> None:
        c = route_compiles.read_log(self.LOG.replace("[shaders] compiled program", "[shaders] built"), 102)
        self.assertEqual((c.frames, c.ok, route_compiles.describe(c)), ([], False, "reached frame 101 of 102"))
        self.assertTrue(route_compiles.read_log(self.LOG.replace("[shaders] compiled program", "x"), 101).ok)


if __name__ == "__main__":
    unittest.main()
