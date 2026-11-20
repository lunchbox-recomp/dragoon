"""What does each of the nightly run's steps play, and what does it check? nightly.py runs one
step at a time and turns what it returns into the report.

  frames   every manifest route at 4:3 and 16:9 through state_goldens.py's bot run, dumping
           frames: each frame's SHA-1 against tests/hashes/gl/ or gl-16x9/ ("drew differently")
           and the game's state at each checkpoint against tests/hashes/state/, the same at
           both aspects ("played differently"), from one game process a route and aspect. A
           check tests/hashes/known-issues.txt lists is marked known (known_issues.py)
  dolphin  every checkpoint tests/hashes/dolphin-triage.txt triages, Dragoon pinned against
           Dolphin's run of the route's movie, reused while nothing it depends on changed
           (dolphin_cache.py). A checkpoint whose class or score moves past its line, or a race
           whose first difference comes earlier, fails; one that gets better is improved
           (dolphin_moves.py, nightly_dolphin.py). No Dolphin beside the clone skips it
  audio    every route's AX hashes against tests/hashes/audio/, as audio_hashes.py check runs them
  shaders  a fresh warm-up, one pass at a time, into a scratch cache, then every route at both
           aspects from that cache, as route_compiles.py plays them. Bar 0 compiles a run
  timed    timed_bars.py's runs from the same cache: four players at 16:9, the boot, the race's
           results frame at both aspects and the menu's held redraw
  soak     bot_soak.py for SOAK_MINUTES in each of Air Ride, Top Ride and City Trial with one
           player, and City Trial with four

A frame that drew differently keeps its dump in the report's dumps/. When the golden build in
build/nightly/golden-build/ draws the golden's hash for that frame, the golden frame is
rebuilt from it and dumps/ gets the two side by side (frame_pair.py). Otherwise the new frame
stands alone beside the golden's hash. A checkpoint that played differently keeps that
frame's dump too. Every other dump and run directory is deleted. After a frames step where
every check but the known issues passed on every route, the build's game is copied to the
golden build, with the commits it was built from in its commit.txt.

Each step calls the context's `before` as each game process is about to start, which raises
power.OnBattery on battery. It has no command line.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import audio_hashes
import bot_link
import bot_record
import bot_soak
import frame_hashes
import known_issues
import nightly_dolphin
import route_compiles
import state_goldens
import timed_bars
import warm_shaders
from frame_dumps import frame_files
from frame_pair import side_by_side, write_png
from framediff import read_png
from nightly_report import FAIL, PASS, Check, Problem
from probe_dirs import remove_run
from routes import Route, parse_manifest

ROOT = Path(__file__).resolve().parents[1]
ASPECTS = ("4:3", "16:9")
SOAKS = (("air-ride", 1), ("top-ride", 1), ("city-trial", 1), ("city-trial", 4))
SOAK_MINUTES = 30.0
GOLDEN_BUILD = "golden-build"  # under build/nightly/, a game whose frames match every golden


def tag(aspect: str) -> str:
    return aspect.replace(":", "x")


def nothing() -> None:
    pass


@dataclass
class Context:
    root: Path  # the tree whose tests/ and build/ the step uses
    report: Path  # the run's directory under build/nightly/
    before: Callable[[], None] = nothing
    routes: list[str] = field(default_factory=list)  # empty for every manifest route
    build: Optional[Path] = None  # a build directory in place of ROOT/build, given to probe.sh as --bin
    soak_minutes: float = SOAK_MINUTES
    menu_runs: int = timed_bars.MENU_RUNS
    seed: int = 0
    say: Callable[[str], None] = print
    built: Optional[str] = None  # the engine commit the game says it was built from, once a run has said

    @property
    def probe(self) -> Path:
        return self.root / "tools" / "probe.sh"

    @property
    def hashes(self) -> Path:
        return self.root / "tests" / "hashes"

    @property
    def work(self) -> Path:
        return self.report / "work"

    @property
    def game(self) -> Path:
        return (self.build or self.root / "build") / "dragoon"

    def bin(self, bench: bool = False) -> tuple[str, ...]:
        if self.build is None:
            return ()
        return (f"--bin={self.build / ('dragoon_bench' if bench else 'dragoon')}",)

    def manifest(self) -> list[Route]:
        return parse_manifest((self.hashes / "manifest.txt").read_text())

    def chosen(self) -> list[Route]:
        routes = self.manifest()
        unknown = set(self.routes) - {r.name for r in routes}
        if unknown:
            raise ValueError(f"not in the manifest: {sorted(unknown)}")
        return [r for r in routes if not self.routes or r.name in self.routes]

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.report))


def sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def golden_build(ctx: Context) -> Path:
    return ctx.root / "build" / "nightly" / GOLDEN_BUILD / "dragoon"


def keep_frames(ctx: Context, run_dir: Path, route: Route, aspect: str, frames: list[int],
                golden: dict[int, str], drew: list[int]) -> dict[int, str]:
    """Copy FRAMES' dumps out of RUN_DIR into the report's dumps/, and for each of DREW, the frames
    that drew differently, that the golden build draws the golden hash of, the pair side by side.
    Returns each frame's dump to look at."""
    files = frame_files(run_dir)
    kept = {}
    out = ctx.report / "dumps" / tag(aspect) / route.name
    for f in frames:
        if f in files:
            out.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(files[f], out / files[f].name)
            kept[f] = ctx.rel(out / files[f].name)
    rebuild = golden_build(ctx)
    changed = [f for f in drew if f in kept and f in golden]
    if not changed or not rebuild.is_file():
        return kept
    ctx.before()
    outcome, _ = state_goldens.play(route, f"nightly-golden-{tag(aspect)}-{route.name}", aspect=aspect,
                                    every=route.dump_every, probe=ctx.probe, settings=(f"--bin={rebuild}",))
    try:
        again = frame_files(outcome.run_dir)
        for f in changed:
            if f in again and sha1(again[f]) == golden[f]:
                pair = out / f"frame_{f:05d}-golden-left.png"
                pair.write_bytes(write_png(side_by_side(read_png(again[f]), read_png(out / files[f].name))))
                kept[f] = ctx.rel(pair)
    finally:
        remove_run(outcome.run_dir)
    return kept


def known(check: Check, golden: dict, states: dict, bad: Optional[str],
          issues: dict[str, known_issues.Issue]) -> Check:
    """CHECK, a state check, marked as its known issue when it passes, or when the run ended as it
    should and STATES match GOLDEN with the issue's values put in. Any other failure, a changed
    value or another field at the issue's checkpoint too, stays a failure like any other."""
    issue = issues.get(check.id)
    if issue is None:
        return check
    if check.status == PASS or (bad is None and not state_goldens.compare(issue.golden(golden), states)):
        check.known = issue.bug
    else:
        check.detail += f", which isn't the known issue at {issue.checkpoint}"
    return check


def frames_route(ctx: Context, route: Route, aspect: str) -> list[Check]:
    golden_path = ctx.hashes / frame_hashes.GOLDENS[aspect] / f"{route.name}.txt"
    state_path = ctx.hashes / state_goldens.STATE / f"{route.name}.txt"
    golden = frame_hashes.read_golden(golden_path)
    states_golden = state_goldens.read_golden(state_path) if state_path.is_file() else None
    issues = known_issues.read(ctx.hashes)
    ctx.before()
    outcome, states = state_goldens.play(route, f"nightly-{tag(aspect)}-{route.name}", aspect=aspect,
                                         every=route.dump_every, probe=ctx.probe, settings=ctx.bin())
    try:
        ctx.built = ctx.built or bot_record.built_engine(outcome.run_dir / "session")
        got = frame_hashes.hash_frames(outcome.run_dir)
        drew = [(f, "not reached" if f not in got else f"{got[f]} != golden {h}")
                for f, h in sorted(golden.items()) if got.get(f) != h]
        played = state_goldens.compare(states_golden, states) if states_golden else []
        bad = state_goldens.ended_badly(outcome)
        dumps = keep_frames(ctx, outcome.run_dir, route, aspect,
                            sorted({f for f, _ in drew} | {f for f, _, _ in played}), golden,
                            [f for f, _ in drew])
    finally:
        remove_run(outcome.run_dir)
    frame_check = Check(f"frames {aspect} {route.name}", "frames", FAIL if drew else PASS,
                        kind="drew differently", route=route.name,
                        detail=f"{len(golden) - len(drew)} of {len(golden)} frames match",
                        problems=[Problem(f"frame {f}", what + ("" if f in dumps or what == "not reached"
                                                                 else ", no dump"), dumps.get(f))
                                  for f, what in drew])
    if states_golden is None:
        state_check = Check(f"state {aspect} {route.name}", "frames", FAIL, kind="played differently",
                            route=route.name, detail=f"no state golden at {state_path}")
    else:
        problems = [Problem(f"frame {f}" + ("" if fld == "frame" else f" {fld}"), what, dumps.get(f))
                    for f, fld, what in played]
        if bad:
            problems.append(Problem(f"frame {outcome.last_frame}", bad))
        state_check = Check(f"state {aspect} {route.name}", "frames", FAIL if problems else PASS,
                            kind="played differently", route=route.name, problems=problems,
                            detail=f"{len(states_golden)} checkpoints")
        known(state_check, states_golden, states, bad, issues)
    return [frame_check, state_check]


def guarded(done: Callable[[Check], None], check_id: str, step: str, route: str,
            play: Callable[[], list[Check]]) -> bool:
    """Hand each check PLAY returns to DONE, or one failed CHECK_ID when it couldn't run, such as
    a missing golden or a probe.sh that exited 2. True when every check but a known issue passed."""
    try:
        checks = play()
    except (OSError, ValueError, bot_link.LinkSetupError) as e:
        checks = [Check(check_id, step, FAIL, kind="couldn't run", route=route,
                        detail=str(e).splitlines()[0] if str(e) else type(e).__name__)]
    for c in checks:
        done(c)
    return all(c.status == PASS or c.known is not None for c in checks)


def frames(ctx: Context, done: Callable[[Check], None]) -> None:
    all_passed = True
    for aspect in ASPECTS:
        for route in ctx.chosen():
            all_passed &= guarded(done, f"frames {aspect} {route.name}", "frames", route.name,
                                  lambda: frames_route(ctx, route, aspect))
    rebuild = golden_build(ctx)
    if all_passed and not ctx.routes and ctx.game.is_file():
        if not rebuild.is_file() or sha1(rebuild) != sha1(ctx.game):
            rebuild.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ctx.game, rebuild)
            ctx.say(f"golden build: {ctx.game} copied to {rebuild}")
        (rebuild.parent / "commit.txt").write_text(
            f"dragoon {bot_record.commits(ctx.root)['dragoon'] or '?'}\nengine {ctx.built or '?'}\n")


def audio_route(ctx: Context, route: Route) -> list[Check]:
    golden = audio_hashes.read_golden(ctx.hashes / "audio" / f"{route.name}.txt")
    ctx.before()
    out = audio_hashes.ROOT / "build" / "probe" / f"audio-{route.name}"
    dump = None
    try:
        got = audio_hashes.hash_route(route, allow_crash=True, settings=ctx.bin(bench=True))
        problems = audio_hashes.compare(golden, got)
        if problems:
            keep = ctx.report / "audio" / f"{route.name}.log"
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / "stdout.txt", keep)
            dump = ctx.rel(keep)
    finally:
        if out.exists():
            remove_run(out)
    return [Check(f"audio {route.name}", "audio", FAIL if problems else PASS, kind="sounded differently",
                  route=route.name, detail=f"{len(golden) - len(problems)} of {len(golden)} rows match",
                  problems=[Problem(p.split(":", 1)[0], p.split(": ", 1)[1], dump) for p in problems],
                  dump=dump)]


def audio(ctx: Context, done: Callable[[Check], None]) -> None:
    for route in ctx.chosen():
        guarded(done, f"audio {route.name}", "audio", route.name, lambda: audio_route(ctx, route))


def warm_cache(ctx: Context) -> tuple[Path, Optional[Check]]:
    """The run's fresh warm-up cache, made the first time a step asks: every manifest pass, one at a
    time, from no cache at all, into the run's work/warm/. Never the player's saves/."""
    saves = ctx.work / "warm"
    cache = saves / warm_shaders.CACHE
    if cache.is_file():
        return cache, None
    saves.mkdir(parents=True, exist_ok=True)
    plan = warm_shaders.passes(ctx.manifest())
    began = time.monotonic()
    try:
        warm_shaders.warm(ctx.game, saves, plan, jobs=1, before=ctx.before)
    except warm_shaders.PassFailed as e:
        return cache, Check("shaders warm-up", "shaders", FAIL, kind="failed", detail=str(e).splitlines()[0])
    keys = len(set(warm_shaders.shader_cache.load(cache).keys))
    return cache, Check("shaders warm-up", "shaders", PASS, value=float(keys), unit="keys",
                        detail=f"{len(plan)} passes one at a time in {time.monotonic() - began:.0f} s")


def shaders(ctx: Context, done: Callable[[Check], None]) -> None:
    cache, warmed = warm_cache(ctx)
    if warmed is not None:
        done(warmed)
    if not cache.is_file():
        return
    for aspect in ASPECTS:
        for route in ctx.chosen():
            guarded(done, f"shaders {aspect} {route.name}", "shaders", route.name,
                    lambda: shaders_route(ctx, route, aspect, cache))


def shaders_route(ctx: Context, route: Route, aspect: str, cache: Path) -> list[Check]:
    keep = ctx.report / "shaders" / f"{tag(aspect)}-{route.name}.log"
    ctx.before()
    c = route_compiles.play(route, cache, aspect, ctx.root, ctx.probe, ctx.bin(), keep)
    where = f"frame {c.frames[0]}" if c.frames else f"frame {c.reached}"
    return [Check(f"shaders {aspect} {route.name}", "shaders", PASS if c.ok else FAIL, kind="compiled",
                  route=route.name, detail=route_compiles.describe(c),
                  problems=[] if c.ok else [Problem(where, route_compiles.describe(c), ctx.rel(keep))])]


def load() -> float:
    return os.getloadavg()[0]


def timed_check(key: str, value: Optional[float], loads: list[float], dump: Optional[str] = None) -> Check:
    """KEY's number against its bar. Only a number in ms is held to nightly_report's slower rule."""
    bar = timed_bars.BARS[key]
    passed = (value is not None and (bar.limit is None or value <= bar.limit)
              and (bar.exact is None or value == bar.exact))
    kind = "over its bar" if bar.exact is None else f"not frame {bar.exact:g}"
    return Check(f"timed {key}", "timed", PASS if passed else FAIL, kind=kind, detail=bar.label,
                 value=value, unit=bar.unit, limit=bar.limit if bar.exact is None else bar.exact,
                 status_value=bar.status, timed=bar.unit == "ms", load=loads, dump=dump)


def timed(ctx: Context, done: Callable[[Check], None]) -> None:
    cache, warmed = warm_cache(ctx)
    if warmed is not None:
        done(warmed)
    if not cache.is_file():
        return
    logs = ctx.report / "logs"

    def four() -> list[Check]:
        began = load()
        got = timed_bars.four_player(cache, root=ctx.root, probe=ctx.probe, settings=ctx.bin(),
                                     keep=logs / "4p.log", before=ctx.before)
        loads = [began, load()]
        return [timed_check(key, got[key], loads, ctx.rel(logs / "4p.log"))
                for key in ("4p.rt_p99", "4p.compiles", "boot.ms")]

    def race(aspect: str) -> list[Check]:
        began = load()
        frame = timed_bars.race_finish(aspect, probe=ctx.probe, settings=ctx.bin(), before=ctx.before)
        return [timed_check(f"race.results_{aspect}", float(frame) if frame is not None else None,
                            [began, load()])]

    def menu() -> list[Check]:
        began = load()
        got = timed_bars.menu_redraw(cache, ctx.menu_runs, root=ctx.root, probe=ctx.probe, settings=ctx.bin(),
                                     keep=logs / "menu.log", before=ctx.before)
        loads = [began, load()]
        return [timed_check(key, got[key], loads, ctx.rel(logs / "menu.log"))
                for key in ("menu.interval_p99", "menu.cpu_p99")]

    guarded(done, "timed 4p.rt_p99", "timed", "city-trial-4p", four)
    for aspect in ASPECTS:
        guarded(done, f"timed race.results_{aspect}", "timed", "air-ride-race", lambda: race(aspect))
    guarded(done, "timed menu.interval_p99", "timed", "menu", menu)


def soak(ctx: Context, done: Callable[[Check], None]) -> None:
    for mode, ports in SOAKS:
        ap = bot_soak.parser()
        args = ap.parse_args(["--seed", str(ctx.seed), "--minutes", f"{ctx.soak_minutes:g}", "--modes", mode,
                              "--ports", str(ports), "--probe", str(ctx.probe)])
        bot_soak.checked(ap, args, time.time)
        lines: list[str] = []
        ctx.before()
        code = bot_soak.soak(args, list(ctx.bin()), out=lines.append, err=lines.append)
        name = lines[0].split(":", 1)[0] if lines else ""
        run_dir = ctx.root / "build" / "probe" / name
        check_id = f"soak {mode} {ports}p"
        if code == 0:
            if name and run_dir.is_dir():
                remove_run(run_dir)
            done(Check(check_id, "soak", PASS, detail=lines[-1].split(": ", 1)[-1] if lines else ""))
            continue
        stop = next((l for l in lines if l.startswith("STOP ")), lines[-1] if lines else f"exit {code}")
        record = next((l.strip() for l in lines if l.strip().endswith("bot.json")), None)
        done(Check(check_id, "soak", FAIL, kind="stopped", detail=f"seed {ctx.seed}",
                   problems=[Problem(f"seed {ctx.seed}", stop, record)], dump=record))


def dolphin(ctx: Context, done: Callable[[Check], None]) -> None:
    plan, why_not = nightly_dolphin.plan(ctx)
    if plan is None:
        assert why_not is not None
        done(why_not)
        return
    for route in plan.routes:
        guarded(done, f"dolphin {route.name}", "dolphin", route.name,
                lambda: nightly_dolphin.route_checks(ctx, route, plan))


STEPS: dict[str, Callable[[Context, Callable[[Check], None]], None]] = {
    "frames": frames, "dolphin": dolphin, "audio": audio, "shaders": shaders, "timed": timed,
    "soak": soak}
TIMED = ("timed",)  # the steps that run at the default priority, not at nice 19
