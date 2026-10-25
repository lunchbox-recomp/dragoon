from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import audio_clicks
import core_audio_log
import noise_blocks
import session_report
import session_text
from testutil import noise, pcm, run_main, tone, write_file, write_wav

OUT, DMA = 48000, 32000
EPOCH = 1792710000
INFO = {"start": "2026-10-22T16:00:00-07:00", "start_epoch": EPOCH,
        "host": {"os": "macOS 26.5", "cpu": "Apple M3 Pro", "refresh_hz": 120.0}, "engine_sha": "b848158",
        "audio_device": {"driver": "coreaudio", "rate": 48000, "channels": 2, "buffer": 512},
        "command_line": ["build/dragoon"]}

# One click each the mixer, the ring and the device explain, and one nothing does.
LOG = """\
[session] build/playtest/20261022-160000
[audio] device driver=coreaudio rate=48000 channels=2 buffer=512
[audio] output frame 0 plays DMA frame 0
[ring] cut 640 frames at output frame 48000
[audio] output frame 48000 plays DMA frame 32640
[audio] underrun at output frame 60000 frames=512
[audio] underrun at output frame 60512 frames=100
[audio] late callback at output frame 72000 gap_ms=17.1
[audio] callbacks n=400 period_ms=10.67 late=1 worst_ms=17.1 underruns=2
[shaders] built program 3 in the background in 9.0 ms
[ft] f298 guest  90.00ms  fe   0.18ms (tex  0.17)  draws    1/   3  verts      4  idx      6  states    1
[rt] f299 render  50.00ms (tex  0.33 vbo  0.00 copies  0.01)  applies    1  programs 6
[ft] f299 guest  16.00ms  fe   0.18ms (tex  0.17)  draws    1/   3  verts      4  idx      6  states    1
[shaders] compiled program 4 in 40.0 ms
[rt] f300 render  45.00ms (tex  0.33 vbo  0.00 copies  0.01)  applies    1  programs 6
[ft] f300 guest  40.00ms  fe   0.18ms (tex  0.17)  draws    1/   3  verts      4  idx      6  states    1
[rt] f301 render   2.00ms (tex  0.33 vbo  0.00 copies  0.01)  applies    1  programs 6
[ft] f301 guest  16.00ms  fe   0.18ms (tex  0.17)  draws    1/   3  verts      4  idx      6  states    1
[rt] f302 render   3.00ms (tex  0.33 vbo  0.00 copies  0.01)  applies    1  programs 6
FATAL: guest panic: game.c:12: oops
"""


def device_sound() -> list[int]:
    """Two seconds at 48 kHz with spikes at 0.5, 1.0, 1.5 and 1.8 s, the last one clipped."""
    x = tone(2 * OUT, OUT)
    for at in (0.5, 1.0, 1.5):
        x[round(at * OUT)] += 8000
    x[round(1.8 * OUT):round(1.8 * OUT) + 3] = [32767] * 3
    return x


def mixer_sound() -> list[int]:
    """Two seconds at 32 kHz with a spike at 0.5 s and 10 ms of silence at 1.2 s."""
    x = tone(2 * DMA, DMA)
    x[round(0.5 * DMA)] += 8000
    x[round(1.2 * DMA):round(1.21 * DMA)] = [0] * round(0.01 * DMA)
    return x


def make_session(directory: Path, log: str = LOG, info: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    write_file(directory, "session.json", json.dumps(INFO if info is None else info))
    write_wav(directory / "out.wav", device_sound(), tone(2 * OUT, OUT))
    mixer = mixer_sound()
    write_file(directory, "aid.raw", pcm(mixer, mixer))
    write_file(directory, "stdout.txt", log)
    return directory


class Fake:
    """Stands in for subprocess.run, so no test reads the live system log."""

    def __init__(self, stdout: str = "", returncode: int = 0, error: Exception | None = None):
        self.stdout, self.returncode, self.error = stdout, returncode, error
        self.cmds: list[list[str]] = []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "log: bad predicate")


class Session(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.dir = make_session(self.tmp / "20261022-160000")

    def report(self, *args: str, run=None) -> tuple[int, dict, str]:
        code, out, err = run_main(lambda argv: session_report.main(argv, run or Fake()), str(self.dir), "--json", *args)
        return code, json.loads(out) if out else {}, err


class ReportTest(Session):
    def test_each_device_click_is_put_down_to_its_stage(self):
        code, r, _ = self.report()
        self.assertEqual(code, 0)
        placed = [(round(p["at"], 2), p["stage"]) for p in r["stages"]["clicks"]]
        self.assertEqual(placed, [(0.5, "mixer"), (1.0, "ring"), (1.5, "device"), (1.8, "unexplained")])
        self.assertEqual(r["stages"]["counts"], {"mixer": 1, "ring": 1, "device": 1, "unexplained": 1})

    def test_counts_both_stages_a_minute(self):
        _, r, _ = self.report()
        device, mixer = r["sound"]["device"], r["sound"]["mixer"]
        self.assertEqual((device["seconds"], device["rate"], mixer["rate"]), (2.0, OUT, DMA))
        self.assertEqual((device["clicks"], device["clipped"], device["gaps"]), (4, 1, 0))
        self.assertEqual(device["per_minute"], {"clicks": 120.0, "gaps": 0.0, "clipped": 30.0})
        self.assertEqual(mixer["gaps"], 1)
        self.assertEqual(mixer["per_minute"]["gaps"], 30.0)
        whole = audio_clicks.analyse(audio_clicks.read_raw(self.dir / "aid.raw", DMA), 0)
        self.assertEqual(mixer["click_times"], [c.at for c in whole.clicks])

    def test_the_device_its_callbacks_and_the_rings_trouble(self):
        _, r, _ = self.report()
        d = r["device"]
        self.assertEqual(d["device"], INFO["audio_device"])
        self.assertEqual(d["callbacks"]["n"], 400)
        self.assertEqual(d["late"], [{"at": 1.5, "gap_ms": 17.1}])
        self.assertEqual(d["short_pulls"], 2)
        self.assertEqual(d["underruns"], [{"at": 1.25, "ms": 612 * 1000 / OUT}])
        self.assertEqual(d["cuts"], [{"at": 1.0, "frames": 640}])

    def test_pacing_counts_from_frame_300(self):
        _, r, _ = self.report()
        p = r["pacing"]
        self.assertEqual((p["guest"]["n"], p["guest"]["worst"], p["guest_over"]), (3, 40.0, 1))
        self.assertEqual((p["render"]["n"], p["render"]["worst"], p["render_over"]), (3, 45.0, 1))
        self.assertEqual((p["compiled"], p["compiled_ms"]), (1, 40.0))
        self.assertEqual(r["shaders_background"], 1)

    def test_crashes_and_the_session(self):
        _, r, _ = self.report()
        self.assertEqual(r["crashes"], ["FATAL: guest panic: game.c:12: oops"])
        s = r["session"]
        self.assertEqual((s["seconds"], s["start"], s["engine_sha"], s["missing"]), (2.0, INFO["start"], "b848158", []))
        self.assertEqual(r["system_log"], None)

    def test_the_text_says_the_same(self):
        code, out, _ = run_main(lambda argv: session_report.main(argv, Fake()), str(self.dir))
        self.assertEqual(code, 0)
        for text in ("length  2.0 s (0 min 2 s)", "macOS 26.5, Apple M3 Pro, a 120 Hz display",
                     "device   coreaudio, 48000 Hz, 2 channels, 512 frames a period (10.67 ms)",
                     "of 4 device clicks: mixer 1, ring 1, device 1, unexplained 1",
                     "1.500 s  device, a callback came 17.1 ms after the last at 1.500 s",
                     "1 over 33 ms", "1 compiled on the render thread", "crashes  1"):
            self.assertIn(text, out)

    def test_a_missing_recording_leaves_its_sections_out(self):
        (self.dir / "aid.raw").rename(self.tmp / "aid.raw")
        code, r, err = self.report()
        self.assertEqual(code, 0)
        self.assertEqual((r["session"]["missing"], r["stages"], r["sound"]["mixer"]), (["aid.raw"], None, None))
        self.assertEqual(r["sound"]["device"]["clicks"], 4)
        self.assertIn("aid.raw: missing or empty", err)

    def test_an_empty_recording_is_missing(self):
        write_wav(self.dir / "out.wav", [], [])
        _, r, _ = self.report()
        self.assertEqual(r["session"]["missing"], ["out.wav"])
        self.assertEqual(r["session"]["seconds"], 2.0)

    def test_a_device_recording_that_ends_before_its_header_says_keeps_its_stage(self):
        wav = self.dir / "out.wav"
        wav.write_bytes(wav.read_bytes()[:-4 * OUT // 2])  # the last half second
        _, r, _ = self.report()
        self.assertEqual(r["session"]["missing"], [])
        self.assertEqual((r["sound"]["device"]["seconds"], r["sound"]["device"]["clicks"]), (1.5, 2))
        self.assertEqual(r["session"]["seconds"], 1.5)

    def test_the_device_comes_from_session_json_without_a_device_line(self):
        write_file(self.dir, "stdout.txt", "\n".join(line for line in LOG.splitlines() if "device driver" not in line))
        _, r, _ = self.report()
        self.assertEqual(r["device"]["device"], INFO["audio_device"])

    def test_no_session_json_exits_2(self):
        (self.dir / "session.json").rename(self.tmp / "session.json")
        code, _, err = self.report()
        self.assertEqual(code, 2)
        self.assertIn("is " + str(self.dir) + " a session directory?", err)

    def test_a_run_directory_reads_its_own_run(self):
        run2 = make_session(self.dir / "run-2", log="")
        write_file(self.dir, "stdout.txt", LOG.replace("FATAL", "[reset] the game reset the console\nFATAL")
                   + "[session] build/playtest/20261022-160000/run-2\n"
                   + "[audio] device driver=dummy rate=48000 channels=2 buffer=512\n")
        (run2 / "stdout.txt").rename(self.tmp / "unused.txt")
        self.dir = run2
        _, r, _ = self.report()
        self.assertEqual(r["device"]["device"]["driver"], "dummy")
        self.assertEqual((r["device"]["late"], r["crashes"], r["session"]["reset"]), ([], [], False))
        self.dir = run2.parent
        _, r, _ = self.report()
        self.assertTrue(r["session"]["reset"])

    def test_the_run_after_a_reset_is_named_from_this_one(self):
        reset = "[reset] the game reset the console (hot reset, code 0)\n"
        write_file(self.dir, "stdout.txt", LOG + reset + "[session] x/run-2\n" + reset)
        _, r, _ = self.report()
        self.assertEqual(r["session"]["next_run"], "run-2")
        run2 = make_session(self.dir / "run-2")
        (run2 / "stdout.txt").unlink()
        self.dir = run2
        _, r, _ = self.report()
        self.assertEqual(r["session"]["next_run"], "run-3")

    def test_a_shutdown_ends_the_run_with_none_after_it(self):
        write_file(self.dir, "stdout.txt", LOG + "[reset] the game reset the console (shutdown, code 0)\n")
        _, r, _ = self.report()
        self.assertEqual((r["session"]["reset"], r["session"]["next_run"]), (True, None))
        _, out, _ = run_main(lambda argv: session_report.main(argv, Fake()), str(self.dir))
        self.assertIn("the game shut the console down, which ended this run", out)
        self.assertNotIn("the next is in", out)

    def test_the_text_names_the_run_a_reset_goes_on_in(self):
        write_file(self.dir, "stdout.txt", LOG + "[reset] the game reset the console (restart, code 0)\n")
        _, out, _ = run_main(lambda argv: session_report.main(argv, Fake()), str(self.dir))
        self.assertIn("the game reset the console, which ended this run, and the next is in run-2/", out)

    def test_a_length_just_under_a_minute_boundary_rounds_before_it_is_split(self):
        info = {"dir": "d", "seconds": 119.6, "start": None, "host": None, "engine_sha": None, "missing": [],
                "reset": False, "next_run": None}
        self.assertIn("  length  119.6 s (2 min 0 s), started None", session_text.session(info))


def noisy_mixer() -> list[int]:
    """Two seconds at 32 kHz of a tone with full-scale noise from 0.5 s to 1.0 s and again from
    1.5 s to 1.6 s."""
    x = tone(2 * DMA, DMA)
    x[DMA // 2:DMA] = noise(DMA // 2, 32767, 1)
    x[3 * DMA // 2:3 * DMA // 2 + DMA // 10] = noise(DMA // 10, 32767, 2)
    return x


def section(out: str, name: str) -> list[str]:
    """The report's lines for one section: its first line and the indented ones after it."""
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(name))
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].startswith(" ")), len(lines))
    return lines[start:end]


class NoiseTest(Session):
    def write_mixer(self, x: list[int], extra: bytes = b"") -> None:
        write_file(self.dir, "aid.raw", pcm(x, x) + extra)

    def text(self, *args: str) -> tuple[int, str, str]:
        return run_main(lambda argv: session_report.main(argv, Fake()), str(self.dir), *args)

    def test_names_each_noise_like_stretch_with_where_it_starts_and_ends(self):
        self.write_mixer(noisy_mixer())
        code, r, err = self.report()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(r["noise"], {"seconds": 2.0, "blocks": 400, "noisy_blocks": 120, "noisy_seconds": 0.6,
                                      "stretches": [{"start": 0.5, "end": 1.0, "blocks": 100},
                                                    {"start": 1.5, "end": 1.6, "blocks": 20}]})
        code, out, err = self.text()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(section(out, "noise"), ["noise    2 stretches in aid.raw, 0.60 s of 2.00 s noise-like",
                                                 "    0.500 s to 1.000 s, 100 blocks",
                                                 "    1.500 s to 1.600 s, 20 blocks"])

    def test_list_caps_the_stretches_printed(self):
        self.write_mixer(noisy_mixer())
        _, out, _ = self.text("--list", "1")
        self.assertEqual(section(out, "noise")[1:], ["    0.500 s to 1.000 s, 100 blocks", "    and 1 more"])

    def test_one_stretch_of_one_block_reads_in_the_singular(self):
        x = tone(2 * DMA, DMA)
        x[DMA // 2:DMA // 2 + 160] = noise(160, 32767, 3)
        self.write_mixer(x)
        _, out, _ = self.text()
        self.assertEqual(section(out, "noise"), ["noise    1 stretch in aid.raw, 0.01 s of 2.00 s noise-like",
                                                 "    0.500 s to 0.505 s, 1 block"])

    def test_a_session_without_noise_says_none(self):
        code, r, err = self.report()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(r["noise"], {"seconds": 2.0, "blocks": 400, "noisy_blocks": 0, "noisy_seconds": 0.0,
                                      "stretches": []})
        code, out, err = self.text()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(section(out, "noise"), ["noise    none in aid.raw"])

    def test_it_reads_aid_raw_and_never_the_device_recording(self):
        write_wav(self.dir / "out.wav", noise(2 * OUT, 32767, 5), noise(2 * OUT, 32767, 6))
        _, r, _ = self.report()
        self.assertEqual(r["noise"]["stretches"], [])
        self.write_mixer(noisy_mixer())
        write_wav(self.dir / "out.wav", tone(2 * OUT, OUT), tone(2 * OUT, OUT))
        _, r, _ = self.report()
        self.assertEqual(len(r["noise"]["stretches"]), 2)

    def test_aid_raw_is_a_recording_noise_blocks_reads_and_gives_the_same_result(self):
        self.write_mixer(noisy_mixer())
        code, out, _ = run_main(noise_blocks.main, str(self.dir / "aid.raw"), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), self.report()[1]["noise"])

    def test_a_recording_cut_off_mid_frame_reads_its_whole_frames(self):
        self.write_mixer(noisy_mixer(), extra=b"\x01\x02\x03")
        _, r, _ = self.report()
        self.assertEqual((r["noise"]["blocks"], len(r["noise"]["stretches"])), (400, 2))

    def test_a_missing_or_empty_aid_raw_is_left_out_as_the_other_stages_are(self):
        for name, data in (("missing", None), ("empty", b""), ("under a frame", b"\0\0\0")):
            with self.subTest(name):
                if data is None:
                    (self.dir / "aid.raw").unlink()
                else:
                    write_file(self.dir, "aid.raw", data)
                code, r, err = self.report()
                self.assertEqual(code, 0)
                self.assertEqual((r["noise"], r["session"]["missing"]), (None, ["aid.raw"]))
                self.assertEqual((r["sound"]["mixer"], r["stages"]), (None, None))
                self.assertEqual(r["sound"]["device"]["clicks"], 4)
                self.assertIn("aid.raw: missing or empty", err)
                code, out, _ = self.text()
                self.assertEqual(code, 0)
                self.assertEqual(section(out, "noise"), ["noise    aid.raw missing"])

    def test_a_stretch_of_noise_doesnt_change_the_exit_code(self):
        self.write_mixer(noisy_mixer())
        for args in ((), ("--json",), ("--list", "0")):
            with self.subTest(args=args):
                code, _, err = self.text(*args)
                self.assertEqual((code, err), (0, ""))


class SystemLogTest(Session):
    def test_counts_overloads_over_the_sessions_wall_clock_window(self):
        line = ("2026-10-22 16:00:01.000 E  dragoon[5150:20a1] [com.apple.coreaudio:] "
                "HALC_ProxyIOContext::IOWorkLoop: skipping cycle due to overload\n")
        fake = Fake(stdout=line * 3)
        _, r, _ = self.report("--system-log", run=fake)
        start = datetime.fromtimestamp(EPOCH)
        self.assertEqual(fake.cmds, [core_audio_log.command(start, start + timedelta(seconds=2 + 5))])
        self.assertEqual((r["system_log"]["overloads"], r["system_log"]["by_process"]), (3, {"dragoon": 3}))

    def test_a_failed_log_show_is_reported_not_fatal(self):
        code, r, _ = self.report("--system-log", run=Fake(returncode=64))
        self.assertEqual(code, 0)
        self.assertEqual(r["system_log"]["error"], "log show exited 64: log: bad predicate")
        _, r, _ = self.report("--system-log", run=Fake(error=FileNotFoundError(2, "No such file")))
        self.assertIn("No such file", r["system_log"]["error"])

    def test_needs_the_start_time(self):
        write_file(self.dir, "session.json", json.dumps({k: v for k, v in INFO.items() if k != "start_epoch"}))
        fake = Fake()
        _, r, _ = self.report("--system-log", run=fake)
        self.assertEqual((fake.cmds, "error" in r["system_log"]), ([], True))


if __name__ == "__main__":
    unittest.main()
