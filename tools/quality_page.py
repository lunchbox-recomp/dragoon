#!/usr/bin/env python3
"""How well is each feature checked today? Writes docs/dev/quality.md from the files that check it.

Usage: quality_page.py [--check] [--root DIR]

The page has a row for every row of the feature table at the top of docs/dev/status.md, marked
by what checks it, never by what status.md's prose says:
  dolphin    a checkpoint in tests/hashes/dolphin-triage.txt falls in the feature, by the scene
             its route's presses put it in (scenes()). The row names its checkpoints' frames
             and counts them by class, gives the race's first difference as the lines name it
             (dolphin_moves.marks) and the gcn-recomp commit the file's head says it was scored on
  goldens    no checkpoint does, but a route COVERS gives the feature has lines in the golden
             folders it names: tests/hashes/gl/, gl-16x9/, state/ or audio/. Those files name no
             commit, so the row says they're held to the gcn-recomp pin in git's index. A state
             check tests/hashes/known-issues.txt lists for one of its routes is counted too
  unchecked  neither, and the row says status.md is the only source
A dolphin row gives its goldens' counts as well. COVERS has an entry for every feature in
status.md's table, and a feature added there or gone from it stops the tool until COVERS
follows, so no row is left off and none is made up.

A triaged route's scenes come from its presses in tests/routes/, which start with menu.txt's,
which start with title.txt's. Its checkpoints before title.txt's second to last press (300 A,
past the card's "data file has been created") are Boot and memory card, then the opening movie
until title.txt's last (900 A skips it), then the title screen until menu.txt's next press
(1000 START), then the mode select until the route's first A past menu.txt's, which goes into
its mode. From there they're the mode's feature, the one whose COVERS prefix the route's name
starts with, and the row splits them at the route's last START, where its race or city starts.
Checkpoints before the mode come after the same presses on every route, so a row says when routes
share them and counts each frame once.

--check writes nothing. It says whether the page on disk is what the tool would write, and
reads only those files and git's index, so it runs no game, Dolphin or build. --root is a tree
in place of this one, for tests.

Exits 0 when it wrote the page or found it current, 1 when --check found it stale or missing, and
2 when a file it reads is missing or doesn't parse, a feature and COVERS disagree, a triaged
route's presses don't start with menu.txt's or match no one COVERS prefix, or git's index has no
gcn-recomp pin.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import dolphin_diff
import dolphin_moves
import known_issues
from routes import Press, Route, parse_manifest, parse_route, route_script

ROOT = Path(__file__).resolve().parents[1]
PAGE = "docs/dev/quality.md"
STATUS = "docs/dev/status.md"
HASHES = "tests/hashes"
TRIAGE = f"{HASHES}/dolphin-triage.txt"
MANIFEST = f"{HASHES}/manifest.txt"
ROUTES = "tests/routes"
KINDS = ("gl", "gl-16x9", "state", "audio")  # the golden folders, each a file a route
PIN = "gcn-recomp"
SCORED = re.compile(r"#.*\bScored on gcn-recomp ([0-9a-f]{7,40})\b")
# The order a row counts classes in. Any other of dolphin_diff.CLASSES comes after.
CLASS_ORDER = ("within", "timing", "unclear", "bug", "dolphin", "setup", "refused")
DOLPHIN, GOLDENS, UNCHECKED = "Dolphin", "Goldens", "Unchecked"
BOOT, OPENING, TITLE = "Boot and memory card", "Opening movie", "Title screen"
MODE_SELECT = "Mode select"
SHARED = (BOOT, OPENING, TITLE, MODE_SELECT)  # the scenes every triaged route plays alike
WIDTH = 100  # the page's prose lines, as the repo's Markdown wraps


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
    BOOT: Cover(("title",)),
    OPENING: Cover(("title",)),
    TITLE: Cover(("title",)),
    MODE_SELECT: Cover(("menu",)),
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
                   "`tools/timed_bars.py`, but its results stay in `build/nightly/`, so status.md "
                   "is the only source in the repo."),
    "Build from the disc": Cover(),
    "Disc check": Cover(),
    "`.gcm` dumps": Cover(),
    "Disc path with spaces": Cover(),
    "Running from another directory": Cover(),
    "Network during the build": Cover(),
    "Idle loop": Cover(),
}


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


def presses(root: Path, route: str) -> list[Press]:
    name = f"{ROUTES}/{route}.txt"
    try:
        return parse_route(route_script(read(root, name)))
    except ValueError as e:
        raise Bad(f"{name}: {e}") from None


def mode_feature(route: str) -> str:
    """The one feature whose COVERS prefix, not the empty one, ROUTE's name starts with."""
    found = [f for f, c in COVERS.items() if any(p and route.startswith(p) for p in c.prefixes)]
    if len(found) != 1:
        raise Bad(f"{TRIAGE}: {route} starts with the COVERS prefix of {len(found)} features, "
                  f"not one: {found}")
    return found[0]


@dataclass(frozen=True)
class Scenes:
    starts: tuple  # (first frame, feature) in order, as the module docstring gives them
    play: Optional[int] = None  # the route's last START past its mode's, where its race starts


def scenes(root: Path, route: str) -> Scenes:
    title, menu, own = presses(root, "title"), presses(root, "menu"), presses(root, route)
    if len(title) < 2 or len(menu) <= len(title) or menu[:len(title)] != title:
        raise Bad(f"{ROUTES}/menu.txt doesn't start with title.txt's presses, of which there are "
                  f"two or more, and then press once more")
    if own[:len(menu)] != menu:
        raise Bad(f"{ROUTES}/{route}.txt doesn't start with menu.txt's presses")
    starts = [(0, BOOT), (title[-2].at, OPENING), (title[-1].at, TITLE),
              (menu[len(title)].at, MODE_SELECT)]
    rest = own[len(menu):]
    pick = next((p for p in rest if "A" in p.buttons), None)
    if pick is None:
        return Scenes(tuple(starts))
    play = [p.at for p in rest if "START" in p.buttons and p.at > pick.at]
    return Scenes((*starts, (pick.at, mode_feature(route))), play[-1] if play else None)


@dataclass(frozen=True)
class Placed:
    """A triaged checkpoint in its feature, with PART "" in a shared scene, "before" its mode's
    START at PLAY and "play" from it."""
    line: dolphin_diff.Triage
    feature: str
    part: str
    play: Optional[int]


def place(t: dolphin_diff.Triage, s: Scenes) -> Placed:
    feature = [f for at, f in s.starts if t.frame >= at][-1]
    if feature in SHARED or s.play is None:
        return Placed(t, feature, "", None)
    return Placed(t, feature, "before" if t.frame < s.play else "play", s.play)


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
    return sum(1 for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#"))


GOLDEN_WORDS = {"gl": ("frame at 4:3", "frames at 4:3"),
                "gl-16x9": ("frame at 16:9", "frames at 16:9"),
                "state": ("state checkpoint", "state checkpoints"),
                "audio": ("audio row", "audio rows")}


def plural(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def and_list(items: list) -> str:
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def class_order() -> list[str]:
    return [*CLASS_ORDER, *(c for c in dolphin_diff.CLASSES if c not in CLASS_ORDER)]


def class_counts(lines: list) -> str:
    counts = Counter(t.cls for t in lines)
    return and_list([f"{counts[c]} `{c}`" for c in class_order() if counts[c]])


def classes_at(lines: list) -> str:
    """LINES by class, naming the frames of each class but `within`."""
    out = []
    for c in class_order():
        frames = [t.frame for t in lines if t.cls == c]
        if frames:
            at = "" if c == "within" else f" at {and_list(frames)}"
            out.append(f"{len(frames)} `{c}`{at}")
    return and_list(out)


def frames_of(lines: list) -> str:
    frames = [t.frame for t in lines]
    return f"{'frame' if len(frames) == 1 else 'frames'} {and_list(frames)}"


def dolphin_sentences(placed: list[Placed]) -> list[str]:
    """The row's checkpoints by route. Routes whose checkpoints are all in shared scenes, at the
    same frames with the same classes, are named together and each frame counted once."""
    by_route: dict = {}
    for p in placed:
        by_route.setdefault(p.line.route, []).append(p)
    groups: dict = {}
    for route, ps in sorted(by_route.items()):
        shared = all(p.part == "" and p.feature in SHARED for p in ps)
        frames = tuple((p.line.frame, p.line.cls) for p in ps)
        groups.setdefault(("shared", frames) if shared else ("own", route), []).append(route)
    out = []
    for key, names in groups.items():
        ps = by_route[names[0]]
        if key[0] == "shared" and len(names) > 1:
            lines = [p.line for p in ps]
            out.append(f"{frames_of(lines).capitalize()} on each of {and_list(names)}, which play "
                       f"the same presses up to those frames: {classes_at(lines)} on each.")
            continue
        for part in ("", "before", "play"):
            lines = [p.line for p in ps if p.part == part]
            if not lines:
                continue
            play = next(p.play for p in ps if p.part == part)
            lead = {"": "", "before": f"Before START at {play}, ",
                    "play": f"From START at {play}, "}[part]
            text = f"{frames_of(lines)} on {names[0]}: {classes_at(lines)}."
            out.append(lead + text if lead else text[0].upper() + text[1:])
        first, through = dolphin_moves.marks([p.line for p in ps])
        if first is not None:
            out.append(f"On {names[0]} the race first differs from Dolphin's at pass {first}.")
        elif through is not None:
            out.append(f"On {names[0]} the race matches Dolphin's through pass {through}.")
    return out


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


def measured_at(dolphin: bool, goldens: bool, scored: Optional[str], pin: str) -> str:
    on = f"Dolphin on gcn-recomp `{scored}`" if scored else \
        "Dolphin on a commit the triage file's head doesn't name"
    if dolphin and goldens:
        return f"{on}, the goldens held to that pin" if scored == pin else \
            f"{on}, the goldens held to the pin `{pin}`"
    if dolphin:
        return on
    if goldens:
        return f"Held to the pin, gcn-recomp `{pin}`"
    return "Not measured here"


def make_row(feature: str, status: str, cover: Cover, placed: list[Placed], routes: list[Route],
             root: Path, scored: Optional[str], pin: str, issues: dict) -> Row:
    names = covered_routes(cover, routes)
    per_route = {r: {k: golden_lines(root, k, r) for k in cover.kinds} for r in names}
    counts = {k: sum(c[k] for c in per_route.values()) for k in cover.kinds}
    counted = [k for k in cover.kinds if counts[k]]
    hashed = [r for r, c in per_route.items() if any(c.values())]
    known = sorted(i for i in issues if "state" in cover.kinds and i.split()[-1] in names)
    parts, files = dolphin_sentences(placed), []
    if placed:
        files.append(link("dolphin-triage.txt", to_hashes("dolphin-triage.txt")))
    if counted:
        parts.append(f"Goldens of {plural(len(hashed), 'route', 'routes')}: "
                     f"{and_list([plural(counts[k], *GOLDEN_WORDS[k]) for k in counted])}.")
        files += [link(f"{k}/", to_hashes(f"{k}/")) for k in counted]
    if known:
        parts.append(f"{plural(len(known), 'state check', 'state checks')} expected to fail "
                     f"as a known issue.")
        files.append(link("known-issues.txt", to_hashes("known-issues.txt")))
    if not placed and not counted:
        parts.append("No golden or Dolphin compare covers it.")
        parts.append(cover.note or "status.md is the only source.")
        files.append(link("status.md", "status.md"))
    elif cover.note:
        parts.append(cover.note)
    files += [link(name, path) for name, path in cover.links]
    mark = DOLPHIN if placed else GOLDENS if counted else UNCHECKED
    return Row(feature, status, mark, " ".join(parts),
               measured_at(bool(placed), bool(counted), scored, pin), ", ".join(files))


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
    route_scenes = {r: scenes(root, r) for r in sorted({t.route for t in triage.lines})}
    by_feature: dict = {f: [] for f in names}
    for t in triage.lines:
        p = place(t, route_scenes[t.route])
        by_feature[p.feature].append(p)
    rows = [make_row(f, s, COVERS[f], by_feature[f], routes, root, scored, pin, issues)
            for f, s in features]
    return render(rows, triage.lines)


def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(text, WIDTH, subsequent_indent=indent, break_long_words=False,
                         break_on_hyphens=False)


def render(rows: list[Row], lines: list) -> str:
    marks = Counter(r.mark for r in rows)
    routes = sorted({t.route for t in lines})
    summary = (f"Of {len(rows)} features, {marks[DOLPHIN]} are checked against Dolphin, "
               f"{marks[GOLDENS]} against our goldens only and {marks[UNCHECKED]} are unchecked.")
    if lines:
        summary += (f" The Dolphin compare has {plural(len(lines), 'checkpoint', 'checkpoints')} "
                    f"on {plural(len(routes), 'route', 'routes')}, {class_counts(lines)}.")
    out = [
        "# Quality",
        "",
        wrap("<!-- tools/quality_page.py writes this page from the files it links. Run it again "
             "after any of them changes. `tools/quality_page.py --check` says whether it's "
             "current. -->"),
        "",
        wrap("How well each feature in [status.md](status.md)'s table is checked today, going by "
             "the files that check it. Each one is marked as one of these:"),
        "",
        wrap("- **Dolphin**: Dragoon is compared with Dolphin at matched game frames, and each "
             "checkpoint in the triage file is counted by its class. `within` is under the budget "
             "with the state matching, `timing` the same pictures in another order or a few "
             "frames apart, `unclear` a difference whose cause isn't known and `bug` a Dragoon "
             "bug. A row names its checkpoints' frames, and splits a mode's at the START that "
             "begins its race or city.", "  "),
        wrap("- **Goldens**: our own frame, state or audio hashes cover it. No Dolphin compare "
             "does, and a golden only says the output hasn't changed, not that it's right.", "  "),
        wrap("- **Unchecked**: no Dolphin compare or golden covers it.", "  "),
        "",
        wrap("The golden files name no commit, so their rows say they're held to the gcn-recomp "
             "pin. `tools/nightly.py` plays the goldens and the triaged checkpoints on the real "
             "game each night. Its reports stay in `build/nightly/`, so none of its numbers are "
             "here."),
        "",
        wrap(summary),
        "",
        "| Feature | Checked | status.md | Latest numbers | Measured at | Files |",
        "|---|---|---|---|---|---|",
    ]
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
