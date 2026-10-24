#!/usr/bin/env python3
"""Change the code on a copy of a commit and see whether the tests notice.

Usage: mutant.py SPEC DEST [--repo DIR] [--rev REV] [--python FILE] [--timeout SECONDS]

SPEC is a JSON file holding a list of mutants. A mutant has three fields and may have a fourth:
  name     what the output calls it, on one line and unlike any other name
  dir      the test directory to discover in, relative to the repo, such as tools
  replace  a list of {"file", "old", "new"} edits applied together, in order, each to the
           text the one before left. FILE is relative to the repo. OLD has to occur in it
           exactly once, so a typo can't make a mutant that changes nothing. NEW may be empty.
  pattern  which test files to run, as unittest's -p takes it (default test_*.py). It matches
           file names, so it has no /. test_export_source.py runs that one file.
DEST is a new directory outside the repo, and outside the checkout holding this tool when
--repo names another. The copies are built there and kept, and nothing is removed. baseline-N
is the copy for the Nth dir and pattern the mutants test, and mutant-N is the Nth mutant's.
The last 64 KiB of each run's output is beside its copy as a .log file.

Every copy is REV (default HEAD) of the repo that holds this tool, or of --repo, made by
git archive. The repo's own files are never edited or run, and its uncommitted changes aren't
tested. A copy has no .git and, since git archive leaves submodules out, no gcn-recomp. A test
that needs either has to skip itself, as RealTreeTest in test_launcher_build.py does.

All the copies are built and all the edits applied before anything runs, so a spec that can't
work costs no test run. Then each distinct dir and pattern gets a baseline, which runs
  PYTHON -B -m unittest discover -s COPY/DIR -p PATTERN
in its copy and has to pass. Without that, a selection that fails on its own would make every
mutant look killed. Each mutant then runs the same command in a copy of its own, so nothing an
earlier run left behind is tested. The tests get PATH=/usr/bin:/bin:/usr/sbin:/sbin (the
TOOL_PATH of launcher_build.py), HOME and TMPDIR from the caller and PYTHONDONTWRITEBYTECODE=1.
Nothing else in the caller's environment reaches them, so no key or token in it does. A run that
outlasts --timeout (600 s by default, for each run) is killed. So is anything a run started
and left running, when the run ends.

It prints one line per mutant as it finishes, and then a total:
  killed NAME     the tests failed
  survived NAME   the tests passed
  timeout NAME    the tests outran --timeout
  total N, killed K, survived S, timeout T
A kill that isn't unittest's exit 1 says how the run ended, as in "killed NAME (exit -9)"
for a signal or "killed NAME (exit 5)" for no tests. A mutant that breaks an import or the
syntax counts as killed too, so read mutant-N.log before trusting a kill that matters.

Exits 0 when every mutant was killed and 1 when any survived or timed out. Exits 2 with a
one-line "mutant:" message on stderr when it couldn't decide, which is any of these:
  a bad argument or spec
  an old found other than once
  a file or dir that isn't in the copy, or a link that leads out of it
  a dir and pattern that match no test file, so a misspelled pattern isn't a survivor
  a DEST that exists or is inside the repo
  a baseline that fails or times out
A mutant's result never exits 2.
"""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
# The launcher's TOOL_PATH, which test_mutant.py checks. It isn't imported, because that would
# run launcher_build.py and the modules it imports from the repo, outside the exit-2 guard below.
TOOL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
TAR = "/usr/bin/tar"  # not the first tar on PATH, which may be GNU's and extract differently
TOOL_ERROR = 2
TAIL = 64 * 1024
PATTERN = "test_*.py"
MODULE_NAME = re.compile(r"[_a-z]\w*\.py$", re.IGNORECASE)  # the names unittest discover loads


class MutantError(Exception):
    """A problem with the spec or the setup, which says nothing about any mutant."""


@dataclass(frozen=True)
class Edit:
    file: str
    old: str
    new: str


@dataclass(frozen=True)
class Mutant:
    name: str
    dir: str
    edits: tuple[Edit, ...]
    pattern: str = PATTERN


def exactly(item: object, keys: tuple[str, ...], where: str,
            optional: tuple[str, ...] = ()) -> dict:
    if not isinstance(item, dict) or not set(keys) <= set(item) <= set(keys + optional):
        more = f" and perhaps {', '.join(optional)}" if optional else ""
        raise MutantError(f"{where} must be an object with {', '.join(keys)}{more} and nothing else")
    return item


def text(item: dict, key: str, where: str, empty: bool = False) -> str:
    value = item[key]
    if not isinstance(value, str) or not (value or empty):
        raise MutantError(f"{where}: {key} must be {'text' if empty else 'non-empty text'}")
    return value


def repo_path(path: str, key: str, where: str) -> str:
    """PATH if it can name something inside the repo: not absolute and with no `..`."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise MutantError(f"{where}: {key} {path!r} isn't a path inside the repo")
    return path


def parse_edit(item: object, where: str) -> Edit:
    item = exactly(item, ("file", "old", "new"), where)
    file = repo_path(text(item, "file", where), "file", where)
    old, new = text(item, "old", where), text(item, "new", where, empty=True)
    if old == new:
        raise MutantError(f"{where}: old and new are the same, so it changes nothing")
    return Edit(file, old, new)


def parse_mutant(item: object, where: str) -> Mutant:
    item = exactly(item, ("name", "dir", "replace"), where, optional=("pattern",))
    name = text(item, "name", where)
    if not name.isprintable():
        raise MutantError(f"{where}: name must be on one line")
    directory = repo_path(text(item, "dir", where), "dir", where)
    pattern = text(item, "pattern", where) if "pattern" in item else PATTERN
    if "/" in pattern:
        raise MutantError(f"{where}: pattern {pattern!r} matches file names, so it has no /")
    edits = item["replace"]
    if not isinstance(edits, list) or not edits:
        raise MutantError(f"{where}: replace must be a list of at least one edit")
    return Mutant(name, directory, tuple(parse_edit(e, f"{where}, edit {n}")
                                         for n, e in enumerate(edits, 1)), pattern)


def load_spec(path: Path) -> list[Mutant]:
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as e:  # json's and the decoder's errors are both ValueErrors
        raise MutantError(f"cannot read {path}: {e}") from e
    if not isinstance(data, list) or not data:
        raise MutantError(f"{path} must hold a list of at least one mutant")
    mutants = [parse_mutant(m, f"{path}: mutant {n}") for n, m in enumerate(data, 1)]
    names = [m.name for m in mutants]
    for name in names:
        if names.count(name) > 1:
            raise MutantError(f"{path}: two mutants are named {name!r}")
    return mutants


def minimal_env() -> dict[str, str]:
    """All a copy's git, tar and tests get: no key, token, `GIT_DIR` or `PYTHONPATH` of ours,
    and the same fixed PATH as the launcher's build tools, not whatever is first on ours."""
    return {"PATH": TOOL_PATH, "HOME": str(Path.home()), "TMPDIR": tempfile.gettempdir(),
            "PYTHONDONTWRITEBYTECODE": "1"}


def archive(repo: Path, rev: str) -> bytes:
    """REV of REPO as a tar, taken once, so every copy is the same commit however long a run is."""
    if rev.startswith("-"):  # git would read it as an option, `--output=FILE` among them
        raise MutantError(f"--rev {rev!r} looks like an option")
    done = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", rev],
                          capture_output=True, env=minimal_env())
    if done.returncode != 0:
        why = done.stderr.decode(errors="replace").strip() or f"exit {done.returncode}"
        raise MutantError(f"git archive {rev} failed: {why}")
    return done.stdout


def extract(tar: bytes, copy: Path) -> Path:
    copy.mkdir()
    done = subprocess.run([TAR, "-x", "-f", "-", "-C", str(copy)], input=tar,
                          capture_output=True, env=minimal_env())
    if done.returncode != 0:
        why = done.stderr.decode(errors="replace").strip() or f"exit {done.returncode}"
        raise MutantError(f"tar into {copy} failed: {why}")
    return copy


def member(copy: Path, rel: str, kind: str) -> Path:
    """COPY/REL, which has to be a file or a dir (KIND) that is inside the copy once links are
    followed. A symlink in the archive could otherwise take an edit to a file outside it."""
    path = (copy / rel).resolve()
    if not path.is_relative_to(copy):
        raise MutantError(f"{rel} leads outside the copy")
    if not (path.is_file() if kind == "file" else path.is_dir()):
        raise MutantError(f"{rel} isn't a {kind} in the copy")
    return path


def apply(copy: Path, mutant: Mutant) -> None:
    """Make COPY the mutant, after checking its dir is there. Edits are bytes in and out, so a
    file keeps its line endings."""
    try:
        member(copy, mutant.dir, "dir")
        for e in mutant.edits:
            path = member(copy, e.file, "file")
            try:
                body = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                raise MutantError(f"{e.file} isn't UTF-8 text") from None
            found = body.count(e.old)
            if found != 1:
                raise MutantError(f"{e.file}: the old text is found {found} times, not once")
            path.write_bytes(body.replace(e.old, e.new).encode("utf-8"))
    except (MutantError, OSError) as err:
        raise MutantError(f"{mutant.name}: {err}") from err


def finds_a_file(start: Path, pattern: str) -> bool:
    """Whether `unittest discover -s START -p PATTERN` would load a file. It looks at a file
    whose name is a module's and matches PATTERN, and goes into the directories that have an
    __init__.py, as discover does, so a pattern discover would use isn't turned away. Python
    3.9 runs no tests and exits 0 when none is found, which would read as a survivor."""
    for entry in start.iterdir():
        if entry.is_file():
            if MODULE_NAME.match(entry.name) and fnmatch.fnmatch(entry.name, pattern):
                return True
        elif (entry / "__init__.py").is_file() and finds_a_file(entry, pattern):
            return True
    return False


def run_tests(python: str, copy: Path, rel: str, pattern: str, timeout: float,
              log: Path) -> Optional[int]:
    """The exit status of test discovery in COPY/REL for the files PATTERN matches, or None if
    it outran TIMEOUT seconds. The last TAIL bytes of its output go to LOG. Whatever the way it
    ends, a timeout and ^C included, the whole process group is killed, so nothing the tests
    started goes on running or holds the pipe open."""
    cmd = [python, "-B", "-m", "unittest", "discover", "-s", str(copy / rel), "-p", pattern]
    proc = subprocess.Popen(cmd, cwd=copy, env=minimal_env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    tail = bytearray()

    def drain() -> None:  # a mutant that prints forever must not fill the disk or the memory
        for chunk in iter(lambda: proc.stdout.read1(1 << 16), b""):
            tail.extend(chunk)
            del tail[:-TAIL]

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    code: Optional[int] = None
    try:
        code = proc.wait(timeout)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # After every run and not only a timeout, so a child the tests left behind can't go on
        # running or keep the pipe open. The group lives as long as one member does, and the
        # leader's pid isn't reused before then.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        if code is None:
            proc.wait()
    reader.join(5)
    if not reader.is_alive():
        proc.stdout.close()
    log.write_bytes(bytes(tail))
    return code


def verdict(code: Optional[int]) -> str:
    return "timeout" if code is None else "survived" if code == 0 else "killed"


def run(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    if not (repo / ".git").exists():  # git would look further up, maybe into another repo
        raise MutantError(f"{repo} isn't a git checkout")
    if os.path.lexists(args.dest):
        raise MutantError(f"{args.dest} exists: give a new directory")
    dest = args.dest.resolve()
    # samefile, so a link or another letter case of the repo's path doesn't get past. With
    # --repo, the checkout holding this tool is as much off limits as the repo.
    for what, root in (("the repo", repo), ("the checkout holding this tool", ROOT)):
        if any(p.exists() and p.samefile(root) for p in (dest, *dest.parents)):
            raise MutantError(f"{dest} is inside {what}: the copies go outside it")
    python = os.path.abspath(args.python)  # not resolved, which would lose a venv's link
    if not (os.path.isfile(python) and os.access(python, os.X_OK)):
        raise MutantError(f"{args.python} isn't an executable file")
    mutants = load_spec(args.spec)
    tar = archive(repo, args.rev)

    dest.mkdir(parents=True)
    suites = list(dict.fromkeys((m.dir, m.pattern) for m in mutants))
    baselines = [(d, p, extract(tar, dest / f"baseline-{n}")) for n, (d, p) in enumerate(suites, 1)]
    copies = []
    for n, m in enumerate(mutants, 1):
        copies.append(extract(tar, dest / f"mutant-{n}"))
        apply(copies[-1], m)

    for d, p, copy in baselines:
        if not finds_a_file(copy / d, p):
            raise MutantError(f"no file in {d} matches the pattern {p!r} for unittest discover, "
                              f"so no test would run")

    for n, (d, p, copy) in enumerate(baselines, 1):
        log = dest / f"baseline-{n}.log"
        code = run_tests(python, copy, d, p, args.timeout, log)
        if code != 0:
            how = f"outran {args.timeout:g} s" if code is None else f"exit {code}"
            what = d if p == PATTERN else f"{d} for {p}"
            raise MutantError(f"the tests in {what} fail without a mutant ({how}), so a kill "
                              f"would mean nothing: see {log}")

    counts = {"killed": 0, "survived": 0, "timeout": 0}
    for n, (m, copy) in enumerate(zip(mutants, copies), 1):
        code = run_tests(python, copy, m.dir, m.pattern, args.timeout, dest / f"mutant-{n}.log")
        result = verdict(code)
        counts[result] += 1
        # unittest exits 1 when tests fail. Another code (a signal, or 5 for no tests) is said.
        how = f" (exit {code})" if result == "killed" and code != 1 else ""
        print(f"{result} {m.name}{how}", flush=True)
    print(f"total {len(mutants)}, killed {counts['killed']}, survived {counts['survived']}, "
          f"timeout {counts['timeout']}", flush=True)
    return 0 if counts["killed"] == len(mutants) else 1


def seconds(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} isn't a number of seconds") from None
    if not (math.isfinite(number) and number > 0):
        raise argparse.ArgumentTypeError(f"{value!r} isn't a number of seconds above 0")
    return number


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mutant.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path, metavar="SPEC", help="a JSON file of mutants")
    ap.add_argument("dest", type=Path, metavar="DEST", help="a new directory outside the repo")
    ap.add_argument("--repo", type=Path, default=ROOT, metavar="DIR",
                    help="the checkout to copy, by default the one holding this tool")
    ap.add_argument("--rev", default="HEAD", help="the commit to copy (default HEAD)")
    ap.add_argument("--python", default=sys.executable, metavar="FILE",
                    help="the interpreter that runs the tests (default the one running this)")
    ap.add_argument("--timeout", type=seconds, default=600, metavar="SECONDS",
                    help="the limit for each run, baselines included (default 600)")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # any of them, or a traceback's exit 1 would read as a survivor
        why = str(e) if isinstance(e, MutantError) else f"{type(e).__name__}: {e}"
        print(f"mutant: {why}", file=sys.stderr)
        return TOOL_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
