#!/usr/bin/env python3
"""Assemble Dragoon.app from the built launcher, an engine kit and a source snapshot.

Usage: make_app.py --out DIR --version V --launcher FILE --kit DIR --source DIR

Writes DIR/Dragoon.app in the layout launcher/bundle-manifest.txt allows:
  Contents/Info.plist           launcher/Info.plist with CFBundleShortVersionString and
                                CFBundleVersion set to V, which is one to three numbers
                                joined by dots, such as 1.2.3
  Contents/MacOS/Dragoon        FILE, the launcher `swift build -c release` made, mode 0755.
                                This tool never runs SwiftPM
  Contents/Resources/kit/       --kit, what engine_kit.py wrote or CI's engine-kit artifact
  Contents/Resources/source/    --source, export_source.py's snapshot
  Contents/Resources/licenses/  Dragoon.txt, the snapshot's LICENSE
The kit and the snapshot arrive byte for byte and are only read. Then `codesign --force --sign -`
seals the app ad hoc, with no hardened runtime and no --deep, as a dev build is signed. DIR is
made if it's missing. The app is built under a temporary name in DIR and renamed into place. A
failed run removes the app's temporary directory and the directories it made for DIR, so it
leaves nothing behind. A directory that another run has put something in stays.

It refuses a kit from another gcn-recomp commit or another src/ than the snapshot's, as
launcher_build.py does, since the kit's engine.o and headers wouldn't match the generated C. It refuses a kit that
lacks a file the manifest lists or holds one it doesn't. It refuses a snapshot that lacks its
source-info.json, source-manifest.txt or LICENSE, and one whose files aren't what
source-manifest.txt lists, whether a file is missing, extra or edited. It refuses a DIR that is
the kit or the snapshot or below one, however its name is spelled.

Exits 0 when the app is there and prints its path. Exits 1 when a step failed, such as codesign,
and 2 on a bad argument or an input it can't use, with one line on stderr saying why and
nothing written.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn, Optional

ROOT = Path(__file__).resolve().parents[2]
# The repo's other tools live in tools/, which isn't on the path of a script in launcher/tools/.
sys.path.append(str(ROOT / "tools"))

import bundle_manifest
import bundle_tree
import export_source
import source_info
from launcher_build import kit_problem

CODESIGN = "/usr/bin/codesign"
MANIFEST = ROOT / "launcher" / "bundle-manifest.txt"
TEMPLATE = ROOT / "launcher" / "Info.plist"
APP = "Dragoon.app"
KIT = "Contents/Resources/kit"
LICENSES = "Contents/Resources/licenses"
LICENSE = "LICENSE"  # Dragoon's own, at the top of the snapshot
VERSION = re.compile(r"[0-9]+(\.[0-9]+){0,2}")


class StepFailed(Exception):
    """A step ran and failed (exit 1)."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(f"make_app.py: {message}", file=sys.stderr)
        sys.exit(2)


def named(paths: list[str]) -> str:
    """The first of PATHS, and how many more there are."""
    return paths[0] + (f" and {len(paths) - 1} more" if len(paths) > 1 else "")


def kit_files(manifest: bundle_manifest.BundleManifest) -> list[str]:
    """The files the manifest lists in the kit, relative to the kit."""
    return sorted(p[len(KIT) + 1:] for p in manifest.files | manifest.objects if p.startswith(KIT + "/"))


def kit_listing_problem(kit: Path, manifest: bundle_manifest.BundleManifest) -> Optional[str]:
    """Why the files in KIT aren't the ones the manifest lists, or None when they are."""
    found = bundle_tree.scan(kit)
    missing = [p for p in kit_files(manifest) if p not in found.files]
    if missing:
        return f"the kit {kit} is missing {named(missing)}"
    extra = ([p for p in sorted(found.files) if not manifest.allows_file(f"{KIT}/{p}")]
             + sorted(found.links) + found.empty_dirs + found.others)
    if extra:
        return f"the kit {kit} holds {named(extra)}, which {MANIFEST.name} doesn't allow"
    return None


def snapshot_problem(source: Path) -> Optional[str]:
    """Why SOURCE isn't a snapshot as export_source.py wrote it, or None when it is. Its own
    three files have to be there, and source-manifest.txt has to be the text export_source.py
    writes for the files SOURCE holds, which catches a file that is missing, extra or edited."""
    missing = [p for p in (source_info.NAME, export_source.MANIFEST, LICENSE) if not (source / p).is_file()]
    if missing:
        return f"the snapshot {source} is missing {named(missing)}"
    want = export_source.format_manifest(export_source.manifest(source))
    have = (source / export_source.MANIFEST).read_text(encoding="utf-8")
    if want == have:
        return None
    differing = set(want.splitlines()) ^ set(have.splitlines())
    paths = sorted({line.partition("  ")[2] or line for line in differing} - {""})
    return (f"the snapshot {source} differs from its {export_source.MANIFEST}"
            + (f" at {named(paths)}" if paths else ""))


def is_inside(path: Path, parent: Path) -> bool:
    """Is PATH, or a directory above it, the directory PARENT? samefile sees through a symlink
    and through another spelling of the name on a volume that ignores case, which comparing
    paths wouldn't."""
    while True:
        if path.exists() and os.path.samefile(path, parent):
            return True
        if path.parent == path:
            return False
        path = path.parent


def bad_argument(a: argparse.Namespace, manifest: bundle_manifest.BundleManifest) -> Optional[str]:
    """Why the tool can't run on A, or None. It reads the inputs and writes nothing."""
    if not VERSION.fullmatch(a.version):
        return f"--version {a.version!r} isn't one to three numbers joined by dots, such as 1.2.3"
    if not a.launcher.is_file():
        return f"--launcher {a.launcher} isn't a file"
    for flag, path in (("--kit", a.kit), ("--source", a.source)):
        if not path.is_dir():
            return f"{flag} {path} isn't a directory"
    if a.out.exists() and not a.out.is_dir():
        return f"--out {a.out} isn't a directory"
    for flag, path in (("--kit", a.kit), ("--source", a.source)):
        if is_inside(a.out, path):
            return f"--out {a.out} is inside {flag} {path}, where the copy would contain itself"
    if os.path.lexists(a.out / APP):
        return f"{a.out / APP} already exists"
    problem = kit_listing_problem(a.kit, manifest) or snapshot_problem(a.source)
    if problem:
        return problem
    info = source_info.read(a.source / source_info.NAME)
    return kit_problem(a.kit, info["gcn-recomp"], a.source)


def assemble(app: Path, a: argparse.Namespace, manifest: bundle_manifest.BundleManifest) -> None:
    """The app's files, unsigned, at APP."""
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    launcher = contents / "MacOS" / "Dragoon"
    shutil.copyfile(a.launcher, launcher)
    launcher.chmod(0o755)
    shutil.copytree(a.kit, app / KIT, symlinks=True)
    shutil.copytree(a.source, app / manifest.source, symlinks=True)
    (app / LICENSES).mkdir()
    shutil.copyfile(a.source / LICENSE, app / LICENSES / "Dragoon.txt")
    with TEMPLATE.open("rb") as f:
        plist = plistlib.load(f)
    plist.update(CFBundleShortVersionString=a.version, CFBundleVersion=a.version)
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump(plist, f)


def seal(app: Path) -> None:
    """Sign APP ad hoc. Raises StepFailed when codesign fails."""
    done = subprocess.run([CODESIGN, "--force", "--sign", "-", str(app)], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    if done.returncode != 0:
        raise StepFailed(f"codesign exited {done.returncode}: {' '.join(done.stdout.split())}")


def topmost_missing(path: Path) -> Optional[Path]:
    """The directory nearest the root on the way to PATH that doesn't exist yet, or None when
    PATH exists. Making PATH makes it and everything below it."""
    missing = None
    while not path.exists():
        missing, path = path, path.parent
    return missing


def make(a: argparse.Namespace, manifest: bundle_manifest.BundleManifest) -> Path:
    """Build the app under a temporary name in the output directory and rename it into place.
    A run that fails removes its temporary directory, then each directory it made for the output
    directory that is empty by then. Another run may share the output directory, and rmdir
    leaves one that holds that run's app or its work."""
    made = topmost_missing(a.out)
    work = None
    try:
        a.out.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=".make_app.", dir=a.out))
        assemble(work / APP, a, manifest)
        seal(work / APP)
        os.rename(work / APP, a.out / APP)
        work.rmdir()
    except BaseException:
        if work:
            shutil.rmtree(work, ignore_errors=True)
        path = a.out
        while made and path != made.parent:
            try:
                os.rmdir(path)  # only an empty one, so another run's app stays
            except OSError:
                pass
            path = path.parent
        raise
    return a.out / APP


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = Parser(prog="make_app.py", description=__doc__,
                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="the directory that gets Dragoon.app")
    ap.add_argument("--version", required=True, help="the app's version, such as 1.2.3")
    ap.add_argument("--launcher", type=Path, required=True, help="the built launcher")
    ap.add_argument("--kit", type=Path, required=True, help="the engine kit")
    ap.add_argument("--source", type=Path, required=True, help="the source snapshot")
    a = ap.parse_args(argv)
    for name in ("out", "launcher", "kit", "source"):
        setattr(a, name, Path(os.path.abspath(getattr(a, name))))
    return a


def main(argv: list[str]) -> int:
    a = parse_args(argv)
    try:
        manifest = bundle_manifest.read(MANIFEST)
        problem = bad_argument(a, manifest)
    except (OSError, ValueError) as e:
        problem = str(e)
    if problem:
        print(f"make_app.py: {problem}", file=sys.stderr)
        return 2
    try:
        app = make(a, manifest)
    except (StepFailed, OSError) as e:  # shutil.Error is an OSError
        print(f"make_app.py: {e}", file=sys.stderr)
        return 1
    print(app)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
