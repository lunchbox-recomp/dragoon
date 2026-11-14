#!/usr/bin/env python3
"""Which of Dragoon's gcn-recomp cites did an engine bump leave pointing at the wrong lines?

Reads every tracked text file in the Dragoon checkout but this tool and its tests, as it sits in
the working tree, for cites of gcn-recomp files by line. These forms count:
  gcn-recomp/PATH:N or gcn-recomp/PATH:N-M   a fork path, always a fork cite
  PATH:N or NAME:N                           a fork-relative path such as runtime/hw/drive.h:64,
                                             or a bare name such as ax.cpp:42, when exactly one
                                             fork file at OLD or NEW is it or ends in /PATH, and
                                             no file Dragoon tracks does
  :N or :N-M after a cite                    a continuation, as in ax.cpp:42, :53-60, on the same
                                             line, taking the file of the cite nearest before it
  , N or , N-M straight after a cite         a list, as in render_gl_batch.cpp:180, 522-523, when
                                             the number ends at ), comma, ; or a backtick
A bare name Dragoon also has, such as CMakeLists.txt, needs the gcn-recomp/ prefix to count. A
name two fork files share is listed as skipped, below. A Markdown :N with no file:N cite before
it on its line is a stray, skipped with a warning on stderr, even one whose file is named there
without a line or on the line before, since the tool can't tell which file it means. So is a
Markdown :N with a file named without a line between it and the cite before it, as :65 in
ax.cpp:617 (dsp_hle.cpp, :65), which may mean either file. PATH:N:M is a
compiler's diagnostic, not a cite, and Markdown's fenced code blocks hold quoted output, so their
lines are skipped. Paths with spaces aren't recognised. A file named without a line is only a
path a cite could hold, so x.cpp-y, lib.so.1 and /usr/x.cpp name no file, just as x.cpp-y:3,
lib.so.1:3 and /usr/x.cpp:3 aren't cites.

Each cite's lines are read at OLD with git -C gcn-recomp show. A cite whose file changed between
OLD and NEW is listed as one of:
  ok DOC:LINE PATH:N-M             the same text sits at N-M at NEW
  moved DOC:LINE PATH:N-M now A-B  it doesn't, and sits at A-B instead (each place, if several)
  gone DOC:LINE PATH:N-M           NEW doesn't have the lines anywhere as one block, though
                                   some may still be there, or the file is gone
Lines are compared with their leading and trailing whitespace stripped. Any cite, in a changed
file or not, whose lines aren't all in the file at OLD is listed as
  outside DOC:LINE PATH:N-M, OLD has K lines   (or "not at OLD")
since it was stale before the bump. A name two fork files at OLD or NEW share is listed as
  skipped DOC:LINE NAME:N-M, names K fork files (PATH, PATH)
since it can't be checked until the cite gives more of the path. A fork file that moves to
another folder between OLD and NEW is two such files, so each bare cite of it is skipped too,
and its cites of the old path, with gcn-recomp/ or fork-relative as hw/ax.cpp:2, are gone.
Cites in unchanged files are only counted. The last line is
"total T, ok O, moved M, gone G, outside X, unchanged U, skipped S, stray W", W counting the
strays, which aren't cites and so aren't in T. DOC and PATH are relative to Dragoon and to
gcn-recomp.

--repo names the Dragoon checkout, by default the one holding this tool. --at REV reads Dragoon's
files at commit REV instead of the working tree, leaving out links. Name the commit that moved
the pin to re-check a bump whose cites were already edited, since a cite moved by hand to NEW's
lines reads as moved from OLD's. Exits 1 when a cite moved, is gone, is outside or was skipped
or there's a stray, 0 when none is, and 2 when gcn-recomp isn't checked out or git can't read OLD or NEW there.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Optional

ROOT = Path(__file__).resolve().parents[1]
ENGINE = "gcn-recomp"
PREFIX = ENGINE + "/"
# The tool and its tests are full of example cites, so their text isn't read.
OWN = ("tools/fork_cites.py", "tools/test_fork_cites.py")

# A path is word characters, dots and hyphens split by slashes, ending in a dot and a letter.
# A cite can't follow a path character, and a digit or ":digit" after it makes it something else.
CITE = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.[A-Za-z]\w*):(\d+)(?:-(\d+))?(?!\d|:\d)")
CONTINUATION = re.compile(r"(?<![\w./:-]):(\d+)(?:-(\d+))?(?!\d|:\d)")
# A file named with no line: a path as CITE has it, then no more path and no ":digit".
NAME = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.[A-Za-z]\w*)(?![\w/-]|\.\w|:\d)")
LIST = re.compile(r",\s*(\d+)(?:-(\d+))?(?=[),;\x60]|$)")
FENCE = re.compile(r"\s*(\x60{3}|~{3})")


class Cite(NamedTuple):
    line: int
    path: str
    first: int
    last: int


def find(text: str, markdown: bool) -> tuple[list[Cite], list[tuple[int, str, Optional[str]]]]:
    """TEXT's cites in order, each continuation and list item carrying its file's path as
    written, and its strays. MARKDOWN skips fenced code blocks and finds strays, each :N with
    no cite before it on its line or with a file named without a line between it and that cite,
    as (line, the :N as written, that file's name or None)."""
    cites: list[Cite] = []
    strays: list[tuple[int, str, Optional[str]]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if markdown and FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        found = [(m.start(), m.end(), m.group(1), m.group(2), m.group(3)) for m in CITE.finditer(line)]
        found += [(m.start(), m.end(), None, m.group(1), m.group(2))
                  for m in CONTINUATION.finditer(line)]
        if markdown:
            found += [(m.start(), m.end(), m.group(1), None, None) for m in NAME.finditer(line)]
        path = named = None
        for start, end, written, first, last in sorted(found):
            if first is None:
                named = written if path else None
                continue
            if written:
                path, named = written, None
            elif path is None or named:
                if markdown:
                    strays.append((number, line[start:end], named))
                continue
            cites.append(Cite(number, path, int(first), int(last or first)))
            while True:
                item = LIST.match(line, end)
                if item is None:
                    break
                cites.append(Cite(number, path, int(item.group(1)), int(item.group(2) or item.group(1))))
                end = item.end()
    return cites, strays


def git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              check=True).stdout
    except subprocess.CalledProcessError as e:
        why = e.stderr.decode(errors="replace").strip() or f"exit {e.returncode}"
        raise ValueError(f"git {' '.join(args)} in {repo} failed: {why}") from None


def names(output: bytes) -> list[str]:
    return [name for name in output.decode().split("\0") if name]


class Fork:
    """gcn-recomp's files at OLD and NEW, read once each."""

    def __init__(self, repo: Path, old: str, new: str) -> None:
        self.repo = repo
        self.old, self.new = old, new
        self.trees = {sha: set(names(git(repo, "ls-tree", "-r", "-z", "--name-only", sha)))
                      for sha in (old, new)}
        self.changed = set(names(git(repo, "diff", "--name-only", "--no-renames", "-z", old, new)))
        self.files = sorted(self.trees[old] | self.trees[new])
        self.read: dict[tuple[str, str], Optional[list[str]]] = {}

    def lines(self, sha: str, path: str) -> Optional[list[str]]:
        """PATH's lines at SHA, stripped, or None when it has no such file."""
        if (sha, path) not in self.read:
            text = None
            if path in self.trees[sha]:
                text = git(self.repo, "show", f"{sha}:{path}").decode(errors="replace")
            self.read[sha, path] = None if text is None else [s.strip() for s in text.splitlines()]
        return self.read[sha, path]


def resolve(path: str, dragoon: list[str], fork: Fork) -> tuple[Optional[str], list[str]]:
    """The fork path PATH cites, or None, and the fork files it could name when that's several."""
    if path.startswith(PREFIX):
        return path[len(PREFIX):], []
    if any(f == path or f.endswith("/" + path) for f in dragoon):
        return None, []
    matches = [f for f in fork.files if f == path or f.endswith("/" + path)]
    return (matches[0] if len(matches) == 1 else None), (matches if len(matches) > 1 else [])


def span(first: int, last: int) -> str:
    return str(first) if first == last else f"{first}-{last}"


def places(block: list[str], lines: list[str]) -> list[int]:
    """Each line number in LINES where BLOCK starts."""
    n = len(block)
    return [i + 1 for i in range(len(lines) - n + 1) if lines[i:i + n] == block]


def check(cite: Cite, path: str, fork: Fork) -> tuple[str, str]:
    """(status, the rest of its line) for CITE of fork file PATH."""
    old = fork.lines(fork.old, path)
    if old is None or not 1 <= cite.first <= cite.last <= len(old):
        return "outside", ", not at OLD" if old is None else f", OLD has {len(old)} lines"
    if path not in fork.changed:
        return "unchanged", ""
    block = old[cite.first - 1:cite.last]
    new = fork.lines(fork.new, path)
    if new is not None and new[cite.first - 1:cite.last] == block:
        return "ok", ""
    found = places(block, new or [])
    if not found:
        return "gone", ""
    return "moved", " now " + ", ".join(span(f, f + len(block) - 1) for f in found)


def dragoon_texts(repo: Path, at: Optional[str]) -> tuple[list[str], dict[str, str]]:
    """Every path Dragoon tracks but gcn-recomp, and each regular file's text, from commit AT or,
    with no AT, from REPO's working tree. Links, binary files and OWN have no text."""
    if at is None:
        tracked = [name for name in names(git(repo, "ls-files", "-z")) if name != ENGINE]
        files = [name for name in tracked if (repo / name).is_file() and not (repo / name).is_symlink()]
    else:
        entries = [entry.split("\t", 1) for entry in names(git(repo, "ls-tree", "-r", "-z", at))]
        tracked = [path for meta, path in entries if " blob " in meta]
        files = [path for meta, path in entries if meta.startswith("100")]
    texts = {}
    for name in sorted(set(files) - set(OWN)):
        data = (repo / name).read_bytes() if at is None else git(repo, "show", f"{at}:{name}")
        if b"\0" not in data:
            texts[name] = data.decode(errors="replace")
    return tracked, texts


def run(repo: Path, old: str, new: str, at: Optional[str]) -> int:
    engine = repo / ENGINE
    try:
        top = git(engine, "rev-parse", "--show-toplevel").decode().strip()
    except (OSError, ValueError):
        top = ""
    if not top or Path(top).resolve() != engine.resolve():
        raise ValueError(f"{engine} isn't a git checkout")
    fork = Fork(engine, old, new)
    dragoon, texts = dragoon_texts(repo, at)
    counts = dict.fromkeys(("ok", "moved", "gone", "outside", "unchanged", "skipped"), 0)
    stray = 0
    for doc, body in texts.items():
        cites, strays = find(body, doc.endswith(".md"))
        stray += len(strays)
        for number, written, named in strays:
            why = (f"follows {named}, named with no line after the last file:N cite on its line"
                   if named else "has no file:N cite before it on its line")
            print(f"fork_cites.py: {doc}:{number}: {written} {why}, so it isn't checked", file=sys.stderr)
        for cite in cites:
            path, several = resolve(cite.path, dragoon, fork)
            if several:
                status, path = "skipped", cite.path
                rest = f", names {len(several)} fork files ({', '.join(several)})"
            elif path is None:
                continue
            else:
                status, rest = check(cite, path, fork)
            counts[status] += 1
            if status != "unchanged":
                print(f"{status} {doc}:{cite.line} {path}:{span(cite.first, cite.last)}{rest}")
    print(f"total {sum(counts.values())}, " + ", ".join(f"{k} {v}" for k, v in counts.items())
          + f", stray {stray}")
    return 0 if counts["ok"] + counts["unchanged"] == sum(counts.values()) and not stray else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(usage="fork_cites.py OLD NEW [--repo DIR] [--at REV]",
                                 description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", metavar="OLD", help="the gcn-recomp commit the cites were written at")
    ap.add_argument("new", metavar="NEW", help="the gcn-recomp commit they should hold at")
    ap.add_argument("--repo", type=Path, default=ROOT, help="the Dragoon checkout")
    ap.add_argument("--at", metavar="REV", help="read Dragoon's files at this commit")
    args = ap.parse_args(argv)
    try:
        return run(args.repo.resolve(), args.old, args.new, args.at)
    except (OSError, ValueError) as e:
        print(f"fork_cites.py: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
