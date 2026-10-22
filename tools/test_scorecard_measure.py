import math
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

import scorecard_measure
from scorecard_measure import Score, Stage, measure, total
from testutil import write_file

BASE_LOG = """\
[ax] frames=400 voices(running, last frame)=0 peak=0 out=80571E00
[ring] fill=3141 avg=3152 trim=-0.015% underruns=1
[ax] frames=800 voices(running, last frame)=4 peak=35461 out=80571E00
[ring] fill=3262 avg=3175 trim=-0.008% underruns=3
[ax] frames=1200 voices(running, last frame)=2 peak=12140 out=80571E00
"""
CURRENT_LOG = """\
[ax] frames=400 voices(running, last frame)=0 peak=0 out=80571E00
[ax] bus list=400 main_l=0 main_r=0 main_s=0 auxa_l=0 auxa_r=0 auxa_s=0 auxb_l=0 auxb_r=0 auxb_s=0 clipped=0
[ring] fill=3141 avg=3152 trim=-0.015% underruns=0 cuts=0
[ring] cut 3200 frames at output frame 30000
[ax] frames=800 voices(running, last frame)=17 peak=35461 out=80571E00
[ax] bus list=800 main_l=35461 main_r=34861 main_s=0 auxa_l=5923 auxa_r=5874 auxa_s=0 auxb_l=0 auxb_r=0 auxb_s=0 clipped=22
[ring] fill=3262 avg=3175 trim=-0.008% underruns=2 cuts=1
[ax] bus list=1200 main_l=1 main_r=1 main_s=0 auxa_l=0 auxa_r=0 auxa_s=0 auxb_l=0 auxb_r=0 auxb_s=0 clipped=5
"""


def tone(n: int, rate: int, freq: float = 440, amp: float = 20000) -> list[int]:
    return [round(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]


def spliced(x: list[int], *cuts: int, skip: int = 37) -> list[int]:
    """X with SKIP samples thrown away at each index in CUTS (indices into the result)."""
    out = list(x)
    for at in cuts:
        out = out[:at] + out[at + skip:]
    return out


def pcm(left: list[int], right: list[int]) -> bytes:
    data = array("h", [v for f in zip(left, right) for v in f])
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


def write_wav(path: Path, left: list[int], right: list[int], rate: int = 48000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm(left, right))
    return path


class LogTest(unittest.TestCase):
    def test_a_build_whose_ring_lines_have_no_cuts_logs_no_cuts(self):
        got = scorecard_measure.ring(BASE_LOG)
        self.assertIsNone(got.cut_frames)
        self.assertEqual(got.underruns, 3)

    def test_underruns_are_the_last_fill_lines_count(self):
        self.assertEqual(scorecard_measure.ring(BASE_LOG.replace("underruns=3", "underruns=0")).underruns, 0)

    def test_a_build_that_logs_cuts_gives_each_cuts_output_frame(self):
        got = scorecard_measure.ring(CURRENT_LOG)
        self.assertEqual(got.cut_frames, [30000])
        self.assertEqual(got.underruns, 2)

    def test_a_build_that_logs_cuts_and_made_none_has_none_not_unknown(self):
        log = CURRENT_LOG.replace("[ring] cut 3200 frames at output frame 30000\n", "").replace("cuts=1", "cuts=0")
        self.assertEqual(scorecard_measure.ring(log).cut_frames, [])

    def test_no_ring_lines_means_neither_is_logged(self):
        got = scorecard_measure.ring("[ax] frames=400 voices(running, last frame)=0 peak=0 out=80571E00\n")
        self.assertIsNone(got.underruns)
        self.assertIsNone(got.cut_frames)

    def test_peak_is_the_highest_main_l_peak(self):
        self.assertEqual(scorecard_measure.peak(BASE_LOG), 35461)
        self.assertIsNone(scorecard_measure.peak("[ring] fill=1 avg=1 trim=+0.000% underruns=0\n"))

    def test_the_clamp_count_sums_every_bus_line(self):
        self.assertEqual(scorecard_measure.clamped(CURRENT_LOG), 27)

    def test_a_build_with_no_bus_lines_logs_no_clamp_count(self):
        self.assertIsNone(scorecard_measure.clamped(BASE_LOG))


class MeasureTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.log = write_file(self.dir, "stdout.txt", CURRENT_LOG)
        self.mixer = self.dir / "mixer.raw"
        self.device = self.dir / "device.wav"

    def test_mixer_clicks_on_a_block_join_are_counted_apart_from_the_rest(self):
        # One splice on the join at 20 blocks and one half a block off a join.
        x = spliced(tone(64000, 32000), 20 * 160, 100 * 160 + 80)
        self.mixer.write_bytes(pcm(x, x))
        got = measure(self.log, self.mixer, self.device).mixer
        self.assertEqual(got.clicks, 2)
        self.assertEqual(got.on_joins, 1)
        self.assertAlmostEqual(got.joins_by_chance, 2 * 5 / 160)
        self.assertAlmostEqual(got.seconds, len(x) / 32000)
        self.assertAlmostEqual(got.per_minute, 2 * 60 / (len(x) / 32000))
        self.assertIsNone(got.on_cuts)

    def test_device_clicks_on_a_logged_cut_are_counted(self):
        x = spliced(tone(96000, 48000), 30000, 70000)
        write_wav(self.device, x, x)
        score = measure(self.log, self.mixer, self.device)
        self.assertEqual(score.device.clicks, 2)
        self.assertEqual(score.device.on_cuts, 1)
        self.assertEqual(score.cuts, 1)
        self.assertIsNone(score.device.on_joins)

    def test_a_build_that_logs_no_cuts_leaves_the_cut_counts_unknown(self):
        write_file(self.dir, "stdout.txt", BASE_LOG)
        x = spliced(tone(96000, 48000), 30000)
        write_wav(self.device, x, x)
        score = measure(self.log, self.mixer, self.device)
        self.assertEqual(score.device.clicks, 1)
        self.assertIsNone(score.device.on_cuts)
        self.assertIsNone(score.cuts)
        self.assertEqual(score.underruns, 3)
        self.assertIsNone(score.clamped)

    def test_gaps_and_clipped_runs_are_counted(self):
        x = tone(48000, 48000) + [0] * 480 + tone(48000, 48000, amp=1000)
        x[70000:70003] = [32767] * 3
        write_wav(self.device, x, x)
        got = measure(self.log, self.mixer, self.device).device
        self.assertEqual(got.gaps, 1)
        self.assertEqual(got.clipped_runs, 2)  # one on each channel
        self.assertEqual(got.clipped_samples, 6)

    def test_the_log_gives_peak_and_clamp(self):
        score = measure(self.log, self.mixer, self.device)
        self.assertEqual((score.peak, score.clamped, score.underruns), (35461, 27, 2))

    def test_a_missing_recording_is_a_stage_not_recorded(self):
        x = tone(32000, 32000)
        self.mixer.write_bytes(pcm(x, x))
        score = measure(self.log, self.mixer, self.device)
        self.assertIsNotNone(score.mixer)
        self.assertIsNone(score.device)

    def test_an_empty_recording_is_an_error(self):
        self.mixer.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "no samples"):
            measure(self.log, self.mixer, self.device)


def stage(seconds: float, clicks: int, **kw) -> Stage:
    return Stage(seconds, clicks, clicks * 60 / seconds, 1, 2, 5, **kw)


class TotalTest(unittest.TestCase):
    def score(self, seconds: float, clicks: int, peak: int | None = 100, clamped: int | None = 4) -> Score:
        return Score(stage(seconds, clicks, on_joins=1, joins_by_chance=0.5),
                     stage(seconds, clicks, on_cuts=2, cuts_by_chance=0.25), 3, 1, peak, clamped)

    def test_clicks_a_minute_come_from_the_summed_seconds_not_the_mean_rate(self):
        got = total([self.score(30, 10), self.score(90, 20)])
        self.assertEqual(got.mixer.seconds, 120)
        self.assertEqual(got.mixer.clicks, 30)
        self.assertAlmostEqual(got.mixer.per_minute, 15.0)

    def test_counts_are_summed_and_the_peak_is_the_highest(self):
        got = total([self.score(30, 10, peak=100), self.score(90, 20, peak=400)])
        self.assertEqual((got.cuts, got.underruns, got.peak, got.clamped), (6, 2, 400, 8))
        self.assertEqual((got.mixer.gaps, got.mixer.clipped_runs, got.mixer.clipped_samples), (2, 4, 10))
        self.assertEqual((got.mixer.on_joins, got.mixer.joins_by_chance), (2, 1.0))
        self.assertEqual((got.device.on_cuts, got.device.cuts_by_chance), (4, 0.5))

    def test_a_value_one_route_lacks_is_unknown_in_the_total(self):
        got = total([self.score(30, 10), self.score(90, 20, peak=None, clamped=None)])
        self.assertIsNone(got.peak)
        self.assertIsNone(got.clamped)
        self.assertEqual(got.cuts, 6)

    def test_a_stage_one_route_lacks_is_missing_from_the_total(self):
        second = self.score(90, 20)
        second.device = None
        got = total([self.score(30, 10), second])
        self.assertIsNone(got.device)
        self.assertEqual(got.mixer.clicks, 30)

    def test_cut_counts_a_route_lacks_are_unknown_in_the_total(self):
        second = self.score(90, 20)
        second.device.on_cuts = second.device.cuts_by_chance = None
        got = total([self.score(30, 10), second])
        self.assertIsNone(got.device.on_cuts)
        self.assertEqual(got.device.clicks, 30)


if __name__ == "__main__":
    unittest.main()
