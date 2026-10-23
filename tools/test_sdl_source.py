import tarfile
import tempfile
import unittest
from pathlib import Path

import sdl_source
from testutil import make_tarball, tar_member as member

REAL_SHA256 = "9c75cf16330322c217dedd2e0609f1124f1b54b8633e763467b4684d0f4334a3"
REAL_URL = "https://github.com/libsdl-org/SDL/releases/download/release-3.4.18/SDL3-3.4.18.tar.gz"
DECLARE = """FetchContent_Declare(openxr_headers
  URL https://example.com/openxr.tar.gz
  URL_HASH SHA256={other})
FetchContent_Declare(sdl3
  URL https://example.com/release/SDL3-3.4.18.tar.gz
  URL_HASH SHA256={sha}
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
""".format(other="1" * 64, sha="2" * 64)
GCN_CMAKE = sdl_source.ROOT / "gcn-recomp" / "CMakeLists.txt"


class PinTest(unittest.TestCase):
    @unittest.skipUnless(GCN_CMAKE.exists(), "gcn-recomp isn't checked out")
    def test_finds_the_real_pin_in_gcn_recomp(self):
        text = GCN_CMAKE.read_text()
        self.assertEqual(sdl_source.pin(text), sdl_source.Pin(REAL_URL, REAL_SHA256))

    def test_takes_sdl3s_declare_and_names_its_directory(self):
        p = sdl_source.pin(DECLARE)
        self.assertEqual(p, sdl_source.Pin("https://example.com/release/SDL3-3.4.18.tar.gz", "2" * 64))
        self.assertEqual(p.top, "SDL3-3.4.18")

    def test_refuses_a_missing_or_malformed_pin(self):
        for text in ("", DECLARE.replace("sdl3", "sdl2"), DECLARE.replace("2" * 64, "2" * 63),
                     DECLARE.replace("SDL3-3.4.18.tar.gz", "SDL3-3.4.18.zip")):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    sdl_source.pin(text)


class ExtractTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.dest = self.dir / "Caches dir" / "sdl"

    def test_extracts_files_and_directories_keeping_the_executable_bit(self):
        tarball = make_tarball(self.dir / "SDL3.tar.gz", [
            (member("./", tarfile.DIRTYPE, 0o755), b""),
            (member("SDL3-3.4.18/", tarfile.DIRTYPE, 0o755), b""),
            (member("SDL3-3.4.18/CMakeLists.txt"), b"project(SDL3)\n"),
            (member("SDL3-3.4.18/build-scripts/run me.sh", mode=0o775), b"#!/bin/sh\n"),
        ])
        sdl_source.extract(tarball, self.dest)
        self.assertEqual((self.dest / "SDL3-3.4.18" / "CMakeLists.txt").read_bytes(), b"project(SDL3)\n")
        script = self.dest / "SDL3-3.4.18" / "build-scripts" / "run me.sh"
        self.assertEqual(script.stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.dest / "SDL3-3.4.18" / "CMakeLists.txt").stat().st_mode & 0o777, 0o644)

    def test_refuses_members_that_leave_or_arent_plain(self):
        cases = {
            "an absolute path": member("/tmp/evil"),
            "a .. path": member("SDL3-3.4.18/../../evil"),
            "a symlink": member("SDL3-3.4.18/link", tarfile.SYMTYPE, link="/etc/passwd"),
            "a hard link": member("SDL3-3.4.18/hard", tarfile.LNKTYPE, link="SDL3-3.4.18/a"),
            "a device": member("SDL3-3.4.18/dev", tarfile.CHRTYPE),
            "a fifo": member("SDL3-3.4.18/fifo", tarfile.FIFOTYPE),
        }
        for name, bad in cases.items():
            with self.subTest(name):
                tarball = make_tarball(self.dir / "bad.tar.gz", [
                    (member("SDL3-3.4.18/a"), b"fine"), (bad, b"")])
                with self.assertRaises(ValueError) as caught:
                    sdl_source.extract(tarball, self.dest)
                self.assertIn(bad.name, str(caught.exception))
                self.assertFalse(self.dest.exists())  # checked before anything is written


if __name__ == "__main__":
    unittest.main()
