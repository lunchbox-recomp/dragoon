#!/usr/bin/env python3
"""Write a source snapshot: Dragoon's HEAD and the gcn-recomp commit it pins, with no git.

Usage: export_source.py OUT [--repo DIR]

Fills OUT, which must be empty or missing, with Dragoon's HEAD and with gcn-recomp at the
commit HEAD pins in OUT/gcn-recomp, as git archive gives them. Untracked and ignored files,
such as rom/game.iso, build/ and saves/, never reach it. It adds two files:
  source-info.json     the two commits as dragoon and gcn-recomp, plus disc_id and dol_sha1
                       from the gcn_add_game call in CMakeLists.txt
  source-manifest.txt  one "<sha256>  <path>" line per other file, sorted by path
--repo names the Dragoon checkout, by default the one holding this tool. git comes from PATH
and tar is /usr/bin/tar.

Exits 0 when the snapshot is written. Exits 2, having written nothing, when a tracked file
in either repository has uncommitted changes, when gcn-recomp is checked out at another
commit than HEAD pins or not at all, when OUT isn't empty, or when git or tar fails. A failure
while writing leaves OUT as it was, missing or empty.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import source_info

ROOT = Path(__file__).resolve().parents[1]
TAR = "/usr/bin/tar"  # not the first tar on PATH, which may be GNU's and extract differently
MANIFEST = "source-manifest.txt"
ENGINE = "gcn-recomp"
_MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  (.+)")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest(root: Path) -> list[tuple[str, str]]:
    """(path, SHA-256) for every file under ROOT, sorted by path. Paths are relative to ROOT
    and /-separated. A symlink is never followed. It's listed with the SHA-256 of the path
    it points to, as git stores one. A source-manifest.txt at the top is left out."""
    entries = []

    def walk(directory: Path) -> None:
        for entry in os.scandir(directory):
            path = Path(entry.path)
            rel = path.relative_to(root).as_posix()
            if entry.is_symlink():
                entries.append((rel, hashlib.sha256(os.readlink(path).encode()).hexdigest()))
            elif entry.is_dir():
                walk(path)
            elif entry.is_file():
                if rel != MANIFEST:
                    entries.append((rel, sha256_file(path)))
            else:
                raise ValueError(f"{path}: not a file, directory or symlink")

    walk(root)
    return sorted(entries)


def format_manifest(entries: list[tuple[str, str]]) -> str:
    return "".join(f"{sha}  {path}\n" for path, sha in entries)


def parse_manifest(text: str) -> list[tuple[str, str]]:
    """The (path, SHA-256) entries of a source-manifest.txt, in its order."""
    entries = []
    for n, line in enumerate(text.splitlines(), 1):
        m = _MANIFEST_LINE.fullmatch(line)
        if not m:
            raise ValueError(f"{MANIFEST} line {n} isn't '<sha256>  <path>': {line!r}")
        entries.append((m.group(2), m.group(1)))
    return entries


def game_ids(cmake_text: str) -> tuple[str, str]:
    """The DISC_ID and DOL_SHA1 of the one gcn_add_game call in a CMakeLists.txt."""
    text = re.sub(r"#[^\n]*", "", cmake_text)
    calls = re.findall(r"\bgcn_add_game\s*\(([^)]*)\)", text)
    if len(calls) != 1:
        raise ValueError(f"CMakeLists.txt has {len(calls)} gcn_add_game calls, not one")
    args = calls[0].split()
    found = []
    for key, field in (("DISC_ID", "disc_id"), ("DOL_SHA1", "dol_sha1")):
        value = args[args.index(key) + 1] if key in args[:-1] else ""
        if not source_info.FIELDS[field].fullmatch(value):
            raise ValueError(f"CMakeLists.txt's gcn_add_game has no well-formed {key}")
        found.append(value)
    return found[0], found[1]


def git(repo: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              check=True)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"git {' '.join(args)} in {repo} failed: {e.stderr.strip()}") from None
    return done.stdout.rstrip("\n")


def changes(repo: Path, *extra: str) -> None:
    """Refuse REPO when a tracked file has uncommitted changes."""
    status = git(repo, "status", "--porcelain", "--untracked-files=no", *extra)
    if status:
        raise ValueError(f"{repo} has uncommitted changes:\n{status}")


def archive(repo: Path, commit: str, dest: Path) -> None:
    """Extract COMMIT of REPO into DEST. Raises ValueError with git's or tar's own message."""
    try:
        tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit],
                             capture_output=True, check=True).stdout
        dest.mkdir(exist_ok=True)
        subprocess.run([TAR, "-x", "-f", "-", "-C", str(dest)], input=tar, capture_output=True,
                       check=True)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"{' '.join(e.cmd)} failed: "
                         f"{e.stderr.decode(errors='replace').strip()}") from None


def clear(out: Path, remove: bool) -> None:
    """Empty OUT, a snapshot that didn't get finished, and remove it too when REMOVE."""
    if remove:
        shutil.rmtree(out, ignore_errors=True)
        return
    for entry in out.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink()


def export(repo: Path, out: Path) -> dict[str, str]:
    """Check REPO, then write its snapshot to OUT. Returns the source-info fields."""
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"{out} isn't empty")
    engine = repo / ENGINE
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}")
    pin = git(repo, "rev-parse", "--verify", f"HEAD:{ENGINE}")
    changes(repo, "--ignore-submodules=all")
    if not (engine / ".git").exists():
        raise ValueError(f"{engine} isn't checked out, and HEAD pins {pin}")
    checked_out = git(engine, "rev-parse", "--verify", "HEAD")
    if checked_out != pin:
        raise ValueError(f"{engine} is at {checked_out}, but HEAD pins {pin}")
    changes(engine)
    disc_id, dol_sha1 = game_ids(git(repo, "show", "HEAD:CMakeLists.txt"))
    info = {"dragoon": head, "gcn-recomp": pin, "disc_id": disc_id, "dol_sha1": dol_sha1}

    made = not out.exists()
    out.mkdir(parents=True, exist_ok=True)
    try:
        archive(repo, head, out)
        archive(engine, pin, out / ENGINE)
        source_info.write(out / source_info.NAME, info)
        (out / MANIFEST).write_text(format_manifest(manifest(out)))
    except BaseException:  # a full disk, say, or ^C, which mustn't leave OUT half written
        clear(out, remove=made)
        raise
    return info


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, help="an empty or missing directory")
    ap.add_argument("--repo", type=Path, default=ROOT, help="the Dragoon checkout")
    args = ap.parse_args(argv)
    try:
        info = export(args.repo.resolve(), args.out)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"export_source.py: {e}", file=sys.stderr)
        return 2
    count = len(manifest(args.out))
    print(f"{args.out}: Dragoon {info['dragoon']} and gcn-recomp {info['gcn-recomp']}, "
          f"{count} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
