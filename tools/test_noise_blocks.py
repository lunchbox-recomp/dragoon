import json
import random
import tempfile
import unittest
from array import array
from pathlib import Path

import noise_blocks
from audio_clicks import Recording
from testutil import pcm, run_main, tone, write_file, write_wav

RATE = 32000


def noise(n: int, amp: int, seed: int) -> list[int]:
    r = random.Random(seed)
    return [r.randint(-amp, amp) for _ in range(n)]


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
        x = tone(RATE + 100, RATE)
        self.assertEqual(noise_blocks.find(rec(x, x)).blocks, 200)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.left = tone(RATE // 2, RATE) + noise(RATE // 2, 32767, 1)
        self.right = tone(RATE, RATE)

    def test_reads_raw_with_raw_and_prints_the_stretches(self):
        path = write_file(self.dir, "mixer.raw", pcm(self.left, self.right))
        code, out, _ = run_main(noise_blocks.main, str(path), "--raw", "32000")
        self.assertEqual(code, 0)
        self.assertIn("200 blocks of 5 ms, 100 noise-like (0.50 s) in 1 stretches", out)
        self.assertIn("0.500 s to 1.000 s, 100 blocks", out)

    def test_reads_a_wav_in_5_ms_blocks_of_its_own_rate(self):
        path = write_wav(self.dir / "device.wav", self.left, self.right, rate=RATE)
        _, out, _ = run_main(noise_blocks.main, str(path), "--json")
        self.assertEqual(json.loads(out)["noisy_blocks"], 100)

    def test_a_file_that_isnt_a_wav_exits_2(self):
        path = write_file(self.dir, "mixer.raw", pcm(self.left, self.right))
        code, _, err = run_main(noise_blocks.main, str(path))
        self.assertEqual(code, 2)
        self.assertEqual(len(err.splitlines()), 1)

    def test_bad_numbers_exit_2(self):
        path = write_file(self.dir, "mixer.raw", pcm(self.left, self.right))
        for bad in (["--raw", "0"], ["--list", "-1"]):
            with self.subTest(bad=bad):
                code, _, _ = run_main(noise_blocks.main, str(path), *bad)
                self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
