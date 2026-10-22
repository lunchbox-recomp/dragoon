import json
import math
import random
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

import audio_clicks
from audio_clicks import Recording
from testutil import run_main, write_file

RATE = 48000


def tone(freq: float, seconds: float, amp: float = 20000, rate: int = RATE) -> list[int]:
    return [round(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(round(seconds * rate))]


def rec(*channels: list[int]) -> Recording:
    return Recording(RATE, [array("h", ch) for ch in channels])


def write_wav(directory: Path, name: str, *channels: list[int], width: int = 2) -> Path:
    path = Path(directory, name)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(channels))
        w.setsampwidth(width)
        w.setframerate(RATE)
        if width == 1:
            w.writeframes(bytes(128 for f in zip(*channels) for _ in f))
        else:
            data = array("h", [v for f in zip(*channels) for v in f])
            if sys.byteorder == "big":
                data.byteswap()
            w.writeframes(data.tobytes())
    return path


def clicks(*channels: list[int]) -> list[float]:
    return audio_clicks.analyse(rec(*channels), 0).clicks


class ClickTest(unittest.TestCase):
    def test_steady_tones_have_no_clicks(self):
        for freq in (50, 440, 3000, 9000):
            with self.subTest(freq=freq):
                self.assertEqual(clicks(tone(freq, 0.5)), [])

    def test_tones_and_noise_together_have_none(self):
        noise = random.Random(1)
        mix = [a + b + noise.randint(-2000, 2000) for a, b in zip(tone(220, 1, 8000), tone(1760, 1, 8000))]
        self.assertEqual(clicks(mix), [])

    def test_audio_resampled_from_32k_the_way_the_engine_does_has_none(self):
        src = tone(700, 1.1, rate=32000)
        step, pos, out = 32000 / RATE * 1.005, 0.0, []
        while pos + 1 < len(src):
            a, f = int(pos), pos - int(pos)
            out.append(int(src[a] * (1 - f) + src[a + 1] * f))
            pos += step
        self.assertEqual(clicks(out), [])

    def test_a_splice_is_one_click_where_it_was_cut(self):
        t = tone(440, 1)
        got = clicks(t[:24000] + t[24037:])
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0], 0.5, delta=2 / RATE)

    def test_a_click_must_stand_8_times_over_the_waveform_around_it(self):
        # Alternating +-1000 has a second difference of 4000 at every sample. A bump of 20000
        # makes one of 44000, 11 times that; a bump of 12000 makes 28000, only 7 times.
        for bump, want in ((20000, 1), (12000, 0)):
            x = [1000 if i % 2 else -1000 for i in range(RATE)]
            x[24001] += bump
            with self.subTest(bump=bump):
                self.assertEqual(len(clicks(x)), want)

    def test_an_impulse_in_silence_is_a_click_unless_it_is_under_the_floor(self):
        for size, want in ((1000, 1), (50, 0)):
            x = [0] * RATE
            x[RATE // 2] = size
            with self.subTest(size=size):
                self.assertEqual(len(clicks(x)), want)

    def test_a_click_on_one_channel_is_one_click(self):
        left, right = tone(440, 1), tone(440, 1)
        left[30000] += 15000
        got = clicks(left, right)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0], 30000 / RATE, delta=2 / RATE)

    def test_detections_under_1_ms_apart_are_one_click(self):
        for apart, want in ((20, 1), (100, 2)):
            x = [0] * RATE
            x[20000] = x[20000 + apart] = 1000
            with self.subTest(apart=apart):
                self.assertEqual(len(clicks(x)), want)


class GapTest(unittest.TestCase):
    def test_silence_straight_after_sound_is_a_gap_of_its_length(self):
        left, right = tone(440, 1, 10000), tone(440, 1, 10000)
        for ch in (left, right):
            ch[24000:24960] = [0] * 960
        gaps = audio_clicks.analyse(rec(left, right), 0).gaps
        self.assertEqual(len(gaps), 1)
        self.assertAlmostEqual(gaps[0].at, 0.5, delta=2 / RATE)
        self.assertAlmostEqual(gaps[0].ms, 20, delta=0.1)

    def test_silence_on_one_channel_only_is_not_a_gap(self):
        left = tone(440, 1, 10000)
        left[24000:24960] = [0] * 960
        self.assertEqual(audio_clicks.analyse(rec(left, tone(440, 1, 10000)), 0).gaps, [])

    def test_a_silence_under_5_ms_is_not_a_gap(self):
        x = tone(440, 1, 10000)
        x[24000:24190] = [0] * 190
        self.assertEqual(audio_clicks.analyse(rec(x), 0).gaps, [])

    def test_a_sound_that_fades_out_first_leaves_no_gap(self):
        fade = [round(v * (1 - i / 9600)) for i, v in enumerate(tone(440, 0.2, 10000))]
        x = tone(440, 0.3, 10000) + fade + [0] * 4800 + tone(440, 0.3, 10000)
        self.assertEqual(audio_clicks.analyse(rec(x), 0).gaps, [])

    def test_silence_at_the_start_is_not_a_gap(self):
        self.assertEqual(audio_clicks.analyse(rec([0] * 4800 + tone(440, 0.5)), 0).gaps, [])


class ClipTest(unittest.TestCase):
    def test_runs_of_two_or_more_full_scale_samples(self):
        self.assertEqual(audio_clicks.clip_runs(array("h", [0, 32767, 0, 32767, 32767, 0, -32768, -32768, -32768])),
                         [(3, 2), (6, 3)])

    def test_a_peak_that_touches_full_scale_once_is_not_clipping(self):
        self.assertEqual(audio_clicks.clip_runs(array("h", [0, 32767, 0, -32768, 0])), [])

    def test_an_overdriven_tone_clips_every_half_cycle(self):
        x = [max(-32768, min(32767, v)) for v in tone(100, 0.1, 40000)]
        clipped = audio_clicks.analyse(rec(x), 0).clipped
        self.assertEqual(len(clipped), 20)
        self.assertTrue(all(c.samples >= 2 for c in clipped))


class AnalyseTest(unittest.TestCase):
    def test_from_skips_the_start_and_keeps_times_from_the_start_of_the_recording(self):
        x = [0] * RATE
        x[9600] = x[38400] = 1000
        report = audio_clicks.analyse(rec(x), 0.5)
        self.assertEqual(report.start, 0.5)
        self.assertEqual(len(report.clicks), 1)
        self.assertAlmostEqual(report.clicks[0], 0.8, delta=2 / RATE)

    def test_period_counts_clicks_on_block_joins_beside_what_chance_would_put_there(self):
        x = [0] * RATE
        for i in (160 * 50, 160 * 100, 160 * 150, 160 * 200 + 80):
            x[i] = 1000
        self.assertEqual(audio_clicks.analyse(rec(x), 0, 160).joins, audio_clicks.Joins(160, 3, 4 * 5 / 160))
        self.assertIsNone(audio_clicks.analyse(rec(x), 0).joins)

    def test_period_counts_joins_from_the_start_of_the_recording_not_from_from(self):
        x = [0] * RATE
        x[160 * 100] = 1000
        self.assertEqual(audio_clicks.analyse(rec(x), 101 / RATE, 160).joins.on_joins, 1)

    def test_marks_count_the_clicks_near_one_and_the_marks_with_a_click_beside_chance(self):
        x = [0] * RATE
        x[10000] = x[20000] = x[30000] = 1000
        got = audio_clicks.analyse(rec(x), 0, marks=[40000, 10000, 20001]).marks
        self.assertEqual(got, audio_clicks.Marks(3, 2, 2, 3 * 3 * 5 / RATE))
        self.assertIsNone(audio_clicks.analyse(rec(x), 0).marks)

    def test_marks_outside_what_is_analysed_are_left_out(self):
        x = [0] * RATE
        x[30000] = 1000
        got = audio_clicks.analyse(rec(x), 0.5, marks=[10000, 30000, RATE]).marks
        self.assertEqual(got, audio_clicks.Marks(1, 1, 1, 1 * 1 * 5 / (RATE // 2)))

    def test_from_past_the_end_is_refused(self):
        with self.assertRaisesRegex(ValueError, "--from 2 is past the end, 1.00 s"):
            audio_clicks.analyse(rec([0] * RATE), 2)


class ReadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_reads_each_channel_apart(self):
        got = audio_clicks.read_wav(write_wav(self.dir, "a.wav", [1, 2, 3], [-1, -2, -3]))
        self.assertEqual((got.rate, [list(ch) for ch in got.channels]), (RATE, [[1, 2, 3], [-1, -2, -3]]))

    def test_a_recording_cut_off_mid_frame_reads_its_whole_frames(self):
        path = write_wav(self.dir, "a.wav", [1, 2, 3], [-1, -2, -3])
        path.write_bytes(path.read_bytes()[:-1])
        self.assertEqual([list(ch) for ch in audio_clicks.read_wav(path).channels], [[1, 2], [-1, -2]])

    def test_reads_raw_little_endian_stereo_at_the_rate_given(self):
        path = write_file(self.dir, "aid.raw", bytes([1, 0, 0xFF, 0xFF, 2, 0, 0xFE, 0xFF, 3]))
        got = audio_clicks.read_raw(path, 32000)
        self.assertEqual((got.rate, [list(ch) for ch in got.channels]), (32000, [[1, 2], [-1, -2]]))

    def test_an_empty_raw_file_is_refused(self):
        path = write_file(self.dir, "aid.raw", b"")
        with self.assertRaisesRegex(ValueError, f"{path}: no samples"):
            audio_clicks.read_raw(path, 32000)

    def test_reads_marks_one_a_line_skipping_blanks_and_comments(self):
        path = write_file(self.dir, "cuts.txt", "# where the ring cut\n100\n\n200  # second\n")
        self.assertEqual(audio_clicks.read_marks(path), [100, 200])

    def test_a_mark_that_is_not_a_sample_index_is_refused(self):
        path = write_file(self.dir, "cuts.txt", "100\n12.5\n")
        with self.assertRaisesRegex(ValueError, f"{path}:2: '12.5' isn't a sample index"):
            audio_clicks.read_marks(path)

    def test_refuses_what_it_cannot_read(self):
        for name, path, msg in (
                ("8-bit", write_wav(self.dir, "b.wav", [0, 0], width=1), "8-bit samples"),
                ("not wav", write_file(self.dir, "c.wav", "hello"), "not a PCM WAV file"),
                ("empty", write_wav(self.dir, "d.wav", []), "no samples")):
            with self.subTest(name), self.assertRaisesRegex(ValueError, f"{path}: {msg}"):
                audio_clicks.read_wav(path)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        x = tone(440, 1)
        x[30000] += 15000
        self.path = write_wav(Path(tmp.name), "out.wav", x, tone(440, 1))

    def test_prints_the_length_and_each_count_with_its_times(self):
        code, out, _ = run_main(audio_clicks.main, str(self.path))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            f"{self.path}: 1.00 s, 48000 Hz, 2 channels, from 0.00 s",
            "clicks   1 (60.0 a minute)", "  0.625 s",
            "gaps     0",
            "clipped  0 runs, 0 samples"])

    def test_list_limits_the_times_and_says_how_many_more(self):
        _, out, _ = run_main(audio_clicks.main, str(self.path), "--list", "0")
        self.assertIn("clicks   1 (60.0 a minute)\n  and 1 more\n", out)

    def test_period_adds_a_line_counting_the_clicks_on_joins(self):
        _, out, _ = run_main(audio_clicks.main, str(self.path), "--period", "160")
        self.assertEqual(out.splitlines()[-1],
                         "joins    0 of 1 clicks within 2 samples of a multiple of 160 (0.0 by chance)")

    def test_marks_adds_a_line_counting_the_clicks_near_them(self):
        marks = write_file(self.path.parent, "cuts.txt", "30000\n1000\n")
        _, out, _ = run_main(audio_clicks.main, str(self.path), "--marks", str(marks))
        self.assertEqual(out.splitlines()[-1], "marks    1 of 1 clicks within 2 samples of a mark "
                                               "(0.0 by chance), 1 of 2 marks with a click")

    def test_raw_reads_the_file_as_stereo_at_the_rate_given(self):
        raw = write_file(self.path.parent, "aid.raw", self.path.read_bytes()[44:])
        _, out, _ = run_main(audio_clicks.main, str(raw), "--raw", "32000")
        self.assertEqual(out.splitlines()[:3], [f"{raw}: 1.50 s, 32000 Hz, 2 channels, from 0.00 s",
                                                "clicks   1 (40.0 a minute)", "  0.937 s"])

    def test_json_has_the_whole_result(self):
        code, out, _ = run_main(audio_clicks.main, str(self.path), "--json")
        got = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((got["seconds"], got["rate"], got["channels"], got["gaps"], got["clipped"]),
                         (1.0, RATE, 2, [], []))
        self.assertEqual(len(got["clicks"]), 1)

    def test_bad_input_exits_2_naming_it(self):
        for argv, msg in (([str(self.path) + "x"], str(self.path) + "x"),
                          ([str(self.path), "--from", "5"], "past the end"),
                          ([str(self.path), "--list", "-1"], "can't be negative"),
                          ([str(self.path), "--period", "-160"], "can't be negative"),
                          ([str(self.path), "--raw", "-1"], "can't be negative"),
                          ([str(self.path), "--marks", str(self.path) + "y"], str(self.path) + "y")):
            with self.subTest(argv=argv):
                code, _, err = run_main(audio_clicks.main, *argv)
                self.assertEqual(code, 2)
                self.assertIn(msg, err)

    def test_help_exits_0(self):
        code, out, _ = run_main(audio_clicks.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
