from __future__ import annotations

import json
import re
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import audio_scorecard
from scorecard_measure import Score, Stage
from scorecard_runs import Build, Commits, Run, Runs
from testutil import run_main, write_file

MANIFEST = "title 20 60 60,960\nmenu 20 60 1200\n"


def score(clicks: int, seconds: float = 30.0, cuts: int | None = 0, clamped: int | None = 7) -> Score:
    mixer = Stage(seconds, clicks, clicks * 60 / seconds, 1, 2, 5, on_joins=clicks // 2, joins_by_chance=0.5)
    device = Stage(seconds, clicks + 1, (clicks + 1) * 60 / seconds, 0, 0, 0,
                   on_cuts=None if cuts is None else 0, cuts_by_chance=None if cuts is None else 0.0)
    return Score(mixer, device, cuts, 0, 30000, clamped)


class ParseBuildsTest(unittest.TestCase):
    def test_label_and_absolute_build_directory(self):
        self.assertEqual(audio_scorecard.parse_builds(["base=/a/build", "now=/b/build"]),
                         [Build("base", Path("/a/build")), Build("now", Path("/b/build"))])

    def test_a_relative_directory_is_made_absolute(self):
        self.assertTrue(audio_scorecard.parse_build("x=build").directory.is_absolute())

    def test_malformed_arguments_are_refused(self):
        for bad in ("build", "=/a/build", "base="):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "not LABEL=BUILD_DIR"):
                audio_scorecard.parse_build(bad)

    def test_a_label_or_directory_twice_is_refused(self):
        with self.assertRaisesRegex(ValueError, "the same label twice: a"):
            audio_scorecard.parse_builds(["a=/a/build", "a=/b/build"])
        with self.assertRaisesRegex(ValueError, "the same build directory twice"):
            audio_scorecard.parse_builds(["a=/a/build", "b=/a/build"])


class TableTest(unittest.TestCase):
    def test_one_column_per_build_in_order_with_each_measure(self):
        text = audio_scorecard.table("title", ["base", "now"], [score(10), score(4)])
        lines = text.splitlines()
        self.assertEqual(lines[0], "title")
        self.assertEqual(lines[1].split(), ["base", "now"])
        row = {name: values for name, *values in (re.split(r" {2,}", line.strip()) for line in lines[2:])}
        self.assertEqual(row["mixer clicks"], ["10", "4"])
        self.assertEqual(row["mixer clicks a minute"], ["20.0", "8.0"])
        self.assertEqual(row["device clicks"], ["11", "5"])
        self.assertIn("5 (0.5 by chance)", text)

    def test_what_a_build_doesnt_log_or_record_says_so(self):
        old = score(10, cuts=None, clamped=None)
        text = audio_scorecard.table("title", ["old"], [old])
        self.assertRegex(text, r"ring cuts +not logged")
        self.assertRegex(text, r"device clicks on a ring cut +not logged")
        self.assertRegex(text, r"samples the clamp changed +not logged")
        old.mixer = None
        text = audio_scorecard.table("title", ["old"], [old])
        self.assertRegex(text, r"mixer clicks a minute +not recorded")
        self.assertRegex(text, r"mixer clicks on a block join +not recorded")

    def test_with_no_mixer_stage_its_log_values_are_not_recorded_either(self):
        old = score(10)
        old.mixer = None
        text = audio_scorecard.table("title", ["old"], [old])
        self.assertRegex(text, r"main L peak before the clamp +not recorded")
        self.assertRegex(text, r"samples the clamp changed +not recorded")
        self.assertRegex(text, r"ring cuts +0")


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        manifest = write_file(self.dir, "manifest.txt", MANIFEST)
        self.order = []
        self.events = []  # every describe and every run, in the order they happened
        self.scores = {("base", "title"): score(10), ("now", "title"): score(2),
                       ("base", "menu"): score(20, 90), ("now", "menu"): score(1, 90)}

        self.unpaced = True  # whether the fake --no-run finds an unpaced run
        self.cuts = []  # the mixer seconds each measure was given

        def run(build, route, *margin, **kwargs):
            self.order.append((build.label, route.name))
            self.events.append(f"run {build.label} {route.name}")
            unpaced = Run(self.dir / build.label / f"unpaced-{route.name}")
            return Runs(Run(self.dir / build.label / route.name), unpaced if self.unpaced else None)

        def describe(path):
            self.events.append(f"describe {path.name}")
            return path.name

        def measured(runs, seconds):
            self.cuts.append(seconds)
            return self.scores[(runs.paced.log.parent.parent.name, runs.paced.log.parent.name)]

        self.play = mock.Mock(side_effect=run)
        self.finished = mock.Mock(side_effect=run)
        for patch in (mock.patch.object(audio_scorecard, "MANIFEST", manifest),
                      mock.patch.object(audio_scorecard, "check_build"),
                      mock.patch.object(audio_scorecard, "play", self.play),
                      mock.patch.object(audio_scorecard, "last_runs", self.finished),
                      mock.patch.object(audio_scorecard, "measure", side_effect=measured),
                      mock.patch.object(audio_scorecard, "describe", side_effect=describe)):
            patch.start()
            self.addCleanup(patch.stop)

    def main(self, *argv: str):
        return run_main(audio_scorecard.main, "base=/a/build", "now=/b/build", *argv)

    def test_plays_a_route_on_every_build_before_the_next_route(self):
        code, _, _ = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(self.order, [("base", "title"), ("now", "title"), ("base", "menu"), ("now", "menu")])
        self.finished.assert_not_called()

    def test_prints_a_table_per_route_and_the_totals(self):
        _, out, _ = self.main()
        self.assertIn("base: /a/build, Dragoon a, gcn-recomp gcn-recomp", out)
        self.assertIn("now: /b/build, Dragoon b, gcn-recomp gcn-recomp", out)
        self.assertIn("title: 31 s a run, to frame 960", out)
        self.assertIn("menu: 35 s a run, to frame 1200", out)
        total = out[out.index("total: 2 routes"):]
        self.assertRegex(total, r"mixer clicks +30 +3\n")
        self.assertRegex(total, r"mixer clicks a minute +15.0 +1.5\n")

    def test_no_run_measures_the_runs_already_there(self):
        code, out, _ = self.main("--no-run")
        self.assertEqual(code, 0)
        self.play.assert_not_called()
        self.assertEqual(len(self.finished.call_args_list), 4)
        self.assertIn("title: to frame 960\n", out)

    def test_the_commits_are_read_before_the_first_run_plays(self):
        self.main()
        described = [i for i, event in enumerate(self.events) if event.startswith("describe")]
        played = [i for i, event in enumerate(self.events) if event.startswith("run")]
        self.assertEqual(len(described), 4)
        self.assertLess(max(described), min(played))

    def test_each_run_is_given_its_builds_commits_to_leave_behind(self):
        self.main()
        given = {c.args[0].label: c.kwargs["commits"] for c in self.play.call_args_list}
        self.assertEqual(given, {"base": Commits("a", "gcn-recomp"), "now": Commits("b", "gcn-recomp")})

    def record(self, label: str, route: str, commits: Commits) -> None:
        directory = self.dir / label / route
        directory.mkdir(parents=True)
        write_file(directory, "commits.json", json.dumps(asdict(commits)))

    def test_each_route_is_measured_over_its_last_checkpoint_plus_the_margin(self):
        self.main()
        self.assertEqual(self.cuts, [31, 31, 35, 35])
        self.cuts.clear()
        self.main("--no-run", "--margin", "75")
        self.assertEqual(self.cuts, [91, 91, 95, 95])

    def test_no_run_reads_the_commits_of_both_runs(self):
        for route in ("title", "menu"):
            self.record("base", route, Commits("6b81b6e", "caf12a2"))
            self.record("base", f"unpaced-{route}", Commits("6b81b6e", "8fabc65"))
        _, out, _ = self.main("--no-run")
        self.assertIn("base: /a/build, Dragoon 6b81b6e, gcn-recomp caf12a2 and 8fabc65\n", out)

    def test_no_run_without_unpaced_runs_reads_the_real_time_runs_commits(self):
        self.unpaced = False
        for route in ("title", "menu"):
            self.record("base", route, Commits("6b81b6e", "caf12a2"))
        _, out, _ = self.main("--no-run")
        self.assertIn("base: /a/build, Dragoon 6b81b6e, gcn-recomp caf12a2\n", out)

    def test_no_run_prints_the_commits_the_runs_recorded_not_the_clones_now(self):
        for route in ("title", "menu"):
            for run in (route, f"unpaced-{route}"):
                self.record("base", run, Commits("6b81b6e", "caf12a2"))
                self.record("now", run, Commits("788571c-dirty", "b848158"))
        _, out, _ = self.main("--no-run")
        self.assertIn("base: /a/build, Dragoon 6b81b6e, gcn-recomp caf12a2\n", out)
        self.assertIn("now: /b/build, Dragoon 788571c-dirty, gcn-recomp b848158\n", out)
        _, out, _ = self.main("--no-run", "--json")
        now = json.loads(out)["builds"][1]
        self.assertEqual((now["dragoon"], now["gcn_recomp"]), ("788571c-dirty", "b848158"))
        self.assertEqual([e for e in self.events if e.startswith("describe")], [])

    def test_no_run_says_so_when_a_run_has_no_commits_recorded(self):
        _, out, _ = self.main("--no-run")
        self.assertIn("base: /a/build, Dragoon not recorded, gcn-recomp not recorded\n", out)

    def test_no_run_gives_every_commit_when_the_runs_differ(self):
        self.unpaced = False
        self.record("base", "title", Commits("6b81b6e", "caf12a2"))
        self.record("base", "menu", Commits("6b81b6e", "8fabc65"))
        _, out, _ = self.main("--no-run")
        self.assertIn("base: /a/build, Dragoon 6b81b6e, gcn-recomp caf12a2 and 8fabc65\n", out)
        self.assertIn("now: /b/build, Dragoon not recorded, gcn-recomp not recorded\n", out)

    def test_runs_play_15_s_past_the_last_checkpoint_unless_a_margin_is_given(self):
        self.main()
        self.assertEqual({c.args[2] for c in self.play.call_args_list}, {15})
        self.play.reset_mock()
        _, out, _ = self.main("--margin", "75")
        self.assertEqual({c.args[2] for c in self.play.call_args_list}, {75})
        self.assertIn("title: 91 s a run, to frame 960", out)

    def test_a_negative_margin_exits_2_before_anything_plays(self):
        code, _, err = self.main("--margin", "-1")
        self.assertEqual(code, 2)
        self.assertIn("--margin can't be negative", err)
        self.play.assert_not_called()

    def test_routes_picks_routes_in_manifest_order(self):
        self.main("--routes", "menu")
        self.assertEqual(self.order, [("base", "menu"), ("now", "menu")])

    def test_json_has_every_route_and_the_total_for_each_build(self):
        code, out, _ = self.main("--json")
        self.assertEqual(code, 0)
        got = json.loads(out)
        self.assertEqual(got["routes"], ["title", "menu"])
        base = got["builds"][0]
        self.assertEqual((base["label"], base["build"], base["dragoon"], base["gcn_recomp"]),
                         ("base", "/a/build", "a", "gcn-recomp"))
        self.assertEqual(base["routes"]["menu"]["mixer"]["clicks"], 20)
        self.assertEqual(base["total"]["mixer"]["clicks"], 30)
        self.assertEqual(base["total"]["clamped"], 14)

    def test_an_unknown_route_exits_2_before_anything_plays(self):
        code, _, err = self.main("--routes", "nope")
        self.assertEqual(code, 2)
        self.assertIn("nope", err)
        self.play.assert_not_called()

    def test_a_failed_run_exits_2_with_its_message(self):
        self.play.side_effect = ValueError("base title: probe.sh exited 2")
        code, _, err = self.main()
        self.assertEqual(code, 2)
        self.assertEqual(err, "base title: probe.sh exited 2\n")

    def test_a_recording_that_cant_be_read_exits_2_with_one_line(self):
        audio_scorecard.measure.side_effect = FileNotFoundError(2, "No such file or directory", "/a/stdout.txt")
        code, _, err = self.main()
        self.assertEqual(code, 2)
        self.assertEqual(err, "[Errno 2] No such file or directory: '/a/stdout.txt'\n")

    def test_a_build_probe_sh_wont_run_exits_2_before_anything_plays(self):
        with mock.patch.object(audio_scorecard, "check_build", side_effect=ValueError("/b/build: not built")):
            code, _, err = self.main()
        self.assertEqual(code, 2)
        self.assertIn("not built", err)
        self.play.assert_not_called()

    def test_help_exits_0(self):
        code, out, _ = run_main(audio_scorecard.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


class DescribeTest(unittest.TestCase):
    ROOT = Path(audio_scorecard.__file__).resolve().parents[1]

    @unittest.skipUnless((ROOT / ".git").exists(), "not a git checkout, as in a git archive copy")
    def test_names_this_checkouts_commit(self):
        got = audio_scorecard.describe(self.ROOT)
        self.assertRegex(got, r"^[0-9a-f]{7,}(-dirty)?$")

    def test_a_directory_outside_git_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(audio_scorecard.describe(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
