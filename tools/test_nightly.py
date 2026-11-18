from __future__ import annotations

import hashlib
import json
import plistlib
import unittest
from pathlib import Path

import nightly
import nightly_agent
import nightly_report
import nightly_steps
import power
import route_compiles
import state_goldens
from frame_pair import side_by_side, write_png
from framediff import Image, read_png
from nightly_report import FAIL, NOT_RUN, PASS, SKIPPED_BATTERY, Check, Problem
from testengine import make_tree, set_plan
from testutil import run_main, temp_dir, write_file

AC = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%; charged; 0:00 remaining present: true\n"
BATTERY = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t80%; discharging; 4:00 remaining\n"
# Two routes the fake game plays. It never leaves the boot screen, which is all a state check needs.
MANIFEST = "title 20 60 60,120\nmenu  20 60 120\n"


def fake_frame(frame: int, blue: int = 0) -> bytes:
    """The dump testengine's fake game writes at FRAME."""
    return write_png(fake_image(frame, blue))


def fake_image(frame: int, blue: int = 0) -> Image:
    return Image(2, 2, 3, bytes([frame % 256, frame // 256 % 256, blue]) * 4)


def booting(read_at: int) -> tuple[int, dict]:
    """The state the fake game shows at the boot screen, read at READ_AT."""
    state = {f: state_goldens.NONE if f.split(".")[-1] in "xyz" else "0" for f in state_goldens.FIELDS}
    state["scene.minor"] = "38"
    return read_at, state


class FakePmset:
    """pmset -g batt as a script that prints whatever `now` was last set to."""

    def __init__(self, test: unittest.TestCase, text: str = AC) -> None:
        self.dir = temp_dir(test)
        self.script = write_file(self.dir, "pmset", f"#!/bin/sh\ncat '{self.dir}/batt.txt'\n")
        self.script.chmod(0o755)
        self.now(text)

    def now(self, text: str) -> None:
        write_file(self.dir, "batt.txt", text)

    def command(self) -> list[str]:
        return [str(self.script)]


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


class FakeTree:
    """A tree with testengine's fake probe.sh, a two-route manifest and goldens that match what
    the fake game draws and shows, which a test then changes."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.root = temp_dir(test)
        make_tree(self.root)
        set_plan(self.root)
        hashes = self.root / "tests" / "hashes"
        for d in ("gl", "gl-16x9", "state", "state-16x9"):
            (hashes / d).mkdir(parents=True)
        write_file(hashes, "manifest.txt", MANIFEST)
        for name, frames in (("title", [60, 120]), ("menu", [60, 120])):
            text = "".join(f"frame_{f:05d} {hashlib.sha1(fake_frame(f)).hexdigest()}\n" for f in frames)
            write_file(hashes / "gl", f"{name}.txt", text)
            write_file(hashes / "gl-16x9", f"{name}.txt", text)
        for d in state_goldens.STATES.values():
            write_file(hashes / d, "title.txt",
                       state_goldens.format_golden("title", {60: booting(60), 120: booting(120)}))
            write_file(hashes / d, "menu.txt", state_goldens.format_golden("menu", {120: booting(120)}))
        self.report = self.root / "build" / "nightly" / "2026-11-18-0130"
        self.report.mkdir(parents=True)
        self.games = 0

    def context(self, before=None, **kw) -> nightly_steps.Context:
        def counted() -> None:
            if before is not None:
                before()
            self.games += 1
        return nightly_steps.Context(self.root, self.report, before=counted, say=lambda text: None, **kw)

    def play(self, step: str, ctx: nightly_steps.Context) -> list[Check]:
        code = nightly.play_step(step, ctx)
        if code not in (0, nightly.STOPPED_ON_BATTERY):
            raise AssertionError(f"{step} exited {code}")
        return nightly_report.from_json(json.loads((ctx.work / f"{step}.json").read_text())["checks"])

    def by_id(self, checks: list[Check]) -> dict[str, Check]:
        return {c.id: c for c in checks}

    def runs_left(self) -> list[str]:
        probe = self.root / "build" / "probe"
        return sorted(p.name for p in probe.iterdir()) if probe.is_dir() else []


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


class TenPercentTest(unittest.TestCase):
    def test_a_move_past_ten_percent_of_last_or_status_is_a_regression(self) -> None:
        last = [timed("timed a", 4.0), timed("timed b", 4.0), timed("timed c", 4.0)]
        now = [timed("timed a", 4.41), timed("timed b", 4.39), timed("timed c", 4.0, status_value=3.6)]
        self.assertEqual(nightly_report.changes(now, last), {
            "timed a": ["10% off last's 4"], "timed c": ["11% off status.md's 3.6"]})

    def test_down_counts_as_much_as_up(self) -> None:
        self.assertEqual(nightly_report.changes([timed("timed a", 3.5)], [timed("timed a", 4.0)]),
                         {"timed a": ["12% off last's 4"]})

    def test_a_count_isnt_held_to_ten_percent(self) -> None:
        now = [check("timed n", value=3.0)]
        self.assertEqual(nightly_report.changes(now, [check("timed n", value=1.0)]), {})

    def test_the_summary_shows_the_load_beside_the_number(self) -> None:
        line = nightly_report.line(timed("timed a", 4.41), ["10% off last's 4"])
        self.assertEqual(line, "  timed a: 4.41 ms (bar 8), load 2.0 to 3.0 [10% off last's 4]")


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
            "  timed x: 5.00 ms (bar 8), load 2.0 to 3.0 [25% off last's 4]",
            "  frames 4:3 a: drew differently, frame 120 3 != golden 4, and 1 more -> "
            "dumps/4x3/a/frame_00120.png [flipped, pass last time]",
            "Failing as last time (1)",
            "  frames 4:3 b: drew differently, frame 60 1 != golden 2 -> dumps/4x3/b/frame_00060.png",
            "Passes",
            "  frames: 1 of 3 checks pass (1 frames)",  # timed x passed its bar, but it's listed above
            "Skipped",
            "  soak: skipped-battery (1 checks)"])

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


class AgentTest(unittest.TestCase):
    def test_install_prints_a_daily_0130_job_and_uninstall_removes_it(self) -> None:
        agents = temp_dir(self)
        code, out, _ = run_main(nightly.main, "install-agent", "--dir", str(agents))
        self.assertEqual(code, 0)
        path = agents / f"{nightly_agent.LABEL}.plist"
        job = plistlib.loads(path.read_bytes())
        self.assertEqual(job["StartCalendarInterval"], {"Hour": 1, "Minute": 30})
        self.assertEqual(job["ProgramArguments"][1:], [str(nightly.ROOT / "tools" / "nightly.py"), "run"])
        self.assertIn("<key>StartCalendarInterval</key>", out)
        self.assertIn("isn't loaded", out)
        code, out, _ = run_main(nightly.main, "uninstall-agent", "--dir", str(agents))
        self.assertEqual((code, path.exists()), (0, False))


if __name__ == "__main__":
    unittest.main()
