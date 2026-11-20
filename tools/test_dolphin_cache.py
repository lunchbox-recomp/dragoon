"""dolphin_cache.ready with a fake Dolphin: what it reuses, what makes it play again, and the
sandbox's log."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import dolphin_cache
import dolphin_ref
import dtm
from routes import parse_route
from testutil import temp_dir, write_file

SCRIPT = "100:A:5,"
FIELDS = 200  # under 256, so the fake's renew count never wraps
HEAD = "tolerance=4 budget=0.1%"


def fake_log(test: unittest.TestCase, *lines: str) -> list[str]:
    """A log stream that prints LINES and stops."""
    folder = temp_dir(test)
    text = "".join(f"{line}\n" for line in lines)
    write_file(folder, "lines.txt", text)
    script = write_file(folder, "log", f"#!/bin/sh\ncat '{folder}/lines.txt'\n")
    script.chmod(0o755)
    return [str(script)]


class FakeDolphin:
    """Plays any movie the same way: game frame N - LAG at the end of field N, and the game reads
    the pad once a field, given the route's buttons at the frame PAD_LAG frames before the one
    it says. It writes two dumps and exits with EXIT."""

    def __init__(self, script: str = SCRIPT) -> None:
        self.script = script
        self.lag, self.pad_lag, self.exit = 3, 0, 0
        self.runs: list[bytes] = []

    def __call__(self, iso: Path, movie: Path, fields: int, out: Path) -> int:
        self.runs.append(movie.read_bytes())
        cols = dolphin_cache.watched()
        at = {w: i for i, w in enumerate(cols)}
        presses = parse_route(self.script)
        frames = [max(0, n - self.lag) for n in range(1, fields + 1)]
        lines = ["frame " + " ".join(cols)]
        queue = [0] * dtm.QUEUE_LENGTH
        for n in range(1, fields + 1):
            words = [0] * len(cols)
            words[at[f"{dtm.RENEW:08X}"]] = frames[n - 1]
            given = frames[n - 2 - self.pad_lag] if n - 2 - self.pad_lag >= 0 else 0
            pad = dtm.pad_at(presses, 0, given)
            queue[n % dtm.QUEUE_LENGTH] = sum(dtm.PAD_BITS[b] for b in pad.buttons) << 16
            words[at[f"{dtm.PAD_STATE:08X}"]] = dtm.QUEUE_LENGTH << 24 | (n % dtm.QUEUE_LENGTH + 1) << 8
            for k, a in enumerate(dtm.BUTTON_WORDS):
                words[at[f"{a:08X}"]] = queue[k]
            lines.append(f"{n} " + " ".join(f"{w:08X}" for w in words))
        (out / "frames").mkdir(parents=True)
        write_file(out, "ram.txt", "\n".join(lines) + "\n")
        for k in (1, 2):
            write_file(out / "frames", f"framedump_{k}.png", b"png")
        write_file(out, "frames.txt", "aa  framedump_1.png\nbb  framedump_2.png\n")
        return self.exit


class CacheCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = temp_dir(self)
        (self.root / "src").mkdir()
        build = self.root / "build"
        (build / dolphin_ref.NOGUI).parent.mkdir(parents=True)
        write_file(build, str(dolphin_ref.NOGUI), b"dolphin 1")
        write_file(build, dolphin_ref.BUILT, '{"src": "409881c", "patch": "6c45"}\n')
        self.cache = temp_dir(self) / "top-ride-grass"
        self.log = self.cache.parent / "sandbox.log"
        self.dolphin = FakeDolphin()
        self.befores = 0
        for name, value in (("play", self.dolphin), ("LOG_STREAM", fake_log(self, "Filtering the log data using x"))):
            p = mock.patch.object(dolphin_cache, name, value)
            p.start()
            self.addCleanup(p.stop)

    def before(self) -> None:
        self.befores += 1

    def ready(self, script: str = SCRIPT, head: str = HEAD) -> dolphin_cache.Side:
        return dolphin_cache.ready(self.cache, script, FIELDS, Path("/disc.iso"), head, self.log,
                                   self.before, self.root)


class ReuseTest(CacheCase):
    def test_the_first_run_converges_and_the_next_reuses_it(self) -> None:
        side = self.ready()
        self.assertEqual((side.runs, side.why, side.off, side.denied), (2, "no saved run", [], []))
        self.assertEqual(self.befores, 2)  # once before each Dolphin run
        movie = (self.cache / "movie.dtm").read_bytes()
        self.assertEqual(movie, self.dolphin.runs[-1])
        self.assertNotEqual(movie, self.dolphin.runs[0])
        again = self.ready()
        self.assertEqual((again.runs, again.why, len(self.dolphin.runs), self.befores), (0, "", 2, 2))
        self.assertEqual(again.text(), "Dolphin's saved run reused")
        self.assertEqual(again.folder, self.cache / "dolphin")

    def test_a_stale_saved_run_is_played_again(self) -> None:
        def binary() -> None:
            write_file(self.root / "build", str(dolphin_ref.NOGUI), b"dolphin 2")

        def movie() -> None:
            path = self.cache / "movie.dtm"
            path.write_bytes(path.read_bytes()[:-1] + b"\1")

        def dump() -> None:
            (self.cache / "dolphin" / "frames" / "framedump_2.png").unlink()

        for change, why, kw in ((binary, "its dolphin changed", {}),
                                (movie, "its movie changed", {}),
                                (lambda: None, "its triage changed", {"head": "tolerance=5 budget=0.1%"}),
                                (lambda: None, "the movie isn't the route's fixed point now",
                                 {"script": "100:A:5,150:B:5"}),
                                (dump, "a dump it lists is gone", {})):
            with self.subTest(why=why):
                self.ready()
                change()
                runs = len(self.dolphin.runs)
                side = self.ready(**kw)
                self.assertEqual(side.why, why)
                self.assertEqual(side.runs, 1)  # from the saved run's timeline, already the fixed point
                self.assertEqual(len(self.dolphin.runs), runs + 1)
                self.assertEqual(self.ready(**kw).runs, 0)
                self.ready()

    def test_the_key_says_what_the_run_depends_on(self) -> None:
        self.ready()
        key = json.loads((self.cache / "key.json").read_text())
        self.assertEqual(sorted(key), ["built", "config", "disc", "dolphin", "fields", "macos", "movie",
                                       "triage", "watches"])
        self.assertEqual((key["triage"], key["fields"], key["disc"]), (HEAD, FIELDS, "console"))
        self.assertIn(f"{dtm.PAD_STATE:08X}", key["watches"])


class PlayTest(CacheCase):
    def test_a_run_that_stops_short_fails_and_leaves_no_key(self) -> None:
        self.ready()
        self.dolphin.exit = 1
        with self.assertRaisesRegex(dolphin_cache.Bad, "Dolphin's run 1 exited 1"):
            self.ready(head="tolerance=5 budget=0.1%")
        self.assertFalse((self.cache / "key.json").exists())
        self.dolphin.exit = 0
        self.assertEqual(self.ready().why, "no saved run")

    def test_no_fixed_point_fails(self) -> None:
        def drifting(iso: Path, movie: Path, fields: int, out: Path) -> int:
            self.dolphin.lag += 1
            return FakeDolphin.__call__(self.dolphin, iso, movie, fields, out)
        with mock.patch.object(dolphin_cache, "play", drifting), \
                self.assertRaisesRegex(dolphin_cache.Bad, "no fixed point in 10 runs"):
            self.ready()

    def test_a_press_off_its_frame_is_named(self) -> None:
        self.dolphin.pad_lag = 1
        self.assertEqual(self.ready().off, ["100:A read at game frame 101"])

    def test_missing_and_refused_set_ups(self) -> None:
        self.assertIsNone(dolphin_cache.missing(self.root))
        (self.root / "build" / dolphin_ref.NOGUI).unlink()
        self.assertIn("dolphin-emu-nogui", dolphin_cache.missing(self.root) or "")
        self.assertIn("src", dolphin_cache.missing(temp_dir(self)) or "")


class SandboxLogTest(CacheCase):
    def test_denials_but_dtracehelper_s_come_back_and_the_log_is_kept(self) -> None:
        command = fake_log(self, "Filtering the log data using x",
                           "Sandbox: dolphin-emu-nogui(1) deny(1) file-write-data /dev/dtracehelper dolphin-ref",
                           "Sandbox: dolphin-emu-nogui(1) deny(1) network-outbound 1.2.3.4:443 dolphin-ref")
        with mock.patch.object(dolphin_cache, "LOG_STREAM", command):
            side = self.ready()
        self.assertEqual(side.denied, ["Sandbox: dolphin-emu-nogui(1) deny(1) network-outbound 1.2.3.4:443 "
                                       "dolphin-ref"])
        self.assertIn("dtracehelper", self.log.read_text())

    def test_a_log_stream_that_doesnt_start_plays_nothing(self) -> None:
        with mock.patch.object(dolphin_cache, "LOG_STREAM", fake_log(self, "log: not allowed")), \
                self.assertRaisesRegex(dolphin_cache.Bad, "log stream didn't start: log: not allowed"):
            self.ready()
        self.assertEqual(self.dolphin.runs, [])


if __name__ == "__main__":
    unittest.main()
