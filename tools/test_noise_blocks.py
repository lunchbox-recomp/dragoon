from __future__ import annotations

import json
import tempfile
import unittest
from array import array
from pathlib import Path

import noise_blocks
from audio_clicks import Recording, Source
from aid_blocks import BLOCK, RATE
from testutil import noise, pcm, run_main, tone, write_file


def interpolated(x: list[int], rate: int) -> list[int]:
    """X, sampled at the DMA's rate, linearly interpolated to RATE as the audio ring does."""
    out = []
    for k in range((len(x) - 1) * rate // RATE):
        at = k * RATE / rate
        i = int(at)
        out.append(round(x[i] + (at - i) * (x[i + 1] - x[i])))
    return out


def rec(left: list[int], right: list[int]) -> Recording:
    return Recording(RATE, [array("h", left), array("h", right)])


class FindTest(unittest.TestCase):
    def test_music_and_effects_arent_noise_however_loud(self):
        for freq in (110, 440, 3000):
            with self.subTest(freq=freq):
                x = tone(RATE, RATE, freq=freq, amp=32000)
                self.assertEqual(noise_blocks.find(rec(x, x)).noisy_blocks, 0)

    def test_full_scale_noise_from_a_point_on_is_one_stretch(self):
        # The music turns to independent noise on each channel 0.5 s in, as in the bisect's menu run.
        music = tone(RATE // 2, RATE, amp=12000)
        got = noise_blocks.find(rec(music + noise(RATE // 2, 32767, 1), music + noise(RATE // 2, 32767, 2)))
        self.assertEqual((got.blocks, got.noisy_blocks), (200, 100))
        self.assertAlmostEqual(got.noisy_seconds, 0.5)
        self.assertEqual([(s.start, s.end, s.blocks) for s in got.stretches], [(0.5, 1.0, 100)])

    def test_noise_on_one_channel_is_enough(self):
        x = tone(RATE, RATE)
        self.assertEqual(noise_blocks.find(rec(x, noise(RATE, 20000, 3))).noisy_blocks, 200)

    def test_quiet_hiss_isnt_flagged(self):
        x = noise(RATE, 8000, 4)
        self.assertEqual(noise_blocks.find(rec(x, x)).noisy_blocks, 0)

    def test_bursts_100_ms_apart_are_one_stretch_and_further_apart_two(self):
        burst = noise(160, 30000, 5)
        quiet = tone(RATE, RATE, amp=1000)
        x = list(quiet)
        for at in (0, 20, 41):  # blocks, 20 of them to 100 ms
            x[at * 160:(at + 1) * 160] = burst
        got = noise_blocks.find(rec(x, x))
        self.assertEqual([(s.start, s.end, s.blocks) for s in got.stretches], [(0.0, 0.105, 2), (0.205, 0.21, 1)])

    def test_a_partial_last_block_is_left_out(self):
        x = tone(RATE, RATE) + noise(100, 30000, 7)
        got = noise_blocks.find(rec(x, x))
        self.assertEqual((got.blocks, got.noisy_blocks), (200, 0))

    def test_the_ratio_divides_by_the_blocks_159_differences(self):
        # A sine with a period of 6 samples has as much energy in its first differences as in
        # its samples, 159 of them against 160. Only the mean over 159 puts it over the ratio of 1.
        x = tone(160, RATE, freq=RATE / 6)
        self.assertEqual(noise_blocks.find(rec(x, x)).noisy_blocks, 1)

    def test_a_block_at_a_ratio_of_exactly_1_isnt_over_it(self):
        # Every step is 1 or -1 and the squares sum to 160, so the mean over the 159 steps and
        # the mean over the 160 samples are both 1 times a square. Scaled to a peak of 10,000
        # they are exactly equal, and a block is noise-like only when the first is bigger.
        walk = [0, 1] * 60 + [2, 1] * 20
        tie = [5000 * v for v in walk]
        self.assertEqual(noise_blocks.find(rec(tie, tie)).noisy_blocks, 0)
        over = tie[:-1] + [0]  # one step of 2 instead of 1 and a little less energy
        self.assertEqual(noise_blocks.find(rec(over, over)).noisy_blocks, 1)

    def test_noise_resampled_to_48_khz_is_flagged_in_far_fewer_blocks(self):
        # The ring interpolates linearly to the device's 48 kHz, which leaves little above
        # 16 kHz. That takes white noise from a ratio of about 1.41 to about 0.97, so most of
        # its blocks fall under the 1 that flags them and the rest sit close to it.
        x = noise(RATE, 30000, 6)
        self.assertEqual(noise_blocks.find(rec(x, x)).noisy_blocks, 200)
        y = interpolated(x, 48000)
        blocks = [array("h", y[k * 240:(k + 1) * 240]) for k in range(len(y) // 240)]
        self.assertLess(sum(noise_blocks.noisy(b) for b in blocks), len(blocks) / 2)


def bursts(at: list[int], blocks: int, tail: int = 0) -> list[int]:
    """BLOCKS blocks of a quiet tone with loud noise in each block of AT, then TAIL samples of
    noise that don't make a whole block."""
    x = tone(blocks * BLOCK, RATE, amp=1000)
    for k in at:
        x[k * BLOCK:(k + 1) * BLOCK] = noise(BLOCK, 30000, k)
    return x + noise(tail, 30000, 99)


def source(left: list[int], right: list[int], asked: list[tuple[int, int]] | None = None) -> Source:
    """The channels as a Source, with each read it's asked for added to ASKED."""
    def read(lo: int, hi: int) -> list[array]:
        if asked is not None:
            asked.append((lo, hi))
        return [array("h", left[lo:hi]), array("h", right[lo:hi])]

    return Source(RATE, 2, len(left), read)


class FindSourceTest(unittest.TestCase):
    PARTS = (1, 2, 3, 7, 10, 20, 21, 41, 60, 61, 140, 6000)  # in blocks, edges falling in every stretch and gap

    def setUp(self):
        # Each channel is quiet in the blocks where the other has the noise, so a block counts when either does.
        # The last whole block is noisy, which a part of one block starts on.
        self.left = bursts([8, 9, 10, 40, 60, 130], 140, tail=100)
        self.right = bursts([11, 12, 81, 131, 139], 140, tail=100)

    def whole(self) -> noise_blocks.Noise:
        return noise_blocks.find(rec(self.left, self.right))

    def test_finds_what_one_pass_finds_at_any_part_size(self):
        whole = self.whole()
        self.assertEqual([(s.start, s.end, s.blocks) for s in whole.stretches],
                         [(0.04, 0.065, 5), (0.2, 0.305, 2), (0.405, 0.41, 1), (0.65, 0.7, 3)])
        for part in self.PARTS:
            with self.subTest(part_blocks=part):
                self.assertEqual(noise_blocks.find_source(source(self.left, self.right), part), whole)

    def test_a_stretch_across_a_parts_edge_is_one_stretch(self):
        # Blocks 8 to 12 have the edge at 10 across them, and 40 and 60 are one stretch with an edge
        # at 41 between them, which is the 100 ms the rule allows.
        got = noise_blocks.find_source(source(self.left, self.right), 10)
        self.assertEqual([(s.blocks, s.start) for s in got.stretches][:2], [(5, 0.04), (2, 0.2)])
        got = noise_blocks.find_source(source(self.left, self.right), 41)
        self.assertEqual([(s.blocks, s.start) for s in got.stretches][:2], [(5, 0.04), (2, 0.2)])

    def test_a_gap_of_exactly_100_ms_across_an_edge_joins_and_one_block_more_doesnt(self):
        for gap, stretches in ((20, 1), (21, 2)):
            for part in (5, 10, 15, 20, 21, 25):
                with self.subTest(gap=gap, part_blocks=part):
                    x = bursts([9, 9 + gap], 60)
                    got = noise_blocks.find_source(source(x, x), part)
                    self.assertEqual(len(got.stretches), stretches)
                    self.assertEqual(got.noisy_blocks, 2)

    def test_a_part_is_whole_blocks_and_every_block_is_read_once(self):
        asked: list[tuple[int, int]] = []
        noise_blocks.find_source(source(self.left, self.right, asked), 8)
        self.assertEqual(asked, [(k * BLOCK, min(140, k + 8) * BLOCK) for k in range(0, 140, 8)])
        self.assertLessEqual(max(hi for _, hi in asked), 140 * BLOCK)  # the 100 samples past it are never read

    def test_the_length_counts_the_partial_last_block_as_one_pass_does(self):
        got = noise_blocks.find_source(source(self.left, self.right), 8)
        self.assertEqual((got.seconds, got.blocks), (len(self.left) / RATE, 140))

    def test_a_recording_under_a_block_has_none(self):
        x = tone(100, RATE)
        self.assertEqual(noise_blocks.find_source(source(x, x), 8), noise_blocks.find(rec(x, x)))
        self.assertEqual(noise_blocks.find_source(source(x, x), 8).blocks, 0)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.left = tone(RATE // 2, RATE) + noise(RATE // 2, 32767, 1)
        self.right = tone(RATE, RATE)

    def test_reads_a_dma_recording_and_prints_the_stretches(self):
        path = write_file(self.dir, "mixer.raw", pcm(self.left, self.right))
        code, out, _ = run_main(noise_blocks.main, str(path))
        self.assertEqual(code, 0)
        self.assertIn("1.00 s, 200 blocks, 100 noise-like (0.50 s) in 1 stretch\n", out)
        self.assertIn("0.500 s to 1.000 s, 100 blocks", out)

    def test_list_caps_the_stretches_printed(self):
        burst = noise(160, 30000, 5)
        x = list(tone(RATE, RATE, amp=1000))
        for at in (0, 50, 100):
            x[at * 160:(at + 1) * 160] = burst
        path = write_file(self.dir, "mixer.raw", pcm(x, x))
        _, out, _ = run_main(noise_blocks.main, str(path), "--list", "1")
        self.assertIn("0.000 s to 0.005 s, 1 block\n", out)
        self.assertNotIn("0.250 s", out)
        self.assertIn("and 2 more", out)

    def test_json_prints_the_whole_result(self):
        path = write_file(self.dir, "mixer.raw", pcm(self.left, self.right))
        _, out, _ = run_main(noise_blocks.main, str(path), "--json")
        got = json.loads(out)
        self.assertEqual((got["blocks"], got["noisy_blocks"]), (200, 100))
        self.assertEqual(got["stretches"], [{"start": 0.5, "end": 1.0, "blocks": 100}])

    def test_a_file_it_cant_read_exits_2(self):
        for name, data in (("missing.raw", None), ("empty.raw", b"")):
            with self.subTest(name=name):
                path = self.dir / name if data is None else write_file(self.dir, name, data)
                code, _, err = run_main(noise_blocks.main, str(path))
                self.assertEqual(code, 2)
                self.assertEqual(len(err.splitlines()), 1)

    def test_a_negative_list_exits_2(self):
        path = write_file(self.dir, "mixer.raw", pcm(self.left, self.right))
        code, _, _ = run_main(noise_blocks.main, str(path), "--list", "-1")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
