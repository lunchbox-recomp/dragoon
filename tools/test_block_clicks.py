import json
import tempfile
import unittest
from pathlib import Path

import block_clicks
from testutil import pcm, run_main, tone, write_file

RATE, BLOCK = 32000, 160
ADDRESSES = ("00571E00", "00572080")  # the guest's two buffers


def dma(blocks: int, replays: set[int] = frozenset(), caught_up: set[int] = frozenset()) -> tuple[list[int], str]:
    """A tone the guest mixed into BLOCKS blocks, as GCN_AIDWAV records the DMA delivering
    them: the samples and the block log. The guest blocks in REPLAYS are played twice from the
    same buffer, and the delivered blocks in CAUGHT_UP are marked as delivered catching up."""
    x = tone(blocks * BLOCK, RATE)
    samples: list[int] = []
    lines = []
    for n in range(blocks):
        for _ in range(2 if n in replays else 1):
            k = len(lines)
            lines.append(f"{len(samples)} {BLOCK} {21223426 + k * 202500} {int(k in caught_up)} {ADDRESSES[n % 2]} 1\n")
            samples += x[n * BLOCK:(n + 1) * BLOCK]
    return samples, "".join(lines)


class PlaceTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, samples: list[int], log: str) -> Path:
        write_file(self.dir, "mixer.raw.txt", log)
        return write_file(self.dir, "mixer.raw", pcm(samples, samples))

    def counts(self, result: block_clicks.Result) -> dict[str, tuple[int, int, float]]:
        return {c.kind: (c.blocks, c.clicks_on, c.by_chance) for c in result.counts}

    def test_a_replayed_block_clicks_where_it_starts_and_counts_on_it(self):
        x, log = dma(100, replays={40})
        got = block_clicks.place(self.write(x, log))
        self.assertEqual((got.blocks, got.clicks), (101, 1))
        self.assertEqual(got.counts[0].kind, "replayed")
        blocks, on, chance = self.counts(got)["replayed"]
        self.assertEqual((blocks, on), (1, 1))
        self.assertAlmostEqual(chance, (BLOCK + 5) / len(x))
        self.assertEqual(self.counts(got)["caught up"], (0, 0, 0.0))
        self.assertEqual(len(got.placed), 1)
        self.assertEqual(got.placed[0].kinds, ["replayed"])
        self.assertEqual(got.placed[0].offset, BLOCK - 1)  # on the join where block 41 starts

    def test_neighbouring_caught_up_blocks_cover_their_samples_once(self):
        x, log = dma(100, replays={40}, caught_up={10, 11, 12})
        blocks, on, chance = self.counts(block_clicks.place(self.write(x, log)))["caught up"]
        self.assertEqual((blocks, on), (3, 0))
        self.assertAlmostEqual(chance, (3 * BLOCK + 5) / len(x))

    def test_a_block_of_both_kinds_counts_once_in_either(self):
        x, log = dma(100, replays={40}, caught_up={41, 60})
        got = self.counts(block_clicks.place(self.write(x, log)))
        self.assertEqual(got["replayed"][:2], (1, 1))
        self.assertEqual(got["caught up"][:2], (2, 1))
        self.assertEqual(got["either"][:2], (2, 1))
        self.assertAlmostEqual(got["either"][2], 2 * (BLOCK + 5) / len(x))

    def test_a_click_on_no_marked_block_isnt_on_one(self):
        x, log = dma(100, replays={40})
        x[3080] += 6000
        got = block_clicks.place(self.write(x, log))
        self.assertEqual(got.clicks, 2)
        self.assertEqual(self.counts(got)["replayed"][:2], (1, 1))
        self.assertAlmostEqual(self.counts(got)["replayed"][2], 2 * (BLOCK + 5) / len(x))
        self.assertEqual(len(got.placed), 1)

    def test_an_unpaced_run_with_no_marks_has_nothing_on_them(self):
        x, log = dma(50)
        got = block_clicks.place(self.write(x, log))
        self.assertEqual(self.counts(got), {"replayed": (0, 0, 0.0), "caught up": (0, 0, 0.0), "either": (0, 0, 0.0)})

    def test_a_log_with_no_blocks_is_refused(self):
        x, _ = dma(10)
        with self.assertRaisesRegex(ValueError, "mixer.raw.txt: no blocks"):
            block_clicks.place(self.write(x, ""))

    def test_a_log_that_ends_far_from_the_recording_isnt_its_log(self):
        x, _ = dma(400)  # 2 s
        two_blocks = "0 160 21223426 0 00571E00 1\n160 160 21425926 0 00572080 1\n"
        with self.assertRaisesRegex(ValueError, r"mixer\.raw\.txt: its last block ends at 0\.01 s and "
                                                r".*mixer\.raw is 2\.00 s, so it isn't this recording's log"):
            block_clicks.place(self.write(x, two_blocks))

    def test_a_log_may_end_up_to_a_second_either_side_of_the_recording(self):
        x, _ = dma(400)  # 64,000 samples
        for ends, ok in ((32000, True), (31999, False), (96000, True), (96001, False)):
            with self.subTest(ends=ends):
                path = self.write(x, f"{ends - BLOCK} {BLOCK} 21223426 0 00571E00 1\n")
                if ok:
                    self.assertEqual(block_clicks.place(path).blocks, 1)
                else:
                    with self.assertRaisesRegex(ValueError, "isn't this recording's log"):
                        block_clicks.place(path)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        x, log = dma(100, replays={40}, caught_up={41})
        write_file(self.dir, "mixer.raw.txt", log)
        self.path = write_file(self.dir, "mixer.raw", pcm(x, x))

    def test_prints_each_kind_and_the_clicks_on_them(self):
        code, out, _ = run_main(block_clicks.main, str(self.path))
        self.assertEqual(code, 0)
        self.assertIn("101 blocks, 1 click\n", out)
        self.assertRegex(out, r"replayed +1 block, 1 click on them \(0\.0 by chance\)")
        self.assertRegex(out, r"caught up +1 block, 1 click on them")
        self.assertRegex(out, r"samples into its block, replayed and caught up\n")

    def test_list_0_prints_no_clicks(self):
        _, out, _ = run_main(block_clicks.main, str(self.path), "--list", "0")
        self.assertNotIn("into its block", out)
        self.assertIn("and 1 more", out)

    def test_json_has_every_count(self):
        _, out, _ = run_main(block_clicks.main, str(self.path), "--json")
        got = json.loads(out)
        self.assertEqual([c["kind"] for c in got["counts"]], ["replayed", "caught up", "either"])
        self.assertEqual(got["placed"][0]["kinds"], ["replayed", "caught up"])

    def test_a_recording_with_no_block_log_exits_2_with_one_line(self):
        (self.dir / "mixer.raw.txt").unlink()
        code, _, err = run_main(block_clicks.main, str(self.path))
        self.assertEqual(code, 2)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("mixer.raw.txt", err)

    def test_a_log_from_another_run_exits_2_with_one_line(self):
        write_file(self.dir, "mixer.raw.txt", "0 160 21223426 0 00571E00 1\n")
        x, _ = dma(400)
        self.path = write_file(self.dir, "mixer.raw", pcm(x, x))
        code, out, err = run_main(block_clicks.main, str(self.path))
        self.assertEqual((code, out, len(err.splitlines())), (2, "", 1))
        self.assertIn("isn't this recording's log", err)

    def test_a_negative_list_exits_2(self):
        code, _, _ = run_main(block_clicks.main, str(self.path), "--list", "-1")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
