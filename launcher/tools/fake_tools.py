"""What the launcher tools' tests share. A test module's fakes are shell scripts all its tests
share, since macOS scans a new executable the first time it runs, which costs more than a script
does. Each test gets its own records file and switches through the environment instead."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# testutil lives in the repo's tools/, which isn't on the path of a test in launcher/tools/.
sys.path.append(str(Path(__file__).resolve().parents[2] / "tools"))

from testutil import run_main, temp_dir


def write(scripts: dict[str, str]) -> dict[str, str]:
    """The paths of SCRIPTS by name, written as executables in a "fake tools" directory that
    goes when the module's tests are done."""
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    directory = Path(tmp.name) / "fake tools"
    directory.mkdir()
    for name, text in scripts.items():
        (directory / name).write_text(text)
        (directory / name).chmod(0o755)
    return {name: str(directory / name) for name in scripts}


class FakeToolsTest(unittest.TestCase):
    """A directory of this test's own holding the records file and the switches directory, which
    the fakes find through $FAKE_RECORDS and $FAKE_SWITCHES."""

    def setUp(self):
        self.dir = temp_dir(self)
        self.records = self.dir / "records.txt"
        self.switches = self.dir / "fake switches"
        self.switches.mkdir()
        self.patch(mock.patch.dict(os.environ, {"FAKE_RECORDS": str(self.records),
                                                "FAKE_SWITCHES": str(self.switches)}))

    def patch(self, patcher) -> None:
        """Start PATCHER until the test ends."""
        patcher.start()
        self.addCleanup(patcher.stop)

    def switch(self, *names: str) -> None:
        """Turn on the switches NAMES."""
        for name in names:
            (self.switches / name).write_text("")

    def recorded(self) -> list[tuple[str, str]]:
        """Each line the fakes recorded, split at its first space, in order."""
        lines = self.records.read_text().splitlines() if self.records.exists() else []
        return [(key, value) for key, _, value in (line.partition(" ") for line in lines)]
