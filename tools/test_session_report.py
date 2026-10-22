import json
import math
import subprocess
import sys
import tempfile
import unittest
import wave
from array import array
from datetime import datetime, timedelta
from pathlib import Path

import audio_clicks
import core_audio_log
import session_report
from testutil import run_main, write_file

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


def tone(seconds: float, rate: int) -> list[int]:
    return [round(20000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(round(seconds * rate))]


def frames(left: list[int], right: list[int]) -> bytes:
    data = array("h", [v for f in zip(left, right) for v in f])
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


def device_sound() -> list[int]:
    """Two seconds at 48 kHz with spikes at 0.5, 1.0, 1.5 and 1.8 s, the last one clipped."""
    x = tone(2, OUT)
    for at in (0.5, 1.0, 1.5):
        x[round(at * OUT)] += 8000
    x[round(1.8 * OUT):round(1.8 * OUT) + 3] = [32767] * 3
    return x


def mixer_sound() -> list[int]:
    """Two seconds at 32 kHz with a spike at 0.5 s and 10 ms of silence at 1.2 s."""
    x = tone(2, DMA)
    x[round(0.5 * DMA)] += 8000
    x[round(1.2 * DMA):round(1.21 * DMA)] = [0] * round(0.01 * DMA)
    return x


def write_wav(path: Path, left: list[int], right: list[int]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(OUT)
        w.writeframes(frames(left, right))


def make_session(directory: Path, log: str = LOG, info: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    write_file(directory, "session.json", json.dumps(INFO if info is None else info))
    left = device_sound()
    write_wav(directory / "out.wav", left, tone(2, OUT))
    mixer = mixer_sound()
    write_file(directory, "aid.raw", frames(mixer, mixer))
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
