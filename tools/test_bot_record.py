from __future__ import annotations

import json
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


class ReplayLineTest(unittest.TestCase):
    def test_it_is_the_probe_line_the_readme_gives_with_the_logs_directory(self) -> None:
        inputs = Path("/r/build/probe/soak-s1-x/session/inputs")
        line = bot_record.replay_line(Path("/r/tools/probe.sh"), "soak-s1-x", inputs, 4000)
        self.assertEqual(shlex.split(line), ["/r/tools/probe.sh", "replay-soak-s1-x", "127", "", "60",
                                             "--replay=/r/build/probe/soak-s1-x/session/inputs", "--exit-after=4000"])

    def test_the_replay_has_its_own_name_so_it_starts_from_a_blank_card(self) -> None:
        line = bot_record.replay_line(Path("/r/tools/probe.sh"), "n", Path("/i"), 10)
        self.assertEqual(shlex.split(line)[1], "replay-n")

    def test_the_seconds_are_the_frames_at_sixty_a_second_and_a_minute(self) -> None:
        for frames, seconds in ((1, 61), (60, 61), (61, 62), (216000, 3660)):
            with self.subTest(frames=frames):
                line = bot_record.replay_line(Path("/p"), "n", Path("/i"), frames)
                self.assertEqual(shlex.split(line)[2], str(seconds))

    def test_a_run_with_no_known_last_frame_is_not_cut_short(self) -> None:
        line = shlex.split(bot_record.replay_line(Path("/p"), "n", Path("/i"), None))
        self.assertEqual((line[2], len(line)), ("3600", 6))

    def test_a_path_with_a_space_is_quoted_so_the_line_runs_as_printed(self) -> None:
        line = bot_record.replay_line(Path("/my repo/tools/probe.sh"), "n", Path("/my repo/build/inputs"), 5)
        self.assertEqual(shlex.split(line)[0], "/my repo/tools/probe.sh")
        self.assertEqual(shlex.split(line)[5], "--replay=/my repo/build/inputs")
        self.assertIn("''", line)  # the empty INPUT_SCRIPT


class RemoveDumpsTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_frames_and_outputs_go_and_the_rest_stays(self) -> None:
        for name in ("frame_00060.png", "frame_00120.png", "output_00060.png", "stdout.txt", "panic.txt",
                     "frame_x.png", "notes_frame_00060.png"):
            write_file(self.dir, name, "x")
        self.assertEqual(bot_record.remove_dumps(self.dir), 3)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         ["frame_x.png", "notes_frame_00060.png", "panic.txt", "stdout.txt"])

    def test_a_directory_with_a_dumps_name_is_left(self) -> None:
        (self.dir / "frame_00060.png").mkdir()
        self.assertEqual(bot_record.remove_dumps(self.dir), 0)
        self.assertTrue((self.dir / "frame_00060.png").is_dir())

    def test_a_link_is_left_and_so_is_its_target(self) -> None:
        target = write_file(self.dir, "keep.png", "x")
        (self.dir / "frame_00060.png").symlink_to(target)
        self.assertEqual(bot_record.remove_dumps(self.dir), 0)
        self.assertTrue(target.exists())

    def test_a_missing_directory_has_none(self) -> None:
        self.assertEqual(bot_record.remove_dumps(self.dir / "nope"), 0)

    def test_frames_in_a_session_below_are_not_touched(self) -> None:
        (self.dir / "session").mkdir()
        write_file(self.dir / "session", "frame_00060.png", "x")
        self.assertEqual(bot_record.remove_dumps(self.dir), 0)


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
        self.assertIs(self.make(Stop(HANG, "x", 1, after_reset=True))["after_reset"], True)

    def test_it_records_the_first_resets_shader_line(self) -> None:
        resets = Resets()
        line = "[shaders] 70 programs from cache (0 from binaries, 70 compiled) in 21500 ms"
        for text in ("[reset] the game reset the console (restart, code 0)", line):
            resets.add(text)
        data = self.make(Stop(HANG, "x", 1, after_reset=True), resets)
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
