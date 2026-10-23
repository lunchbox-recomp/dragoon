import json
import os
import tempfile
import time
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

    def test_an_attach_that_hangs_is_an_error_and_gets_a_forced_detach(self):
        write_file(self.tools, "attach hangs", "")
        with mock.patch.object(bundle_dmg, "ATTACH_SECONDS", 1):
            with self.assertRaisesRegex(bundle_dmg.DmgError, "attach didn't finish in 1 s"):
                with bundle_dmg.mounted(self.dmg):
                    self.fail("the body ran")
        attach, detach = self.calls()  # it may have mounted before it hung
        self.assertEqual(attach[0], "attach")
        self.assertEqual(detach, ["detach", "-force", attach[attach.index("-mountpoint") + 1]])

    def test_a_detach_that_hangs_is_forced(self):
        write_file(self.tools, "detach hangs", "")
        with mock.patch.object(bundle_dmg, "DETACH_SECONDS", 1):
            with bundle_dmg.mounted(self.dmg) as mount:
                pass
        self.assertEqual(self.calls()[1:], [["detach", str(mount)], ["detach", "-force", str(mount)]])
        self.assertFalse(mount.exists())

    def test_a_forced_detach_that_hangs_is_an_error(self):
        write_file(self.tools, "busy", "")
        write_file(self.tools, "force hangs", "")
        with mock.patch.object(tempfile, "tempdir", str(self.dir)):
            with mock.patch.object(bundle_dmg, "DETACH_SECONDS", 1):
                with self.assertRaisesRegex(bundle_dmg.DmgError, "detach didn't finish in 1 s"):
                    with bundle_dmg.mounted(self.dmg):
                        pass
        attach, detach, forced = self.calls()
        mount = attach[attach.index("-mountpoint") + 1]
        self.assertEqual([detach, forced], [["detach", mount], ["detach", "-force", mount]])

    def test_the_forced_detach_after_a_hung_attach_is_cut_short_too(self):
        write_file(self.tools, "attach hangs", "")
        write_file(self.tools, "force hangs", "")
        started = time.monotonic()
        with mock.patch.object(bundle_dmg, "ATTACH_SECONDS", 1):
            with mock.patch.object(bundle_dmg, "DETACH_SECONDS", 1):
                with self.assertRaisesRegex(bundle_dmg.DmgError, "attach didn't finish in 1 s"):
                    with bundle_dmg.mounted(self.dmg):
                        self.fail("the body ran")
        self.assertEqual([c[:2] for c in self.calls()], [["attach", "-readonly"], ["detach", "-force"]])
        self.assertLess(time.monotonic() - started, 30)  # the fake hangs for 60 s

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
