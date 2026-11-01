from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
import unittest
from pathlib import Path

import bot_link
import bot_record
import source_info
from bot_stop import HANG, PANIC, Stop
from bot_watch import Resets
from testutil import commit, write_file

SHA_A = "a" * 40
SHA_B = "b" * 40


class NewNameTest(unittest.TestCase):
    def test_a_name_has_the_seed_and_the_start_time(self) -> None:
        name = bot_record.new_name(7, 1_800_000_000, lambda n: False)
        self.assertRegex(name, r"^soak-s7-\d{8}-\d{6}$")

    def test_a_name_run_directories_accept(self) -> None:
        name = bot_record.new_name(123456, 1_800_000_000, lambda n: False)
        self.assertRegex(name, r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
        bot_link.run_directory(name)

    def test_the_time_changes_the_name(self) -> None:
        a = bot_record.new_name(1, 1_800_000_000, lambda n: False)
        b = bot_record.new_name(1, 1_800_000_061, lambda n: False)
        self.assertNotEqual(a, b)

    def test_a_name_that_is_taken_gets_a_number(self) -> None:
        first = bot_record.new_name(1, 1_800_000_000, lambda n: False)
        taken = {first}
        second = bot_record.new_name(1, 1_800_000_000, taken.__contains__)
        taken.add(second)
        third = bot_record.new_name(1, 1_800_000_000, taken.__contains__)
        self.assertEqual((second, third), (f"{first}-2", f"{first}-3"))

    def test_a_directory_on_disk_makes_a_name_taken(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = bot_record.new_name(1, 1_800_000_000, lambda n: (root / n).exists())
            (root / first).mkdir()
            self.assertEqual(bot_record.new_name(1, 1_800_000_000, lambda n: (root / n).exists()), f"{first}-2")


class CommitsTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def info(self, dragoon: str = SHA_A, engine: str = SHA_B) -> None:
        source_info.write(self.root / source_info.NAME, {"dragoon": dragoon, "gcn-recomp": engine,
                                                         "disc_id": "GKYE01", "dol_sha1": "c" * 40})

    def test_a_checkout_asks_git_for_both(self) -> None:
        dragoon = commit(self.root, {"a.txt": "a"})
        engine = commit(self.root / "gcn-recomp", {"b.txt": "b"})
        self.assertEqual(bot_record.commits(self.root), {"dragoon": dragoon, "engine": engine})

    def test_a_source_snapshot_reads_source_info(self) -> None:
        self.info()
        self.assertEqual(bot_record.commits(self.root), {"dragoon": SHA_A, "engine": SHA_B})

    def test_git_wins_in_a_tree_that_has_both(self) -> None:
        self.info()
        dragoon = commit(self.root, {"a.txt": "a"})
        engine = commit(self.root / "gcn-recomp", {"b.txt": "b"})
        self.assertEqual(bot_record.commits(self.root), {"dragoon": dragoon, "engine": engine})

    def test_each_commit_is_found_on_its_own(self) -> None:
        self.info()
        engine = commit(self.root / "gcn-recomp", {"b.txt": "b"})
        self.assertEqual(bot_record.commits(self.root), {"dragoon": SHA_A, "engine": engine})

    def test_a_tree_that_knows_neither_gives_none(self) -> None:
        self.assertEqual(bot_record.commits(self.root), {"dragoon": None, "engine": None})

    def test_a_source_info_that_is_malformed_is_not_a_commit(self) -> None:
        write_file(self.root, source_info.NAME, "{}")
        self.assertEqual(bot_record.commits(self.root), {"dragoon": None, "engine": None})

    def test_a_repository_with_no_commit_gives_none(self) -> None:
        (self.root / ".git").mkdir()
        self.assertEqual(bot_record.commits(self.root)["dragoon"], None)


class BuiltEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.session = Path(tmp.name)

    def test_it_is_the_engine_sha_the_session_recorded_with_its_dirty_mark(self) -> None:
        write_file(self.session, "session.json", json.dumps({"engine_sha": SHA_B + "-dirty", "x": 1}))
        self.assertEqual(bot_record.built_engine(self.session), SHA_B + "-dirty")

    def test_a_session_with_no_file_no_sha_or_a_bad_file_has_none(self) -> None:
        self.assertIsNone(bot_record.built_engine(self.session))  # no file
        for text in ("{}", '{"engine_sha": ""}', '{"engine_sha": 5}', "[1]", "not json", ""):
            with self.subTest(text=text):
                write_file(self.session, "session.json", text)
                self.assertIsNone(bot_record.built_engine(self.session))
        self.assertIsNone(bot_record.built_engine(self.session / "nowhere"))


class ReplayLineTest(unittest.TestCase):
    def test_it_is_the_probe_line_the_readme_gives_with_the_logs_directory(self) -> None:
        inputs = Path("/r/build/probe/soak-s1-x/session/inputs")
        line = bot_record.replay_line(Path("/r/tools/probe.sh"), "soak-s1-x", inputs, 4000)
        self.assertEqual(shlex.split(line), ["/r/tools/probe.sh", "replay-soak-s1-x", "127", "", str(bot_link.NO_DUMPS),
                                             "--replay=/r/build/probe/soak-s1-x/session/inputs", "--exit-after=4000"])

    def test_the_replay_runs_under_the_runs_name_with_replay_before_it(self) -> None:
        line = bot_record.replay_line(Path("/r/tools/probe.sh"), "n", Path("/i"), 10)
        self.assertEqual(shlex.split(line)[1], "replay-n")

    def test_the_replay_writes_no_frame_dumps_since_one_is_over_a_megabyte(self) -> None:
        for last in (None, 0, 10, 216000):
            with self.subTest(last=last):
                line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), last))
                self.assertGreaterEqual(int(line[4]), 1_000_000)
                self.assertEqual(line[4], str(bot_link.NO_DUMPS))

    def test_the_seconds_are_the_frames_at_sixty_a_second_and_a_minute(self) -> None:
        for frames, seconds in ((1, 61), (60, 61), (61, 62), (216000, 3660)):
            with self.subTest(frames=frames):
                line = bot_record.replay_line(Path("/p"), "n", Path("/i"), frames)
                self.assertEqual(shlex.split(line)[2], str(seconds))

    def test_a_run_with_no_known_last_frame_is_not_cut_short(self) -> None:
        line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), None))
        self.assertEqual((line[2], len(line)), ("3600", 6))

    def test_frame_zero_is_no_frame_to_give_since_probe_sh_refuses_an_exit_after_of_zero(self) -> None:
        line = bot_record.replay_line(Path("/p"), "n", Path("/i"), 0)
        self.assertEqual((shlex.split(line)[2], len(shlex.split(line))), ("3600", 6))
        self.assertNotIn("--exit-after", line)

    def test_the_runs_settings_go_in_the_line_before_the_replay_without_the_ones_the_soak_sets(self) -> None:
        settings = ["GCN_AXVOICES=1", "--bin=/x/build/dragoon", "DRAGOON_CENSUS=1", "GCN_SESSION=/s",
                    "--exit-after=500", "GCN_BOT=/b.sock", "--disc=/my disc.iso"]
        line = bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, settings)
        self.assertEqual(shlex.split(line), ["/p", "replay-n", "61", "", str(bot_link.NO_DUMPS), "--bin=/x/build/dragoon",
                                             "DRAGOON_CENSUS=1", "--disc=/my disc.iso", "--replay=/i",
                                             "--exit-after=10"])

    def test_the_ports_the_soak_drove_are_plugged_in_the_replay_right_after_the_dump_interval(self) -> None:
        for pads in (1, 2, 4):
            with self.subTest(pads=pads):
                line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, ["DRAGOON_CENSUS=1"],
                                                          pads=pads))
                self.assertEqual(line[4:7], [str(bot_link.NO_DUMPS), f"--pads={pads}", "DRAGOON_CENSUS=1"])

    def test_no_ports_given_leaves_pads_to_probe_shs_default(self) -> None:
        self.assertNotIn("--pads", bot_record.replay_line(Path("/p"), "n", Path("/i"), 10))

    def test_a_switch_is_left_out_only_when_it_is_one_of_the_names_the_soak_sets(self) -> None:
        kept = ["GCN_BOTTLE=1", "GCN_SESSION_DIR=/d", "GCN_AXVOICES2=1", "GCN_WAVE=1", "GCN_AIDWAVE=1",
                "--exit-after-x"]
        settings = [*kept, "GCN_AXVOICES=1", "GCN_SESSION=/s", "GCN_BOT=/b.sock", "--exit-after=500"]
        line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, settings))
        self.assertEqual(line[5:5 + len(kept)], kept)
        self.assertEqual(line[5 + len(kept):], ["--replay=/i", "--exit-after=10"])

    def test_the_recordings_are_left_out_so_the_replay_does_not_write_over_the_soaks(self) -> None:
        line = bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, ["GCN_WAV=/a.wav", "GCN_AIDWAV=/b.wav",
                                                                        "DRAGOON_CENSUS=1"])
        self.assertEqual(shlex.split(line)[5:], ["DRAGOON_CENSUS=1", "--replay=/i", "--exit-after=10"])

    def test_a_disc_or_bin_path_is_printed_absolute_since_probe_sh_reads_it_from_where_it_ran(self) -> None:
        settings = ["--disc=rel/disc.iso", "--bin=build/dragoon", "--bin=../up/dragoon", "--disc=./fast",
                    "--disc=/abs/disc.iso", "--bin=/abs/dragoon"]
        line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, settings))
        self.assertEqual(line[5:11], [f"--disc={os.path.abspath('rel/disc.iso')}", f"--bin={os.path.abspath('build/dragoon')}",
                                      f"--bin={os.path.abspath('../up/dragoon')}", f"--disc={os.path.abspath('./fast')}",
                                      "--disc=/abs/disc.iso", "--bin=/abs/dragoon"])
        self.assertTrue(all(os.path.isabs(s.split("=", 1)[1]) for s in line[5:11]))

    def test_a_disc_speed_is_not_a_path(self) -> None:
        line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, ["--disc=fast"]))
        self.assertEqual(line[5], "--disc=fast")
        line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, ["--disc=console"]))
        self.assertEqual(line[5], "--disc=console")

    def test_a_setting_with_a_space_is_quoted_in_the_line(self) -> None:
        line = bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, ["--disc=/my disc.iso"])
        self.assertIn("'--disc=/my disc.iso'", line)

    def test_no_settings_leave_the_line_as_it_was(self) -> None:
        self.assertEqual(bot_record.replay_line(Path("/p"), "n", Path("/i"), 10),
                         bot_record.replay_line(Path("/p"), "n", Path("/i"), 10, []))

    def test_a_replay_can_leave_the_exit_after_out_and_keeps_the_seconds_for_the_frames(self) -> None:
        line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), 4000, exit_after=False))
        self.assertEqual(line, ["/p", "replay-n", "127", "", str(bot_link.NO_DUMPS), "--replay=/i"])

    def test_a_path_with_a_space_is_quoted_so_the_line_runs_as_printed(self) -> None:
        line = bot_record.replay_line(Path("/my repo/tools/probe.sh"), "n", Path("/my repo/build/inputs"), 5)
        self.assertEqual(shlex.split(line)[0], "/my repo/tools/probe.sh")
        self.assertEqual(shlex.split(line)[5], "--replay=/my repo/build/inputs")
        self.assertIn("''", line)  # the empty INPUT_SCRIPT


class RecordTest(unittest.TestCase):
    def make(self, stop: Stop, resets: Resets | None = None,
             input_log: Path | None = Path("/r/session/inputs")) -> dict:
        return bot_record.record(name="soak-s3-x", seed=3, arguments={"minutes": 5.0, "modes": ["air-ride"]},
                                 commit_ids={"dragoon": SHA_A, "engine": SHA_B}, stop=stop,
                                 resets=resets or Resets(), input_log=input_log, replay="tools/probe.sh ...",
                                 frames=1234, wall_seconds=12.345,
                                 watched={"picture_hashes": False, "axv_lines": True})

    def test_it_holds_the_seed_the_commits_and_the_arguments(self) -> None:
        data = self.make(Stop(PANIC, "boom", 4500))
        self.assertEqual((data["seed"], data["commits"], data["arguments"]),
                         (3, {"dragoon": SHA_A, "engine": SHA_B}, {"minutes": 5.0, "modes": ["air-ride"]}))

    def test_it_says_how_the_run_stopped_and_when(self) -> None:
        data = self.make(Stop(PANIC, "boom", 4500))
        self.assertEqual(data["stop"], {"kind": "panic", "detail": "boom", "frame": 4500, "game_seconds": 75.0})
        self.assertEqual((data["frames_answered"], data["wall_seconds"]), (1234, 12.3))

    def test_it_says_whether_the_stop_came_after_a_console_reset(self) -> None:
        self.assertIs(self.make(Stop(HANG, "x", 1))["after_reset"], False)
        self.assertIs(self.make(Stop(HANG, "x", 1, resets_before=1))["after_reset"], True)

    def test_it_says_whether_a_console_reset_came_after_the_stop(self) -> None:
        self.assertIs(self.make(Stop(HANG, "x", 1))["before_reset"], False)
        self.assertIs(self.make(Stop(HANG, "x", None, 0, True, "/r/session"))["before_reset"], True)

    def test_it_records_the_first_resets_shader_line(self) -> None:
        resets = Resets()
        line = "[shaders] 70 programs from cache (0 from binaries, 70 compiled) in 21500 ms"
        for text in ("[reset] the game reset the console (restart, code 0)", line):
            resets.add(text)
        data = self.make(Stop(HANG, "x", 1, resets_before=1), resets)
        self.assertEqual(data["resets"], {"count": 1, "first_shaders_line": line, "first_shaders_ms": 21500})

    def test_a_run_with_no_reset_has_none_to_record(self) -> None:
        self.assertEqual(self.make(Stop(PANIC, "x", 1))["resets"],
                         {"count": 0, "first_shaders_line": None, "first_shaders_ms": None})

    def test_a_stop_with_no_frame_has_no_game_time(self) -> None:
        data = self.make(Stop(PANIC, "x", None), input_log=None)
        self.assertEqual((data["stop"]["frame"], data["stop"]["game_seconds"], data["input_log"]), (None, None, None))

    def test_it_says_which_detectors_had_something_to_read(self) -> None:
        data = self.make(Stop(PANIC, "x", 1))
        self.assertEqual(data["watched"], {"picture_hashes": False, "axv_lines": True})

    def test_the_input_log_and_the_replay_line_are_in_it(self) -> None:
        data = self.make(Stop(PANIC, "x", 1))
        self.assertEqual((data["input_log"], data["replay"]), ("/r/session/inputs", "tools/probe.sh ..."))


class WriteTest(unittest.TestCase):
    def test_bot_json_is_written_beside_the_input_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = {"seed": 3, "stop": {"kind": "panic"}, "after_reset": False}
            path = bot_record.write(Path(tmp), data)
            self.assertEqual(path, Path(tmp) / "bot.json")
            text = path.read_text()
            self.assertEqual(json.loads(text), data)
            self.assertTrue(text.endswith("}\n"))
            self.assertRegex(text, re.compile(r'^\{\n  "seed": 3,', re.M))


if __name__ == "__main__":
    unittest.main()
