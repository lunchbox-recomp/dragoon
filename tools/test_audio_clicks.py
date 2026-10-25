import json
import math
import random
import struct
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from unittest import mock

import audio_clicks
from audio_clicks import Recording
from testutil import pcm, run_main, write_file

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


def list_chunk(size: int) -> bytes:
    """A LIST chunk of SIZE bytes, which a WAV reader skips."""
    return b"LIST" + struct.pack("<I", size) + bytes(size)


def clicks(*channels: list[int]) -> list[float]:
    return [c.at for c in audio_clicks.analyse(rec(*channels), 0).clicks]


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

    def test_a_click_is_as_big_as_its_largest_second_difference_in_db_from_full_scale(self):
        # An impulse of n in silence has second differences n, -2n and n.
        for size, db in ((1000, 20 * math.log10(2000 / 32768)), (100, 20 * math.log10(200 / 32768))):
            x = [0] * RATE
            x[RATE // 2] = size
            with self.subTest(size=size):
                got = audio_clicks.analyse(rec(x), 0).clicks
                self.assertEqual(len(got), 1)
                self.assertAlmostEqual(got[0].db, db)

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
        self.assertAlmostEqual(report.clicks[0].at, 0.8, delta=2 / RATE)

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


class AnalyseFileTest(unittest.TestCase):
    """analyse_file must find what one pass finds, with every event near a part's edge."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def check(self, *channels: list[int], part_s: float) -> audio_clicks.Report:
        """What analyse_file finds in the channels (one is both sides) at part_s, which has to be
        what one pass finds."""
        left, right = channels if len(channels) == 2 else (channels[0], channels[0])
        got = audio_clicks.analyse_file(write_file(self.dir, "r.raw", pcm(left, right)), RATE, part_s=part_s)
        self.assertEqual(got, audio_clicks.analyse(rec(left, right), 0))
        return got

    def recording(self) -> tuple[list[int], list[int]]:
        noise = random.Random(7)
        left = [a + noise.randint(-300, 300) for a in tone(330, 1, 6000)]
        right = [a + noise.randint(-300, 300) for a in tone(500, 1, 6000)]
        for i in (4799, 4800, 4801, 9597, 14403, 19200 + 500):  # parts of 4800 frames
            left[i] += 9000
        for ch in (left, right):
            ch[12000:20500] = [0] * 8500  # a gap across two part edges
            ch[24000:24400] = [0] * 400   # one that starts on an edge
        left[28790:28812] = [32767] * 22  # a clipped run across an edge
        right[33598:33600] = [-32768] * 2  # one that ends on an edge
        right[38399:38401] = [32767] * 2  # one that straddles it
        return left, right

    def test_finds_what_one_pass_finds(self):
        whole = audio_clicks.analyse(rec(*self.recording()), 0)
        self.assertGreater(len(whole.clicks), 4)
        self.assertEqual(len(whole.gaps), 2)
        self.assertEqual(len(whole.clipped), 3)
        for part_s in (0.1, 0.0371, 0.25, 5):
            with self.subTest(part_s=part_s):
                self.check(*self.recording(), part_s=part_s)

    def test_follows_a_gap_and_a_clipped_run_to_their_ends(self):
        got = self.check(*self.recording(), part_s=0.1)
        self.assertAlmostEqual(got.gaps[0].ms, 8500 / 48)
        self.assertEqual(got.clipped[0].samples, 22)

    def test_follows_them_a_block_at_a_time(self):
        with mock.patch.object(audio_clicks, "FOLLOW_FRAMES", 100):
            got = self.check(*self.recording(), part_s=0.1)
        self.assertAlmostEqual(got.gaps[0].ms, 8500 / 48)

    def test_a_clipped_run_is_counted_once_wherever_it_starts_in_the_stretch_past_an_edge(self):
        x = tone(440, 1, 10000)
        x[9500:9900] = [32767] * 400    # starts in a part and runs on past what was read for it
        x[19205:19208] = [-32768] * 3   # starts just after an edge, inside the stretch read past it
        x[28800:28803] = [32767] * 3    # starts on one
        got = self.check(x, tone(330, 1, 10000), part_s=0.1)
        self.assertEqual([c.samples for c in got.clipped], [400, 3, 3])

    def test_a_clipped_run_on_the_right_channel_is_followed_on_that_channel(self):
        # The left channel is a tone that never sits at full scale, so following it would end the run at the edge.
        y = tone(440, 1, 10000)
        y[9500:9900] = [-32768] * 400
        got = self.check(tone(330, 1, 10000), y, part_s=0.1)
        self.assertEqual([c.samples for c in got.clipped], [400])

    def test_a_gap_and_a_clipped_run_that_end_the_recording_end_with_it(self):
        x = tone(440, 1, 10000)
        x[-3000:] = [0] * 3000
        y = tone(440, 1, 10000)
        y[-6:] = [32767] * 6
        self.assertEqual(self.check(x, part_s=0.1).gaps[0].ms, 3000 / 48)
        self.assertEqual(self.check(y, x, part_s=0.1).clipped[0].samples, 6)

    def test_a_sample_near_a_parts_end_is_judged_on_the_context_past_it(self):
        # An impulse 5 samples before the edge at 9600 stands out from silence, but a burst
        # 220 to 236 samples after it is inside its 5 ms of context and drowns it out.
        x = [0] * RATE
        x[9595] = 2000
        x[9820:9836] = [3000 if i % 2 else -3000 for i in range(16)]
        self.assertNotIn(9595, [round(c.at * RATE) for c in audio_clicks.analyse(rec(x), 0).clicks])
        self.check(x, part_s=0.2)

    def test_the_first_and_last_sample_of_a_part_are_judged_on_all_their_context(self):
        # A spike 241 samples (5 ms and one) from an impulse is the furthest one that its second
        # difference's context reaches, after the last sample of a part or before the first.
        for impulse, spike in ((9599, 9599 + 241), (9600, 9600 - 241)):
            x = [0] * RATE
            x[impulse], x[spike] = 2000, 30000
            with self.subTest(impulse=impulse):
                self.assertNotIn(impulse, [round(c.at * RATE) for c in audio_clicks.analyse(rec(x), 0).clicks])
                self.check(x, part_s=0.2)

    def test_a_gap_that_starts_one_sample_before_a_part_is_counted_once(self):
        x = tone(440, 1, 10000)
        x[9599:9999] = [0] * 400
        self.assertEqual(len(self.check(x, part_s=0.2).gaps), 1)

    def test_noise_with_random_events_matches_at_any_part_size(self):
        rnd = random.Random(3)
        x = [rnd.randint(-2000, 2000) for _ in range(RATE)]
        for _ in range(40):
            x[rnd.randrange(RATE)] += rnd.choice((-1, 1)) * rnd.randint(5000, 20000)
        for _ in range(6):
            at, length = rnd.randrange(1000, RATE - 2000), rnd.randint(100, 1500)
            x[at:at + length] = [0] * length
        x = [max(-32768, min(32767, v)) for v in x]
        self.assertEqual(len(x), RATE)
        for part_s in (0.013, 0.1, 0.33):
            with self.subTest(part_s=part_s):
                self.check(x, part_s=part_s)

    def test_a_wav_is_read_a_part_at_a_time_too(self):
        left, right = self.recording()
        path = write_wav(self.dir, "out.wav", left, right)
        got = audio_clicks.analyse_file(path, part_s=0.1)
        self.assertEqual(got, audio_clicks.analyse(audio_clicks.read_wav(path), 0))
        self.assertEqual(len(got.gaps), 2)

    def test_a_raw_recording_is_cut_to_the_frames_asked_for(self):
        left, right = self.recording()
        path = write_file(self.dir, "aid.raw", pcm(left, right))
        got = audio_clicks.analyse_file(path, RATE, 30000, part_s=0.1)
        self.assertEqual(got, audio_clicks.analyse(audio_clicks.read_raw(path, RATE, 30000), 0))
        self.assertEqual(got.seconds, 30000 / RATE)

    def test_it_holds_about_a_part_and_never_the_whole_recording(self):
        left, right = self.recording()
        asked = []

        def read(lo: int, hi: int) -> list[array]:
            asked.append(hi - lo)
            return [array("h", left[lo:hi]), array("h", right[lo:hi])]

        with mock.patch.object(audio_clicks, "FOLLOW_FRAMES", 100):
            audio_clicks.analyse_source(audio_clicks.Source(RATE, 2, len(left), read), 0.1)
        self.assertLessEqual(max(asked), 4800 + 2 * 241)
        self.assertGreater(len(asked), 10)

    def test_refuses_what_it_cannot_read_as_read_wav_and_read_raw_do(self):
        no_frames = write_wav(self.dir, "f.wav", [1, 2], [-1, -2])
        no_frames.write_bytes(no_frames.read_bytes()[:-8])  # the header says 2 frames and none are there
        for name, path, rate, msg in (
                ("8-bit", write_wav(self.dir, "b.wav", [0, 0], width=1), None, "8-bit samples"),
                ("not wav", write_file(self.dir, "c.wav", "hello"), None, "not a PCM WAV file"),
                ("empty wav", write_wav(self.dir, "d.wav", []), None, "no samples"),
                ("no frames there", no_frames, None, "no samples"),
                ("empty raw", write_file(self.dir, "e.raw", b"\0\0\0"), 32000, "no samples")):
            with self.subTest(name):
                with self.assertRaisesRegex(ValueError, f"{path}: {msg}") as whole:
                    if rate is None:
                        audio_clicks.read_wav(path)
                    else:
                        audio_clicks.read_raw(path, rate)
                with self.assertRaises(ValueError) as parts:
                    audio_clicks.analyse_file(path, rate, part_s=0.1)
                self.assertEqual(str(parts.exception), str(whole.exception))

    def test_a_wav_that_ends_before_its_header_says_has_the_frames_that_are_there(self):
        left, right = self.recording()
        path = write_wav(self.dir, "out.wav", left, right)
        path.write_bytes(path.read_bytes()[:-8003])  # the last 2,000 frames and three bytes of the one before
        whole = audio_clicks.read_wav(path)
        self.assertEqual(whole.frames, len(left) - 2001)
        got = audio_clicks.analyse_file(path, part_s=0.1)
        self.assertEqual(got, audio_clicks.analyse(whole, 0))
        self.assertEqual(got.seconds, whole.frames / RATE)

    def wav_with(self, name: str, *channels: list[int], before: bytes = b"", after: bytes = b"", cut: int = 0) -> Path:
        """A WAV of the channels with BEFORE as chunks ahead of its data and AFTER as chunks past it,
        then the last CUT bytes gone."""
        raw = write_wav(self.dir, name, *channels).read_bytes()
        at = raw.index(b"data")
        path = self.dir / name
        path.write_bytes((raw[:at] + before + raw[at:] + after)[:len(raw) + len(before) + len(after) - cut])
        return path

    def test_a_chunk_after_the_data_isnt_frames(self):
        left, right = self.recording()
        path = self.wav_with("out.wav", left, right, after=list_chunk(1000))
        whole = audio_clicks.read_wav(path)
        self.assertEqual(whole.frames, len(left))
        self.assertEqual(audio_clicks.analyse_file(path, part_s=0.1), audio_clicks.analyse(whole, 0))

    def test_a_mono_wav_that_ends_before_its_header_says_has_the_frames_that_are_there(self):
        left, _ = self.recording()
        path = self.wav_with("out.wav", left, cut=4001)  # the last 2,000 frames and a byte of the one before
        whole = audio_clicks.read_wav(path)
        self.assertEqual((len(whole.channels), whole.frames), (1, len(left) - 2001))
        self.assertEqual(audio_clicks.analyse_file(path, part_s=0.1), audio_clicks.analyse(whole, 0))

    def test_a_wav_with_a_chunk_ahead_of_its_data_that_ends_early_has_the_frames_that_are_there(self):
        left, right = self.recording()
        path = self.wav_with("out.wav", left, right, before=list_chunk(1000), cut=8003)
        whole = audio_clicks.read_wav(path)
        self.assertEqual(whole.frames, len(left) - 2001)
        self.assertEqual(audio_clicks.analyse_file(path, part_s=0.1), audio_clicks.analyse(whole, 0))


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

    def test_reads_only_the_first_frames_asked_for(self):
        path = write_file(self.dir, "aid.raw", pcm([1, 2, 3], [-1, -2, -3]))
        self.assertEqual([list(ch) for ch in audio_clicks.read_raw(path, 32000, 2).channels], [[1, 2], [-1, -2]])
        self.assertEqual(audio_clicks.read_raw(path, 32000, 10).frames, 3)

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

    def test_a_mark_in_non_ascii_digits_is_refused(self):
        path = write_file(self.dir, "cuts.txt", "١٢\n")
        with self.assertRaisesRegex(ValueError, f"{path}:1: .* isn't a sample index"):
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
            "clicks   1 (60.0 a minute)", "  0.625 s, -0.8 dB",
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
                                                "clicks   1 (40.0 a minute)", "  0.937 s, -0.8 dB"])

    def test_json_has_the_whole_result(self):
        code, out, _ = run_main(audio_clicks.main, str(self.path), "--json")
        got = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((got["seconds"], got["rate"], got["channels"], got["gaps"], got["clipped"]),
                         (1.0, RATE, 2, [], []))
        self.assertEqual(list(got["clicks"][0]), ["at", "db"])

    def test_bad_input_exits_2_naming_it(self):
        for argv, msg in (([str(self.path) + "x"], str(self.path) + "x"),
                          ([str(self.path), "--from", "5"], "past the end"),
                          ([str(self.path), "--list", "-1"], "can't be negative"),
                          ([str(self.path), "--period", "-160"], "can't be negative"),
                          ([str(self.path), "--marks", str(self.path) + "y"], str(self.path) + "y")):
            with self.subTest(argv=argv):
                code, _, err = run_main(audio_clicks.main, *argv)
                self.assertEqual(code, 2)
                self.assertIn(msg, err)

    def test_raw_below_1_exits_2_instead_of_reading_a_wav(self):
        for rate in ("0", "-1"):
            with self.subTest(rate=rate):
                code, _, err = run_main(audio_clicks.main, str(self.path), "--raw", rate)
                self.assertEqual(code, 2)
                self.assertIn("--raw RATE must be at least 1", err)

    def test_help_exits_0(self):
        code, out, _ = run_main(audio_clicks.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
