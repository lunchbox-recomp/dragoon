#!/usr/bin/env python3
"""Does Dragoon.app, or the DMG around it, hold anything game-derived?

Usage: check_bundle.py PATH --commit SHA [--repo DIR] [--manifest FILE]

PATH is a .app or a .dmg. A DMG is attached read-only (hdiutil attach -readonly -nobrowse
-mountpoint), checked and detached. Run it before anything is signed. The checks are:
  1  paths        outside the source snapshot every file, link and empty directory is on the
                  manifest (launcher/bundle-manifest.txt). Nothing anywhere matches
                  check_no_game_data.is_game_data or is a build's own output (gen/, rels/,
                  inputs/, main.dol, CMakeCache.txt, build.ninja, memcard_*, .shader-warmup,
                  in any letter case)
  2  executables  every file that starts with a Mach-O magic is at a path the manifest lists
  3  content      no file has the GameCube disc magic at offset 0x1C or starts with CISO, and
                  the disc ID appears only inside the source snapshot
  4  source       the snapshot equals export_source.py's output for SHA, file by file by
                  SHA-256. SHA has to be what --repo has checked out
  5  size         the app and the DMG stay inside the manifest's budgets
  6  the DMG      it holds Dragoon.app and an Applications link to /Applications and nothing
                  else, and checks 1 to 5 pass on the app inside it
It prints one "kind: path (detail)" line per finding, with paths relative to the app, and
nothing when the bundle is clean. --repo is the Dragoon checkout and --manifest the manifest,
by default the ones beside this tool.

Exits 0 when the bundle is clean, 1 when it has findings and 2 when it couldn't check: a bad
argument, a manifest it can't read, a checkout that isn't at SHA, or a DMG that won't attach
or detach. A detach that fails after the checks found something still exits 1 with the findings.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import bundle_checks
import bundle_dmg
import bundle_manifest
import export_source

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "launcher" / "bundle-manifest.txt"


def reference_snapshot(repo: Path, commit: str, out: Path) -> dict[str, str]:
    """Export REPO's HEAD into OUT, once HEAD is COMMIT. Returns the source-info fields."""
    want = export_source.git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}")
    head = export_source.git(repo, "rev-parse", "--verify", "HEAD^{commit}")
    if want != head:
        raise ValueError(f"{repo} is at {head}, not at {want}. Check out the commit first")
    return export_source.export(repo, out)


def check(args: argparse.Namespace) -> list[bundle_checks.Finding]:
    path = args.path
    if not path.exists():
        raise ValueError(f"{path} doesn't exist")
    kind = path.suffix.lower()
    if kind not in (".app", ".dmg"):
        raise ValueError(f"{path} isn't a .app or a .dmg")
    if kind == ".app" and not path.is_dir():
        raise ValueError(f"{path} isn't a directory")
    manifest = bundle_manifest.read(args.manifest)
    with tempfile.TemporaryDirectory(prefix="check_bundle.") as tmp:
        reference = Path(tmp) / "reference"
        disc_id = reference_snapshot(args.repo.resolve(), args.commit, reference)["disc_id"]
        if kind == ".app":
            return bundle_checks.check_app(path, manifest, reference, disc_id)
        found: list[bundle_checks.Finding] = []
        try:
            with bundle_dmg.mounted(path) as mount:
                found += bundle_checks.check_dmg(mount, path, manifest)
                app = mount / bundle_checks.APP_NAME
                if app.is_dir() and not app.is_symlink():
                    found += bundle_checks.check_app(app, manifest, reference, disc_id)
        except bundle_dmg.DmgError as e:
            if not found:
                raise
            # The detach failed after the checks ran. The findings still say what's wrong.
            print(f"check_bundle.py: {e}", file=sys.stderr)
        return found


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path, help="a .app or a .dmg")
    ap.add_argument("--commit", required=True, help="the Dragoon commit the bundle was built from")
    ap.add_argument("--repo", type=Path, default=ROOT, help="the Dragoon checkout")
    ap.add_argument("--manifest", type=Path, default=MANIFEST, help="the bundle manifest")
    args = ap.parse_args(argv)
    try:
        found = check(args)
    except (OSError, ValueError, bundle_dmg.DmgError) as e:
        print(f"check_bundle.py: {e}", file=sys.stderr)
        return 2
    for finding in found:
        print(finding)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
