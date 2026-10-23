#!/usr/bin/env python3
"""Sign Dragoon.app, put it in a DMG, sign that and notarize it.

Usage: sign_and_package.py --app APP --identity NAME --out DIR
           [--notary-key FILE --notary-key-id ID --notary-issuer ID] [--dry-run]

APP is left as it is. The tool signs a copy in DIR, which must be empty or missing:
  1  ditto copies APP to DIR/dmg-root/Dragoon.app, beside an Applications link to /Applications
  2  codesign -f -s NAME -o runtime --timestamp, inside out and never with --deep. Contents/
     MacOS/cmake and ninja go first with -i identifiers made from the app's bundle ID, then
     Sparkle's Autoupdate, Updater.app and framework if the app has them, then the app. The
     launcher claims no entitlements
  3  hdiutil create -format UDZO makes DIR/Dragoon.dmg from dmg-root, and codesign --timestamp
     -i signs it
  4  with the Team API key, notarytool submit --wait, then stapler staple on the DMG
  5  codesign --verify --strict --deep on the app. A notarized DMG also gets stapler validate
     and the spctl assessments for an app and for a disk image
--identity - signs ad hoc. Without the three --notary-* options the tool stops after step 3 and
step 5's signature check, and says the DMG isn't notarized. The key file is only named to
notarytool, never read or printed. --dry-run prints every command and runs none.

Every command is printed with a "+ " as it runs, and the DMG's path is the last line of a
finished run. A rejected notarization prints the submission ID and the notarytool log command
that shows why.

Exits 0 when the DMG is made, 1 when a command failed or Apple rejected the notarization and 2
on a bad argument.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

import sign_plan
from sign_plan import Notary


class StepFailed(Exception):
    pass


class Runner:
    """Runs commands, printing each first. Under dry_run it only prints."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run

    def run(self, cmd: list[str], capture: bool = False) -> Optional[subprocess.CompletedProcess]:
        """Run CMD, keeping its stdout when CAPTURE. Returns None under dry_run."""
        print("+ " + shlex.join(cmd), flush=True)
        if self.dry_run:
            return None
        return subprocess.run(cmd, stdin=subprocess.DEVNULL, text=True,
                              stdout=subprocess.PIPE if capture else None)

    def step(self, cmd: list[str]) -> None:
        done = self.run(cmd)
        if done is not None and done.returncode != 0:
            raise StepFailed(f"{shlex.join(cmd)} exited {done.returncode}")


def parse_notary(text: str) -> tuple[str, str]:
    """The submission ID and status in notarytool's JSON, or two empty strings."""
    start = text.find("{")
    if start < 0:
        return "", ""
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("id", "")), str(data.get("status", ""))


def submit(runner: Runner, dmg: Path, notary: Notary) -> None:
    """Notarize DMG and wait. Raises StepFailed unless Apple accepts it."""
    done = runner.run(sign_plan.notarize(dmg, notary), capture=True)
    if done is None:
        return
    print(done.stdout, end="", flush=True)
    submission, status = parse_notary(done.stdout)
    if done.returncode == 0 and status == "Accepted":
        return
    if not submission:
        raise StepFailed(f"notarytool exited {done.returncode} and printed no submission ID")
    log = shlex.join(sign_plan.notary_log(submission, notary))
    raise StepFailed(f"notarization failed with status {status or 'unknown'} (submission ID "
                     f"{submission}). To see why, run {log}")


def package(a: argparse.Namespace, runner: Runner, notary: Optional[Notary]) -> Path:
    """Every step in order. Returns the DMG's path."""
    staging = a.out / sign_plan.STAGING
    app, dmg = staging / sign_plan.APP, a.out / sign_plan.DMG
    identifier = sign_plan.bundle_identifier(a.app)
    if not a.dry_run:
        staging.mkdir(parents=True)
    runner.step(sign_plan.copy_app(a.app, app))
    runner.step(sign_plan.applications_link(staging))
    for cmd in sign_plan.sign_app(a.app, app, a.identity):
        runner.step(cmd)
    runner.step(sign_plan.make_dmg(staging, dmg))
    runner.step(sign_plan.sign_dmg(a.identity, dmg, identifier))
    if notary:
        submit(runner, dmg, notary)
        runner.step(sign_plan.staple(dmg))
    for cmd in sign_plan.verify(app, dmg, notary is not None):
        runner.step(cmd)
    return dmg


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", type=Path, required=True, help="the built Dragoon.app")
    ap.add_argument("--identity", required=True,
                    help="a signing identity's name or SHA-1, or - for ad hoc")
    ap.add_argument("--out", type=Path, required=True, help="an empty or missing directory")
    ap.add_argument("--notary-key", type=Path, help="the Team API key (.p8)")
    ap.add_argument("--notary-key-id")
    ap.add_argument("--notary-issuer")
    ap.add_argument("--dry-run", action="store_true", help="print every command and run none")
    a = ap.parse_args(argv)
    a.app, a.out = Path(os.path.abspath(a.app)), Path(os.path.abspath(a.out))
    return a


def bad_argument(a: argparse.Namespace) -> Optional[str]:
    given = [a.notary_key, a.notary_key_id, a.notary_issuer]
    if any(given) and not all(given):
        return ("--notary-key, --notary-key-id and --notary-issuer go together. "
                "Give all three or none")
    try:
        sign_plan.check_app(a.app)
    except ValueError as e:
        return str(e)
    if a.out.exists() and (not a.out.is_dir() or any(a.out.iterdir())):
        return f"{a.out} isn't empty"
    if a.notary_key and not a.dry_run and not a.notary_key.is_file():
        return f"--notary-key {a.notary_key} isn't a file"
    return None


def main(argv: list[str]) -> int:
    a = parse_args(argv)
    problem = bad_argument(a)
    if problem:
        print(f"sign_and_package.py: {problem}", file=sys.stderr)
        return 2
    notary = Notary(a.notary_key, a.notary_key_id, a.notary_issuer) if a.notary_key else None
    if not notary:
        print("sign_and_package.py: no notary key, so the DMG isn't notarized", file=sys.stderr)
    try:
        dmg = package(a, Runner(a.dry_run), notary)
    except StepFailed as e:
        print(f"sign_and_package.py: {e}", file=sys.stderr)
        return 1
    if not a.dry_run:
        print(dmg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
