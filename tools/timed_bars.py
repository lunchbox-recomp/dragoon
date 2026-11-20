"""What do the timed Player targets measure on this build? The runs status.md's rows describe,
each read into numbers with its bar beside it as data.

  four_player   city-trial-4p for 130 s at --real-time --scale=2 --aspect=16:9 with
                GCN_FRAMETIME=1, from a copy of a warm cache, read with frametime.py from frame
                3,400: [rt] at the 99th percentile, the programs compiled and the boot's
                "programs from cache ... in N ms" line ("Four players at 16:9" and "Time added
                to every boot on macOS GL")
  race_finish   air-ride-race left alone, unpaced to frame 26,700 through bot_link.py, and the
                frame Air Ride's results screen (scene.minor 11) first shows. The race's own
                time on that screen isn't mapped in kar_ram.json, so the frame stands in for it,
                held to RESULTS_FRAME exactly at both aspects ("Simulation")
  menu_redraw   RUNS windowed runs over the title at --real-time --aspect=16:9 with the menu
                opened at frame 600 for 60 redraws, GCN_OVERLAY_PAGE cycling 0, 1 and 2, read
                with frametime.py --menu: the held redraw interval and the menu's CPU time at
                the 99th percentile ("Menu smooth while it moves")

Each run's directory in build/probe/ is deleted once read, but its log can be kept. Every
function takes BEFORE, called before each game process starts, which the nightly run uses to
stop on battery. It has no command line.
"""
from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import bot_link
import frametime
import kar_ram
from bot_link import Pad
from probe_dirs import remove_run, run_probe
from routes import route_file
from warm_shaders import BOOT_LINE, CACHE

FOUR_FROM = 3400  # where status.md's four-player numbers start
RACE_FRAMES = 26700
RACE_SECONDS = 150
AIR_RESULTS = 11  # scene.minor on Air Ride's results
RESULTS_FRAME = 13062
MENU_RUNS = 21  # seven a page, as status.md's row
MENU_PAGES = 3


@dataclass(frozen=True)
class Bar:
    """A timed number's bar: LIMIT or less, or exactly EXACT, and the number status.md's row
    gave, None when it has none to compare."""
    label: str
    unit: str
    limit: Optional[float]
    status: Optional[float]
    row: str  # the Player targets row in status.md
    exact: Optional[float] = None


BARS = {
    "4p.rt_p99": Bar("four players at 16:9, [rt] p99 from frame 3,400", "ms", 8.0, 4.20,
                     "Four players at 16:9"),
    "4p.compiles": Bar("four players at 16:9, programs compiled", "", 0, 0, "Four players at 16:9"),
    "boot.ms": Bar("boot, programs from cache, four players at 16:9", "ms", 1000.0, 837.0,
                   "Time added to every boot on macOS GL"),
    # The engine frame Air Ride's results first showed at gcn-recomp b4f8ddb, at both aspects. The
    # race is the same race only if it ends on the same frame, so a pin that moves it moves this.
    "race.results_4:3": Bar("race left alone, results screen at 4:3", "frame", None, None, "Simulation",
                            exact=RESULTS_FRAME),
    "race.results_16:9": Bar("race left alone, results screen at 16:9", "frame", None, None, "Simulation",
                             exact=RESULTS_FRAME),
    "menu.interval_p99": Bar("menu held redraw interval p99", "ms", 17.0, 17.00, "Menu smooth while it moves"),
    "menu.cpu_p99": Bar("menu CPU time a frame p99", "ms", 1.5, 0.722, "Menu smooth while it moves"),
}


def _fresh(name: str, cache: Optional[Path], root: Path) -> Path:
    out = root / "build" / "probe" / name
    if out.exists():
        remove_run(out)
    (out / "saves").mkdir(parents=True)
    if cache is not None:
        shutil.copyfile(cache, out / "saves" / CACHE)
    return out


def _keep(log: Path, keep: Optional[Path]) -> None:
    if keep is not None:
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(log, keep)


def four_player(cache: Path, *, root: Path, probe: Path, settings: tuple[str, ...],
                keep: Optional[Path], before: Callable[[], None]) -> dict[str, Optional[float]]:
    name = "nightly-4p"
    out = _fresh(name, cache, root)
    before()
    try:
        run_probe([str(probe), name, "130", str(route_file("city-trial-4p")), "100000", "--pads=4",
                   "--real-time", "--scale=2", "--aspect=16:9", "GCN_FRAMETIME=1", *settings], root, name)
        log = out / "stdout.txt"
        text = log.read_text(errors="replace")
        frames = frametime.parse(text.splitlines())
        render = frametime.summary(frames, FOUR_FROM)["render"]
        if not render["n"]:
            raise ValueError(f"{name}: no [rt] lines from frame {FOUR_FROM} on")
        boot = BOOT_LINE.search(text)
        _keep(log, keep)
        return {"4p.rt_p99": render["p99"], "4p.frames": render["n"],
                "4p.compiles": sum(len(f.compiles) for f in frames.values()),
                "boot.ms": float(boot[2]) if boot else None,
                "boot.programs": float(boot[1]) if boot else None}
    finally:
        remove_run(out)


class ResultsWatch:
    """A bot that presses nothing and notes the first frame scene.minor reads AIR_RESULTS."""

    def __init__(self) -> None:
        self.entry = kar_ram.load()["scene.minor"]
        self.frame: Optional[int] = None

    def __call__(self, link) -> dict[int, Pad]:
        if self.frame is None and kar_ram.decode(self.entry, link.read(self.entry.address, 1)) == AIR_RESULTS:
            self.frame = link.frame
        return {1: Pad()}


def race_finish(aspect: str, *, probe: Optional[Path], settings: tuple[str, ...],
                before: Callable[[], None]) -> Optional[int]:
    """The frame the race's results first show at ASPECT, None when they never did."""
    name = f"nightly-race-{aspect.replace(':', 'x')}"
    out = bot_link.run_directory(name, probe)
    if out.exists():
        remove_run(out)
    watch = ResultsWatch()
    wide = () if aspect == "4:3" else (f"--aspect={aspect}",)
    before()
    outcome = bot_link.run(name, RACE_SECONDS, watch, script=str(route_file("air-ride-race")), every=None,
                           settings=[f"--exit-after={RACE_FRAMES}", *wide, *settings], probe=probe)
    remove_run(outcome.run_dir)
    if outcome.reason not in bot_link.CLEAN:
        raise ValueError(f"{name}: the run ended on {outcome.reason}: {outcome.detail}")
    return watch.frame


def menu_redraw(cache: Path, runs: int, *, root: Path, probe: Path,
                settings: tuple[str, ...], keep: Optional[Path],
                before: Callable[[], None]) -> dict[str, float]:
    logs: dict[str, list[frametime.MenuFrame]] = {}
    kept = []
    for i in range(runs):
        name = f"nightly-menu-{i + 1}"
        out = _fresh(name, cache, root)
        before()
        try:
            run_probe([str(probe), name, "40", "", "100000", "--real-time", "--aspect=16:9", "GCN_FRAMETIME=1",
                       "GCN_OVERLAY_AT=600:60", f"GCN_OVERLAY_PAGE={i % MENU_PAGES}", "--exit-after=900",
                       *settings], root, name)
            logs[name] = frametime.read_menu(out / "stdout.txt")
            kept.append((out / "stdout.txt").read_text(errors="replace"))
        finally:
            remove_run(out)
    if keep is not None:
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text("".join(kept))
    s = frametime.menu_summary(logs)
    return {"menu.interval_p99": s["interval"]["p99"], "menu.cpu_p99": s["cpu"]["p99"],
            "menu.opens": float(s["opens"]), "menu.redraws": float(s["interval"]["n"])}
