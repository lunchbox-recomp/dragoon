"""The commands that sign, package and notarize Dragoon.app, as argument lists in order.

Nothing here runs anything. sign_and_package.py runs them, or prints them under --dry-run.
The order is Apple's: sign inside out with the hardened runtime and a secure timestamp and
never with --deep, verify the signed app, make the DMG, sign it, notarize it as the outermost
container, staple it and verify the ticket and the assessments. An ad hoc run (identity -)
leaves out the runtime and the timestamp, as sign_item says. The launcher claims no
entitlements, so no command passes any.
"""
from __future__ import annotations

import os
import plistlib
from pathlib import Path
from typing import NamedTuple

CODESIGN = "/usr/bin/codesign"
DITTO = "/usr/bin/ditto"
HDIUTIL = "/usr/bin/hdiutil"
LN = "/bin/ln"
SPCTL = "/usr/sbin/spctl"
XCRUN = "/usr/bin/xcrun"

AD_HOC = "-"  # codesign's identity for a signature with no certificate
APP = "Dragoon.app"  # in the DMG, whatever the input is called
DMG = "Dragoon.dmg"
STAGING = "dmg-root"  # what hdiutil packs: the app and an Applications link
VOLUME = "Dragoon"
SPARKLE = "Contents/Frameworks/Sparkle.framework"
# How long notarytool may wait unless --notary-timeout says otherwise. Apple finishes 98 percent
# of submissions within 15 minutes.
NOTARY_MINUTES = 30
# The most --notary-timeout takes. subprocess.run raises OverflowError for a much longer wait.
NOTARY_MAX_MINUTES = 24 * 60


class Notary(NamedTuple):
    key: Path
    key_id: str
    issuer: str

    def flags(self) -> list[str]:
        return ["--key", str(self.key), "--key-id", self.key_id, "--issuer", self.issuer]


def bundle_identifier(app: Path) -> str:
    """The app's CFBundleIdentifier. Raises ValueError when it can't be read."""
    plist = app / "Contents" / "Info.plist"
    try:
        with plist.open("rb") as f:
            identifier = plistlib.load(f).get("CFBundleIdentifier")
    except (OSError, ValueError) as e:
        raise ValueError(f"can't read {plist}: {e}") from None
    if not isinstance(identifier, str) or not identifier:
        raise ValueError(f"{plist} has no CFBundleIdentifier")
    return identifier


def check_app(app: Path) -> None:
    """Raise ValueError unless APP is an app this plan can sign: one with a bundle ID and none of
    Sparkle's XPC services, which would hold code this plan never signs."""
    if not app.is_dir():
        raise ValueError(f"{app} isn't a directory")
    bundle_identifier(app)
    framework = app / SPARKLE
    for services in [*sorted(framework.glob("Versions/*/XPCServices")), framework / "XPCServices"]:
        if os.path.lexists(services):  # a link counts, even one with nothing left to point at
            raise ValueError(f"{app} still has Sparkle's XPC services at "
                             f"{services.relative_to(app)}. A launcher that isn't sandboxed "
                             "doesn't need them, so take them out before signing")


def timestamp_flag(identity: str) -> str:
    """A Developer ID signature gets Apple's secure timestamp, which notarization requires.
    An ad hoc one (identity -) asks for none: the timestamp server wants an Apple identity and
    the internet, and codesign fails the signing when it can't have them."""
    return "--timestamp=none" if identity == AD_HOC else "--timestamp"


def sign_item(identity: str, path: Path) -> list[str]:
    """Sign a piece of the app. -f replaces the signature a vendor or lipo left.

    A Developer ID signature has the hardened runtime, which notarization requires. Library
    validation comes with it, and it lets the launcher load Sparkle because both carry our team
    ID. An ad hoc signature has no team ID, so the same flag would stop an ad hoc launcher
    loading an ad hoc Sparkle, and dev builds leave the runtime off."""
    cmd = [CODESIGN, "-f", "-s", identity]
    cmd += [] if identity == AD_HOC else ["-o", "runtime"]
    cmd.append(timestamp_flag(identity))
    return cmd + [str(path)]


def sign_app(source: Path, app: Path, identity: str) -> list[list[str]]:
    """Sign the copy at APP inside out. Sparkle's pieces go first, in Sparkle's order without its
    XPC services, which a launcher that isn't sandboxed doesn't ship, then the app. SOURCE is
    the input, where Sparkle is looked for."""
    steps: list[list[str]] = []
    if (source / SPARKLE).is_dir():
        framework = app / SPARKLE
        current = (source / SPARKLE / "Versions" / "Current").resolve().name  # B in Sparkle 2
        version = framework / "Versions" / current
        steps += [sign_item(identity, version / "Autoupdate"),
                  sign_item(identity, version / "Updater.app"), sign_item(identity, framework)]
    return steps + [sign_item(identity, app)]


def copy_app(source: Path, app: Path) -> list[str]:
    return [DITTO, str(source), str(app)]


def applications_link(staging: Path) -> list[str]:
    return [LN, "-s", "/Applications", str(staging / "Applications")]


def make_dmg(staging: Path, dmg: Path) -> list[str]:
    """-ov lets a second try replace what a failed first one left behind."""
    return [HDIUTIL, "create", "-format", "UDZO", "-volname", VOLUME, "-ov", "-srcfolder",
            str(staging), str(dmg)]


def sign_dmg(identity: str, dmg: Path, identifier: str) -> list[str]:
    return [CODESIGN, "-s", identity, timestamp_flag(identity), "-i", f"{identifier}.dmg", str(dmg)]


def notarize(dmg: Path, notary: Notary) -> list[str]:
    return [XCRUN, "notarytool", "submit", str(dmg), *notary.flags(), "--wait", "--output-format",
            "json"]


def notary_log(submission: str, notary: Notary) -> list[str]:
    return [XCRUN, "notarytool", "log", submission, *notary.flags()]


def notary_history(notary: Notary) -> list[str]:
    return [XCRUN, "notarytool", "history", *notary.flags()]


def staple(dmg: Path) -> list[str]:
    return [XCRUN, "stapler", "staple", str(dmg)]


def verify_app(app: Path) -> list[str]:
    """The signature on the signed app. It runs before the DMG is made, so a broken signature
    costs no notarization round trip."""
    return [CODESIGN, "--verify", "--strict", "--deep", str(app)]


def verify_notarized(app: Path, dmg: Path) -> list[list[str]]:
    """For a notarized DMG its ticket and the assessments Apple gives for an app and for a
    disk image."""
    return [[XCRUN, "stapler", "validate", str(dmg)],
            [SPCTL, "--assess", "--type", "execute", "-vv", str(app)],
            [SPCTL, "--assess", "--type", "open", "--context", "context:primary-signature",
             "-vv", str(dmg)]]
