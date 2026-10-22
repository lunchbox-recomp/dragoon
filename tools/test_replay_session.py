import json
import math
import subprocess
import sys
import tempfile
import unittest
from array import array
from pathlib import Path

import replay_session
from testutil import run_main, write_file

DMA = 32000
PARTED = ("[input] the replay has parted from its recording: a clock jump at poll 90 (frame 12), "
          "recorded between polls 80 and 85")


def mixer_sound(seconds: float) -> bytes:
    """A 440 Hz tone at 32 kHz on both channels with a spike at 0.5 s."""
    x = [round(20000 * math.sin(2 * math.pi * 440 * i / DMA)) for i in range(round(seconds * DMA))]
    x[DMA // 2] += 8000
    data = array("h", [v for v in x for _ in range(2)])
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


class FakeProbe:
    """Stands in for probe.sh: writes the replay's aid.raw where GCN_AIDWAV says, and its log."""

    def __init__(self, probe_root: Path, aid: bytes, log: str = "", returncode: int = 0):
        self.probe_root, self.aid, self.log, self.returncode = probe_root, aid, log, returncode
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, args, **kw):
        self.calls.append((args, kw))
        out = self.probe_root / args[1]
        aid = next(a.split("=", 1)[1] for a in args if a.startswith("GCN_AIDWAV="))
        Path(aid).write_bytes(self.aid)
        write_file(out, "stdout.txt", self.log)
        return subprocess.CompletedProcess(args, self.returncode)


class ReplayTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.probe_root = self.tmp / "probe"
        self.session = self.tmp / "20261022-160000"
        (self.session / "inputs").mkdir(parents=True)
        write_file(self.session / "inputs", "inputs.txt", "# gcn-recomp input log v4\n# end 120 12\n")
        self.sound = mixer_sound(2)
        write_file(self.session, "aid.raw", self.sound)
        write_file(self.session, "session.json", json.dumps({"engine_sha": "b848158"}))
        self.header = write_file(self.tmp, "gcn_engine_sha.h", '#define GCN_ENGINE_SHA "b848158"\n')

    def replay(self, fake: FakeProbe, trash=None) -> replay_session.Replay:
        return replay_session.replay(self.session, self.probe_root, fake, trash or self.fail_trash, self.header)

    def fail_trash(self, path: Path) -> None:
        self.fail(f"trashed {path}")

    def before(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.session)): p.read_bytes() for p in self.session.rglob("*") if p.is_file()}

    def test_a_faithful_replay_matches(self):
        kept = self.before()
        fake = FakeProbe(self.probe_root, self.sound + mixer_sound(1))
        r = self.replay(fake)
        self.assertTrue(r.comparison.match)
        self.assertEqual(r.comparison.session_bytes, len(self.sound))
        self.assertEqual((r.parted, r.engine), ([], None))
        self.assertEqual(self.before(), kept)

    def test_it_runs_probe_on_a_copy_of_the_inputs_with_the_dummy_driver(self):
        fake = FakeProbe(self.probe_root, self.sound)
        self.replay(fake)
        (args, kw), = fake.calls
        out = self.probe_root / "replay-20261022-160000"
        self.assertEqual(args, [str(replay_session.PROBE), "replay-20261022-160000", "124", "", "1000000",
                                f"GCN_AIDWAV={out / 'aid.raw'}", "GCN_AXSTATS=1", f"--replay={out / 'inputs'}",
                                "--exit-after=720"])
        self.assertEqual(kw["env"]["SDL_AUDIO_DRIVER"], "dummy")
        self.assertEqual((out / "inputs" / "inputs.txt").read_text(), "# gcn-recomp input log v4\n# end 120 12\n")

    def test_a_run_directory_gets_its_own_replay_name(self):
        run2 = self.session / "run-2"
        (run2 / "inputs").mkdir(parents=True)
        write_file(run2, "aid.raw", self.sound)
        self.session = run2
        fake = FakeProbe(self.probe_root, self.sound)
        self.assertEqual(self.replay(fake).out, self.probe_root / "replay-20261022-160000-run-2")

    def test_a_replay_that_differs_says_where(self):
        changed = bytearray(self.sound)
        changed[48000 * 4 + 2] ^= 1
        r = self.replay(FakeProbe(self.probe_root, bytes(changed)))
        self.assertFalse(r.comparison.match)
        self.assertEqual(r.comparison.first_difference, 48000 * 4 + 2)
        self.assertIn("first differ 1.500 s in", "\n".join(replay_session.render(self.session, r, 10)))

    def test_a_short_replay_doesnt_match(self):
        r = self.replay(FakeProbe(self.probe_root, self.sound[:len(self.sound) // 2]))
        self.assertTrue(r.comparison.short)
        self.assertFalse(r.comparison.match)
        self.assertIsNone(r.comparison.first_difference)
        self.assertIn("stops at 1.0 s of 2.0", "\n".join(replay_session.render(self.session, r, 10)))

    def test_mixer_clicks_over_the_sessions_length(self):
        r = self.replay(FakeProbe(self.probe_root, self.sound + mixer_sound(1)))
        self.assertEqual([round(t, 3) for t in r.clicks], [0.5])

    def test_parted_lines_and_another_engine_are_reported(self):
        write_file(self.session, "session.json", json.dumps({"engine_sha": "0123abc"}))
        r = self.replay(FakeProbe(self.probe_root, self.sound, log=f"[ft] f1\n{PARTED}\n"))
        self.assertEqual(r.parted, [PARTED])
        self.assertEqual(r.engine, "the session was recorded on engine 0123abc and the build is b848158")

    def test_an_old_replay_is_trashed_first(self):
        old = self.probe_root / "replay-20261022-160000"
        old.mkdir(parents=True)
        trashed = []
        self.replay(FakeProbe(self.probe_root, self.sound), trash=lambda p: (trashed.append(p), p.rename(self.tmp / "t")))
        self.assertEqual(trashed, [old])


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.session = self.tmp / "s"
        (self.session / "inputs").mkdir(parents=True)
        self.sound = mixer_sound(1)
        write_file(self.session, "aid.raw", self.sound)

    def main(self, fake, *args: str) -> tuple[int, str, str]:
        return run_main(lambda argv: replay_session.main(argv, fake, self.tmp / "probe"), str(self.session), *args)

    def test_exits_0_on_a_match(self):
        code, out, _ = self.main(FakeProbe(self.tmp / "probe", self.sound))
        self.assertEqual(code, 0)
        self.assertIn("match    yes", out)

    def test_exits_1_on_a_difference(self):
        code, out, _ = self.main(FakeProbe(self.tmp / "probe", self.sound[:-4] + b"\0\0\0\1"))
        self.assertEqual(code, 1)
        self.assertIn("match    no", out)

    def test_a_session_without_inputs_or_aid_raw_exits_2(self):
        for name in ("inputs", "aid.raw"):
            with self.subTest(name=name):
                (self.session / name).rename(self.tmp / name)
                code, _, err = self.main(FakeProbe(self.tmp / "probe", self.sound))
                self.assertEqual(code, 2)
                self.assertIn(f"{name}: missing", err)
                (self.tmp / name).rename(self.session / name)

    def test_a_failed_probe_run_exits_2(self):
        code, _, err = self.main(FakeProbe(self.tmp / "probe", self.sound, returncode=2))
        self.assertEqual(code, 2)
        self.assertIn("probe.sh exited 2", err)


if __name__ == "__main__":
    unittest.main()
