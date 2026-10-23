"""Look inside a DMG without changing it: attach it read-only, then detach it again."""
from __future__ import annotations

import contextlib
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

HDIUTIL = "/usr/bin/hdiutil"
# A DMG of 60 MB attaches in a few seconds, so a minute or two means hdiutil is stuck and a CI
# job shouldn't wait for its own timeout.
ATTACH_SECONDS = 120
DETACH_SECONDS = 60
TIMED_OUT = 124  # the exit status timeout(1) uses, for a command that was cut short


class DmgError(Exception):
    pass


def _hdiutil(*args: str, timeout: float) -> subprocess.CompletedProcess:
    """Run hdiutil, killing it after TIMEOUT seconds and giving that exit status TIMED_OUT."""
    try:
        return subprocess.run([HDIUTIL, *args], stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, TIMED_OUT, "",
                                           f"{args[0]} didn't finish in {timeout:g} s")


def _why(done: subprocess.CompletedProcess) -> str:
    return done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}"


def detach(mount: Path) -> None:
    """Detach MOUNT, forcing it if the plain detach fails or hangs, as a volume Spotlight is
    still reading does."""
    done = _hdiutil("detach", str(mount), timeout=DETACH_SECONDS)
    if done.returncode != 0:
        done = _hdiutil("detach", "-force", str(mount), timeout=DETACH_SECONDS)
    if done.returncode != 0:
        raise DmgError(f"hdiutil couldn't detach {mount}: {_why(done)}")


@contextlib.contextmanager
def mounted(dmg: Path) -> Iterator[Path]:
    """Attach DMG read-only at a fresh directory, yield that directory and always detach.
    Raises DmgError when hdiutil won't attach or detach it, or hangs."""
    mount = Path(tempfile.mkdtemp(prefix="check_bundle."))
    try:
        done = _hdiutil("attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(dmg),
                        timeout=ATTACH_SECONDS)
        if done.returncode != 0:
            if done.returncode == TIMED_OUT:  # it may have mounted before it hung
                _hdiutil("detach", "-force", str(mount), timeout=DETACH_SECONDS)
            raise DmgError(f"hdiutil couldn't attach {dmg}: {_why(done)}")
        try:
            yield mount
        finally:
            detach(mount)
    finally:
        with contextlib.suppress(OSError):
            mount.rmdir()
