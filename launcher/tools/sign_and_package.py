#!/usr/bin/env python3
"""Sign Dragoon.app, put it in a DMG, sign that and notarize it.

Usage: sign_and_package.py --app APP --identity NAME --out DIR
           [--notary-key FILE --notary-key-id ID --notary-issuer ID] [--notary-timeout MINUTES]
           [--dry-run]

APP is left as it is. The tool signs a copy in DIR, which must be empty or missing:
  1  ditto copies APP to DIR/dmg-root/Dragoon.app, beside an Applications link to /Applications
  2  codesign -f -s NAME -o runtime --timestamp, inside out and never with --deep. Contents/
     MacOS/cmake and ninja go first with -i identifiers made from the app's bundle ID, then
     Sparkle's Autoupdate, Updater.app and framework if the app has them, then the app. The
     launcher claims no entitlements. An app that still has Sparkle's XPC services is refused,
     since nothing here would sign them
  3  codesign --verify --strict --deep on the signed app, before the DMG is made, so a broken
     signature costs no notarization round trip
  4  hdiutil create -format UDZO makes DIR/Dragoon.dmg from dmg-root, tried up to three times
     since it sometimes fails with Resource busy, and codesign -i signs it, with --timestamp
     or, ad hoc, --timestamp=none
  5  with the Team API key, notarytool submit --wait, which is cut off after --notary-timeout
     minutes (30 unless given), then stapler staple on the DMG
  6  a notarized DMG gets stapler validate and the spctl assessments for an app and for a
     disk image
--identity - signs ad hoc, with --timestamp=none and without -o runtime. Apple's timestamp
server wants an Apple identity and the internet, and the runtime's library validation would
stop an ad hoc launcher loading an ad hoc Sparkle, since neither has a team ID. A Developer ID
run passes -o runtime and --timestamp, which notarization requires, and its pieces share a
team ID. Without the three --notary-* options the tool stops after step 4 and says the DMG
isn't notarized. Apple rejects an ad hoc signature, so --identity - with a notary option is
refused. The key file is only named to notarytool, never read or printed. --dry-run
prints every command and runs none. DIR can't be inside APP, where ditto would copy the app
into itself.

Every command is printed with a "+ " as it runs, and the DMG's path is the last line of a
finished run. A rejected notarization prints the submission ID and the notarytool log command
that shows why. One that outlasts the cut-off prints the notarytool history command that finds
the submission. A re-run needs an empty DIR and uploads again, so give a slow submission a longer
--notary-timeout instead.

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
import time
from pathlib import Path
from typing import Optional

import sign_plan
from sign_plan import Notary

DMG_TRIES = 3  # hdiutil create now and then fails with "Resource busy" and works a moment later
RETRY_PAUSE_SECONDS = 5


class StepFailed(Exception):
    pass


class Runner:
    """Runs commands, printing each first. Under dry_run it only prints."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run

    def run(self, cmd: list[str], capture: bool = False, timeout: Optional[float] = None
            ) -> Optional[subprocess.CompletedProcess]:
        """Run CMD, keeping its stdout when CAPTURE and killing it after TIMEOUT seconds, which
        raises subprocess.TimeoutExpired. Returns None under dry_run."""
        print("+ " + shlex.join(cmd), flush=True)
        if self.dry_run:
            return None
        return subprocess.run(cmd, stdin=subprocess.DEVNULL, text=True, timeout=timeout,
                              stdout=subprocess.PIPE if capture else None)

    def step(self, cmd: list[str], tries: int = 1) -> None:
        """Run CMD, up to TRIES times while it fails. Raises StepFailed after the last."""
        for attempt in range(1, tries + 1):
            done = self.run(cmd)
            if done is None or done.returncode == 0:
                return
            if attempt == tries:
                raise StepFailed(f"{shlex.join(cmd)} exited {done.returncode}")
            print(f"sign_and_package.py: {Path(cmd[0]).name} exited {done.returncode}, trying "
                  f"again in {RETRY_PAUSE_SECONDS} s", file=sys.stderr, flush=True)
            time.sleep(RETRY_PAUSE_SECONDS)


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


def submit(runner: Runner, dmg: Path, notary: Notary, minutes: float) -> None:
    """Notarize DMG and wait, for MINUTES at most. Raises StepFailed unless Apple accepts it."""
    try:
        done = runner.run(sign_plan.notarize(dmg, notary), capture=True, timeout=minutes * 60)
    except subprocess.TimeoutExpired:
        history = shlex.join(sign_plan.notary_history(notary))
        raise StepFailed(f"notarytool didn't finish in {minutes:g} min. Apple may still be "
                         f"working on it, so run {history} to find the submission") from None
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
    runner.step(sign_plan.verify_app(app))
    runner.step(sign_plan.make_dmg(staging, dmg), tries=DMG_TRIES)
    runner.step(sign_plan.sign_dmg(a.identity, dmg, identifier))
    if notary:
        submit(runner, dmg, notary, a.notary_timeout)
        runner.step(sign_plan.staple(dmg))
        for cmd in sign_plan.verify_notarized(app, dmg):
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
    ap.add_argument("--notary-timeout", type=float, default=sign_plan.NOTARY_MINUTES,
                    metavar="MINUTES", help="how long to wait for Apple (default %(default)g)")
    ap.add_argument("--dry-run", action="store_true", help="print every command and run none")
    a = ap.parse_args(argv)
    a.app, a.out = Path(os.path.abspath(a.app)), Path(os.path.abspath(a.out))
    return a


def bad_argument(a: argparse.Namespace) -> Optional[str]:
    given = [a.notary_key, a.notary_key_id, a.notary_issuer]
    if any(given) and not all(given):
        return ("--notary-key, --notary-key-id and --notary-issuer go together. "
                "Give all three or none")
    if any(given) and a.identity == sign_plan.AD_HOC:
        return ("--identity - signs ad hoc, which Apple rejects, so it can't go with the "
                "--notary-* options. Give a Developer ID identity or no notary key")
    if not 0 < a.notary_timeout < float("inf"):
        return f"--notary-timeout {a.notary_timeout:g} isn't a number of minutes above 0"
    try:
        sign_plan.check_app(a.app)
    except ValueError as e:
        return str(e)
    if a.out.resolve() == a.app.resolve() or a.app.resolve() in a.out.resolve().parents:
        return f"--out {a.out} is inside --app {a.app}, where ditto would copy the app into itself"
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
