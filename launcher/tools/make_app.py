#!/usr/bin/env python3
"""Assemble Dragoon.app from the built launcher, the fetched pieces and a source snapshot.

Usage: make_app.py --out DIR --version VERSION [--launcher FILE] [--third-party DIR]
           [--pins FILE] [--repo DIR]

Writes DIR/Dragoon.app, which must not exist yet. The inputs are:
  --launcher     the release binary from `swift build -c release --package-path launcher`,
                 by default SwiftPM's launcher/.build/release/Dragoon. This tool builds nothing
  --third-party  what fetch_third_party.py --dest wrote, by default launcher/.third_party
  --pins         the pins that tool read, by default launcher/third_party.txt, which name the
                 versions to look for
  --repo         the Dragoon checkout export_source.py snapshots, by default this one. Its
                 tracked files must be committed, and so must gcn-recomp's
and the layout, which is the launcher plan's:
  Contents/Info.plist                launcher/Info.plist with --version as its version
  Contents/MacOS/Dragoon             the launcher
  Contents/MacOS/cmake, ninja        thinned to arm64 with lipo, or copied if they already are
  Contents/Resources/cmake/share/    CMake's modules, from its CMake.app
  Contents/Resources/cmake/bin/cmake a symlink to ../../../MacOS/cmake, since CMake finds its
                                     modules at ../share from where it was started
  Contents/Resources/third_party/    SDL's tarball, checked against the pin in the snapshot's
                                     gcn-recomp/CMakeLists.txt
  Contents/Resources/source/         the snapshot from export_source.py
  Contents/Resources/licenses/       CMake/ (its license and the notices of the libraries built
                                     into it), Ninja.txt, SDL.txt, Dragoon.txt, gcn-recomp.txt.
                                     Ninja's zip has no license, so Ninja.txt is
                                     launcher/ninja-COPYING.txt, the COPYING of its v1.13.2 tag
Sparkle (Contents/Frameworks) is not added here yet. The app is signed ad hoc with no hardened
runtime, by the commands sign_and_package.py uses for a release, and verified.

Exits 0 when the app is made. Exits 1, having removed what it wrote, when a step failed, and 2,
having written nothing, when an input is missing or an argument is wrong.
"""
from __future__ import annotations

import argparse
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import export_source  # noqa: E402
import fetch_third_party  # noqa: E402
import sdl_source  # noqa: E402
import sign_plan  # noqa: E402

LIPO = "/usr/bin/lipo"
APP = sign_plan.APP
ARCH = "arm64"
INFO_PLIST = ROOT / "launcher" / "Info.plist"
LAUNCHER = ROOT / "launcher" / ".build" / "release" / "Dragoon"
THIRD_PARTY = ROOT / "launcher" / ".third_party"
NINJA_LICENSE = ROOT / "launcher" / "ninja-COPYING.txt"
CMAKE_LINK = "../../../MacOS/cmake"
CMAKE_LICENSE = "LICENSE.rst"
_VERSION = re.compile(r"[0-9][0-9A-Za-z.+-]*")


class Missing(Exception):
    """An input that isn't there or isn't usable."""


class Pieces(NamedTuple):
    cmake: Path
    modules: Path
    cmake_notices: Path
    ninja: Path


def only(matches: list[Path], what: str, where: Path) -> Path:
    """The one path of MATCHES. Raises Missing, naming WHAT and WHERE, for none or several."""
    if len(matches) != 1:
        raise Missing(f"{where} has {len(matches)} of {what}, not one")
    return matches[0]


def find_pieces(third_party: Path, pins: Path) -> Pieces:
    """Where fetch_third_party.py put CMake's and Ninja's files, for the versions PINS names."""
    versions = {i.name: i for i in fetch_third_party.parse_pins(pins.read_text())}
    for name in ("cmake", "ninja"):
        if name not in versions:
            raise Missing(f"{pins} pins no {name}")
    tree = third_party / versions["cmake"].folder
    contents = only(sorted(tree.glob("*/CMake.app/Contents")), "CMake.app/Contents", tree)
    pieces = Pieces(
        cmake=contents / "bin" / "cmake",
        modules=only(sorted((contents / "share").glob("cmake-*")), "share/cmake-* directories",
                     contents),
        cmake_notices=contents / "doc" / "cmake",
        ninja=third_party / versions["ninja"].folder / "ninja")
    for needed in (pieces.cmake, pieces.ninja, pieces.cmake_notices / CMAKE_LICENSE):
        if not needed.is_file():
            raise Missing(f"{needed} isn't there. fetch_third_party.py fetches it")
    return pieces


def copy_cmake_notices(notices: Path, dest: Path) -> None:
    """Copy CMake's license and the notices of the libraries built into it from its doc/cmake
    into DEST. They are LICENSE.rst, CONTRIBUTORS.rst, which it links, and one cm* directory
    for each library. The rest of doc/cmake is the manual, which stays out."""
    dest.mkdir()
    for entry in sorted(notices.iterdir()):
        if entry.name in (CMAKE_LICENSE, "CONTRIBUTORS.rst"):
            shutil.copy2(entry, dest / entry.name)
        elif entry.is_dir() and entry.name.startswith("cm"):
            shutil.copytree(entry, dest / entry.name, symlinks=True)


def archs(binary: Path) -> list[str]:
    done = subprocess.run([LIPO, "-archs", str(binary)], capture_output=True, text=True)
    if done.returncode:
        raise ValueError(f"lipo -archs {binary} failed: {done.stderr.strip()}")
    return done.stdout.split()


def thin(source: Path, dest: Path) -> None:
    """Put SOURCE's arm64 slice at DEST, as a copy when that is all SOURCE has."""
    have = archs(source)
    if ARCH not in have:
        raise ValueError(f"{source} has no {ARCH} slice, only {' '.join(have) or 'none'}")
    if have == [ARCH]:
        shutil.copy2(source, dest)
    else:
        done = subprocess.run([LIPO, "-thin", ARCH, str(source), "-output", str(dest)],
                              capture_output=True, text=True)
        if done.returncode:
            raise ValueError(f"lipo -thin {ARCH} {source} failed: {done.stderr.strip()}")
    dest.chmod(0o755)


def write_plist(dest: Path, version: str) -> None:
    with INFO_PLIST.open("rb") as f:
        info = plistlib.load(f)
    info["CFBundleShortVersionString"] = info["CFBundleVersion"] = version
    with dest.open("wb") as f:
        plistlib.dump(info, f)


def sdl_license(tarball: Path, top: str) -> bytes:
    """LICENSE.txt in SDL's release tarball."""
    with tarfile.open(tarball, "r:gz") as tar:
        try:
            member = tar.extractfile(f"{top}/LICENSE.txt")
        except KeyError:
            member = None
        if member is None:
            raise ValueError(f"{tarball} has no {top}/LICENSE.txt")
        return member.read()


def copy_sdl(source: Path, third_party: Path, dest: Path) -> bytes:
    """Copy SDL's tarball into DEST after checking it against the pin in the snapshot SOURCE,
    which is the one the build will check it against. Returns its license."""
    text = (source / "gcn-recomp" / "CMakeLists.txt").read_text()
    pin, archive = sdl_source.pin(text), fetch_third_party.sdl_item(text).archive
    tarball = third_party / archive
    if not tarball.is_file():
        raise Missing(f"{tarball} isn't there. fetch_third_party.py fetches it")
    found = export_source.sha256_file(tarball)
    if found != pin.sha256:
        raise ValueError(f"{tarball} has SHA-256 {found}, but gcn-recomp pins {pin.sha256}")
    dest.mkdir(parents=True)
    shutil.copy2(tarball, dest / archive)
    return sdl_license(tarball, pin.top)


def assemble(a: argparse.Namespace, pieces: Pieces) -> None:
    app = a.out / APP
    contents = app / "Contents"
    macos, resources = contents / "MacOS", contents / "Resources"
    macos.mkdir(parents=True)
    write_plist(contents / "Info.plist", a.version)
    shutil.copy2(a.launcher, macos / "Dragoon")
    (macos / "Dragoon").chmod(0o755)
    thin(pieces.cmake, macos / "cmake")
    thin(pieces.ninja, macos / "ninja")

    cmake = resources / "cmake"
    shutil.copytree(pieces.modules, cmake / "share" / pieces.modules.name, symlinks=True)
    (cmake / "bin").mkdir()
    (cmake / "bin" / "cmake").symlink_to(CMAKE_LINK)

    source = resources / "source"
    export_source.export(a.repo, source)
    licenses = resources / "licenses"
    licenses.mkdir()
    (licenses / "SDL.txt").write_bytes(copy_sdl(source, a.third_party, resources / "third_party"))
    copy_cmake_notices(pieces.cmake_notices, licenses / "CMake")
    shutil.copy2(NINJA_LICENSE, licenses / "Ninja.txt")
    shutil.copy2(source / "LICENSE", licenses / "Dragoon.txt")
    shutil.copy2(source / "gcn-recomp" / "LICENSE", licenses / "gcn-recomp.txt")

    for cmd in sign_plan.sign_app(app, app, sign_plan.AD_HOC) + [sign_plan.verify_app(app)]:
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode:
            raise ValueError(f"{' '.join(cmd)} failed: {done.stderr.strip() or done.returncode}")


def bad_argument(a: argparse.Namespace) -> str:
    """Why the arguments can't make an app, or an empty string."""
    if not _VERSION.fullmatch(a.version):
        return f"--version {a.version!r} isn't a number followed by letters, digits and . + -"
    if not a.launcher.is_file():
        return (f"{a.launcher} isn't there. Build it first with swift build -c release "
                "--package-path launcher, or point --launcher at it")
    if a.out.exists() and (not a.out.is_dir() or any(a.out.iterdir())):
        return f"{a.out} isn't empty"
    return ""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="an empty or missing directory")
    ap.add_argument("--version", required=True, help="the app's version, such as 0.1.0")
    ap.add_argument("--launcher", type=Path, default=LAUNCHER, help="default %(default)s")
    ap.add_argument("--third-party", type=Path, default=THIRD_PARTY, help="default %(default)s")
    ap.add_argument("--pins", type=Path, default=fetch_third_party.PINS, help="default %(default)s")
    ap.add_argument("--repo", type=Path, default=ROOT, help="the Dragoon checkout, default %(default)s")
    a = ap.parse_args(argv)
    a.out, a.launcher = a.out.resolve(), a.launcher.resolve()
    a.third_party, a.repo = a.third_party.resolve(), a.repo.resolve()
    problem = bad_argument(a)
    if not problem:
        try:
            pieces = find_pieces(a.third_party, a.pins)
        except (OSError, ValueError, Missing) as e:
            problem = str(e)
    if problem:
        print(f"make_app.py: {problem}", file=sys.stderr)
        return 2
    made = not a.out.exists()
    try:
        assemble(a, pieces)
    except Missing as e:
        problem, code = str(e), 2
    except (OSError, ValueError) as e:
        problem, code = str(e), 1
    else:
        print(a.out / APP)
        return 0
    shutil.rmtree(a.out if made else a.out / APP, ignore_errors=True)
    print(f"make_app.py: {problem}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
