"""The nightly's dolphin step for one route: the Dolphin diff of every checkpoint
tests/hashes/dolphin-triage.txt triages on it, each held to its line (dolphin_moves.py).

The triage file is the only list of checkpoints: its routes are the ones played, each for the
fields its `ROUTE fields=N` line gives, and each route's lines are the frames compared, nothing
more. Dolphin's side comes from dolphin_cache.ready, reused or played again. Dragoon's is dolphin_diff.play_dragoon with the
test seed, which only dolphin_diff sets, through the nightly's probe.sh and --bin. Before
Dragoon plays, the movie's presses have to read on their route frames in Dolphin's run, as dtm.py
presses checks them; a press that doesn't fails the route without playing it. Each side runs
after the context's `before`, one game process at a time.

Each failing or improved checkpoint keeps its side-by-side, Dragoon left, Dolphin middle and the
difference right, in the report's dolphin/ as ROUTE-FRAME.png, and the rest of the run goes.
Dolphin's sandbox log stays in logs/ when a denial other than /dev/dtracehelper's fails the
route's sandbox check. It has no command line.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import dolphin_cache
import dolphin_diff
import dolphin_ref
import dolphin_moves
import dtm
import race_trace
from dolphin_diff import Triage, TriageFile
from nightly_report import FAIL, PASS, SKIPPED, Check, Problem
from routes import Route, route_script

STEP = dolphin_moves.STEP
TRIAGE = "dolphin-triage.txt"


@dataclass
class Plan:
    triage: TriageFile
    head: str  # the triage file's head line
    routes: list[Route]
    root: Path  # dolphin_ref.py's Dolphin

    def lines(self, route: str) -> list[Triage]:
        return [t for t in self.triage.lines if t.route == route]


def plan(ctx) -> tuple[Optional[Plan], Optional[Check]]:
    """What the step plays, or the one check that says why it plays nothing: skipped when
    there's no Dolphin, failed when the triage file or Dolphin's tree won't do."""
    path = ctx.hashes / TRIAGE
    try:
        triage = dolphin_diff.parse_triage(path.read_text(), str(path))
    except (OSError, ValueError) as e:
        return None, Check(STEP, STEP, FAIL, kind="couldn't run", detail=str(e))
    root = dolphin_cache.dolphin_root()
    gone = dolphin_cache.missing(root)
    if gone:
        return None, Check(STEP, STEP, SKIPPED, detail=f"no Dolphin, {gone}")
    head = dolphin_diff.triage_head(triage.tolerance, triage.budget)
    tool = dolphin_diff.triage_head()
    if head != tool:
        return None, Check(STEP, STEP, FAIL, kind="couldn't run",
                           detail=f"{path.name} was scored at {head} and the diff scores at {tool}")
    try:
        dolphin_cache.checked(root)
    except dolphin_ref.Refused as e:
        return None, Check(STEP, STEP, FAIL, kind="couldn't run", detail=f"Dolphin refused: {e}")
    names = {t.route for t in triage.lines}
    unplayed = sorted(names - triage.fields.keys())
    if unplayed:
        return None, Check(STEP, STEP, FAIL, kind="couldn't run",
                           detail=f"{path.name} gives no 'ROUTE fields=N' line for {unplayed}")
    manifest = ctx.manifest()
    unknown = names - {r.name for r in manifest}
    if unknown:
        return None, Check(STEP, STEP, FAIL, kind="couldn't run",
                           detail=f"{path.name} triages routes not in the manifest: {sorted(unknown)}")
    chosen = [r for r in manifest if r.name in names and (not ctx.routes or r.name in ctx.routes)]
    return Plan(triage, head, chosen, root), None


def keeper(ctx):
    """Copies a report entry's side-by-side into the report's dolphin/, giving its path there."""
    def keep(entry: dict) -> Optional[str]:
        side = Path(entry["side"]) if "side" in entry else None
        if side is None or not side.is_file():
            return None
        out = ctx.report / STEP / side.name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(side, out)
        return ctx.rel(out)
    return keep


def route_checks(ctx, route: Route, p: Plan) -> list[Check]:
    lines = p.lines(route.name)
    fields = p.triage.fields[route.name]
    script = route_script((ctx.root / "tests" / "routes" / f"{route.name}.txt").read_text())
    iso = ctx.root / "rom" / "game.iso"
    if not iso.is_file():
        raise ValueError(f"no disc at {iso}")
    log = ctx.report / "logs" / f"{STEP}-{route.name}-sandbox.log"
    cache = ctx.root / "build" / "nightly" / dolphin_cache.CACHE / route.name
    try:
        side = dolphin_cache.ready(cache, script, fields, iso, p.head, log, ctx.before, p.root)
    except (dolphin_cache.Bad, dtm.Bad, dolphin_ref.Refused) as e:
        raise ValueError(f"Dolphin's side: {e}") from None
    ctx.say(f"{route.name}: {side.text()}")
    checks = [Check(f"{STEP} {route.name} sandbox", STEP, FAIL if side.denied else PASS,
                    kind="was denied", route=route.name, detail=side.text(),
                    dump=ctx.rel(log) if side.denied else None,
                    problems=[Problem("Dolphin", d, ctx.rel(log)) for d in side.denied])]
    if not side.denied:
        log.unlink(missing_ok=True)
    if side.off:
        return checks + [Check(f"{STEP} {route.name} movie", STEP, FAIL, kind="presses off",
                               route=route.name,
                               detail="the game read a press of the movie off its route frame",
                               problems=[Problem("press", off) for off in side.off])]
    work = ctx.work / STEP / route.name
    frames = sorted(t.frame for t in lines)
    try:
        ctx.before()
        bad = dolphin_diff.play_dragoon(route, work, side.folder, frames, ctx.probe, ctx.bin())
        report = dolphin_diff.compare(route, work, frames, side.folder)
    except dolphin_diff.Bad as e:
        raise ValueError(str(e)) from None
    if bad:
        checks.append(Check(f"{STEP} {route.name} run", STEP, FAIL, kind="ended badly", route=route.name,
                            detail=bad))
    trace = race_trace.read_trace(json.loads((dolphin_diff.dragoon_dir(work) / "state.json").read_text())
                                  .get("trace", {}))
    found = race_trace.races(dtm.read_lines(side.folder / "ram.txt"), trace)
    checks += dolphin_moves.checks(route.name, lines, p.triage.budget, report, found,
                                   keeper(ctx))
    shutil.rmtree(work)
    return checks
