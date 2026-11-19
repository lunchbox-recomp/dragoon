#!/usr/bin/env python3
"""Does Dragoon draw and play a route as Dolphin does? Diff the two at matched game frames.

Usage: dolphin_diff.py run ROUTE --movie DTM [--iso ISO] [--out DIR]
       dolphin_diff.py dolphin ROUTE --movie DTM [--iso ISO] [--out DIR]
       dolphin_diff.py dragoon ROUTE [--out DIR]
       dolphin_diff.py compare ROUTE [--out DIR]
       dolphin_diff.py repeat DIR_A DIR_B
       dolphin_diff.py triage [FILE]

Both sides read the disc as a console's drive does: Dolphin plays ROUTE's converged movie (from
dtm.py converge --disc console) through dolphin_ref.py boot with frame dumps and the memory
watcher on, and Dragoon plays the route through state_goldens.play with --disc=console. run
does dolphin, then dragoon, then compare, one game process at a time. Everything goes in OUT,
build/dolphin-diff/ROUTE/ by default: dolphin/ (dolphin_ref.py's ram.txt, frames.txt and
dumps), dragoon/ (the checkpoint frames and state.json), sides/ (a side-by-side PNG a
checkpoint), summary.txt, report.json and triage-draft.txt (a triage line a checkpoint, the
ones over BUDGET marked unclear for a person to look at). run deletes both sides' frame dumps
once compare has made the side-by-sides, so only those pictures stay, and dolphin, dragoon and
compare run alone keep them. None of it goes in git.

Checkpoints are game frames: the route's required frames in tests/hashes/manifest.txt, and the
first frame of each scene Dolphin's run goes through, as dtm.scene_steps gives it, and SETTLE
frames after that, once the picture has settled. Dolphin's game frame is dtm.game_frames,
counted from vi.renew_count, which is what dtm.py gives the route's presses by and what Dragoon's
own frame count matched within a frame at every scene change (docs/dev/status.md, Dolphin
reference). Dragoon's is its presented frame, the N of its frame_N.png and the frame the bot
reads state at.

A Dolphin dump has no frame number: it writes one PNG for each new picture its VI shows.
vi.next_buffer changes once for each picture the game puts up, so the pictures by a field are its
changes since field 1, and the picture showing game frame N is the one up at the first field
whose game frame is N, the dump with that number. That count drifts from Dolphin's own,
since Dolphin writes the dump it holds at the game's next XFB copy and a second picture before
one replaces it, and takes a copy into the XFB on screen as a new picture. On top-ride-grass it
was 3 dumps ahead by field 1380 and 9 behind by field 3830. So compare looks at the DRIFT dumps
either side of the counted one and takes the one nearest Dragoon's frame, on a coarse error
over every COARSE-th pixel each way. How sure the match is goes in the report: "sure" when the
best is clearly the nearest (its coarse error under MARGIN times the next different
picture's), "still" when every dump in reach shows the same picture, so a frame either way
makes no difference, and "unsure" otherwise. A checkpoint is refused when no field of Dolphin's
run reaches its game frame, which is so for the boot scenes at frame 0, when the dumps stop
before it, when Dragoon has no frame there or when the two pictures aren't the same size.

Both sides dump the picture before any scaling to the window: Dolphin its raw XFB (GFX.ini's
FrameDumpsResolutionType 2, InternalResolution 1) and Dragoon its EFB or XFB at --scale=1, so
both are 640x480 at 4:3 and pixels line up one to one. compare never scales one to the other:
pictures of different sizes are refused.

The picture score is over all pixels: the share whose largest channel error is over TOLERANCE,
and the largest and the mean channel error. A checkpoint whose share is over BUDGET goes to
triage. threshold() gives TOLERANCE from repeat runs: the largest channel error two runs of one
side give at the same checkpoint, which is 0 for both (repeat prints it), plus STEP, 4 levels
of 255, so a rounding difference between two correct renderers' 8-bit blends and filters isn't
counted. The game draws to an RGB8 EFB (HSD_PixelFormat at 805DE2AC reads 0), so neither side
drops colour bits that a 6-bit format would. On the three routes first run, the checkpoints
under BUDGET came out at 0 and every one over it had a largest error of 14 or more, so no
result there turns on STEP. A side-by-side is Dragoon on the left, Dolphin in the middle and the
difference on the right: black under TOLERANCE, and over it white for a small error through
red for a large one.

The state compare reads every state_goldens.FIELDS value at each checkpoint on both sides
through kar_ram.read, from guest RAM in Dragoon and from the watched words in Dolphin's
ram.txt, pointers followed as kar_ram.json's paths say. Dolphin reads RAM at the end of a field,
partway into the next frame's work, so a checkpoint's values are taken from the fields at its
game frame and the one either side. "same" is a match at its frame, "same, a frame off" one
only next to it, and "differs" no match, with each value that differs listed apart from the
picture's score for triage.

The triage file, tests/hashes/dolphin-triage.txt, has one line a route and checkpoint:

  ROUTE FRAME share=S% max=M mean=E CLASS REASON

S, M and E are the checkpoint's score when it was triaged, and CLASS one of CLASSES: bug (a
Dragoon bug, the reason saying what's wrong), dolphin (Dolphin differs and it isn't our bug,
such as its own inaccuracy or filtering by design), unclear, within (under BUDGET) or refused
(no match, the reason saying why). # lines and blank lines are comments. parse_triage reads it.

repeat compares two dolphin/ folders by their dumps' sha256 or two dragoon/ folders frame by
frame, and prints the largest channel error. triage checks the file parses.

Exits 0 when the command ran, 1 when a checkpoint's state differs or a run fell short, and 2
on a bad argument, a missing or unreadable file or a refused run.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import bot_link
import dolphin_ref
import dtm
import kar_ram
import state_goldens
from framediff import Image, read_png
from frame_dumps import frame_files
from frame_pair import side_by_side, write_png
from probe_dirs import remove_run
from routes import MANIFEST, ROOT, Route, select_routes

OUT = ROOT / "build" / "dolphin-diff"
ISO = ROOT / "rom" / "game.iso"
TRIAGE = ROOT / "tests" / "hashes" / "dolphin-triage.txt"
DISC = "console"
SETTLE = 10  # frames after a scene's first for its settled checkpoint
DRIFT = 12  # the dumps either side of the counted one a match may take
COARSE = 4  # the coarse error looks at every 4th pixel each way
MARGIN = 0.8  # a match is sure when its coarse error is under this times the next picture's
STEP = 4  # levels of 255 two correct renderers may round apart
REPEAT_ERROR = 0  # the largest channel error two runs of one side gave (repeat, docs/dev/status.md)
BUDGET = 0.001  # a checkpoint over this share of pixels goes to triage, framediff.py's default
SLOW = 3  # a Dragoon run's seconds, times state_goldens.SLOW times the manifest's
CLASSES = ("bug", "dolphin", "unclear", "within", "refused")
TRIAGE_LINE = re.compile(r"(\S+) (\d+) share=(\d+(?:\.\d+)?)% max=(\d+) mean=(\d+(?:\.\d+)?) "
                         r"(\S+) (\S.*)")
FIELDS = state_goldens.FIELDS
TABLE = kar_ram.load()


def threshold(repeat_error: int, step: int = STEP) -> int:
    """The channel error over which a pixel counts as different: the most two runs of one side
    differ by, plus STEP."""
    return repeat_error + step


TOLERANCE = threshold(REPEAT_ERROR)


def over_budget(s: "Score") -> bool:
    """Whether a checkpoint scored S goes to triage: more than BUDGET of its pixels over."""
    return s.share > BUDGET


class Bad(Exception):
    """A run, file or folder the tool can't use."""


@dataclass(frozen=True)
class Checkpoint:
    frame: int
    why: str


@dataclass
class Match:
    """Where a checkpoint's picture is in Dolphin's dumps: the field its game frame is first up
    at, the dump counted for that field and the one taken, and how sure that is."""
    field: int
    counted: int
    dump: int
    sure: str


@dataclass(frozen=True)
class Score:
    share: float
    max: int
    mean: float


@dataclass(frozen=True)
class Triage:
    route: str
    frame: int
    share: float
    max: int
    mean: float
    cls: str
    reason: str


# Watches.


def state_watches(fields: Sequence[str] = FIELDS, table: dict = TABLE) -> list[str]:
    """The words Dolphin's watcher reads for FIELDS: each one's word at a fixed address, or each
    pointer on its path and the word at its end."""
    out: list[str] = []
    for name in fields:
        e = table[name]
        if not e.path:
            first = e.address & ~(dolphin_ref.WORD - 1)
            words = [dolphin_ref.chain(a, ()) for a in
                     range(first, e.address + e.length, dolphin_ref.WORD)]
        else:
            if e.length > dolphin_ref.WORD:
                raise Bad(f"{name}: the watcher reads a word at a path's end, and this is "
                          f"{e.length} bytes")
            words = [dolphin_ref.chain(e.address, e.path[:k]) for k in range(len(e.path) + 1)]
        out.extend(w for w in words if w not in out)
    return out


def watches(fields: Sequence[str] = FIELDS) -> list[str]:
    """The scene word, the renew count and the XFB word for the timeline, then FIELDS' words."""
    head = [f"{dolphin_ref.word_of(n, TABLE):08X}"
            for n in ("scene.major", "vi.renew_count", "vi.next_buffer")]
    return head + [w for w in state_watches(fields) if w not in head]


class Watched:
    """Guest RAM as one ram.txt row read it, for kar_ram.read: each watch's word at the address
    it was read from, which for a path is the pointer before it plus its last offset."""

    def __init__(self, words: dict[str, int]) -> None:
        self.memory: dict[int, int] = {}
        for text, value in words.items():
            head, *offsets = text.split(dolphin_ref.CHAIN)
            if offsets:
                base = words.get(dolphin_ref.CHAIN.join([head, *offsets[:-1]]))
                if base is None or not kar_ram.in_ram(base, 1):
                    continue  # the watcher stopped at a pointer outside RAM
                address = base + int(offsets[-1], 16)
            else:
                address = int(head, 16)
            for i, byte in enumerate(value.to_bytes(dolphin_ref.WORD, "big")):
                self.memory[address + i] = byte

    def read(self, address: int, length: int) -> bytes:
        try:
            return bytes(self.memory[address + i] for i in range(length))
        except KeyError:
            raise Bad(f"{address:08X}: not watched") from None


def ram_rows(lines: Sequence[str]) -> list[dict[str, int]]:
    head = lines[0].split()[1:]
    return [dict(zip(head, (int(w, 16) for w in line.split()[1:]))) for line in lines[1:]]


def state_of(words: dict[str, int], fields: Sequence[str] = FIELDS) -> dict[str, str]:
    link = Watched(words)
    return {f: state_goldens.value_text(kar_ram.read(link, f, TABLE)) for f in fields}


# Checkpoints and the picture match.


def checkpoints(route: Route, lines: Sequence[str]) -> list[Checkpoint]:
    """ROUTE's required frames, and each scene's first frame in Dolphin's run and SETTLE after."""
    out = {f: f"golden {f}" for f in route.required}
    last = None
    for _, frame, major, minor in dtm.scene_steps(lines):
        if (major, minor) == last:
            continue  # the scene word's middle bytes changed, not the scene
        last = (major, minor)
        out.setdefault(frame, f"scene {major}/{minor} starts")
        out.setdefault(frame + SETTLE, f"scene {major}/{minor}, {SETTLE} frames in")
    return [Checkpoint(f, why) for f, why in sorted(out.items())]


def pictures(lines: Sequence[str]) -> list[int]:
    """The pictures the game had put up by the end of each field: vi.next_buffer's changes
    since field 1."""
    col = lines[0].split().index(f"{dolphin_ref.word_of('vi.next_buffer', TABLE):08X}")
    out, count, last = [], 0, None
    for line in lines[1:]:
        value = line.split()[col]
        count += last is not None and value != last
        last = value
        out.append(count)
    return out


def first_field(frames: Sequence[int], frame: int) -> Optional[int]:
    """The first field (from 1) whose game frame is FRAME, or None when none is."""
    return next((n for n, f in enumerate(frames, 1) if f == frame), None)


def coarse(a: Image, b: Image, every: int = COARSE) -> float:
    """The mean channel error over every EVERY-th pixel each way."""
    total = count = 0
    for y in range(0, a.height, every):
        for x in range(0, a.width, every):
            i, j = (y * a.width + x) * a.channels, (y * b.width + x) * b.channels
            total += sum(abs(a.pixels[i + k] - b.pixels[j + k]) for k in range(3))
            count += 3
    return total / count if count else 0.0


def pick(errors: dict[int, float], same: dict[int, str], counted: int) -> tuple[int, str]:
    """The dump to take of ERRORS' (dump to coarse error) and how sure: the least error, the
    nearest COUNTED on a tie. SAME gives each dump's sha256, so dumps of one picture count as
    one."""
    best = min(errors, key=lambda k: (errors[k], abs(k - counted)))
    others = [e for k, e in errors.items() if same[k] != same[best]]
    if not others:
        return best, "still"
    return best, "sure" if errors[best] < MARGIN * min(others) else "unsure"


def score(a: Image, b: Image, tolerance: int = TOLERANCE) -> tuple[Score, Image]:
    """A's error against B over every pixel, and the difference map."""
    if (a.width, a.height) != (b.width, b.height):
        raise Bad(f"sizes differ: {a.width}x{a.height} and {b.width}x{b.height}")
    over = worst = total = 0
    out = bytearray()
    for i in range(a.width * a.height):
        d = [abs(a.pixels[i * a.channels + k] - b.pixels[i * b.channels + k]) for k in range(3)]
        big = max(d)
        total += sum(d)
        worst = max(worst, big)
        if big > tolerance:
            over += 1
            out += bytes((255, 255 - big, 255 - big))
        else:
            out += b"\0\0\0"
    n = a.width * a.height
    return (Score(over / n, worst, total / (3 * n)),
            Image(a.width, a.height, 3, bytes(out)))


# The runs.


def dolphin_dir(out: Path) -> Path:
    return out / "dolphin"


def dragoon_dir(out: Path) -> Path:
    return out / "dragoon"


def cmd_dolphin(route: Route, movie: Path, iso: Path, out: Path) -> int:
    fields = dtm.read_header(movie.read_bytes())["frameCount"]
    cmd = dtm.boot_command(iso, movie, fields, dolphin_dir(out), DISC, watches(), dump=True)
    print(f"{route.name}: Dolphin, {fields} fields")
    return subprocess.run(cmd).returncode


class Keeper(state_goldens.Checkpoints):
    """Checkpoints that also deletes each frame dump it won't need, LAG frames behind."""
    LAG = 10

    def __init__(self, frames: Sequence[int], folder: Path) -> None:
        super().__init__(frames, 1)
        self.keep = set(frames)
        self.folder = folder
        self.done = 0

    def __call__(self, link):
        for n in range(self.done + 1, link.frame - self.LAG):
            if n not in self.keep:
                (self.folder / f"frame_{n:05d}.png").unlink(missing_ok=True)
        self.done = max(self.done, link.frame - self.LAG - 1)
        return super().__call__(link)


def cmd_dragoon(route: Route, out: Path) -> int:
    lines = dtm.read_lines(dolphin_dir(out) / "ram.txt")
    frames = [c.frame for c in checkpoints(route, lines) if c.frame > 0]
    name = f"dolphin-diff-{route.name}"
    run_dir = bot_link.run_directory(name)
    bot = Keeper(frames, run_dir)
    played = dataclasses.replace(route, required=frames, dump_every=1, seconds=route.seconds * SLOW)
    print(f"{route.name}: Dragoon, {len(frames)} checkpoints to frame {max(frames)}")
    outcome, states = state_goldens.play(
        played, name, every=1, bot=bot,
        settings=[f"--disc={DISC}", f"GCN_DUMP_RANGE={min(frames)}-{max(frames)}"])
    try:
        if outcome.reason == bot_link.NEVER_LINKED:
            raise Bad(f"{route.name}: the game never connected: {outcome.detail}")
        folder = dragoon_dir(out)
        if folder.exists():
            remove_run(folder)
        folder.mkdir(parents=True)
        dumps = frame_files(outcome.run_dir)
        for n in frames:
            if n in dumps:
                dumps[n].rename(folder / dumps[n].name)
        (folder / "state.json").write_text(json.dumps({
            "end": outcome.reason, "detail": outcome.detail,
            "states": {str(f): [at, s] for f, (at, s) in sorted(states.items())},
        }, indent=1) + "\n")
    finally:
        remove_run(outcome.run_dir)
    bad = state_goldens.ended_badly(outcome)
    if bad:
        print(f"{route.name}: {bad}")
    return 1 if bad else 0


# The comparison.


def compare_state(want: dict[str, str], read_at: int, frames: Sequence[int],
                  rows: Sequence[dict[str, int]]) -> tuple[str, list[str]]:
    """Dragoon's state WANT at READ_AT against Dolphin's at the fields of that game frame and the
    one either side: ("same" | "same, a frame off" | "differs", what differs at READ_AT)."""
    off = False
    first = None
    for n, frame in enumerate(frames):
        if abs(frame - read_at) > 1:
            continue
        got = state_of(rows[n], list(want))
        if frame == read_at and first is None:
            first = got
        if got == want:
            if frame == read_at:
                return "same", []
            off = True
    if off:
        return "same, a frame off", []
    if first is None:
        return "differs", [f"Dolphin never reached game frame {read_at}"]
    return "differs", [f"{k}: Dragoon {v}, Dolphin {first[k]}" for k, v in want.items()
                       if first[k] != v]


def compare_picture(n: int, frames: Sequence[int], shown: Sequence[int], dumps: list[tuple],
                    dragoon: dict[int, Path]):
    """The checkpoint at game frame N's match, or a reason to refuse it."""
    field = first_field(frames, n)
    if field is None:
        return None, f"Dolphin's run never shows game frame {n}"
    counted = shown[field - 1]
    if not counted:
        return None, f"Dolphin's run has put up no picture by game frame {n}"
    if counted > len(dumps):
        return None, f"Dolphin's dumps stop at {len(dumps)}, before picture {counted}"
    if n not in dragoon:
        return None, f"Dragoon has no frame {n}"
    ours = read_png(dragoon[n])
    reach = range(max(1, counted - DRIFT), min(len(dumps), counted + DRIFT) + 1)
    images, errors = {}, {}
    for k in reach:
        sha, path = dumps[k - 1]
        if sha not in images:
            images[sha] = read_png(path)
            if (images[sha].width, images[sha].height) != (ours.width, ours.height):
                return None, (f"Dragoon's frame is {ours.width}x{ours.height} and Dolphin's "
                              f"{images[sha].width}x{images[sha].height}")
        errors[k] = coarse(ours, images[sha])
    k, sure = pick(errors, {k: dumps[k - 1][0] for k in reach}, counted)
    return (Match(field, counted, k, sure), ours, images[dumps[k - 1][0]]), None


def compare(route: Route, out: Path) -> dict:
    lines = dtm.read_lines(dolphin_dir(out) / "ram.txt")
    frames, shown, rows = dtm.game_frames(lines), pictures(lines), ram_rows(lines)
    listed = [line.split() for line in (dolphin_dir(out) / "frames.txt").read_text().splitlines()]
    dumps = sorted(((sha, dolphin_dir(out) / "frames" / name) for sha, name in listed),
                   key=lambda d: dolphin_ref.dump_index(d[1]))
    ours = json.loads((dragoon_dir(out) / "state.json").read_text())
    states = {int(f): (at, s) for f, (at, s) in ours["states"].items()}
    dragoon = frame_files(dragoon_dir(out))
    sides = out / "sides"
    sides.mkdir(exist_ok=True)
    report = []
    for c in checkpoints(route, lines):
        entry: dict = {"frame": c.frame, "why": c.why}
        found, refused = compare_picture(c.frame, frames, shown, dumps, dragoon)
        if refused:
            entry["refused"] = refused
        else:
            match, a, b = found
            s, diff = score(a, b)
            side = sides / f"{route.name}-{c.frame:05d}.png"
            side.write_bytes(write_png(side_by_side(side_by_side(a, b), diff)))
            entry.update(dataclasses.asdict(match), share=s.share, max=s.max, mean=s.mean,
                         over=over_budget(s), side=str(side))
        if c.frame in states:
            read_at, want = states[c.frame]
            result, what = compare_state(want, read_at, frames, rows)
            entry.update(read_at=read_at, state=result, state_diff=what)
        else:
            entry.update(state="not read", state_diff=["Dragoon never read this checkpoint"])
        report.append(entry)
    return {"route": route.name, "tolerance": TOLERANCE, "budget": BUDGET, "disc": DISC,
            "dragoon_end": ours["end"], "checkpoints": report}


def summary(report: dict) -> str:
    lines = [f"{report['route']}: Dragoon against Dolphin 2609a, both --disc {report['disc']}, "
             f"640x480 each, tolerance {report['tolerance']}, budget {report['budget']:.1%}",
             f"Dragoon's run ended on {report['dragoon_end']}", ""]
    for e in report["checkpoints"]:
        head = f"frame {e['frame']} ({e['why']}):"
        if "refused" in e:
            pic = f"refused, {e['refused']}"
        else:
            pic = (f"share {e['share']:.3%}, max {e['max']}, mean {e['mean']:.2f}"
                   f"{' OVER' if e['over'] else ''}; dump {e['dump']} (counted {e['counted']}, "
                   f"field {e['field']}), {e['sure']}")
        state = e["state"] + ("" if not e["state_diff"] else ": " + "; ".join(e["state_diff"]))
        lines.append(f"{head} {pic}; state {state}")
    return "\n".join(lines) + "\n"


def triage_line(route: str, e: dict) -> str:
    """A draft triage line for report entry E: within or refused, or unclear to be triaged."""
    if "refused" in e:
        return f"{route} {e['frame']} share=0% max=0 mean=0 refused {e['refused']}"
    cls, why = ("unclear", "not triaged yet") if e["over"] else ("within", "under the budget")
    return (f"{route} {e['frame']} share={100 * e['share']:.3f}% max={e['max']} "
            f"mean={e['mean']:.2f} {cls} {why}")


def cmd_compare(route: Route, out: Path) -> int:
    report = compare(route, out)
    (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    text = summary(report)
    (out / "summary.txt").write_text(text)
    (out / "triage-draft.txt").write_text(
        "".join(triage_line(route.name, e) + "\n" for e in report["checkpoints"]))
    print(text, end="")
    differs = [e for e in report["checkpoints"] if e["state"] == "differs"]
    return 1 if differs else 0


def clean(out: Path) -> None:
    """Delete OUT's frame dumps from both sides, keeping the side-by-sides and the reports."""
    for folder in (dolphin_dir(out) / "frames", dragoon_dir(out)):
        for path in sorted(folder.glob("*.png")) if folder.is_dir() else ():
            path.unlink()


def cmd_repeat(a: Path, b: Path) -> int:
    """The largest channel error between two runs of one side at their common frames."""
    if (a / "frames.txt").exists():
        sa = [line.split()[0] for line in (a / "frames.txt").read_text().splitlines()]
        sb = [line.split()[0] for line in (b / "frames.txt").read_text().splitlines()]
        common = min(len(sa), len(sb))
        same = sum(x == y for x, y in zip(sa, sb))
        print(f"Dolphin: {same} of the first {common} dumps the same")
        return 0 if same == common else 1
    fa, fb = frame_files(a), frame_files(b)
    common = sorted(fa.keys() & fb.keys())
    if not common:
        raise Bad(f"{a} and {b}: no frames in common")
    worst = max(score(read_png(fa[n]), read_png(fb[n]))[0].max for n in common)
    print(f"Dragoon: {len(common)} frames, the largest channel error {worst}")
    return 0 if worst == REPEAT_ERROR else 1


def parse_triage(text: str, where: str = "triage") -> list[Triage]:
    """TEXT's triage lines, as the module docstring gives them. A ValueError names a malformed
    line, an unknown class or a route's checkpoint listed twice."""
    out, seen = [], set()
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = TRIAGE_LINE.fullmatch(line)
        if not m:
            raise ValueError(f"{where}: line {n}: not 'ROUTE FRAME share=S% max=M mean=E CLASS "
                             f"REASON': {line!r}")
        if m[6] not in CLASSES:
            raise ValueError(f"{where}: line {n}: class {m[6]!r} isn't one of {', '.join(CLASSES)}")
        key = (m[1], int(m[2]))
        if key in seen:
            raise ValueError(f"{where}: line {n}: {m[1]} {m[2]} is triaged twice")
        seen.add(key)
        out.append(Triage(m[1], int(m[2]), float(m[3]) / 100, int(m[4]), float(m[5]), m[6], m[7]))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("run", "dolphin", "dragoon", "compare"):
        p = sub.add_parser(name)
        p.add_argument("route", metavar="ROUTE")
        p.add_argument("--out", type=Path, metavar="DIR",
                       help="the report folder (default build/dolphin-diff/ROUTE)")
        if name in ("run", "dolphin"):
            p.add_argument("--movie", type=Path, required=True, metavar="DTM")
            p.add_argument("--iso", type=Path, default=ISO)
    rp = sub.add_parser("repeat", help="the largest error between two runs of one side")
    rp.add_argument("a", type=Path)
    rp.add_argument("b", type=Path)
    tr = sub.add_parser("triage", help="check the triage file parses")
    tr.add_argument("file", type=Path, nargs="?", default=TRIAGE)
    args = ap.parse_args(argv)
    try:
        if args.command == "repeat":
            return cmd_repeat(args.a, args.b)
        if args.command == "triage":
            lines = parse_triage(args.file.read_text(), str(args.file))
            print(f"{args.file}: {len(lines)} checkpoints triaged")
            return 0
        (route,) = select_routes([args.route], MANIFEST)
        out = args.out or OUT / route.name
        out.mkdir(parents=True, exist_ok=True)
        code = 0
        if args.command in ("run", "dolphin"):
            code = cmd_dolphin(route, args.movie, args.iso, out)
            if code:
                return code
        if args.command in ("run", "dragoon"):
            code = cmd_dragoon(route, out)
        if args.command in ("run", "compare"):
            code = max(code, cmd_compare(route, out))
        if args.command == "run":
            clean(out)
        return code
    except (Bad, OSError, ValueError, KeyError, bot_link.LinkSetupError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
