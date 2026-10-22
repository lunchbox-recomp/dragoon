import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audio_scorecard
from scorecard_measure import Score, Stage
from scorecard_runs import Build, Run
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
        old.mixer = None
        text = audio_scorecard.table("title", ["old"], [old])
        self.assertRegex(text, r"ring cuts +not logged")
        self.assertRegex(text, r"device clicks on a ring cut +not logged")
        self.assertRegex(text, r"samples the clamp changed +not logged")
        self.assertRegex(text, r"mixer clicks a minute +not recorded")
        self.assertRegex(text, r"mixer clicks on a block join +not recorded")


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        manifest = write_file(self.dir, "manifest.txt", MANIFEST)
        self.order = []
        self.scores = {("base", "title"): score(10), ("now", "title"): score(2),
                       ("base", "menu"): score(20, 90), ("now", "menu"): score(1, 90)}

        def run(build, route):
            self.order.append((build.label, route.name))
            return Run(self.dir / build.label / route.name)

        def measured(log, mixer, device):
            return self.scores[(log.parent.parent.name, log.parent.name)]

        self.play = mock.Mock(side_effect=run)
        self.finished = mock.Mock(side_effect=run)
        for patch in (mock.patch.object(audio_scorecard, "MANIFEST", manifest),
                      mock.patch.object(audio_scorecard, "check_build"),
                      mock.patch.object(audio_scorecard, "play", self.play),
                      mock.patch.object(audio_scorecard, "finished", self.finished),
                      mock.patch.object(audio_scorecard, "measure", side_effect=measured),
                      mock.patch.object(audio_scorecard, "describe", return_value="abc1234")):
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
        self.assertIn("base: /a/build, Dragoon abc1234, gcn-recomp abc1234", out)
        self.assertIn("title: 31 s a run, to frame 960", out)
        self.assertIn("menu: 35 s a run, to frame 1200", out)
        total = out[out.index("total: 2 routes"):]
        self.assertRegex(total, r"mixer clicks +30 +3\n")
        self.assertRegex(total, r"mixer clicks a minute +15.0 +1.5\n")

    def test_no_run_measures_the_runs_already_there(self):
        self.assertEqual(self.main("--no-run")[0], 0)
        self.play.assert_not_called()
        self.assertEqual(len(self.finished.call_args_list), 4)

    def test_routes_picks_routes_in_manifest_order(self):
        self.main("--routes", "menu")
        self.assertEqual(self.order, [("base", "menu"), ("now", "menu")])

    def test_json_has_every_route_and_the_total_for_each_build(self):
        code, out, _ = self.main("--json")
        self.assertEqual(code, 0)
        got = json.loads(out)
        self.assertEqual(got["routes"], ["title", "menu"])
        base = got["builds"][0]
        self.assertEqual((base["label"], base["build"], base["gcn_recomp"]), ("base", "/a/build", "abc1234"))
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
    def test_names_this_checkouts_commit(self):
        got = audio_scorecard.describe(Path(audio_scorecard.__file__).resolve().parents[1])
        self.assertRegex(got, r"^[0-9a-f]{7,}(-dirty)?$")

    def test_a_directory_outside_git_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(audio_scorecard.describe(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
