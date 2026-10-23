"""Look inside a DMG without changing it: attach it read-only, then detach it again."""
from __future__ import annotations

import contextlib
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

HDIUTIL = "/usr/bin/hdiutil"


class DmgError(Exception):
    pass


def _hdiutil(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([HDIUTIL, *args], stdin=subprocess.DEVNULL, capture_output=True, text=True)


def _why(done: subprocess.CompletedProcess) -> str:
    return done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}"


def detach(mount: Path) -> None:
    """Detach MOUNT, forcing it if the plain detach fails, as a volume Spotlight is still
    reading does."""
    done = _hdiutil("detach", str(mount))
    if done.returncode != 0:
        done = _hdiutil("detach", "-force", str(mount))
    if done.returncode != 0:
        raise DmgError(f"hdiutil couldn't detach {mount}: {_why(done)}")


@contextlib.contextmanager
def mounted(dmg: Path) -> Iterator[Path]:
    """Attach DMG read-only at a fresh directory, yield that directory and always detach.
    Raises DmgError when hdiutil won't attach or detach it."""
    mount = Path(tempfile.mkdtemp(prefix="check_bundle."))
    try:
        done = _hdiutil("attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(dmg))
        if done.returncode != 0:
            raise DmgError(f"hdiutil couldn't attach {dmg}: {_why(done)}")
        try:
            yield mount
        finally:
            detach(mount)
    finally:
        with contextlib.suppress(OSError):
            mount.rmdir()
