import unittest

import click_stages
from click_stages import Placed
from session_log import SessionLog

OUT, DMA = 48000, 32000


def place(device: list[float], mixer: list[float], **log) -> list[Placed]:
    return click_stages.place(device, mixer, SessionLog(**{"positions": [(0, 0)], **log}), OUT, DMA)


def stages(device: list[float], mixer: list[float], **log) -> list[str]:
    return [p.stage for p in place(device, mixer, **log)]


class SilentSpansTest(unittest.TestCase):
    def test_pulls_end_to_end_are_one_stretch(self):
        self.assertEqual(click_stages.silent_spans([(1000, 200), (1200, 512), (1712, 512)]), [(1000, 2224)])

    def test_separate_pulls_stay_apart(self):
        self.assertEqual(click_stages.silent_spans([(5000, 512), (1000, 100)]), [(1000, 1100), (5000, 5512)])


class DmaFrameTest(unittest.TestCase):
    def test_moves_on_from_the_last_position_at_the_dma_rate(self):
        positions = [(0, 0), (48000, 40000)]
        self.assertEqual(click_stages.dma_frame(24000, positions, [], DMA / OUT), 16000)
        self.assertEqual(click_stages.dma_frame(48000, positions, [], DMA / OUT), 40000)
        self.assertEqual(click_stages.dma_frame(72000, positions, [], DMA / OUT), 56000)

    def test_nothing_before_the_ring_first_played(self):
        self.assertIsNone(click_stages.dma_frame(999, [(1000, 0)], [], DMA / OUT))

    def test_nothing_inside_a_pull_the_ring_couldnt_fill(self):
        spans = [(2000, 2512)]
        self.assertIsNone(click_stages.dma_frame(2000, [(0, 0)], spans, DMA / OUT))
        self.assertIsNone(click_stages.dma_frame(2511, [(0, 0)], spans, DMA / OUT))
        self.assertAlmostEqual(click_stages.dma_frame(2512, [(0, 0)], spans, DMA / OUT), 2512 * DMA / OUT)


class NearestTest(unittest.TestCase):
    def test_the_closer_neighbour_within_reach(self):
        self.assertEqual(click_stages.nearest([10, 20, 30], 24, 5), 20)
        self.assertEqual(click_stages.nearest([10, 20, 30], 26, 5), 30)

    def test_none_out_of_reach_or_in_an_empty_list(self):
        self.assertIsNone(click_stages.nearest([10, 30], 20, 5))
        self.assertIsNone(click_stages.nearest([], 20, 5))


class PlaceTest(unittest.TestCase):
    def test_a_click_aid_raw_has_at_the_same_moment_is_the_mixers(self):
        got = place([1.0], [1.0016])
        self.assertEqual(got, [Placed(1.0, "mixer", "aid.raw clicks at 1.002 s")])

    def test_a_mixer_click_further_off_than_mixer_ms_isnt(self):
        self.assertEqual(stages([1.0], [1.003]), ["unexplained"])

    def test_the_mixer_moment_follows_a_jump_in_the_positions(self):
        positions = [(0, 0), (48000, 40000)]
        self.assertEqual(stages([1.5], [1.75], positions=positions), ["mixer"])
        self.assertEqual(stages([1.5], [1.5], positions=positions), ["unexplained"])

    def test_a_click_near_a_cut_is_the_rings(self):
        got = place([2.003], [], cuts=[(96000, 640)])
        self.assertEqual(got, [Placed(2.003, "ring", "the ring cut 640 frames at 2.000 s")])

    def test_a_click_where_the_ring_ran_dry_or_came_back_is_the_rings(self):
        underruns = [(96000, 512), (96512, 512)]
        self.assertEqual(stages([1.999, 2.0215, 2.03], [], underruns=underruns), ["ring", "ring", "unexplained"])

    def test_a_click_inside_a_dry_stretch_is_never_the_mixers(self):
        underruns = [(96000, 4800)]
        self.assertEqual(stages([2.05], [2.05]), ["mixer"])
        self.assertEqual(stages([2.05], [2.05], underruns=underruns), ["unexplained"])
        self.assertEqual(place([2.05], [], underruns=underruns)[0].why, "the ring had no sound there")

    def test_a_click_near_a_late_callback_is_the_devices(self):
        got = place([3.004], [], late=[(144000, 17.1)])
        self.assertEqual(got, [Placed(3.004, "device", "a callback came 17.1 ms after the last at 3.000 s")])
        self.assertEqual(stages([3.006], [], late=[(144000, 17.1)]), ["unexplained"])

    def test_the_mixer_comes_before_the_ring_and_the_ring_before_the_device(self):
        log = {"cuts": [(48000, 640)], "late": [(48000, 17.1)]}
        self.assertEqual(stages([1.0], [1.0], **log), ["mixer"])
        self.assertEqual(stages([1.0], [], **log), ["ring"])
        self.assertEqual(stages([1.0], [], late=[(48000, 17.1)]), ["device"])

    def test_counts_every_stage(self):
        placed = [Placed(0, "mixer", ""), Placed(1, "mixer", ""), Placed(2, "device", "")]
        self.assertEqual(click_stages.counts(placed), {"mixer": 2, "ring": 0, "device": 1, "unexplained": 0})


if __name__ == "__main__":
    unittest.main()
