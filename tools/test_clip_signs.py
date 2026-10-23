from __future__ import annotations

import tempfile
import unittest
from array import array
from pathlib import Path
from unittest import mock

import clip_signs
from audio_clicks import Recording
from testutil import pcm, run_main, write_file, write_wav

MANIFEST = "title 1 60 60\nmenu 1 60 120\n"
LOG = ("[ax] frames=400 voices(running, last frame)=3 peak=33396 out=80571E00\n"
       "[ax] frames=800 voices(running, last frame)=3 peak=500 out=80571E00\n")


def groups(out: str) -> dict[str, list[str]]:
    """The output's unindented lines, each with the indented lines under it."""
    got: dict[str, list[str]] = {}
    head = ""
    for line in out.splitlines():
        if line and not line.startswith(" "):
            head = line
            got[head] = []
        elif line:
            got[head].append(line.strip())
    return got


def mixer_samples() -> tuple[list[int], list[int]]:
    """40,000 frames, of which a 1 s cut holds 32,000. Inside the cut, a positive run of 3, two
    negative runs of 2, a lone full-scale sample and a run of 4 at -32,767, which isn't a clipped
    run. A positive run of 3 lies past the cut."""
    left, right = [0] * 40000, [0] * 40000
    left[100:103] = [32767] * 3
    left[200] = 32767
    left[300:304] = [-32767] * 4
    right[400:402] = [-32768] * 2
    right[500:502] = [-32768] * 2
    right[600] = -32767
    right[35000:35003] = [32767] * 3
    return left, right


class SignsTest(unittest.TestCase):
    def test_runs_are_split_by_sign_and_counted_per_channel(self):
        left = array("h", [0, 32767, 32767, 32767, 0, -32768, -32768, 0, 32767, 0])
        right = array("h", [-32768, -32768, -32768, -32768, 0, 0, 0, 0, 32767, 32767])
        got = clip_signs.signs(Recording(1000, [left, right]))
        self.assertEqual((got.high_runs, got.high_samples), (2, 5))
        self.assertEqual((got.low_runs, got.low_samples), (2, 6))
        self.assertAlmostEqual(got.seconds, 0.01)

    def test_a_run_at_minus_32767_isnt_a_clipped_run_but_its_samples_are_counted(self):
        got = clip_signs.signs(Recording(1000, [array("h", [-32767, -32767, -32767, 0, -32767])]))
        self.assertEqual((got.low_runs, got.high_runs), (0, 0))
        self.assertEqual(got.at_minus_32767, 4)
        self.assertEqual(got.lowest, -32767)

    def test_the_lowest_and_highest_samples_come_from_any_channel(self):
        got = clip_signs.signs(Recording(1000, [array("h", [5, 9, 7]), array("h", [6, 20, 8])]))
        self.assertEqual((got.lowest, got.highest), (5, 20))

    def test_a_recording_that_never_goes_negative_has_a_positive_lowest(self):
        got = clip_signs.signs(Recording(1000, [array("h", [5, 6, 7])]))
        self.assertEqual((got.lowest, got.highest), (5, 7))

    def test_a_recording_that_never_goes_positive_has_a_negative_highest(self):
        got = clip_signs.signs(Recording(1000, [array("h", [-5, -6, -7])]))
        self.assertEqual((got.lowest, got.highest), (-7, -5))


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        manifest = write_file(self.dir, "manifest.txt", MANIFEST)
        patch = mock.patch.object(clip_signs, "MANIFEST", manifest)
        patch.start()
        self.addCleanup(patch.stop)

    def build(self, label: str) -> Path:
        return self.dir / label / "build"

    def run_dir(self, label: str, name: str, last_frame: int, log: str | None = LOG) -> Path:
        d = self.build(label) / "probe" / name
        d.mkdir(parents=True, exist_ok=True)
        write_file(d, f"frame_{last_frame:05d}.png", b"")
        if log is not None:
            write_file(d, "stdout.txt", log)
        return d

    def play(self, label: str, route: str = "title", last_frame: int = 60, *, mixer=None, device=None,
             unpaced: bool = True) -> None:
        """A route's two runs on the build: MIXER is the unpaced run's samples, DEVICE the real-time
        run's."""
        paced = self.run_dir(label, f"scorecard-{route}", last_frame)
        if device is not None:
            write_wav(paced / "device.wav", *device)
        if unpaced:
            run = self.run_dir(label, f"scorecard-unpaced-{route}", last_frame)
            if mixer is not None:
                (run / "mixer.raw").write_bytes(pcm(*mixer))

    def main(self, *argv: str):
        labels = sorted(p.name for p in self.dir.iterdir() if p.is_dir())
        return run_main(clip_signs.main, *(f"{label}={self.build(label)}" for label in labels), *argv)

    def test_each_recording_is_split_by_sign(self):
        left, right = [0] * 48000, [0] * 48000
        left[1:3] = [32767, 32767]
        right[0] = -32734
        self.play("now", mixer=mixer_samples(), device=(left, right))
        code, out, err = self.main("--routes", "title", "--margin", "0")
        self.assertEqual((code, err), (0, ""))
        got = groups(out)
        self.assertEqual(got["now mixer (unpaced run)"],
                         ["1.00 s", "runs at +32767 1 (3 samples)", "runs at -32768 2 (4 samples)",
                          "samples at -32767 5", "lowest -32768, highest 32767"])
        self.assertEqual(got["now device (real-time run)"],
                         ["1.00 s", "runs at +32767 1 (2 samples)", "runs at -32768 0 (0 samples)",
                          "samples at -32767 0", "lowest -32734, highest 32767", "main L peak in the log 33396"])

    def test_the_mixer_is_cut_at_the_last_checkpoint_plus_the_margin(self):
        # The title's last checkpoint is frame 60, a second. A margin of 1 s cuts at 2 s, which is
        # 64,000 frames, so the run at 35,000 is in and a run at 66,000 is out.
        left, right = mixer_samples()
        left, right = left + [0] * 32000, right + [0] * 32000
        left[66000:66003] = [32767] * 3
        self.play("now", mixer=(left, right))
        code, out, _ = self.main("--routes", "title", "--margin", "1")
        got = groups(out)
        self.assertEqual(code, 0)
        self.assertIn("title: mixer cut at 2 s", got)
        self.assertEqual(got["now mixer (unpaced run)"][:3],
                         ["2.00 s", "runs at +32767 2 (6 samples)", "runs at -32768 2 (4 samples)"])

    def test_the_default_margin_is_the_scorecards(self):
        self.play("now")
        self.assertIn("title: mixer cut at 16 s", groups(self.main("--routes", "title")[1]))

    def test_every_route_is_read_in_manifest_order_across_the_builds(self):
        for label in ("a", "b"):
            self.play(label, "title", 60)
            self.play(label, "menu", 120)
        _, out, _ = self.main("--margin", "0")
        self.assertEqual([line for line in out.splitlines() if line and not line.startswith(" ")], [
            "title: mixer cut at 1 s", "a mixer (unpaced run)", "a device (real-time run)",
            "b mixer (unpaced run)", "b device (real-time run)",
            "menu: mixer cut at 2 s", "a mixer (unpaced run)", "a device (real-time run)",
            "b mixer (unpaced run)", "b device (real-time run)"])

    def test_a_recording_that_isnt_there_reads_not_recorded(self):
        self.play("now")
        got = groups(self.main("--routes", "title", "--margin", "0")[1])
        self.assertEqual(got["now mixer (unpaced run)"], ["not recorded"])
        self.assertEqual(got["now device (real-time run)"][0], "not recorded")

    def test_a_build_with_no_unpaced_run_has_no_mixer_stage(self):
        self.play("now", device=([0] * 48000, [0] * 48000), unpaced=False)
        got = groups(self.main("--routes", "title", "--margin", "0")[1])
        self.assertEqual(got["now mixer (unpaced run)"], ["not recorded"])
        self.assertEqual(got["now device (real-time run)"][0], "1.00 s")

    def test_a_log_without_ax_frames_lines_reads_not_logged(self):
        self.play("now", device=([0] * 48000, [0] * 48000))
        write_file(self.build("now") / "probe" / "scorecard-title", "stdout.txt", "[ring] fill=1\n")
        got = groups(self.main("--routes", "title", "--margin", "0")[1])
        self.assertEqual(got["now device (real-time run)"][-1], "main L peak in the log not logged")

    def test_the_peak_is_the_highest_in_the_log(self):
        self.play("now", device=([0] * 48000, [0] * 48000))
        write_file(self.build("now") / "probe" / "scorecard-title", "stdout.txt", LOG + LOG.replace("33396", "61359"))
        got = groups(self.main("--routes", "title", "--margin", "0")[1])
        self.assertEqual(got["now device (real-time run)"][-1], "main L peak in the log 61359")

    def test_an_unpaced_recording_shorter_than_the_cut_exits_2(self):
        short = ([0] * 16000, [0] * 16000)
        self.play("now", mixer=short)
        code, out, err = self.main("--routes", "title", "--margin", "0")
        self.assertEqual(code, 2)
        self.assertIn("short of the 1 s", err)
        self.assertEqual(err.count("\n"), 1)

    def test_a_run_that_didnt_reach_the_last_checkpoint_exits_2(self):
        self.play("now", last_frame=59)
        code, _, err = self.main("--routes", "title")
        self.assertEqual(code, 2)
        self.assertIn("reached frame 60", err)

    def test_an_unknown_route_a_bad_label_and_a_negative_margin_exit_2(self):
        self.play("now")
        self.assertEqual(self.main("--routes", "nowhere")[0], 2)
        self.assertEqual(run_main(clip_signs.main, "no-label")[0], 2)
        self.assertEqual(self.main("--margin", "-1")[0], 2)

    def test_help_exits_0(self):
        code, out, _ = run_main(clip_signs.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("LABEL=BUILD_DIR", out)


if __name__ == "__main__":
    unittest.main()
