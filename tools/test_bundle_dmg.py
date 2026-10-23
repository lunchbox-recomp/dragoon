import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bundle_dmg
from testutil import fake_hdiutil, write_file


class MountedTest(unittest.TestCase):
    """The mounts are fake: attach copies <dmg>.contents into the mount point."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.records = self.dir / "records.jsonl"
        self.tools = self.dir / "fake tools"
        self.tools.mkdir()
        hdiutil = fake_hdiutil(self.tools, self.records)
        patch = mock.patch.object(bundle_dmg, "HDIUTIL", str(hdiutil))
        patch.start()
        self.addCleanup(patch.stop)
        self.dmg = write_file(self.dir, "Dragoon 1.0.dmg", b"fake dmg")
        (self.dir / "Dragoon 1.0.dmg.contents").mkdir()
        write_file(self.dir / "Dragoon 1.0.dmg.contents", "README", "inside")

    def calls(self) -> list[list[str]]:
        if not self.records.exists():
            return []
        return [json.loads(line) for line in self.records.read_text().splitlines()]

    def test_attaches_read_only_and_out_of_the_finder_then_detaches(self):
        with bundle_dmg.mounted(self.dmg) as mount:
            self.assertEqual((mount / "README").read_text(), "inside")
            self.assertEqual(self.calls(), [
                ["attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(self.dmg)]])
        self.assertEqual(self.calls()[1:], [["detach", str(mount)]])
        self.assertFalse(mount.exists())

    def test_detaches_when_the_checks_raise(self):
        with self.assertRaises(RuntimeError):
            with bundle_dmg.mounted(self.dmg) as mount:
                raise RuntimeError("a check blew up")
        self.assertEqual(self.calls()[1:], [["detach", str(mount)]])
        self.assertFalse(mount.exists())

    def test_a_busy_volume_is_detached_with_force(self):
        write_file(self.tools, "busy", "")
        with bundle_dmg.mounted(self.dmg) as mount:
            pass
        self.assertEqual(self.calls()[1:], [["detach", str(mount)], ["detach", "-force", str(mount)]])
        self.assertFalse(mount.exists())

    def test_a_volume_that_will_not_detach_is_an_error(self):
        write_file(self.tools, "detach fails", "")
        with self.assertRaisesRegex(bundle_dmg.DmgError, "detach"):
            with bundle_dmg.mounted(self.dmg):
                pass

    def test_a_failed_attach_is_an_error_naming_hdiutil_and_leaves_nothing(self):
        write_file(self.tools, "attach fails", "")
        with mock.patch.object(tempfile, "tempdir", str(self.dir)):
            with self.assertRaisesRegex(bundle_dmg.DmgError, "Resource temporarily unavailable"):
                with bundle_dmg.mounted(self.dmg):
                    self.fail("the body ran")
        self.assertEqual([c[0] for c in self.calls()], ["attach"])
        self.assertEqual(sorted(os.listdir(self.dir)),
                         ["Dragoon 1.0.dmg", "Dragoon 1.0.dmg.contents", "fake tools", "records.jsonl"])


if __name__ == "__main__":
    unittest.main()
