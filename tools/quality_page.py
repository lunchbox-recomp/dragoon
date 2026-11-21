#!/usr/bin/env python3
"""How well is each feature checked today? Writes docs/dev/quality.md from the files that check them.

Usage: quality_page.py [--check] [--root DIR]

The page has a row for every row of the feature table at the top of docs/dev/status.md, marked
by what checks it, never by what status.md's prose says:
  dolphin    a checkpoint in tests/hashes/dolphin-triage.txt falls in the feature: the route's
             own mode (MODES) past SCENES' last boundary, or the shared scene before it. The row
             counts its checkpoints by class, gives the race's first difference as the lines name
             it (dolphin_moves.marks) and the gcn-recomp commit the file's head says it was
             scored on
  goldens    no checkpoint does, but a route COVERS gives the feature has lines in the golden
             folders it names: tests/hashes/gl/, gl-16x9/, state/ or audio/. Those files name no
             commit, so the row gives the gcn-recomp pin in git's index, which the goldens are
             held to. A state check tests/hashes/known-issues.txt lists for one of its routes is
             counted too
  unchecked  neither, and the row says status.md is the only source
A dolphin row gives its goldens' counts as well. COVERS has an entry for every feature in
status.md's table, and a feature added there or gone from it stops the tool until COVERS
follows, so no row is left off and none is made up.

--check writes nothing. It says whether the page on disk is what the tool would write, and
reads only those files and git's index, so it runs no game, Dolphin or build. --root is a tree
in place of this one, for tests.

Exits 0 when it wrote the page or found it current, 1 when --check found it stale or missing, and
2 when a file it reads is missing or doesn't parse, a feature and COVERS disagree, a triaged
route has no entry in MODES or git's index has no gcn-recomp pin.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import dolphin_diff
import dolphin_moves
import known_issues
from routes import Route, parse_manifest

ROOT = Path(__file__).resolve().parents[1]
PAGE = "docs/dev/quality.md"
STATUS = "docs/dev/status.md"
HASHES = "tests/hashes"
TRIAGE = f"{HASHES}/dolphin-triage.txt"
MANIFEST = f"{HASHES}/manifest.txt"
KINDS = ("gl", "gl-16x9", "state", "audio")  # the golden folders, each a file a route
PIN = "gcn-recomp"
SCORED = re.compile(r"#.*\bScored on gcn-recomp ([0-9a-f]{7,40})\b")
# The order a row counts classes in. Any other of dolphin_diff.CLASSES comes after.
CLASS_ORDER = ("within", "timing", "unclear", "bug", "dolphin", "setup", "refused")
DOLPHIN, GOLDENS, UNCHECKED = "Dolphin", "Goldens", "Unchecked"


@dataclass(frozen=True)
class Cover:
    """The goldens of the manifest routes whose names start with one of PREFIXES, or that plug in
    more than one pad when PADS, in the folders KINDS. NOTE ends the row's numbers, and LINKS are
    (name, path from the page) the row links besides its evidence."""
    prefixes: tuple = ()
    pads: bool = False
    kinds: tuple = KINDS
    note: str = ""
    links: tuple = ()


# Every feature in status.md's table. A route's goldens count for the features whose prefixes
# match it, and a Dolphin checkpoint for the one feature its frame's scene is in.
COVERS = {
    "Boot and memory card": Cover(("title",)),
    "Opening movie": Cover(("title",)),
    "Title screen": Cover(("title",)),
    "Mode select": Cover(("menu",)),
    "Air Ride race": Cover(("air-ride-",)),
    "City Trial": Cover(("city-trial",)),
    "Top Ride": Cover(("top-ride-",)),
    "Audio": Cover(("",), kinds=("audio",), note="The click and clipping counts, scored with "
                   "nobody listening, are in the audio scorecard.",
                   links=(("scorecard.md", "scorecard.md"),)),
    "Controllers": Cover(pads=True, note="The routes play scripted presses with no gamepad "
                         "open, so gamepads and the Controllers page aren't hashed."),
    "Picture": Cover(("",), kinds=("gl-16x9",)),
    "Speed": Cover(note="The nightly's timed step measures it against the bars in "
                   "`tools/timed_bars.py`, and its results stay in `build/nightly/`."),
    "Build from the disc": Cover(),
    "Disc check": Cover(),
    "`.gcm` dumps": Cover(),
    "Disc path with spaces": Cover(),
    "Running from another directory": Cover(),
    "Network during the build": Cover(),
    "Idle loop": Cover(),
}
# Every triaged route plays menu.txt's presses first: 300 A past the card's "data file has been
# created", 900 A skips the opening movie (title.txt) and 1000 START leaves the title for the
# mode select. Its next press, at 1300, picks its mode. A checkpoint is in the scene of the last
# boundary at or before its frame, and None is the route's own mode, from MODES.
SCENES = ((0, "Boot and memory card"), (300, "Opening movie"), (1000, "Mode select"), (1300, None))
MODES = {"air-ride-race": "Air Ride race", "city-trial": "City Trial", "top-ride-grass": "Top Ride"}


class Bad(Exception):
    """A file the page is made from that's missing or doesn't parse, or COVERS out of step."""


def read(root: Path, name: str) -> str:
    try:
        return (root / name).read_text()
    except OSError as e:
        raise Bad(f"{name}: {e.strerror or e}") from None


def status_features(text: str) -> list[tuple[str, str]]:
    """Each row of the first table in status.md, the feature table: (feature, status)."""
    rows, started = [], False
    for line in text.splitlines():
        if not line.startswith("|"):
            if started:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not started:
            if cells[:2] != ["Feature", "Status"]:
                raise Bad(f"{STATUS}: its first table isn't headed Feature, Status: {line!r}")
            started = True
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        if len(cells) < 2:
            raise Bad(f"{STATUS}: a feature row with no status: {line!r}")
        rows.append((cells[0], cells[1]))
    if not rows:
        raise Bad(f"{STATUS}: no feature table")
    return rows


def scene_of(route: str, frame: int) -> str:
    """The feature a triaged checkpoint of ROUTE at FRAME falls in."""
    feature = [f for start, f in SCENES if frame >= start][-1]
    if feature is not None:
        return feature
    if route not in MODES:
        raise Bad(f"{TRIAGE}: {route} has no entry in quality_page.py's MODES")
    return MODES[route]


def pads(route: Route) -> int:
    return max([int(s.split("=", 1)[1]) for s in route.extra if s.startswith("--pads=")] or [1])


def covered_routes(cover: Cover, routes: list[Route]) -> list[str]:
    return [r.name for r in routes
            if any(r.name.startswith(p) for p in cover.prefixes) or (cover.pads and pads(r) > 1)]


def golden_lines(root: Path, kind: str, route: str) -> int:
    """How many checks the golden of ROUTE in KIND holds: frames, checkpoints or audio rows."""
    path = root / HASHES / kind / f"{route}.txt"
    if not path.is_file():
        return 0
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    if kind == "state":
        return sum(ln.startswith("frame ") for ln in lines)
    return len(lines)


GOLDEN_WORDS = {"gl": ("frame at 4:3", "frames at 4:3"),
                "gl-16x9": ("frame at 16:9", "frames at 16:9"),
                "state": ("state checkpoint", "state checkpoints"),
                "audio": ("audio row", "audio rows")}


def plural(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def and_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def class_counts(lines: list) -> str:
    counts = Counter(t.cls for t in lines)
    order = [*CLASS_ORDER, *(c for c in dolphin_diff.CLASSES if c not in CLASS_ORDER)]
    return and_list([f"{counts[c]} `{c}`" for c in order if counts[c]])


@dataclass
class Row:
    feature: str
    status: str
    mark: str
    numbers: str
    measured: str
    files: str


def link(name: str, path: str) -> str:
    return f"[{name}]({path})"


def to_hashes(rest: str) -> str:
    """A path under tests/hashes/ as the page, in docs/dev/, links it."""
    return f"../../{HASHES}/{rest}"


def make_row(feature: str, status: str, cover: Cover, lines: list, routes: list[Route], root: Path,
             scored: Optional[str], pin: str, issues: dict) -> Row:
    names = covered_routes(cover, routes)
    per_route = {r: {k: golden_lines(root, k, r) for k in cover.kinds} for r in names}
    counts = {k: sum(c[k] for c in per_route.values()) for k in cover.kinds}
    counted = [k for k in cover.kinds if counts[k]]
    hashed = [r for r, c in per_route.items() if any(c.values())]
    known = sorted(i for i in issues if "state" in cover.kinds and i.split()[-1] in names)
    parts, files = [], []
    if lines:
        routes_in = sorted({t.route for t in lines})
        parts.append(f"{plural(len(lines), 'Dolphin checkpoint', 'Dolphin checkpoints')} on "
                     f"{and_list(routes_in)}: {class_counts(lines)}.")
        for route in routes_in:
            first, through = dolphin_moves.marks([t for t in lines if t.route == route])
            if first is not None:
                parts.append(f"On {route} the race first differs from Dolphin's at pass {first}.")
            elif through is not None:
                parts.append(f"On {route} the race matches Dolphin's through pass {through}.")
        files.append(link("dolphin-triage.txt", to_hashes("dolphin-triage.txt")))
    if counted:
        parts.append(f"Goldens of {plural(len(hashed), 'route', 'routes')}: "
                     f"{and_list([plural(counts[k], *GOLDEN_WORDS[k]) for k in counted])}.")
        files += [link(f"{k}/", to_hashes(f"{k}/")) for k in counted]
    if known:
        parts.append(f"{plural(len(known), 'state check', 'state checks')} expected to fail "
                     f"as a known issue.")
        files.append(link("known-issues.txt", to_hashes("known-issues.txt")))
    if not lines and not counted:
        parts.append("Nothing in `tests/hashes/` measures it, so status.md is the only source.")
        files.append(link("status.md", "status.md"))
    if cover.note:
        parts.append(cover.note)
    files += [link(name, path) for name, path in cover.links]
    mark = DOLPHIN if lines else GOLDENS if counted else UNCHECKED
    if lines:
        measured = f"gcn-recomp `{scored}`" if scored else "not in the triage file's head"
        if counted:
            measured = (f"gcn-recomp `{scored}`, the pin" if scored == pin else
                        f"{measured} (Dolphin), the pin `{pin}` (goldens)")
    elif counted:
        measured = f"gcn-recomp `{pin}`, the pin"
    else:
        measured = "Not measured here"
    return Row(feature, status, mark, " ".join(parts), measured, ", ".join(files))


def git_pin(root: Path) -> str:
    """The gcn-recomp commit git's index pins, short."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-s", "--", PIN],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Bad(f"git ls-files -s {PIN}: {e}") from None
    m = re.fullmatch(r"160000 ([0-9a-f]{40}) 0\t" + re.escape(PIN) + r"\n", out)
    if not m:
        raise Bad(f"{root}: git's index has no {PIN} pin")
    return m[1][:7]


def page(root: Path, pin: str) -> str:
    """The page, from ROOT's files, with PIN the gcn-recomp commit the goldens are held to."""
    features = status_features(read(root, STATUS))
    names = [f for f, _ in features]
    extra, missing = sorted(set(names) - set(COVERS)), sorted(set(COVERS) - set(names))
    if extra or missing or len(set(names)) != len(names):
        raise Bad(f"{STATUS}'s features and quality_page.py's COVERS disagree: "
                  f"only in status.md {extra}, only in COVERS {missing}, or one is listed twice")
    triage_text = read(root, TRIAGE)
    try:
        triage = dolphin_diff.parse_triage(triage_text, TRIAGE)
        routes = parse_manifest(read(root, MANIFEST))
        issues = known_issues.read(root / HASHES)
    except ValueError as e:
        raise Bad(str(e)) from None
    scored = next((m[1] for m in map(SCORED.match, triage_text.splitlines()) if m), None)
    by_feature: dict = {f: [] for f in names}
    for t in triage.lines:
        by_feature[scene_of(t.route, t.frame)].append(t)
    rows = [make_row(f, s, COVERS[f], by_feature[f], routes, root, scored, pin, issues)
            for f, s in features]
    return render(rows, triage.lines)


def render(rows: list[Row], lines: list) -> str:
    marks = Counter(r.mark for r in rows)
    routes = sorted({t.route for t in lines})
    out = [
        "# Quality",
        "",
        "<!-- tools/quality_page.py writes this page from the files it links. Run it again after "
        "any of them changes. `tools/quality_page.py --check` says whether it's current. -->",
        "",
        "How well each feature in [status.md](status.md)'s table is checked today, going by the "
        "files that check it. Each one is marked as one of these:",
        "",
        "- **Dolphin**: Dragoon is compared with Dolphin at matched game frames, and each "
        "checkpoint in the triage file is counted by its class. `within` is under the budget "
        "with the state matching, `timing` the same pictures in another order or a few frames "
        "apart, `unclear` a difference whose cause isn't known and `bug` a Dragoon bug.",
        "- **Goldens**: our own frame, state or audio hashes cover it. No Dolphin compare does, "
        "and a golden only says the output hasn't changed, not that it's right.",
        "- **Unchecked**: no Dolphin compare or golden covers it.",
        "",
        "The golden files name no commit, so their rows give the gcn-recomp pin they're held to. "
        "`tools/nightly.py` plays the goldens and the triaged checkpoints on the real game each "
        "night. Its reports stay in `build/nightly/`, so none of its numbers are here.",
        "",
        f"Of {len(rows)} features, {marks[DOLPHIN]} are checked against Dolphin, "
        f"{marks[GOLDENS]} against our goldens only and {marks[UNCHECKED]} are unchecked.",
    ]
    if lines:
        out[-1] += (f" The Dolphin compare has {plural(len(lines), 'checkpoint', 'checkpoints')} "
                    f"on {plural(len(routes), 'route', 'routes')}, {class_counts(lines)}.")
    out += ["", "| Feature | Checked | status.md | Latest numbers | Measured at | Files |",
            "|---|---|---|---|---|---|"]
    out += [f"| {r.feature} | {r.mark} | {r.status} | {r.numbers} | {r.measured} | {r.files} |"
            for r in rows]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="say whether the page is current")
    ap.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        want = page(args.root, git_pin(args.root))
    except Bad as e:
        print(f"quality_page.py: {e}", file=sys.stderr)
        return 2
    path = args.root / PAGE
    have = path.read_text() if path.is_file() else None
    if args.check:
        if have != want:
            print(f"{PAGE} is {'missing' if have is None else 'stale'}: run tools/quality_page.py")
            return 1
        print(f"{PAGE} is current")
        return 0
    if have != want:
        path.write_text(want)
        print(f"wrote {PAGE}")
    else:
        print(f"{PAGE} is current")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
