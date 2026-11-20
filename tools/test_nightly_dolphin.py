"""The nightly's dolphin step on nightly_fakes.FakeTree, with test_dolphin_cache's fake Dolphin
and Dragoon's run and the picture compare standing in for the game's."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest import mock

import dolphin_cache
import dolphin_diff
import dolphin_ref
import nightly
import nightly_dolphin
import nightly_steps
from nightly_report import FAIL, PASS, SKIPPED
from test_dolphin_cache import FakeDolphin, fake_log
from test_nightly_steps import StepCase
from testutil import write_file

TRIAGE = ("tolerance=4 budget=0.1%\ntitle fields=200\n"
          "title 60 share=0.000% max=3 mean=0.01 state=same within under the budget and the state matching\n"
          "title 120 share=1.342% max=230 mean=1.11 state=same timing the SAVE icon's load order\n")


class DolphinStepTest(StepCase):
    def setUp(self) -> None:
        super().setUp()
        write_file(self.tree.hashes, "dolphin-triage.txt", TRIAGE)
        (self.tree.root / "tests" / "routes").mkdir(parents=True)
        write_file(self.tree.root / "tests" / "routes", "title.txt", "100:A:5\n")
        (self.tree.root / "rom").mkdir()
        write_file(self.tree.root / "rom", "game.iso", b"GKYE01")
        self.dolphin_root = self.tree.root / "dolphin-ref"
        (self.dolphin_root / "src").mkdir(parents=True)
        (self.dolphin_root / "build" / dolphin_ref.NOGUI).parent.mkdir(parents=True)
        write_file(self.dolphin_root / "build", str(dolphin_ref.NOGUI), b"dolphin")
        write_file(self.dolphin_root / "build", dolphin_ref.BUILT, "{}\n")
        self.dolphin = FakeDolphin("100:A:5")
        self.shares = {60: 0.0, 120: 0.01342}
        self.played: list[tuple] = []
        self.patch(dolphin_cache, "dolphin_root", lambda: self.dolphin_root)
        self.patch(dolphin_cache, "checked", lambda root: None)
        self.patch(dolphin_cache, "play", self.counted)
        self.patch(dolphin_cache, "LOG_STREAM", fake_log(self, "Filtering the log data using x"))
        self.patch(dolphin_diff, "play_dragoon", self.dragoon)
        self.patch(dolphin_diff, "compare", self.compare)

    def counted(self, *args) -> int:
        return self.dolphin(*args)

    def dragoon(self, route, out: Path, dolphin: Path, frames, probe, settings) -> Optional[str]:
        self.played.append((route.name, list(frames), dolphin, tuple(settings)))
        (out / "dragoon").mkdir(parents=True)
        write_file(out / "dragoon", "state.json", json.dumps({"states": {}, "trace": {}}))
        return None

    def compare(self, route, out: Path, frames, dolphin: Path) -> dict:
        (out / "sides").mkdir()
        entries = []
        for f in frames:
            side = write_file(out / "sides", f"{route.name}-{f:05d}.png", b"side")
            entries.append({"frame": f, "share": self.shares[f], "max": 9, "mean": 0.1, "state": "same",
                            "over": self.shares[f] > 0.001, "state_diff": [], "side": str(side)})
        return {"checkpoints": entries}

    def test_a_checkpoint_that_moved_fails_and_keeps_only_its_picture(self) -> None:
        self.shares[60] = 0.02677
        checks = self.play("dolphin", build=self.tree.root / "elsewhere")
        self.assertEqual({k: c.status for k, c in checks.items()},
                         {"dolphin title sandbox": PASS, "dolphin title 60": FAIL, "dolphin title 120": PASS})
        moved = checks["dolphin title 60"]
        self.assertEqual((moved.kind, moved.dump, moved.problems[0].where),
                         ("moved", "dolphin/title-00060.png", "frame 60"))
        self.assertIn("within at share 0.000% max 3", moved.problems[0].what)
        self.assertIn("over at share 2.677% max 9", moved.problems[0].what)
        self.assertEqual(self.kept(), ["dolphin/title-00060.png"])
        self.assertEqual(self.played[0][:2], ("title", [60, 120]))
        self.assertEqual(self.played[0][3], (f"--bin={self.tree.root / 'elsewhere' / 'dragoon'}",))
        self.assertEqual(self.tree.games, 3)  # Dolphin twice to its fixed point, then Dragoon

    def test_the_next_night_reuses_dolphin_s_run(self) -> None:
        self.play("dolphin")
        self.tree.games = 0
        checks = self.play("dolphin")
        self.assertEqual(checks["dolphin title sandbox"].detail, "Dolphin's saved run reused")
        self.assertEqual((self.tree.games, len(self.dolphin.runs)), (1, 2))
        cache = self.tree.root / "build" / "nightly" / "dolphin-cache" / "title"
        self.assertEqual(self.played[1][2], cache / "dolphin")

    def test_an_improvement_passes_and_keeps_its_picture(self) -> None:
        self.shares[120] = 0.0
        c = self.play("dolphin")["dolphin title 120"]
        self.assertEqual((c.status, c.dump), (PASS, "dolphin/title-00120.png"))
        self.assertIn("within where it was timing", c.better or "")

    def test_no_dolphin_is_a_skip_that_fails_nothing(self) -> None:
        (self.dolphin_root / "build" / dolphin_ref.NOGUI).unlink()
        checks, steps, stopped = nightly.run_steps(["dolphin"], self.tree.report, lambda: None,
                                                   lambda step: nightly.play_step(step, self.tree.context()))
        self.assertEqual([(c.id, c.status) for c in checks], [("dolphin", SKIPPED)])
        self.assertTrue(checks[0].detail.startswith("no Dolphin, no "))
        self.assertEqual((self.tree.games, self.played, self.dolphin.runs), (0, [], []))
        code = nightly.finish(self.tree.report, checks, steps, stopped, 0.0, [1.0, 1.0], None, self.tree.root,
                              lambda text: None)
        self.assertEqual(code, 0)
        self.assertIn("dolphin: skipped: no Dolphin, no ", (self.tree.report / "summary.txt").read_text())

    def test_a_triage_scored_at_another_tolerance_plays_nothing(self) -> None:
        write_file(self.tree.hashes, "dolphin-triage.txt", TRIAGE.replace("tolerance=4", "tolerance=6"))
        c = self.play("dolphin")["dolphin"]
        self.assertEqual((c.status, c.kind), (FAIL, "couldn't run"))
        self.assertIn("tolerance=6 budget=0.1% and the diff scores at tolerance=4", c.detail)
        self.assertEqual(self.tree.games, 0)

    def test_a_press_dolphin_read_off_its_frame_fails_the_route_before_dragoon_plays(self) -> None:
        self.dolphin.pad_lag = 1
        c = self.play("dolphin")["dolphin title movie"]
        self.assertEqual((c.status, c.kind, c.problems[0].what),
                         (FAIL, "presses off", "100:A: read at field 105, given at game frame 101, +1 frames off"))
        self.assertEqual(self.played, [])

    def test_a_triaged_route_with_no_fields_line_plays_nothing(self) -> None:
        write_file(self.tree.hashes, "dolphin-triage.txt", TRIAGE.replace("title fields=200\n", ""))
        c = self.play("dolphin")["dolphin"]
        self.assertEqual((c.status, c.kind), (FAIL, "couldn't run"))
        self.assertIn("no 'ROUTE fields=N' line for ['title']", c.detail)
        self.assertEqual(self.tree.games, 0)

    def test_routes_narrows_the_triaged_routes_and_dolphin_runs_after_frames(self) -> None:
        self.assertEqual(self.play("dolphin", routes=["menu"]), {})
        self.assertEqual(list(nightly_steps.STEPS)[:2], ["frames", "dolphin"])
