import tempfile
import unittest
from pathlib import Path

import stream_voices
from testutil import run_main, write_file

PB = "80579F88"
OTHER = "80579FA8"
SFX = "00DCB362"  # an effect's loop address, and its end
SFX_END = "00DD49F4"
MUSIC = "01808A02"  # a music stream's slot, and its end
MUSIC_END = "018189FF"
EARLY = "ended early"


def state(n: int, kind: str, pb: str = PB, run: int = 1, looping: int = 1, stream: int = 1,
          loop: str = SFX, end: str = SFX_END, cur: str = "00DD0195") -> str:
    return (f"[axv] list={n} pb={pb} {kind} run={run} looping={looping} stream={stream} fmt=00 src=0 "
            f"loop={loop} end={end} cur={cur} ratio=00010000")


def level(n: int, peak: int, pb: str = PB) -> str:
    return f"[axv] list={n} pb={pb} level peak={peak} cur=0180ABCD"


def text(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def one(*lines: str) -> "stream_voices.Voice":
    voices, _, _ = stream_voices.parse(text(*lines))
    assert len(voices) == 1, voices
    return voices[0]


class ParseTest(unittest.TestCase):
    def test_a_stream_that_runs_without_its_loop_flag_and_ends_after_its_first_slot_is_ended_early(self):
        # The shape of the trace in docs/dev/audio.md: the SDK never copies the loop flag, so the
        # stream runs with looping=0 and stream=0, the game moves its loop and end to the next
        # slot, and the mixer ends it 1.79 s (358 lists) after it started.
        v = one(state(3551, "run", looping=0, stream=0, loop="01808A02", end="018189FF"),
                state(3553, "set", looping=0, stream=0, loop="01818A02", end="018289FF"),
                state(3909, "end", run=0, looping=0, stream=0, loop="01818A02", end="018289FF"))
        self.assertEqual((v.start, v.how, v.end_list), (3551, EARLY, 3909))
        self.assertEqual(v.why, [stream_voices.AT_STREAM, stream_voices.MOVED])

    def test_a_voice_at_a_stream_address_that_the_mixer_ends_is_ended_early_though_the_game_moved_nothing(self):
        v = one(state(10, "run", looping=0, stream=0, loop=MUSIC, end=MUSIC_END),
                state(50, "end", run=0, looping=0, stream=0, loop=MUSIC, end=MUSIC_END))
        self.assertEqual((v.how, v.why), (EARLY, [stream_voices.AT_STREAM]))

    def test_the_pcm_ring_addresses_are_stream_addresses_too(self):
        for loop in ("0062A280", "0062A780", "018FFFFF", "01800000"):
            with self.subTest(loop=loop):
                v = one(state(10, "run", looping=0, stream=0, loop=loop),
                        state(50, "end", run=0, looping=0, stream=0, loop=loop))
                self.assertEqual(v.how, EARLY)

    def test_addresses_next_to_the_streams_are_not_stream_addresses(self):
        for loop in ("017FFFFF", "01900000", "0062A27F", "0062A281", "0062A790", "0062A180", SFX):
            with self.subTest(loop=loop):
                voices, _, others = stream_voices.parse(text(
                    state(10, "run", looping=0, stream=0, loop=loop),
                    state(50, "end", run=0, looping=0, stream=0, loop=loop)))
                self.assertEqual((voices, others), ([], 1))

    def test_a_voice_the_game_moved_with_a_set_that_the_mixer_ends_is_ended_early(self):
        v = one(state(10, "run", looping=0, stream=0), state(20, "set", looping=0, stream=0, end="00DD5000"),
                state(90, "end", run=0, looping=0, stream=0, end="00DD5000"))
        self.assertEqual((v.how, v.end_list, v.why), (EARLY, 90, [stream_voices.MOVED]))

    def test_moving_only_the_loop_address_counts(self):
        v = one(state(10, "run", looping=0, stream=0), state(20, "set", looping=0, stream=0, loop="00DCB400"),
                state(90, "end", run=0, looping=0, stream=0, loop="00DCB400"))
        self.assertEqual(v.how, EARLY)

    def test_moving_only_the_end_address_counts(self):
        v = one(state(10, "run", looping=0, stream=0), state(20, "set", looping=0, stream=0, end="00DD5000"),
                state(90, "end", run=0, looping=0, stream=0, end="00DD5000"))
        self.assertEqual(v.how, EARLY)

    def test_a_voice_moved_to_a_stream_address_gets_both_reasons(self):
        v = one(state(10, "run", looping=0, stream=0), state(20, "set", looping=0, stream=0, loop=MUSIC),
                state(90, "end", run=0, looping=0, stream=0, loop=MUSIC))
        self.assertEqual(v.why, [stream_voices.AT_STREAM, stream_voices.MOVED])

    def test_a_stream_address_the_voice_left_still_counts(self):
        v = one(state(10, "run", looping=0, stream=0, loop=MUSIC),
                state(20, "set", looping=0, stream=0, loop=SFX), state(90, "end", run=0, looping=0, stream=0))
        self.assertEqual(v.why, [stream_voices.AT_STREAM, stream_voices.MOVED])

    def test_a_voice_the_game_restarted_on_a_new_sample_with_the_loop_flag_cleared_is_not_early(self):
        # What the title route does a dozen times: the game starts a new one-shot sample on a
        # block that still runs a looping effect, with no stop between, and the mixer ends it.
        v = one(state(10, "run", looping=1, stream=0),
                state(20, "set", looping=0, stream=0, loop="012F8AA2", end="012FC2C6"),
                state(90, "end", run=0, looping=0, stream=0, loop="012F8AA2", end="012FC2C6"))
        self.assertEqual((v.how, v.why), ("ended by the mixer", []))

    def test_a_set_that_restarts_the_block_on_a_new_sample_is_not_a_move(self):
        # A one-shot started over another with no stop between: the set puts cur on the new loop.
        voices, _, others = stream_voices.parse(text(
            state(10, "run", looping=0, stream=0),
            state(20, "set", looping=0, stream=0, loop="00D13BF2", end="00D1A7C6", cur="00D13BF2"),
            state(90, "end", run=0, looping=0, stream=0, loop="00D13BF2", end="00D1A7C6", cur="00D1A7C7")))
        self.assertEqual((voices, others), ([], 1))

    def test_a_move_after_a_restart_counts(self):
        v = one(state(10, "run", looping=0, stream=0),
                state(20, "set", looping=0, stream=0, loop="00D13BF2", end="00D1A7C6", cur="00D13BF2"),
                state(30, "set", looping=0, stream=0, loop="00D1B000", end="00D1A7C6", cur="00D13F00"),
                state(90, "end", run=0, looping=0, stream=0, loop="00D1B000", end="00D1A7C6", cur="00D1A7C7"))
        self.assertEqual((v.how, v.why), (EARLY, [stream_voices.MOVED]))

    def test_a_set_that_repeats_a_restarted_samples_addresses_is_not_a_move(self):
        voices, _, others = stream_voices.parse(text(
            state(10, "run", looping=0, stream=0),
            state(20, "set", looping=0, stream=0, loop="00D13BF2", end="00D1A7C6", cur="00D13BF2"),
            state(30, "set", looping=0, stream=0, loop="00D13BF2", end="00D1A7C6", cur="00D13F00"),
            state(90, "end", run=0, looping=0, stream=0, loop="00D13BF2", end="00D1A7C6", cur="00D1A7C7")))
        self.assertEqual((voices, others), ([], 1))

    def test_a_voice_the_game_moved_while_its_loop_flag_was_set_is_not_early(self):
        v = one(state(10, "run", looping=1, stream=0),
                state(20, "set", looping=1, stream=0, end="00DD5000"),
                state(60, "set", looping=0, stream=0, end="00DD5000"),
                state(90, "end", run=0, looping=0, stream=0, end="00DD5000"))
        self.assertEqual((v.how, v.why), ("ended by the mixer", []))

    def test_a_voice_that_got_its_loop_flag_after_the_game_moved_it_is_not_early(self):
        v = one(state(10, "run", looping=0, stream=0), state(20, "set", looping=0, stream=0, end="00DD5000"),
                state(30, "set", looping=1, stream=0, end="00DD5000"),
                state(90, "end", run=0, looping=0, stream=0, end="00DD5000"))
        self.assertEqual(v.how, "ended by the mixer")

    def test_a_voice_with_the_stream_flag_that_the_game_moved_is_not_early(self):
        v = one(state(10, "run", looping=0, stream=1), state(20, "set", looping=0, stream=1, end="00DD5000"),
                state(90, "end", run=0, looping=0, stream=1, end="00DD5000"))
        self.assertEqual(v.how, "ended by the mixer")

    def test_a_move_the_game_undid_still_counts(self):
        v = one(state(10, "run", looping=0, stream=0), state(20, "set", looping=0, stream=0, end="00DD5000"),
                state(30, "set", looping=0, stream=0), state(90, "end", run=0, looping=0, stream=0))
        self.assertEqual((v.how, v.why), (EARLY, [stream_voices.MOVED]))

    def test_a_set_that_only_changes_the_loop_flag_is_not_a_move(self):
        # The voice is listed for its flags on the run line alone, which the later lines clear.
        v = one(state(10, "run", stream=0), state(20, "set", looping=0, stream=0),
                state(90, "end", run=0, looping=0, stream=0))
        self.assertEqual((v.how, v.end_list, v.why), ("ended by the mixer", 90, []))

    def test_a_set_that_repeats_the_addresses_is_not_a_move(self):
        v = one(state(10, "run"), state(20, "set", stream=0), state(90, "end", run=0, looping=0))
        self.assertEqual(v.how, "ended by the mixer")

    def test_a_game_that_moves_a_voice_and_then_stops_it_stopped_it(self):
        v = one(state(10, "run", loop=MUSIC), state(20, "set", loop="01818A02"), state(50, "stop", run=0, looping=0))
        self.assertEqual(v.how, "stopped by the game")

    def test_the_mixer_ending_a_looping_effect_it_never_moved_is_ended_by_the_mixer(self):
        v = one(state(10, "run"), state(60, "loop"), state(90, "end", run=0, looping=0))
        self.assertEqual((v.how, v.end_list, v.loops, v.why), ("ended by the mixer", 90, 1, []))

    def test_a_voice_with_neither_stream_nor_loop_flag_that_ends_in_the_ordinary_way_is_counted_not_listed(self):
        voices, _, others = stream_voices.parse(text(state(10, "run", looping=0, stream=0),
                                                     state(20, "end", run=0, looping=0, stream=0),
                                                     level(200, 900)))
        self.assertEqual((voices, others), ([], 1))

    def test_a_voice_that_ended_early_is_listed_though_it_never_had_either_flag(self):
        voices, _, others = stream_voices.parse(text(
            state(10, "run", looping=0, stream=0, loop=MUSIC), state(20, "end", run=0, looping=0, stream=0, loop=MUSIC)))
        self.assertEqual(([v.how for v in voices], others), ([EARLY], 0))

    def test_a_voice_that_the_game_stopped_and_never_flagged_is_not_counted(self):
        voices, _, others = stream_voices.parse(text(state(10, "run", looping=0, stream=0),
                                                     state(20, "stop", run=0, looping=0, stream=0)))
        self.assertEqual((voices, others), ([], 0))

    def test_a_streamed_voice_that_keeps_looping_is_still_running(self):
        v = one(state(100, "run"), state(300, "loop"), level(400, 500), state(600, "loop"),
                state(800, "loop"), level(800, 700))
        self.assertEqual((v.pb, v.start, v.loops, v.peak, v.how), (PB, 100, 3, 700, "still running"))

    def test_a_looping_voice_that_is_not_a_stream_is_listed(self):
        self.assertEqual(one(state(10, "run", stream=0)).pb, PB)

    def test_a_stream_voice_that_is_not_looping_is_listed(self):
        self.assertEqual(one(state(10, "run", looping=0)).pb, PB)

    def test_the_game_stopping_a_voice_is_stopped_by_the_game(self):
        v = one(state(10, "run"), state(50, "stop", run=0))
        self.assertEqual((v.how, v.end_list), ("stopped by the game", 50))

    def test_the_mixer_ending_a_voice_that_never_looped_is_ended_by_the_mixer(self):
        v = one(state(10, "run", looping=0), state(50, "end", run=0, looping=0))
        self.assertEqual((v.how, v.end_list), ("ended by the mixer", 50))

    def test_a_voice_the_game_stops_after_clearing_its_loop_flag_was_stopped(self):
        v = one(state(10, "run"), state(20, "set", looping=0), state(50, "stop", run=0, looping=0))
        self.assertEqual(v.how, "stopped by the game")

    def test_a_voice_slot_used_again_is_a_voice_for_each_run(self):
        voices, _, others = stream_voices.parse(text(
            state(10, "run", looping=0, stream=0), state(20, "end", run=0, looping=0, stream=0),
            state(30, "run"), state(40, "loop"), state(50, "stop", run=0),
            state(60, "run"), state(70, "loop"), state(80, "loop")))
        self.assertEqual([(v.start, v.loops, v.how) for v in voices],
                         [(30, 1, "stopped by the game"), (60, 2, "still running")])
        self.assertEqual(others, 1)

    def test_an_earlier_move_does_not_count_against_a_voice_that_starts_later_in_its_slot(self):
        voices, _, _ = stream_voices.parse(text(
            state(10, "run", looping=0, stream=0), state(15, "set", looping=0, stream=0, end="00DD5000"),
            state(20, "end", run=0, looping=0, stream=0, end="00DD5000"),
            state(30, "run", looping=0, stream=1), state(90, "loop", looping=0, stream=1)))
        self.assertEqual([(v.start, v.how) for v in voices], [(10, EARLY), (30, "still running")])

    def test_a_level_line_after_the_end_belongs_to_the_voice_that_ended(self):
        v = one(state(190, "run"), state(195, "end", run=0, looping=0), level(200, 321))
        self.assertEqual(v.peak, 321)

    def test_a_voice_keeps_the_loop_address_it_started_with(self):
        v = one(state(10, "run", loop="0062A780"), state(20, "set", loop="0062A280"),
                state(30, "loop", loop="0062A280"))
        self.assertEqual(v.at, "0062A780")

    def test_a_slot_used_again_has_the_loop_address_of_its_new_run(self):
        voices, _, _ = stream_voices.parse(text(state(10, "run", loop="0062A780"), state(20, "stop", run=0),
                                                state(30, "run", loop="01800000")))
        self.assertEqual([v.at for v in voices], ["0062A780", "01800000"])

    def test_a_voice_with_no_level_line_has_no_peak(self):
        self.assertIsNone(one(state(10, "run")).peak)

    def test_voices_are_told_apart_by_their_address(self):
        voices, _, _ = stream_voices.parse(text(
            state(10, "run", pb=PB), state(12, "run", pb=OTHER), state(20, "loop", pb=OTHER),
            state(30, "end", pb=PB, run=0, looping=0), level(200, 5, pb=OTHER)))
        self.assertEqual([(v.pb, v.loops, v.how, v.peak) for v in voices],
                         [(PB, 0, "ended by the mixer", None), (OTHER, 1, "still running", 5)])

    def test_a_voice_seen_first_mid_run_starts_at_its_first_line(self):
        v = one(state(500, "loop"), state(700, "loop"))
        self.assertEqual((v.start, v.loops, v.how), (500, 2, "still running"))

    def test_a_voice_whose_first_line_is_a_set_has_not_been_moved(self):
        v = one(state(500, "set"), state(700, "end", run=0, looping=0))
        self.assertEqual((v.how, v.why), ("ended by the mixer", []))

    def test_the_last_list_is_the_highest_any_axv_line_gives(self):
        _, last, _ = stream_voices.parse(text(state(10, "run", looping=0, stream=0), level(4800, 1)))
        self.assertEqual(last, 4800)

    def test_a_state_line_after_a_later_level_line_does_not_lower_the_last_list(self):
        _, last, _ = stream_voices.parse(text(level(4800, 1), state(10, "run")))
        self.assertEqual(last, 4800)

    def test_other_lines_and_lines_cut_off_mid_field_are_skipped(self):
        v = one("[ax] pb list=400 voice_ms=3", "[axv] list=9 pb=80579F88 run run=1 looping=1 stream=1",
                state(10, "run"),
                "[axv] list=11 pb=80579F88 loop run=1 looping=1 stream=1 fmt=00 src=0 loop=00DCB362 "
                "end=00DD49F4 cur=00DD0195 ratio=0001",
                "[axv] list=12 pb=80579F88 level peak=12 cur=0180AB",
                "[axv] list=13 pb=80579F88 level peak=1")
        self.assertEqual((v.loops, v.peak), (0, None))

    def test_a_line_cut_off_in_the_end_address_is_skipped(self):
        voices, _, _ = stream_voices.parse(text(
            state(10, "run"), "[axv] list=11 pb=80579F88 end run=0 looping=0 stream=1 fmt=00 src=0 "
                              "loop=01808A02 end=0181"))
        self.assertEqual([v.how for v in voices], ["still running"])

    def test_a_log_with_no_axv_lines_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "GCN_AXVOICES=1"):
            stream_voices.parse("[ax] pb list=400 voice_ms=3\n")


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def run_on(self, *lines: str):
        log = write_file(self.dir, "stdout.txt", text(*lines))
        return log, run_main(stream_voices.main, str(log))

    def test_prints_a_row_for_each_voice_with_its_start_loops_peak_and_end(self):
        log, (code, out, err) = self.run_on(
            state(3551, "run", loop=MUSIC), state(3700, "loop", loop=MUSIC), level(3800, 11945),
            state(3900, "loop", loop=MUSIC),
            state(4000, "run", pb=OTHER, looping=0, stream=0),
            state(4100, "stop", pb=OTHER, run=0, looping=0, stream=0),
            state(5000, "run", pb="8057A0C8", loop=MUSIC),
            state(5100, "end", pb="8057A0C8", run=0, looping=0, loop=MUSIC),
            level(19400, 1, pb="8057A0E8"))
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], f"{log}: 19400 lists, 97.000 s")
        self.assertEqual(lines[1], "2 voices listed: 1 still running, 0 stopped by the game, "
                                   "0 ended by the mixer, 1 ended early")
        self.assertEqual(lines[2], f"pb {PB}  list 3551  at {MUSIC}  loops 2  peak 11945  "
                                   "still running at the end of the log")
        self.assertEqual(len(lines), 4)

    def test_ended_early_voices_come_last_with_their_list_the_time_and_the_reason(self):
        _, (code, out, err) = self.run_on(
            state(100, "run", pb="8057A000", loop=MUSIC), state(150, "loop", pb="8057A000", loop=MUSIC),
            state(160, "end", pb="8057A000", run=0, looping=0, loop=MUSIC),
            state(200, "run", pb=PB), state(300, "run", pb=OTHER, looping=0),
            state(310, "end", pb=OTHER, run=0, looping=0),
            state(500, "run", pb="8057A020"), state(520, "stop", pb="8057A020", run=0))
        self.assertEqual((code, err), (0, ""))
        rows = out.splitlines()[2:]
        self.assertEqual([r.split()[1] for r in rows], [PB, OTHER, "8057A020", "8057A000"])
        self.assertTrue(rows[1].endswith("ended by the mixer at list 310"), rows[1])
        self.assertTrue(rows[2].endswith("stopped by the game at list 520"), rows[2])
        self.assertTrue(rows[3].endswith("ended early at list 160 (0.800 s) because its loop address is a stream's"),
                        rows[3])

    def test_a_voice_that_the_game_moved_says_so(self):
        _, (_, out, _) = self.run_on(state(1, "run", looping=0, stream=0),
                                     state(2, "set", looping=0, stream=0, end="00DD5000"),
                                     state(3, "end", run=0, looping=0, stream=0, end="00DD5000"))
        self.assertIn("ended early at list 3 (0.015 s) because the game moved its loop or end but it never "
                      "had a loop flag", out)

    def test_a_voice_with_both_reasons_gives_both(self):
        _, (_, out, _) = self.run_on(state(1, "run", looping=0, stream=0, loop=MUSIC),
                                     state(2, "set", looping=0, stream=0, loop="01818A02"),
                                     state(3, "end", run=0, looping=0, stream=0, loop="01818A02"))
        self.assertIn("because its loop address is a stream's and the game moved its loop or end but it never "
                      "had a loop flag", out)

    def test_the_audio_md_trace_is_reported_though_it_has_neither_flag(self):
        _, (code, out, err) = self.run_on(
            state(3551, "run", looping=0, stream=0, loop="01808A02", end="018189FF"),
            state(3553, "set", looping=0, stream=0, loop="01818A02", end="018289FF"),
            state(3909, "end", run=0, looping=0, stream=0, loop="01818A02", end="018289FF"))
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[1], "1 voice listed: 0 still running, 0 stopped by the game, "
                                   "0 ended by the mixer, 1 ended early")
        self.assertIn("ended early at list 3909 (19.545 s)", lines[2])

    def test_voices_that_ended_in_the_ordinary_way_without_either_flag_are_counted(self):
        _, (code, out, err) = self.run_on(
            state(3, "run", looping=0, stream=0), state(9, "end", run=0, looping=0, stream=0),
            state(10, "run", pb=OTHER, looping=0, stream=0), state(19, "end", pb=OTHER, run=0, looping=0, stream=0),
            state(20, "run", pb="8057A000"))
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[1], "1 voice listed: 1 still running, 0 stopped by the game, "
                                   "0 ended by the mixer, 0 ended early")
        self.assertEqual(lines[2], "2 other voices ended by the mixer without stream=1 or looping=1")
        self.assertEqual(len(lines), 4)

    def test_one_other_voice_is_not_plural(self):
        _, (_, out, _) = self.run_on(state(3, "run", looping=0, stream=0), state(9, "end", run=0, looping=0, stream=0))
        self.assertIn("1 other voice ended by the mixer without stream=1 or looping=1", out.splitlines())

    def test_a_voice_that_ended_early_is_reported_without_failing(self):
        _, (code, out, _) = self.run_on(state(1, "run", loop=MUSIC), state(2, "end", run=0, looping=0, loop=MUSIC))
        self.assertEqual(code, 0)
        self.assertIn("ended early at list 2 (0.010 s)", out)

    def test_five_milliseconds_a_list(self):
        _, (_, out, _) = self.run_on(state(3, "run", loop=MUSIC), state(3551, "end", run=0, looping=0, loop=MUSIC))
        self.assertIn("ended early at list 3551 (17.755 s)", out)

    def test_a_voice_that_never_got_a_level_line_says_so(self):
        _, (_, out, _) = self.run_on(state(3, "run"))
        self.assertIn("peak none", out)

    def test_a_log_with_no_voices_to_list_says_so(self):
        _, (code, out, err) = self.run_on(state(3, "run", looping=0, stream=0))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines()[1], "no voice with stream=1 or looping=1, and none ended early")
        self.assertEqual(len(out.splitlines()), 2)

    def test_a_missing_log_exits_2_with_one_line_naming_it(self):
        code, out, err = run_main(stream_voices.main, str(self.dir / "nope.txt"))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("nope.txt", err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_a_directory_in_place_of_a_log_exits_2(self):
        code, out, err = run_main(stream_voices.main, str(self.dir))
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(len(err.splitlines()), 1)

    def test_a_log_without_axv_lines_exits_2_naming_the_log_and_the_setting(self):
        log = write_file(self.dir, "stdout.txt", "[ax] frames=400\n")
        code, out, err = run_main(stream_voices.main, str(log))
        self.assertEqual((code, out), (2, ""))
        self.assertIn(str(log), err)
        self.assertIn("GCN_AXVOICES=1", err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_bytes_that_are_not_text_do_not_stop_it(self):
        log = write_file(self.dir, "stdout.txt", state(3, "run").encode() + b"\n\xff\xfe junk\n")
        code, out, _ = run_main(stream_voices.main, str(log))
        self.assertEqual(code, 0)
        self.assertIn(PB, out)

    def test_a_bad_argument_exits_2(self):
        log = write_file(self.dir, "stdout.txt", text(state(3, "run")))
        for argv in ([], [str(log), str(log)], [str(log), "--until", "5"]):
            with self.subTest(argv=argv):
                self.assertEqual(run_main(stream_voices.main, *argv)[0], 2)

    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = run_main(stream_voices.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)
        self.assertIn("GCN_AXVOICES", out)


if __name__ == "__main__":
    unittest.main()
