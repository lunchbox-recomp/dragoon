import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import routes
import scorecard_runs
from routes import Route
from scorecard_runs import Build, Commits, Run
from testutil import write_file

RACE = Route("air-ride-race", 30, 60, [4200, 6000], ["--pads=4"])
COMMITS = Commits("6b81b6e-dirty", "caf12a2")


def executable(directory: Path, name: str) -> Path:
    path = write_file(directory, name, "#!/bin/sh\n")
    path.chmod(0o755)
    return path


class Clone(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clone = Path(tmp.name).resolve()
        (self.clone / "tools").mkdir()
        (self.clone / "build").mkdir()
        executable(self.clone / "tools", "probe.sh")
        executable(self.clone / "build", "dragoon")
        self.build = Build("base", self.clone / "build")
        self.out = self.clone / "build" / "probe" / "scorecard-air-ride-race"
        self.unpaced = self.clone / "build" / "probe" / "scorecard-unpaced-air-ride-race"


class CheckBuildTest(Clone):
    def test_a_built_clone_passes(self):
        scorecard_runs.check_build(self.build)

    def test_a_directory_not_named_build_is_refused(self):
        other = self.clone / "build-other"
        other.mkdir()
        executable(other, "dragoon")
        with self.assertRaisesRegex(ValueError, "build-other: probe.sh runs the game only from its clone's build/"):
            scorecard_runs.check_build(Build("x", other))

    def test_a_clone_without_probe_sh_is_refused(self):
        (self.clone / "tools" / "probe.sh").rename(self.clone / "probe.sh")
        with self.assertRaisesRegex(ValueError, "probe.sh"):
            scorecard_runs.check_build(self.build)

    def test_an_unbuilt_game_is_refused(self):
        (self.clone / "build" / "dragoon").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "dragoon: not built"):
            scorecard_runs.check_build(self.build)


class SecondsTest(unittest.TestCase):
    def test_the_last_checkpoint_at_60_a_second_plus_15_rounded_up(self):
        for required, want in (([60, 960], 31), ([4200, 6000], 115), ([3481], 74)):
            with self.subTest(required=required):
                self.assertEqual(scorecard_runs.seconds(Route("r", 20, 60, required, [])), want)

    def test_a_margin_replaces_the_15(self):
        self.assertEqual(scorecard_runs.seconds(Route("r", 20, 60, [60, 960], []), 75), 91)


class ProbeArgsTest(Clone):
    def test_a_real_time_run_of_the_route_recording_both_stages_with_absolute_paths(self):
        self.assertEqual(scorecard_runs.probe_args(self.build, RACE), [
            str(self.clone / "tools" / "probe.sh"), "scorecard-air-ride-race", "115",
            str(routes.route_file("air-ride-race")), "6000", "--real-time", "GCN_DUMP_RANGE=6000",
            f"GCN_WAV={self.out / 'device.wav'}", f"GCN_AIDWAV={self.out / 'mixer.raw'}",
            "GCN_AXSTATS=1", "--pads=4"])

    def test_a_margin_lengthens_the_run_and_still_dumps_one_frame(self):
        args = scorecard_runs.probe_args(self.build, RACE, 60)
        self.assertEqual(args[2], "160")
        self.assertEqual(args[4:7], ["6000", "--real-time", "GCN_DUMP_RANGE=6000"])

    def test_the_route_file_is_this_clones_whatever_the_build(self):
        self.assertEqual(scorecard_runs.probe_args(self.build, RACE)[3],
                         str(Path(scorecard_runs.__file__).resolve().parents[1] / "tests" / "routes" / "air-ride-race.txt"))

    def test_an_unpaced_run_plays_as_long_and_records_only_the_dmas_blocks(self):
        self.assertEqual(scorecard_runs.probe_args(self.build, RACE, unpaced=True), [
            str(self.clone / "tools" / "probe.sh"), "scorecard-unpaced-air-ride-race", "115",
            str(routes.route_file("air-ride-race")), "6000", "GCN_DUMP_RANGE=6000",
            f"GCN_AIDWAV={self.unpaced / 'mixer.raw'}", "GCN_AXSTATS=1", "--pads=4"])


def frame_at(directory: Path, frame: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_file(directory, f"frame_{frame:05d}.png", b"")


class PlayTest(Clone):
    def play(self, run: mock.Mock, *margin: int) -> mock.Mock:
        self.calls = mock.Mock()
        remove = self.calls.remove
        self.calls.attach_mock(run, "run")
        with (mock.patch.object(scorecard_runs, "remove_run", remove),
              mock.patch.object(subprocess, "run", run)):
            self.result = scorecard_runs.play(self.build, RACE, *margin, commits=COMMITS)
        return remove

    def reaches(self, frame: int = 6000, unpaced_frame: int = 6000):
        def run(args, **kwargs):
            unpaced = args[1].startswith("scorecard-unpaced-")
            frame_at(self.unpaced if unpaced else self.out, unpaced_frame if unpaced else frame)
        return mock.Mock(side_effect=run)

    def test_runs_the_clones_probe_from_the_clone_with_sdls_dummy_audio_driver(self):
        run = self.reaches()
        self.play(run)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["cwd"], self.clone)
            self.assertEqual(call.kwargs["env"]["SDL_AUDIO_DRIVER"], "dummy")
            self.assertTrue(call.kwargs["check"])

    def test_plays_in_real_time_then_unpaced(self):
        run = self.reaches()
        self.play(run)
        self.assertEqual([c.args[0] for c in run.call_args_list],
                         [scorecard_runs.probe_args(self.build, RACE),
                          scorecard_runs.probe_args(self.build, RACE, unpaced=True)])

    def test_plays_both_for_the_margin_it_is_given(self):
        run = self.reaches()
        self.play(run, 60)
        self.assertEqual([c.args[0][2] for c in run.call_args_list], ["160", "160"])

    def test_returns_both_runs_files(self):
        self.play(self.reaches())
        paced, unpaced = self.result.paced, self.result.unpaced
        self.assertEqual((paced.mixer, paced.device, paced.log),
                         (self.out / "mixer.raw", self.out / "device.wav", self.out / "stdout.txt"))
        self.assertEqual((unpaced.mixer, unpaced.log), (self.unpaced / "mixer.raw", self.unpaced / "stdout.txt"))

    def test_leaves_the_commits_it_was_given_in_each_runs_directory(self):
        self.play(self.reaches())
        for directory in (self.out, self.unpaced):
            self.assertEqual(json.loads((directory / "commits.json").read_text()),
                             {"dragoon": "6b81b6e-dirty", "gcn_recomp": "caf12a2"})
        self.assertEqual(scorecard_runs.read_commits(self.result.unpaced), COMMITS)

    def test_removes_each_earlier_run_before_playing_so_the_card_is_blank(self):
        self.out.mkdir(parents=True)
        self.unpaced.mkdir(parents=True)
        remove = self.play(self.reaches())
        self.assertEqual(remove.call_args_list, [mock.call(self.out), mock.call(self.unpaced)])
        self.assertEqual([name for name, _, _ in self.calls.mock_calls], ["remove", "run", "remove", "run"])

    def test_removes_nothing_when_there_is_no_earlier_run(self):
        self.play(self.reaches()).assert_not_called()

    def test_a_failed_probe_names_the_build_and_route(self):
        run = mock.Mock(side_effect=subprocess.CalledProcessError(2, "probe"))
        with self.assertRaisesRegex(ValueError, "base air-ride-race: probe.sh exited 2"):
            self.play(run)

    def test_a_failed_unpaced_probe_says_so(self):
        def run(args, **kwargs):
            if args[1].startswith("scorecard-unpaced-"):
                raise subprocess.CalledProcessError(2, "probe")
            frame_at(self.out, 6000)
        with self.assertRaisesRegex(ValueError, "base air-ride-race unpaced: probe.sh exited 2"):
            self.play(mock.Mock(side_effect=run))

    def test_a_run_that_stops_short_of_the_last_checkpoint_is_refused(self):
        with self.assertRaisesRegex(ValueError, "base air-ride-race: .*scorecard-air-ride-race reached frame 6000"):
            self.play(self.reaches(4200))
        with self.assertRaisesRegex(ValueError, "base air-ride-race: .*scorecard-unpaced-air-ride-race reached"):
            self.play(self.reaches(6000, 4200))


class FinishedTest(Clone):
    def test_an_earlier_run_that_reached_the_last_checkpoint_is_measured(self):
        frame_at(self.out, 6000)
        self.assertEqual(scorecard_runs.finished(self.build, RACE).directory, self.out)

    def test_no_earlier_run_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no run in .*scorecard-air-ride-race reached frame 6000"):
            scorecard_runs.finished(self.build, RACE)


class LastRunsTest(Clone):
    def test_both_runs_when_both_reached_the_last_checkpoint(self):
        frame_at(self.out, 6000)
        frame_at(self.unpaced, 6000)
        got = scorecard_runs.last_runs(self.build, RACE)
        self.assertEqual((got.paced.directory, got.unpaced.directory), (self.out, self.unpaced))

    def test_a_build_with_no_unpaced_run_has_none(self):
        frame_at(self.out, 6000)
        self.assertIsNone(scorecard_runs.last_runs(self.build, RACE).unpaced)

    def test_an_unpaced_run_that_stopped_short_is_refused(self):
        frame_at(self.out, 6000)
        frame_at(self.unpaced, 4200)
        with self.assertRaisesRegex(ValueError, "scorecard-unpaced-air-ride-race reached frame 6000"):
            scorecard_runs.last_runs(self.build, RACE)

    def test_no_real_time_run_is_refused_whatever_the_unpaced_one(self):
        frame_at(self.unpaced, 6000)
        with self.assertRaisesRegex(ValueError, "scorecard-air-ride-race reached frame 6000"):
            scorecard_runs.last_runs(self.build, RACE)


class ReadCommitsTest(Clone):
    def test_a_run_made_before_commits_were_recorded_has_none(self):
        self.out.mkdir(parents=True)
        self.assertIsNone(scorecard_runs.read_commits(Run(self.out)))

    def test_a_commit_outside_git_comes_back_as_none(self):
        self.out.mkdir(parents=True)
        write_file(self.out, "commits.json", '{"dragoon": null, "gcn_recomp": "caf12a2"}\n')
        self.assertEqual(scorecard_runs.read_commits(Run(self.out)), Commits(None, "caf12a2"))

    def test_a_file_that_isnt_two_commits_is_refused_by_name(self):
        self.out.mkdir(parents=True)
        for bad in ("", "{", "[]", '{"dragoon": "a"}'):
            with self.subTest(bad=bad):
                write_file(self.out, "commits.json", bad)
                with self.assertRaisesRegex(ValueError, "commits.json: not a commits file"):
                    scorecard_runs.read_commits(Run(self.out))


if __name__ == "__main__":
    unittest.main()
