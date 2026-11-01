from __future__ import annotations

import contextlib
import io
import json
import re
import shlex
import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional

import bot_link
import bot_menus
import bot_record
import bot_soak
from bot_watch import engine_picture
from testengine import PICTURE_ADDR, axv, built_sha, make_tree, set_plan
from testutil import commit, run_main

SEED = "3"


def at(do: list, *, frame: Optional[int] = None, race: Optional[int] = None, process: int = 1) -> dict:
    """A plan event: DO at FRAME, or at the RACEth frame of the process's first race."""
    event: dict = {"process": process, "do": do}
    if frame is not None:
        event["frame"] = frame
    if race is not None:
        event["race"] = race
    return event


class SoakCase(unittest.TestCase):
    """A temp tree with the fake probe.sh of testengine.py, and the soak run against it."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.probe = make_tree(self.root)
        self.plan()

    def plan(self, **plan: object) -> None:
        set_plan(self.root, **plan)

    def soak(self, *argv: str, settings: tuple[str, ...] = ()) -> tuple[int, str, str]:
        """The command's exit code, stdout and stderr."""
        args = ["--probe", str(self.probe), *argv]
        if settings:
            args += ["--", *settings]
        return run_main(bot_soak.main, *args)

    def direct(self, *argv: str, picture=engine_picture, settings: tuple[str, ...] = ()) -> tuple[int, str, str]:
        """The same through `soak`, which takes the function the picture's hash comes from."""
        ap = bot_soak.parser()
        args = ap.parse_args(["--probe", str(self.probe), *argv])
        bot_soak.checked(ap, args, time.time)
        out: list[str] = []
        err: list[str] = []
        code = bot_soak.soak(args, list(settings), picture=picture, out=out.append, err=err.append)
        return code, "\n".join(out), "\n".join(err)

    def name(self, out: str) -> str:
        return out.splitlines()[0].split(":")[0]

    def run_dir(self, out: str) -> Path:
        return self.root / "build" / "probe" / self.name(out)

    def record(self, out: str) -> dict:
        return json.loads((self.run_dir(out) / "record.json").read_text())

    def bot_json(self, out: str) -> dict:
        found = list(self.run_dir(out).rglob("bot.json"))
        self.assertEqual(len(found), 1, found)
        return json.loads(found[0].read_text())

    def lines(self, out: str, start: str) -> list[str]:
        return [line for line in out.splitlines() if line.startswith(start)]


class CleanRunTest(SoakCase):
    def test_a_run_that_reaches_its_time_limit_has_no_stop(self) -> None:
        self.plan(race=100000, events=[at([["say", axv(1, "run")]], frame=10)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "0.05", "--round", "5", "--modes", "air-ride,top-ride")
        self.assertEqual((code, err), (0, ""), out)
        name = self.name(out)
        self.assertEqual(out.splitlines()[0], f"{name}: seed 3, 0.05 min, modes air-ride,top-ride, "
                                              "1 port, round 5 s, stuck 120 s, hang 30 s")
        self.assertRegex(out, rf"(?m)^{name}: no stop in \d+\.\d min \(\d+ frames, \d+ rounds?, 0 console resets\), "
                              "ended on time_limit$")
        self.assertFalse(list(self.run_dir(out).rglob("bot.json")))
        self.assertEqual(self.record(out)["visited"][0], bot_menus.BOOT)

    def test_the_game_is_played_through_the_menus_into_rounds_and_back(self) -> None:
        self.plan(race=100000)
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride", "--round", "5",
                                   settings=("--exit-after=9000",))
        self.assertEqual((code, err), (0, ""), out)
        self.assertRegex(out, r"(?m)no stop in \d+\.\d min \(9000 frames, \d+ rounds, 0 console resets\), "
                              "ended on exit_after$")
        record = self.record(out)
        self.assertGreaterEqual(len(record["started"]), 2)
        self.assertEqual({mode for mode, _ in record["started"]}, {"air"})
        said = re.findall(r"(?m)^frame \d+: round (\d+): air-ride$", out)
        rounds = int(re.search(r"9000 frames, (\d+) rounds", out)[1])
        self.assertEqual(said, [str(n) for n in range(1, rounds + 1)])
        self.assertIn(rounds - len(record["started"]), (0, 1))  # the last round may not have reached its race
        self.assertEqual(record["visited"][:7], [38, 0, 2, 23, 6, 8, 18])
        self.assertTrue(self.lines(out, "frame 300: round 1: air-ride"))

    def test_four_ports_play_a_four_player_city_trial(self) -> None:
        self.plan(race=100000)
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "city-trial", "--ports", "4",
                                   settings=("--exit-after=5000",))
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("4 ports", out.splitlines()[0])
        record = self.record(out)
        self.assertEqual(record["started"], [["city", 0]])
        self.assertIn("--pads=4", record["settings"])

    def test_the_game_gets_axvoices_the_users_settings_and_no_dumps(self) -> None:
        code, out, err = self.soak("--seed", SEED, "--minutes", "1",
                                   settings=("DRAGOON_CENSUS=1", "--real-time", "--exit-after=50"))
        self.assertEqual((code, err), (0, ""), out)
        record = self.record(out)
        self.assertEqual(record["argv"][3], str(bot_link.NO_DUMPS))
        self.assertEqual(record["settings"][:3], ["GCN_AXVOICES=1", "DRAGOON_CENSUS=1", "--real-time"])

    def test_two_runs_of_a_seed_in_one_second_get_different_names(self) -> None:
        names = []
        for _ in range(3):
            code, out, err = self.direct("--seed", "1", "--minutes", "1", settings=("--exit-after=20",))
            self.assertEqual((code, err), (0, ""), out)
            names.append(self.name(out))
        self.assertEqual(len(set(names)), 3)

    def test_a_name_with_a_directory_already_is_not_used(self) -> None:
        ap = bot_soak.parser()
        args = ap.parse_args(["--probe", str(self.probe), "--seed", "9", "--minutes", "1"])
        lines: list[str] = []
        clock = lambda: 1_800_000_000.0  # noqa: E731
        old = self.root / "build" / "probe" / bot_record.new_name(9, clock(), lambda n: False)
        old.mkdir(parents=True)
        (old / "memory-card.raw").write_text("a card an earlier run left")
        self.assertEqual(bot_soak.soak(args, ["--exit-after=20"], out=lines.append, err=lines.append, clock=clock), 0)
        self.assertEqual(lines[0].split(":")[0], old.name + "-2")
        self.assertEqual((old / "memory-card.raw").read_text(), "a card an earlier run left")

    def test_it_says_when_a_detector_had_nothing_to_read(self) -> None:
        _, out, _ = self.soak("--seed", SEED, "--minutes", "1", settings=("--exit-after=30",))
        self.assertIn("the frozen-picture check saw no frame hash, so it did not run", out)
        self.assertIn("the music check saw no [axv] lines, so it did not run", out)

    def test_it_is_quiet_about_a_detector_that_had_input(self) -> None:
        self.plan(race=100000, events=[at([["say", axv(1, "run")]], race=800)])
        code, out, _ = self.direct("--seed", SEED, "--minutes", "1", picture=lambda link: link.read(PICTURE_ADDR, 4),
                                   settings=("--exit-after=6000",))
        self.assertEqual(code, 0)
        self.assertNotIn("did not run", out)

    def test_a_ctrl_c_ends_the_command_with_the_run_named(self) -> None:
        ap = bot_soak.parser()
        args = ap.parse_args(["--probe", str(self.probe), "--seed", "9"])
        err: list[str] = []

        def interrupted(*a, **kw):
            raise KeyboardInterrupt

        code = bot_soak.soak(args, [], out=lambda text: None, err=err.append, run=interrupted)
        self.assertEqual(code, 2)
        self.assertRegex(err[0], r"^bot_soak.py: interrupted; the run is in .*build/probe/soak-s9-")


class StopTest(SoakCase):
    def stop(self, events: list, *argv: str, settings: tuple[str, ...] = (), **plan: object) -> tuple[str, dict]:
        """Runs the soak to a stop. Returns its output and bot.json."""
        self.plan(race=100000, events=events, **plan)
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", *argv, settings=settings)
        self.assertEqual((code, err), (1, ""), out)
        return out, self.bot_json(out)

    def test_a_panic_stops_the_run_and_keeps_its_input_log(self) -> None:
        out, data = self.stop([at([["panic"]], race=50)])
        self.assertEqual(data["stop"]["kind"], "panic")
        self.assertEqual(data["stop"]["detail"], "guest panic: foo.c:12: boom")
        self.assertIn("STOP panic: guest panic: foo.c:12: boom", out)
        log = Path(data["input_log"])
        self.assertTrue((log / "inputs.txt").is_file())
        self.assertTrue((log / "inputs.txt").read_text().rstrip().splitlines()[-1].startswith("# end "))

    def test_a_game_that_exits_stops_the_run(self) -> None:
        out, data = self.stop([at([["exit"]], frame=400)])
        self.assertEqual(data["stop"]["kind"], "game_exit")
        self.assertEqual(data["stop"]["detail"], "the game ended at frame 400")

    def test_the_engine_stopping_the_game_stops_the_run_with_its_line(self) -> None:
        out, data = self.stop([at([["say", "[bot] frame 399: a read outside RAM"], ["exit"]], frame=400)])
        self.assertEqual(data["stop"]["kind"], "engine_stop")
        self.assertEqual(data["stop"]["detail"], "[bot] frame 399: a read outside RAM")

    def test_no_frame_for_the_hang_limit_stops_the_run(self) -> None:
        began = time.monotonic()
        out, data = self.stop([at([["hang", 60]], frame=300)], "--hang", "1")
        self.assertLess(time.monotonic() - began, 30)
        self.assertEqual(data["stop"]["kind"], "hang")
        self.assertEqual(data["stop"]["detail"], "no frame for 1 s after frame 299")
        self.assertEqual(data["stop"]["frame"], 299)

    def test_a_pad_line_the_bot_drops_is_the_engines_stop_with_its_line(self) -> None:
        self.plan(race=100000)
        ap = bot_soak.parser()
        args = ap.parse_args(["--probe", str(self.probe), "--seed", SEED, "--minutes", "1", "--ports", "2"])
        out: list[str] = []
        err: list[str] = []

        def dropping(name, seconds, bot, **kw):
            def bot_that_drops_a_port(link):
                pads = dict(bot(link))
                if link.frame == 500:
                    del pads[2]
                return pads

            return bot_link.run(name, seconds, bot_that_drops_a_port, **kw)

        self.assertEqual(bot_soak.soak(args, [], out=out.append, err=err.append, run=dropping), 1, out)
        self.assertEqual(err, [])
        data = self.bot_json("\n".join(out))
        self.assertEqual(data["stop"]["kind"], "engine_stop")
        self.assertEqual(data["stop"]["detail"],
                         '[bot] frame 500: done without a pad line for port 2, which the bot drives: "done"')
        self.assertEqual(data["stop"]["frame"], 500)

    def test_a_hangs_replay_has_no_exit_after_since_the_replay_may_not_reach_the_hang(self) -> None:
        out, data = self.stop([at([["hang", 60]], frame=300)], "--hang", "1")
        self.assertEqual(data["stop"]["kind"], "hang")
        log = Path(data["input_log"])
        self.assertEqual(shlex.split(data["replay"])[2:], ["65", "", str(bot_link.NO_DUMPS), f"--replay={log}"])
        self.assertNotIn("--exit-after", data["replay"])

    def test_a_music_stream_that_ends_early_stops_the_run(self) -> None:
        out, data = self.stop([at([["say", axv(100, "run")], ["say", axv(120, "end")]], race=10)])
        self.assertEqual(data["stop"]["kind"], "music_cut")
        self.assertIn("a music stream ended early: pb 80579F88  list 100", data["stop"]["detail"])
        self.assertTrue(data["watched"]["axv_lines"])

    def test_the_stop_is_at_the_look_after_the_line_and_not_before(self) -> None:
        out, data = self.stop([at([["say", axv(100, "run")], ["say", axv(120, "end")]], frame=2000)])
        self.assertTrue(2000 <= data["stop"]["frame"] < 2000 + 60 + 1, data["stop"]["frame"])

    def test_a_cut_in_the_last_second_is_found_after_the_run_ends(self) -> None:
        out, data = self.stop([at([["say", axv(100, "run")], ["say", axv(120, "end")]], frame=2010)],
                              settings=("--exit-after=2030",))
        self.assertEqual(data["stop"]["kind"], "music_cut")

    def test_a_menu_screen_that_stays_up_stops_the_run(self) -> None:
        out, data = self.stop([at([["screen", 12]], frame=300)], "--stuck", "3")
        self.assertEqual(data["stop"]["kind"], "menus_stuck")
        self.assertRegex(data["stop"]["detail"], r"^screen 12 \(not named in kar_ram.json\) has stayed up for 3 s ")
        self.assertIn("screen 12 isn't in kar_ram.json; pressing A", out)

    def test_a_frozen_picture_stops_the_run(self) -> None:
        self.plan(race=100000, events=[at([["freeze_picture"]], race=30)])
        code, out, err = self.direct("--seed", SEED, "--minutes", "1",
                                     picture=lambda link: link.read(PICTURE_ADDR, 4))
        self.assertEqual((code, err), (1, ""), out)
        data = self.bot_json(out)
        self.assertEqual(data["stop"]["kind"], "frozen_picture")
        self.assertRegex(data["stop"]["detail"], r"^the picture's hash 0000[0-9a-f]{4} stayed the same from frame \d+ "
                                                 r"to frame \d+, 10.0 s of game time, while the bots' input changed")
        self.assertTrue(data["watched"]["picture_hashes"])
        self.assertIn("STOP frozen_picture:", out)
        self.assertNotIn("saw no frame hash", out)

    def test_a_picture_that_keeps_changing_does_not_stop_the_run(self) -> None:
        self.plan(race=100000)
        code, out, err = self.direct("--seed", SEED, "--minutes", "1", picture=lambda link: link.read(PICTURE_ADDR, 4),
                                     settings=("--exit-after=4000",))
        self.assertEqual((code, err), (0, ""), out)

    def test_a_frozen_picture_in_a_menu_is_not_a_stop(self) -> None:
        self.plan(race=100000, events=[at([["freeze_picture"]], frame=0)])
        code, out, err = self.direct("--seed", SEED, "--minutes", "1", "--modes", "air-ride",
                                     picture=lambda link: link.read(PICTURE_ADDR, 4), settings=("--exit-after=1000",))
        self.assertEqual((code, err), (0, ""), out)
        # The menus had the pads for most of the 1000 frames, pressing, under a picture that never changed.
        self.assertEqual(self.record(out)["frame"], 1000)

    def test_bot_json_holds_the_seed_the_arguments_and_the_commits(self) -> None:
        dragoon = commit(self.root, {"README": "x"})
        engine = commit(self.root / "gcn-recomp", {"engine": "y"})
        out, data = self.stop([at([["panic"]], race=50)], "--modes", "air-ride,city-trial", "--ports", "2",
                              "--round", "90", "--stuck", "60", "--hang", "20")
        self.assertEqual(data["seed"], 3)
        self.assertEqual(data["name"], self.name(out))
        self.assertEqual(data["commits"], {"dragoon": dragoon, "engine": engine, "engine_built": built_sha(1)})
        self.assertEqual(data["arguments"], {"seed": 3, "minutes": 1.0, "modes": ["air-ride", "city-trial"],
                                             "ports": 2, "round_seconds": 90.0, "stuck_seconds": 60.0, "hang": 20.0,
                                             "settings": []})
        self.assertIs(data["after_reset"], False)
        self.assertEqual(data["resets"], {"count": 0, "first_shaders_line": None, "first_shaders_ms": None})
        self.assertEqual(data["watched"], {"picture_hashes": False, "axv_lines": False})
        self.assertGreater(data["frames_answered"], 100)

    def test_the_engine_built_is_the_one_the_stops_own_session_recorded(self) -> None:
        self.plan(race=100000, events=[at([["reset", {"shaders_ms": 100}]], frame=500),
                                       at([["panic"]], frame=700, process=2)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride")
        self.assertEqual((code, err), (1, ""), out)
        data = self.bot_json(out)
        self.assertEqual(Path(data["input_log"]).parent.name, "run-2")
        self.assertEqual(data["commits"]["engine_built"], built_sha(2))

    def test_the_engine_built_for_a_cut_before_a_reset_is_the_earlier_processs(self) -> None:
        self.plan(race=100000, events=[at([["say", axv(100, "run")], ["say", axv(120, "end")],
                                           ["reset", {"shaders_ms": 100}]], frame=2010)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride")
        self.assertEqual((code, err), (1, ""), out)
        self.assertEqual(self.bot_json(out)["commits"]["engine_built"], built_sha(1))

    def test_a_session_with_no_session_json_has_no_engine_built(self) -> None:
        self.plan(race=100000, events=[at([["panic"]], race=50)])
        ap = bot_soak.parser()
        args = ap.parse_args(["--probe", str(self.probe), "--seed", SEED, "--minutes", "1"])
        out: list[str] = []

        def forgetting(name, seconds, bot, **kw):
            outcome = bot_link.run(name, seconds, bot, **kw)
            (outcome.input_log.parent / "session.json").unlink()
            return outcome

        self.assertEqual(bot_soak.soak(args, [], out=out.append, err=out.append, run=forgetting), 1, out)
        self.assertIsNone(self.bot_json("\n".join(out))["commits"]["engine_built"])

    def test_bot_json_is_beside_the_input_log(self) -> None:
        out, data = self.stop([at([["panic"]], race=50)])
        log = Path(data["input_log"])
        self.assertEqual(log.name, "inputs")
        self.assertEqual(self.bot_json_path(out), log.parent / "bot.json")

    def bot_json_path(self, out: str) -> Path:
        return list(self.run_dir(out).rglob("bot.json"))[0]

    def test_the_stop_prints_the_replay_line_that_plays_the_log_back(self) -> None:
        out, data = self.stop([at([["panic"]], race=50)])
        line = self.lines(out, "  replay: ")[0][len("  replay: "):]
        self.assertEqual(line, data["replay"])
        words = shlex.split(line)
        name = self.name(out)
        self.assertEqual(words[:2], [str(self.probe), f"replay-{name}"])
        self.assertEqual(words[3:6], ["", str(bot_link.NO_DUMPS), f"--replay={data['input_log']}"])
        self.assertEqual(words[6], f"--exit-after={data['stop']['frame']}")

    def test_the_replay_line_carries_the_runs_settings_but_not_the_ones_the_soak_sets(self) -> None:
        out, data = self.stop([at([["panic"]], race=50)], settings=("--bin=/x/build/dragoon", "DRAGOON_CENSUS=1"))
        words = shlex.split(data["replay"])
        self.assertEqual(words[5:], ["--bin=/x/build/dragoon", "DRAGOON_CENSUS=1", f"--replay={data['input_log']}",
                                     f"--exit-after={data['stop']['frame']}"])
        for left_out in ("GCN_AXVOICES", "GCN_SESSION", "GCN_BOT", "--pads"):
            self.assertNotIn(left_out, data["replay"])

    def test_the_stop_prints_where_and_when_it_was(self) -> None:
        out, data = self.stop([at([["panic"]], race=50)])
        frame = data["stop"]["frame"]
        self.assertRegex(out, rf"(?m)^  at frame {frame}, \d+\.\d s of game time, after \d+ s of wall time$")
        self.assertRegex(out, rf"(?m)^  run {self.run_dir(out)}$")
        self.assertRegex(out, rf"(?m)^  input log {data['input_log']}$")
        self.assertNotIn("console reset", "\n".join(self.lines(out, "  after")))

    def test_a_game_that_shuts_itself_down_stops_the_run(self) -> None:
        out, data = self.stop([at([["shutdown"]], frame=400)])
        self.assertEqual(data["stop"]["kind"], "game_exit")
        self.assertEqual(data["stop"]["detail"], "[reset] the game reset the console (shutdown, code 0)")
        self.assertEqual(data["stop"]["frame"], 399)
        self.assertIn("STOP game_exit: [reset] the game reset the console (shutdown, code 0)", out)
        self.assertEqual(data["resets"]["count"], 0)
        self.assertIs(data["after_reset"], False)

    def test_a_game_that_runs_to_the_frame_the_user_gave_is_not_a_stop(self) -> None:
        self.plan(race=100000)
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", settings=("--exit-after=400",))
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("ended on exit_after", out)
        self.assertFalse(list(self.run_dir(out).rglob("bot.json")))

    def test_a_game_that_exits_before_the_frame_the_user_gave_stops_the_run(self) -> None:
        out, data = self.stop([at([["exit"]], frame=300)], settings=("--exit-after=400",))
        self.assertEqual((data["stop"]["kind"], data["stop"]["detail"]), ("game_exit", "the game ended at frame 300"))

    def test_a_stop_exits_1_and_a_clean_end_0(self) -> None:
        self.plan(events=[at([["panic"]], frame=100)])
        self.assertEqual(self.soak("--seed", SEED, "--minutes", "1")[0], 1)
        self.plan()
        self.assertEqual(self.soak("--seed", SEED, "--minutes", "1", settings=("--exit-after=100",))[0], 0)


class ResetTest(SoakCase):
    def test_a_reset_is_counted_and_the_walker_starts_over_from_the_boot(self) -> None:
        self.plan(race=100000, events=[at([["reset", {"shaders_ms": 2107}]], race=40)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride",
                                   settings=("--exit-after=4500",))
        self.assertEqual((code, err), (0, ""), out)
        self.assertRegex(out, r"(?m)no stop in \d+\.\d min \(\d+ frames, \d+ rounds?, 1 console reset\), "
                              "ended on exit_after$")
        self.assertIn("the first reset: [shaders] 70 programs from cache (0 from binaries, 70 compiled, "
                      "0 of them from the game's key list) in 2107 ms", out)
        self.assertNotIn("hang limit", out)
        record = self.record(out)
        self.assertEqual(record["processes"], 2)
        self.assertEqual(record["visited"][:7], [38, 0, 2, 23, 6, 8, 18])

    def test_a_stop_after_a_reset_says_so_and_keeps_the_new_processs_log(self) -> None:
        self.plan(race=100000, events=[at([["reset", {"shaders_ms": 2107}]], race=40),
                                       at([["panic"]], race=60, process=2)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride")
        self.assertEqual((code, err), (1, ""), out)
        data = self.bot_json(out)
        self.assertIs(data["after_reset"], True)
        self.assertEqual(data["resets"]["count"], 1)
        self.assertEqual(data["resets"]["first_shaders_ms"], 2107)
        self.assertTrue(data["resets"]["first_shaders_line"].endswith("in 2107 ms"))
        log = Path(data["input_log"])
        self.assertEqual(log.parent.name, "run-2")
        self.assertEqual(self.bot_json_path(out), log.parent / "bot.json")
        self.assertIn("  after 1 console reset; a replay starts from the card as it stood at the last reset", out)
        self.assertNotIn("blank card", out)

    def bot_json_path(self, out: str) -> Path:
        return list(self.run_dir(out).rglob("bot.json"))[0]

    def test_a_cut_just_before_a_reset_is_kept_with_the_process_it_was_in(self) -> None:
        self.plan(race=100000, events=[at([["say", axv(100, "run")], ["say", axv(120, "end")],
                                           ["reset", {"shaders_ms": 2107}]], frame=2010)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride")
        self.assertEqual((code, err), (1, ""), out)
        data = self.bot_json(out)
        self.assertEqual(data["stop"]["kind"], "music_cut")
        self.assertEqual((data["after_reset"], data["before_reset"]), (False, True))
        self.assertEqual((data["resets"]["count"], data["resets"]["first_shaders_ms"]), (1, 2107))
        self.assertEqual((data["stop"]["frame"], data["stop"]["game_seconds"]), (None, None))
        log = Path(data["input_log"])
        self.assertEqual(log, self.run_dir(out) / "session" / "inputs")  # the first process's, not run-2's
        self.assertEqual(self.bot_json_path(out), log.parent / "bot.json")
        self.assertEqual(shlex.split(data["replay"])[5:], [f"--replay={log}"])  # and no --exit-after to give
        self.assertIn("  a console reset came after it, so the last process's replay can't show it; the input log "
                      "and replay below are for the process it happened in", out)
        self.assertIn(f"  input log {log}", out)
        self.assertNotRegex(out, r"(?m)^  at frame")
        self.assertNotIn("--exit-after=0", out)

    def test_a_cut_in_the_last_second_after_a_reset_is_after_it(self) -> None:
        self.plan(race=100000, events=[at([["reset", {"shaders_ms": 100}]], frame=500),
                                       at([["say", axv(100, "run")], ["say", axv(120, "end")]], frame=2010,
                                          process=2)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride",
                                   settings=("--exit-after=2030",))
        self.assertEqual((code, err), (1, ""), out)
        data = self.bot_json(out)
        self.assertEqual(data["stop"]["kind"], "music_cut")
        self.assertEqual((data["after_reset"], data["before_reset"]), (True, False))
        self.assertEqual(data["stop"]["frame"], 2029)
        log = Path(data["input_log"])
        self.assertEqual(log.parent.name, "run-2")
        self.assertEqual(shlex.split(data["replay"])[5:], [f"--replay={log}", "--exit-after=2029"])

    def test_a_slow_restart_is_warned_about_as_it_happens(self) -> None:
        self.plan(race=100000, events=[at([["reset", {"shaders_ms": 25000}]], race=40),
                                       at([["panic"]], frame=500, process=2)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride")
        self.assertEqual((code, err), (1, ""), out)
        self.assertIn("that is a good part of the 30 s hang limit, and a hang after it may be only that rebuild; "
                      "run again with a higher --hang", out)
        self.assertLess(out.index("in 25000 ms"), out.index("hang limit"))

    def test_a_hang_after_a_slow_restart_names_the_restart(self) -> None:
        self.plan(race=100000, events=[at([["reset", {"shaders_ms": 1500}]], race=40),
                                       at([["hang", 60]], frame=5, process=2)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride", "--hang", "2")
        self.assertEqual((code, err), (1, ""), out)
        data = self.bot_json(out)
        self.assertEqual(data["stop"]["kind"], "hang")
        self.assertIn("The first reset's shader rebuild took 1.5 s of the 2 s hang limit", data["stop"]["detail"])
        self.assertIs(data["after_reset"], True)

    def test_a_shutdown_after_a_reset_is_an_exit_and_does_not_count_as_a_second_reset(self) -> None:
        self.plan(race=100000, events=[at([["reset", {"shaders_ms": 100}]], race=40),
                                       at([["shutdown"]], frame=500, process=2)])
        code, out, err = self.soak("--seed", SEED, "--minutes", "1", "--modes", "air-ride")
        self.assertEqual((code, err), (1, ""), out)
        data = self.bot_json(out)
        self.assertEqual(data["stop"]["kind"], "game_exit")
        self.assertEqual(data["resets"]["count"], 1)
        self.assertIs(data["after_reset"], True)


class RefusalTest(SoakCase):
    def test_a_game_that_never_links_is_exit_2_with_no_bot_json(self) -> None:
        self.plan(refuse="usage: probe.sh NAME SECONDS")
        code, out, err = self.soak("--seed", SEED, "--minutes", "0.1")
        self.assertEqual(code, 2)
        self.assertEqual(err.strip(), "bot_soak.py: never_linked: usage: probe.sh NAME SECONDS")
        self.assertFalse(list(self.run_dir(out).rglob("bot.json")))

    def test_a_game_whose_connect_fails_is_exit_2_with_the_engines_line(self) -> None:
        self.plan(connect_fails=True)
        code, out, err = self.soak("--seed", SEED, "--minutes", "0.1")
        self.assertEqual(code, 2)
        self.assertRegex(err, r"^bot_soak.py: connect_failed: --bot .*: can't connect: Connection refused$")
        self.assertFalse(list(self.run_dir(out).rglob("bot.json")))

    def test_a_bot_that_raises_something_else_is_exit_2_with_its_traceback(self) -> None:
        self.plan(race=100000)

        def broken(link):
            raise KeyError("scene.minor")

        code, out, err = self.direct("--seed", SEED, "--minutes", "1", picture=broken)
        self.assertEqual(code, 2)
        self.assertIn("bot_soak.py: a bot raised KeyError: 'scene.minor'", err)
        self.assertIn("Traceback (most recent call last)", err)
        self.assertFalse(list(self.run_dir(out).rglob("bot.json")))

    def test_a_missing_probe_is_exit_2(self) -> None:
        self.probe.unlink()
        code, out, err = self.soak("--seed", SEED)
        self.assertEqual(code, 2)
        self.assertRegex(err, r"^bot_soak.py: no .*probe.sh$")


class ArgumentTest(SoakCase):
    def refused(self, *argv: str) -> str:
        code, out, err = self.soak(*argv)
        self.assertEqual((code, out), (2, ""))
        return err

    def test_the_modes_are_air_ride_top_ride_and_city_trial(self) -> None:
        self.assertIn("'air' isn't one of air-ride, top-ride, city-trial", self.refused("--modes", "air"))
        self.assertIn("names a mode twice", self.refused("--modes", "air-ride,air-ride"))

    def test_ports_are_one_to_four(self) -> None:
        for ports in ("5", "0"):
            self.assertIn("argument --ports: invalid choice", self.refused("--ports", ports))

    def test_the_seed_is_a_whole_number_from_zero(self) -> None:
        self.assertIn("--seed is a whole number from 0", self.refused("--seed", "-1"))
        self.assertIn("invalid int value", self.refused("--seed", "1.5"))

    def test_the_times_are_finite_numbers_above_zero(self) -> None:
        for name in ("minutes", "round", "stuck", "hang"):
            for value in ("0", "-1", "-inf", "nan", "inf", "infinity"):
                with self.subTest(name=name, value=value):
                    ap = bot_soak.parser()
                    args = ap.parse_args([f"--{name}={value}"])
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                        bot_soak.checked(ap, args, time.time)
                    self.assertEqual(caught.exception.code, 2)
                    self.assertIn(f"--{name} is a finite number above 0", err.getvalue())

    def test_a_time_that_is_not_finite_is_refused_before_anything_is_run(self) -> None:
        for argv in (["--minutes", "inf"], ["--hang", "nan"], ["--minutes", "nan"], ["--hang", "inf"]):
            with self.subTest(argv=argv):
                code, out, err = self.soak(*argv)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("is a finite number above 0", err)
        self.assertFalse((self.root / "build").exists())

    def test_nothing_is_run_for_a_bad_argument(self) -> None:
        self.refused("--ports", "5")
        self.assertFalse((self.root / "build").exists())

    def test_help_prints_the_usage_and_what_it_stops_on(self) -> None:
        code, out, _ = self.soak("--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage: bot_soak.py", out)
        for text in ("the game exits, shuts itself down, panics", "no frame for --hang", "the picture's hash stays the same",
                     "a music stream ends early"):
            self.assertIn(text, out)

    def test_the_seed_defaults_to_one_from_the_clock(self) -> None:
        ap = bot_soak.parser()
        args = ap.parse_args([])
        bot_soak.checked(ap, args, lambda: 1_800_000_123.9)
        self.assertEqual(args.seed, 1_800_000_123 % 1_000_000)

    def test_the_defaults_are_ten_minutes_all_three_modes_one_port_and_a_thirty_second_hang(self) -> None:
        args = bot_soak.parser().parse_args([])
        self.assertEqual((args.minutes, args.modes, args.ports, args.round, args.stuck, args.hang),
                         (10, ["air-ride", "top-ride", "city-trial"], 1, 120, 120, 30))


class RunOptionsTest(SoakCase):
    def test_the_run_is_given_a_hang_no_dumps_and_a_new_session(self) -> None:
        seen: dict = {}

        def fake_run(name, seconds, bot, **kw):
            seen.update(kw, name=name, seconds=seconds)
            return bot_link.Outcome(0, None, bot_link.TIME_LIMIT, "", self.root, None)

        ap = bot_soak.parser()
        args = ap.parse_args(["--probe", str(self.probe), "--seed", "1", "--minutes", "2", "--ports", "3",
                              "--hang", "12"])
        out: list[str] = []
        self.assertEqual(bot_soak.soak(args, ["--real-time"], out=out.append, err=out.append, run=fake_run), 0)
        self.assertEqual((seen["seconds"], seen["pads"], seen["every"], seen["hang"]), (120, 3, None, 12.0))
        self.assertEqual(seen["settings"], ["GCN_AXVOICES=1", "--real-time"])
        self.assertEqual(seen["probe"], self.probe)
        self.assertRegex(seen["name"], r"^soak-s1-\d{8}-\d{6}$")


if __name__ == "__main__":
    unittest.main()
