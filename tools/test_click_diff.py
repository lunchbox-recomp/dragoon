from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from array import array
from pathlib import Path

import click_diff
from audio_clicks import Recording
from testutil import pcm, run_main, spliced, tone, write_file

RATE = 32000


def rec(*channels: list[int]) -> Recording:
    return Recording(RATE, [array("h", ch) for ch in channels])


class DiffTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def diff(self, a: list[int], b: list[int], seconds: float | None = None) -> click_diff.Diff:
        return click_diff.diff(write_file(self.dir, "a.raw", pcm(a, a)), write_file(self.dir, "b.raw", pcm(b, b)),
                               seconds)

    def test_the_same_recording_twice_has_no_one_sided_clicks(self):
        x = spliced(tone(32000, RATE), 9000)
        got = self.diff(x, x)
        self.assertEqual((got.a_clicks, got.b_clicks, got.only_a, got.only_b), (1, 1, 0, 0))
        self.assertEqual(got.same_samples, 1.0)

    def test_a_sound_b_adds_over_as_silence_steps_at_a_join(self):
        # B starts a stream on the join at block 100 and A stays silent, as fd1f6a8's intro stream did.
        # A click is reported at its first detection, which is a sample before the step.
        a = [0] * 32000
        b = [0] * 16000 + tone(16018, RATE)[18:]
        got = self.diff(a, b)
        self.assertEqual((got.a_clicks, got.only_b, got.other_silent, got.join_steps), (0, 1, 1, 1))
        c = got.clicks[0]
        self.assertEqual((c.build, c.offset, c.a_silent, c.b_silent, c.join_step), ("B", 159, True, False, True))
        self.assertGreater(c.diff_peak, 19000)
        self.assertGreater(c.diff_d2, 0)
        self.assertEqual(got.same_samples, (16000 + b[16000:].count(0)) / 32000)

    def test_a_sound_that_starts_mid_block_doesnt_step_at_a_join(self):
        a = [0] * 32000
        b = [0] * 16080 + tone(15938, RATE)[18:]
        c = self.diff(a, b).clicks[0]
        self.assertEqual((c.offset, c.join_step), (79, False))

    def test_a_join_where_b_minus_a_moves_no_more_than_around_it_isnt_a_step(self):
        # B - A is a quiet tone across the join at 8000 with a tick just after it.
        b = tone(32000, RATE, amp=1000)
        b[8003] += 3000
        got = self.diff([0] * 32000, b)
        self.assertEqual(got.only_b, 1)
        self.assertEqual((got.clicks[0].offset // 4, got.clicks[0].join_step), (0, False))

    def test_a_click_only_a_has_is_reported_as_as(self):
        a = tone(32000, RATE)
        a[5000] += 6000
        got = self.diff(a, tone(32000, RATE))
        self.assertEqual((got.only_a, got.only_b, got.other_silent), (1, 0, 0))
        c = got.clicks[0]
        self.assertEqual((c.build, c.a_silent, c.b_silent, c.join_step), ("A", False, False, False))
        self.assertEqual(c.diff_peak, 6000)

    def test_the_same_edge_in_both_is_one_sided_when_only_whats_around_it_differs(self):
        # Both builds tick at 8000 out of silence, and B gets loud 3 ms later, so B's tick
        # doesn't stand out from the 5 ms around it. B - A is silent at the tick itself.
        a = [0] * 32000
        a[8000] = 300
        b = list(a)
        b[8096:] = tone(32000 - 8096, RATE, freq=3000)
        got = self.diff(a, b)
        self.assertEqual((got.only_a, got.same_edge), (1, 1))
        self.assertEqual(got.clicks[0].diff_d2, 0)

    def test_both_are_cut_to_the_shorter_or_to_the_seconds_given(self):
        a, b = tone(16000, RATE), spliced(tone(32000, RATE), 24000)
        self.assertEqual((self.diff(a, b).seconds, self.diff(a, b).b_clicks), (0.5, 0))
        self.assertEqual(self.diff(b, b, 0.8).b_clicks, 1)
        with self.assertRaisesRegex(ValueError, r"a.raw: 0.50 s recorded, short of 0.8 s"):
            self.diff(a, b, 0.8)

    def test_a_sample_is_the_same_only_when_every_channel_is(self):
        # The right channel is one step off in the second half and the left is the same throughout.
        x = tone(32000, RATE)
        right = x[:16000] + [v + 1 for v in x[16000:]]
        a, b = write_file(self.dir, "a.raw", pcm(x, x)), write_file(self.dir, "b.raw", pcm(x, right))
        self.assertEqual(click_diff.diff(a, b).same_samples, 0.5)


class UnmatchedTest(unittest.TestCase):
    def test_a_click_is_shared_when_the_other_has_one_within_1_ms_either_side(self):
        # 1 ms is 32 samples.
        for gap, shared in ((31, True), (32, True), (33, False)):
            for sign in (1, -1):
                with self.subTest(gap=gap, sign=sign):
                    self.assertEqual(click_diff.unmatched([1000], [1000 + sign * gap]), [] if shared else [1000])

    def test_only_the_clicks_with_no_partner_are_left(self):
        self.assertEqual(click_diff.unmatched([100, 5000, 9000], [110, 9100]), [5000, 9000])
        self.assertEqual(click_diff.unmatched([100], []), [100])


class DescribeTest(unittest.TestCase):
    def test_the_second_difference_and_the_peak_are_taken_around_the_click(self):
        # B - A is 1000, 5000, 2000 across the click at 300 and 9000 a hundred samples before it.
        n, i = 600, 300
        left = [0] * n
        left[i - 1:i + 2] = [1000, 5000, 2000]
        left[i - 100] = 9000
        got = click_diff.describe(i, "B", -20.0, rec([1] * n, [1] * n), rec([0] * n, [0] * n), [left, [0] * n])
        self.assertEqual((got.diff_d2, got.diff_peak), (7000, 9000))
        self.assertEqual((got.a_silent, got.b_silent, got.offset), (False, True, i % 160))

    def test_the_peak_covers_160_samples_either_side_of_the_click_and_no_more(self):
        n, i = 1000, 500  # 5 ms is 160 samples
        for at, counts in ((i - 161, False), (i - 160, True), (i + 160, True), (i + 161, False)):
            with self.subTest(at=at):
                left = [0] * n
                left[at] = 7000
                got = click_diff.describe(i, "B", -20.0, rec([1] * n, [1] * n), rec([0] * n, [0] * n),
                                          [left, [0] * n])
                self.assertEqual(got.diff_peak, 7000 if counts else 0)

    def test_silence_needs_every_channel(self):
        r = rec([0] * 100, [0] * 50 + [5] * 50)
        self.assertEqual((click_diff.silent(r, 0, 50), click_diff.silent(r, 0, 100)), (True, False))

    def test_a_step_must_be_over_8_times_the_differences_around_it_and_at_least_8(self):
        # Flat, then up by STEP. Nothing else moves, so the floor of 1 on the RMS sets the bar.
        for step, stepping in ((8, False), (9, True)):
            with self.subTest(step=step):
                self.assertEqual(click_diff.steps_at([0] * 10 + [step] * 10, 10), stepping)


    def test_a_step_is_judged_against_the_wobble_on_both_sides_of_it(self):
        # The step is 500. Against silence that's a step. Against 100 samples of wobble, 200 a
        # sample, on either side it isn't, so neither side of the 5 ms window may be left out.
        j = 500
        flat = [0] * j + [500] * j
        self.assertTrue(click_diff.steps_at(flat, j))
        left, right = list(flat), list(flat)
        for k in range(j - 100, j):
            left[k] = 100 if k % 2 else -100
        left[j:] = [left[j - 1] + 500] * j
        for k in range(j + 1, j + 101):
            right[k] = 500 + (100 if k % 2 else -100)
        for side, d in (("left", left), ("right", right)):
            with self.subTest(side):
                self.assertEqual(d[j] - d[j - 1], 500)
                self.assertFalse(click_diff.steps_at(d, j))


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        a = [0] * 32000
        b = [0] * 16000 + tone(16018, RATE)[18:]
        self.a = write_file(self.dir, "a.raw", pcm(a, a))
        self.b = write_file(self.dir, "b.raw", pcm(b, b))

    def test_prints_the_counts_then_each_one_sided_click(self):
        code, out, _ = run_main(click_diff.main, str(self.a), str(self.b))
        self.assertEqual(code, 0)
        self.assertIn("clicks   A 0, B 1, only A 0, only B 1", out)
        self.assertIn("the other build silent 1", out)
        self.assertRegex(out, r"0\.500 s only B, .* A silent, B sounding, B-A steps at a join\n")

    def test_an_offset_of_one_sample_reads_in_the_singular(self):
        for offset, text in ((0, "0 samples into its block"), (1, "1 sample into its block"),
                             (2, "2 samples into its block")):
            with self.subTest(offset=offset):
                click = click_diff.OneSided(0.5, "B", -20.0, offset, 100, 100, True, False, False)
                shown = click_diff.Diff(1.0, 0, 1, 0, 1, 1.0, 0, 0, 0, [click])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    click_diff.print_diff(shown, 20)
                self.assertIn(f"dB, {text}, ", out.getvalue())

    def test_json_has_each_click(self):
        _, out, _ = run_main(click_diff.main, str(self.a), str(self.b), "--json")
        got = json.loads(out)
        self.assertEqual(got["clicks"][0]["build"], "B")
        self.assertTrue(got["clicks"][0]["join_step"])

    def test_a_missing_recording_exits_2_with_one_line(self):
        code, _, err = run_main(click_diff.main, str(self.a), str(self.dir / "none.raw"))
        self.assertEqual(code, 2)
        self.assertEqual(len(err.splitlines()), 1)

    def test_bad_numbers_exit_2(self):
        for bad in (["--seconds", "0"], ["--list", "-1"]):
            with self.subTest(bad=bad):
                code, _, _ = run_main(click_diff.main, str(self.a), str(self.b), *bad)
                self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
