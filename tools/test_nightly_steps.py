"""The audio, shaders, timed and soak steps on nightly_fakes.FakeTree, with the runs each step
plays standing in for the game's: what they return becomes the checks, and what's kept."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import audio_hashes
import bot_soak
import nightly_steps
import route_compiles
import timed_bars
import warm_shaders
from nightly_fakes import FakeTree
from nightly_report import FAIL, PASS, Check
from testutil import write_file


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_file(path.parent, path.name, text)

HASH = "0123456789ABCDEF"


class StepCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = FakeTree(self)

    def patch(self, target: object, name: str, new: object) -> None:
        p = mock.patch.object(target, name, new)
        p.start()
        self.addCleanup(p.stop)

    def play(self, step: str, **kw) -> dict[str, Check]:
        return self.tree.by_id(self.tree.play(step, self.tree.context(**kw)))

    def kept(self) -> list[str]:
        return sorted(p.relative_to(self.tree.report).as_posix() for p in self.tree.report.rglob("*")
                      if p.is_file() and "work" not in p.parts)


class AudioStepTest(StepCase):
    def setUp(self) -> None:
        super().setUp()
        for name in ("title", "menu"):
            write_file(self.tree.hashes / "audio", f"{name}.txt", f"400 {HASH}\n800 {HASH}\n")
        self.patch(audio_hashes, "ROOT", self.tree.root)
        self.patch(audio_hashes, "hash_route", self.hash_route)

    def hash_route(self, route, allow_crash: bool = False, settings: tuple[str, ...] = ()) -> dict[int, str]:
        out = self.tree.root / "build" / "probe" / f"audio-{route.name}"
        put(out / "stdout.txt", f"[ax] the {route.name} log\n")
        return {400: HASH, 800: HASH} if route.name == "title" else {400: HASH, 800: "F" * 16}

    def test_a_changed_row_fails_and_keeps_only_its_log(self) -> None:
        checks = self.play("audio")
        self.assertEqual(checks["audio title"].status, PASS)
        menu = checks["audio menu"]
        self.assertEqual((menu.status, menu.kind, menu.dump), (FAIL, "sounded differently", "audio/menu.log"))
        self.assertEqual([(p.where, p.what) for p in menu.problems], [("list 800", f"{'F' * 16} != golden {HASH}")])
        self.assertEqual(self.kept(), ["audio/menu.log"])
        self.assertEqual((self.tree.games, self.tree.runs_left()), (2, []))


class ShadersStepTest(StepCase):
    def setUp(self) -> None:
        super().setUp()
        self.warmed = 0
        self.patch(warm_shaders, "warm", self.warm)
        self.patch(warm_shaders.shader_cache, "load", lambda path: SimpleNamespace(keys=[b"a", b"b", b"a"]))
        self.patch(route_compiles, "play", self.compiles)

    def warm(self, game: Path, saves: Path, plan, jobs: int = 1, before=None) -> None:
        self.warmed += 1
        before()
        write_file(saves, warm_shaders.CACHE, "a cache")

    def compiles(self, route, cache: Path, aspect: str, root: Path, probe: Path, settings, keep: Path):
        self.assertEqual(cache.read_text(), "a cache")
        c = route_compiles.Compiles([70] if route.name == "title" else [], 100, 100)
        if not c.ok:
            put(keep, "[shaders] compiled program 1\n")
        return c

    def test_a_route_that_compiles_fails_at_its_frame_and_keeps_its_log(self) -> None:
        checks = self.play("shaders")
        self.assertEqual(self.warmed, 1)
        self.assertEqual((checks["shaders warm-up"].status, checks["shaders warm-up"].value), (PASS, 2.0))
        for aspect, tag in (("4:3", "4x3"), ("16:9", "16x9")):
            title = checks[f"shaders {aspect} title"]
            self.assertEqual((title.status, title.problems[0].where, title.problems[0].dump),
                             (FAIL, "frame 70", f"shaders/{tag}-title.log"))
            self.assertEqual(checks[f"shaders {aspect} menu"].status, PASS)
        self.assertEqual(self.kept(), ["shaders/16x9-title.log", "shaders/4x3-title.log"])
        self.assertEqual(self.tree.games, 5)  # the warm-up, then two routes at two aspects

    def test_a_warm_up_that_fails_plays_no_route(self) -> None:
        def failed(*args, **kw) -> None:
            raise warm_shaders.PassFailed("pass 3 never reached frame 900\nmore")
        self.patch(warm_shaders, "warm", failed)
        checks = self.play("shaders")
        self.assertEqual(list(checks), ["shaders warm-up"])
        self.assertEqual((checks["shaders warm-up"].status, checks["shaders warm-up"].detail),
                         (FAIL, "pass 3 never reached frame 900"))


class TimedStepTest(StepCase):
    def setUp(self) -> None:
        super().setUp()
        self.patch(warm_shaders, "warm", lambda game, saves, plan, jobs=1, before=None:
                   write_file(saves, warm_shaders.CACHE, "a cache"))
        self.patch(warm_shaders.shader_cache, "load", lambda path: SimpleNamespace(keys=[b"a"]))
        self.patch(timed_bars, "four_player", self.four)
        self.patch(timed_bars, "menu_redraw", self.menu)
        self.patch(timed_bars, "race_finish", self.race)
        self.results = {"4:3": timed_bars.RESULTS_FRAME, "16:9": timed_bars.RESULTS_FRAME + 1}

    def four(self, cache: Path, *, root, probe, settings, keep: Path, before) -> dict:
        put(keep, "[rt] lines\n")
        return {"4p.rt_p99": 9.0, "4p.compiles": 0, "boot.ms": 600.0}

    def menu(self, cache: Path, runs: int, *, root, probe, settings, keep: Path, before) -> dict:
        put(keep, "[overlay] lines\n")
        return {"menu.interval_p99": 16.9, "menu.cpu_p99": 0.7}

    def race(self, aspect: str, *, probe, settings, before) -> int:
        return self.results[aspect]

    def test_each_number_against_its_bar(self) -> None:
        checks = self.play("timed")
        got = {k: (c.status, c.value) for k, c in checks.items() if k.startswith("timed ")}
        self.assertEqual(got, {
            "timed 4p.rt_p99": (FAIL, 9.0), "timed 4p.compiles": (PASS, 0.0), "timed boot.ms": (PASS, 600.0),
            "timed race.results_4:3": (PASS, 13062.0), "timed race.results_16:9": (FAIL, 13063.0),
            "timed menu.interval_p99": (PASS, 16.9), "timed menu.cpu_p99": (PASS, 0.7)})
        self.assertEqual(checks["timed race.results_16:9"].kind, "not frame 13062")
        self.assertEqual({k for k, c in checks.items() if c.timed},
                         {"timed 4p.rt_p99", "timed boot.ms", "timed menu.interval_p99", "timed menu.cpu_p99"})
        self.assertEqual(checks["timed 4p.rt_p99"].dump, "logs/4p.log")
        self.assertEqual(len(checks["timed menu.cpu_p99"].load or []), 2)

    def test_a_race_that_ends_late_at_both_aspects_fails_at_both(self) -> None:
        self.results = {"4:3": 13862, "16:9": 13862}
        checks = self.play("timed")
        self.assertEqual([checks[f"timed race.results_{a}"].status for a in ("4:3", "16:9")], [FAIL, FAIL])


class SoakStepTest(StepCase):
    def setUp(self) -> None:
        super().setUp()
        self.calls: list[tuple[str, str, int]] = []
        self.patch(bot_soak, "soak", self.soak)

    def soak(self, args, settings: list[str], *, out, err) -> int:
        mode, name = args.modes[0], f"soak-{len(self.calls)}"
        self.calls.append((mode, str(args.ports), args.seed))
        run_dir = self.tree.root / "build" / "probe" / name
        put(run_dir / "stdout.txt", "x")
        out(f"{name}: seed {args.seed}, {args.minutes:g} min")
        if mode == "top-ride":
            out("STOP panic: guest panic: foo.c:12: boom")
            out(f"  {run_dir / 'bot.json'}")
            return 1
        out(f"{name}: no stop in 0.1 min (6 frames)")
        return 0

    def test_four_soaks_with_the_runs_seed_and_a_stop_kept(self) -> None:
        checks = self.play("soak", seed=181331, soak_minutes=0.1)
        self.assertEqual(self.calls, [("air-ride", "1", 181331), ("top-ride", "1", 181331),
                                      ("city-trial", "1", 181331), ("city-trial", "4", 181331)])
        self.assertEqual(checks["soak air-ride 1p"].detail, "no stop in 0.1 min (6 frames)")
        top = checks["soak top-ride 1p"]
        self.assertEqual((top.status, top.problems[0].what), (FAIL, "STOP panic: guest panic: foo.c:12: boom"))
        self.assertTrue(top.dump.endswith("soak-1/bot.json"))
        self.assertEqual(self.tree.runs_left(), ["soak-1"])  # only the stop's run stays
        self.assertEqual(self.tree.games, 4)


if __name__ == "__main__":
    unittest.main()
