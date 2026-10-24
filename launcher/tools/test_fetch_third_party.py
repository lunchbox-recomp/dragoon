from __future__ import annotations

import hashlib
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import fetch_third_party

sys.path.insert(0, str(fetch_third_party.ROOT / "tools"))

from testutil import make_tarball, run_main, tar_member as member, write_file  # noqa: E402

TOP = "cmake-9.9.9-macos-universal"
SDL_CMAKE = """FetchContent_Declare(sdl3
  URL {url}
  URL_HASH SHA256={sha}
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_zip(path: Path, files: dict[str, tuple[bytes, int]]) -> Path:
    """A .zip of FILES (name: data and Unix mode), made the way Info-ZIP records modes."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, (data, mode) in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            zf.writestr(info, data)
    return path


def line(name: str, version: str, archive: Path, sha: str = "") -> str:
    return f"{name} {version} {archive.as_uri()} {sha or sha256(archive)}\n"


class FetchTestCase(unittest.TestCase):
    """CMake-like and Ninja-like archives and a stand-in SDL tarball in a source directory,
    pinned by file: URLs, all at paths with spaces."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.src = self.dir / "release files"
        self.src.mkdir()
        self.dest = self.dir / "third party" / "fetched"
        self.cmake = make_tarball(self.src / "cmake-9.9.9-macos-universal.tar.gz", [
            (member(f"{TOP}/", tarfile.DIRTYPE, 0o755), b""),
            (member(f"{TOP}/CMake.app/Contents/bin/cmake", mode=0o755), b"fake cmake"),
            (member(f"{TOP}/CMake.app/Contents/share/cmake-9.9/Modules/A Module.cmake"), b"# module\n"),
            (member(f"{TOP}/bin", tarfile.SYMTYPE, link="CMake.app/Contents/bin"), b""),
        ])
        self.ninja = make_zip(self.src / "ninja-mac.zip", {"ninja": (b"fake ninja", 0o755)})
        self.sdl = make_tarball(self.src / "SDL3-9.9.9.tar.gz", [
            (member("SDL3-9.9.9/CMakeLists.txt"), b"project(SDL3)\n")])
        self.pins = write_file(self.dir, "third_party.txt", (
            "# comments and blank lines are left out\n\n"
            + line("cmake", "9.9.9", self.cmake) + line("ninja", "1.2.3", self.ninja)))
        self.gcn = self.dir / "gcn recomp"
        self.gcn.mkdir()
        write_file(self.gcn, "CMakeLists.txt", SDL_CMAKE.format(url=self.sdl.as_uri(),
                                                                sha=sha256(self.sdl)))

    def fetch(self, *names: str, pins: Path | None = None) -> tuple[int, str, str]:
        return run_main(fetch_third_party.main, "--dest", str(self.dest), "--pins",
                        str(pins or self.pins), "--gcn-recomp", str(self.gcn), *names)

    def listing(self) -> list[str]:
        return sorted(p.name for p in self.dest.iterdir()) if self.dest.exists() else []


class PinsTest(unittest.TestCase):
    def test_reads_the_real_pins_file(self):
        items = fetch_third_party.parse_pins(fetch_third_party.PINS.read_text())
        self.assertEqual([(i.name, i.version, i.archive) for i in items], [
            ("cmake", "4.4.4", "cmake-4.4.4-macos-universal.tar.gz"),
            ("ninja", "1.13.2", "ninja-mac.zip")])
        for i in items:
            self.assertTrue(i.url.startswith("https://"), i.url)

    def test_leaves_out_comments_and_blank_lines(self):
        sha = "a" * 64
        items = fetch_third_party.parse_pins(
            f"# top\n\n  # indented\nx 1 https://example.com/a/x.zip {sha}\n   \n")
        self.assertEqual(items, [fetch_third_party.Item("x", "1", "https://example.com/a/x.zip", sha)])

    def test_refuses_a_malformed_line_and_names_it(self):
        good = "https://example.com/x.zip"
        sha = "a" * 64
        cases = {
            "three fields": f"x 1 {good}",
            "five fields": f"x 1 {good} {sha} extra",
            "a short hash": f"x 1 {good} {'a' * 63}",
            "an upper-case hash": f"x 1 {good} {'A' * 64}",
            "plain http": f"x 1 http://example.com/x.zip {sha}",
            "an ftp URL": f"x 1 ftp://example.com/x.zip {sha}",
            "a .dmg": f"x 1 https://example.com/x.dmg {sha}",
            "a bad name": f"X 1 {good} {sha}",
            "sdl3, which gcn-recomp pins": f"sdl3 1 {good} {sha}",
            "a repeated name": f"x 1 {good} {sha}\nx 2 {good} {sha}",
        }
        for why, text in cases.items():
            with self.subTest(why):
                with self.assertRaises(ValueError) as caught:
                    fetch_third_party.parse_pins("# fine\n" + text + "\n")
                self.assertRegex(str(caught.exception), r"line [23]")

    def test_names_the_archive_by_the_urls_last_segment(self):
        item = fetch_third_party.Item("x", "1", "https://example.com/a%20b/x%201.tar.gz?raw=1", "a" * 64)
        self.assertEqual(item.archive, "x 1.tar.gz")

    def test_sdl_item_comes_from_the_cmake_pin_and_ships_whole(self):
        item = fetch_third_party.sdl_item(SDL_CMAKE.format(
            url="https://example.com/SDL3-3.4.18.tar.gz", sha="b" * 64))
        self.assertEqual(item, fetch_third_party.Item(
            "sdl3", "3.4.18", "https://example.com/SDL3-3.4.18.tar.gz", "b" * 64, extract=False))


class FetchTest(FetchTestCase):
    def test_downloads_checks_and_extracts_each_item(self):
        code, out, err = self.fetch("cmake", "ninja")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.listing(), ["cmake-9.9.9", "cmake-9.9.9-macos-universal.tar.gz",
                                          "ninja-1.2.3", "ninja-mac.zip"])
        cmake = self.dest / "cmake-9.9.9" / TOP / "CMake.app" / "Contents"
        self.assertEqual((cmake / "bin" / "cmake").read_bytes(), b"fake cmake")
        self.assertEqual((cmake / "bin" / "cmake").stat().st_mode & 0o777, 0o755)
        self.assertEqual((cmake / "share/cmake-9.9/Modules/A Module.cmake").stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.dest / "cmake-9.9.9" / TOP / "bin").readlink(),
                         Path("CMake.app/Contents/bin"))
        ninja = self.dest / "ninja-1.2.3" / "ninja"
        self.assertEqual((ninja.read_bytes(), ninja.stat().st_mode & 0o777), (b"fake ninja", 0o755))
        self.assertEqual(sha256(self.dest / self.cmake.name), sha256(self.cmake))
        self.assertIn("cmake 9.9.9: downloaded cmake-9.9.9-macos-universal.tar.gz", out)
        self.assertIn("ninja 1.2.3: downloaded ninja-mac.zip", out)

    def test_with_no_names_it_fetches_sdl_whole_from_the_cmake_pin(self):
        code, out, err = self.fetch()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.listing(), [
            "SDL3-9.9.9.tar.gz", "cmake-9.9.9", "cmake-9.9.9-macos-universal.tar.gz",
            "ninja-1.2.3", "ninja-mac.zip"])
        self.assertEqual((self.dest / "SDL3-9.9.9.tar.gz").read_bytes(), self.sdl.read_bytes())
        self.assertIn("sdl3 9.9.9: downloaded SDL3-9.9.9.tar.gz, SHA-256 matches\n", out)

    def test_names_fetch_only_those_and_never_read_a_missing_gcn_recomp(self):
        self.gcn = self.dir / "no such checkout"
        self.assertEqual(self.fetch("ninja")[0], 0)
        self.assertEqual(self.listing(), ["ninja-1.2.3", "ninja-mac.zip"])

    def test_a_wrong_hash_is_refused_and_leaves_nothing(self):
        pins = write_file(self.dir, "wrong.txt", line("ninja", "1.2.3", self.ninja, "0" * 64))
        code, out, err = self.fetch(pins=pins)
        self.assertEqual(code, 1)
        self.assertIn(sha256(self.ninja), err)
        self.assertIn("0" * 64, err)
        self.assertIn("ninja 1.2.3", err)
        self.assertEqual((out, self.listing()), ("", []))

    def test_a_wrong_hash_stops_the_run_before_the_next_item(self):
        pins = write_file(self.dir, "wrong.txt", line("cmake", "9.9.9", self.cmake, "0" * 64)
                          + line("ninja", "1.2.3", self.ninja))
        self.assertEqual(self.fetch(pins=pins)[0], 1)
        self.assertEqual(self.listing(), [])

    def test_a_wrong_sdl_hash_is_refused(self):
        write_file(self.gcn, "CMakeLists.txt", SDL_CMAKE.format(url=self.sdl.as_uri(), sha="0" * 64))
        code, _, err = self.fetch("sdl3")
        self.assertEqual(code, 1)
        self.assertIn("sdl3 9.9.9", err)
        self.assertEqual(self.listing(), [])

    def test_a_missing_file_is_a_failure_that_leaves_nothing(self):
        pins = write_file(self.dir, "gone.txt", line("ninja", "1.2.3", self.ninja))
        self.ninja.unlink()
        code, _, err = self.fetch(pins=pins)
        self.assertEqual(code, 1)
        self.assertIn("can't download", err)
        self.assertEqual(self.listing(), [])

    def test_a_rerun_finds_the_intact_archive_and_downloads_nothing(self):
        self.assertEqual(self.fetch("ninja")[0], 0)
        self.ninja.rename(self.src / "moved.zip")
        write_file(self.dest / "ninja-1.2.3", "stale.txt", "from an earlier run")
        code, out, err = self.fetch("ninja")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("ninja 1.2.3: cached ninja-mac.zip", out)
        self.assertEqual(sorted(p.name for p in (self.dest / "ninja-1.2.3").iterdir()), ["ninja"])

    def test_a_damaged_archive_is_downloaded_again(self):
        self.assertEqual(self.fetch("ninja")[0], 0)
        (self.dest / "ninja-mac.zip").write_bytes(b"damaged")
        code, out, _ = self.fetch("ninja")
        self.assertEqual(code, 0)
        self.assertIn("downloaded ninja-mac.zip", out)
        self.assertEqual(sha256(self.dest / "ninja-mac.zip"), sha256(self.ninja))

    def test_an_unknown_name_or_bad_pins_file_is_a_bad_argument(self):
        code, _, err = self.fetch("gcc")
        self.assertEqual(code, 2)
        self.assertIn("gcc", err)
        self.assertIn("cmake, ninja, sdl3", err)
        code, _, err = self.fetch(pins=write_file(self.dir, "bad.txt", "cmake 1\n"))
        self.assertEqual(code, 2)
        self.assertIn("line 1", err)
        self.assertEqual(self.fetch(pins=self.dir / "none.txt")[0], 2)
        self.assertEqual(self.listing(), [])

    def test_everything_needs_gcn_recomp_for_sdls_pin(self):
        self.gcn = self.dir / "no such checkout"
        code, _, err = self.fetch()
        self.assertEqual(code, 2)
        self.assertIn("SDL's pin", err)
        self.assertEqual(self.listing(), [])


class ExtractionTest(FetchTestCase):
    """Archives whose hash is right but whose members are not safe. Each is refused, nothing
    is left in the destination and nothing is written outside it."""

    def refused(self, archive: Path, reason: str) -> None:
        """Fetch ARCHIVE into a fresh destination. It fails with REASON in the message, having
        kept the archive alone, and no file named pwned appears anywhere."""
        self.dest = Path(tempfile.mkdtemp(dir=self.dir))
        pins = write_file(self.dir, "evil.txt", line("evil", "1", archive))
        code, _, err = self.fetch(pins=pins)
        self.assertEqual(code, 1, err)
        self.assertIn("can't extract", err)
        self.assertIn(reason, err)
        self.assertEqual(self.listing(), [archive.name])
        self.assertEqual(list(self.dir.rglob("pwned")), [])

    def tar(self, *members) -> Path:
        return make_tarball(self.src / "evil.tar.gz", [(member("top/a"), b"fine"), *members])

    def test_tar_members_that_leave_or_arent_plain(self):
        outside, plain = "is outside the tree", "isn't a file, a directory or a symlink"
        cases = {
            "an absolute path": (member(str(self.dir / "pwned")), outside),
            "a .. path": (member("top/../../../../pwned"), outside),
            "a hard link": (member("top/hard", tarfile.LNKTYPE, link="top/a"), plain),
            "a device": (member("top/dev", tarfile.CHRTYPE), plain),
            "a fifo": (member("top/fifo", tarfile.FIFOTYPE), plain),
            "an absolute symlink": (member("top/link", tarfile.SYMTYPE, link="/etc"),
                                    "top/link -> /etc leads out of the tree"),
            "a symlink up and out": (member("top/link", tarfile.SYMTYPE, link="../../.."),
                                     "top/link -> ../../.. leads out of the tree"),
        }
        for why, (bad, reason) in cases.items():
            with self.subTest(why):
                self.refused(self.tar((bad, b"")), reason)

    def test_a_symlink_that_only_leaves_through_another_symlink(self):
        # x/s points at x, so x/t reads as the tree's root lexically and as its parent in fact.
        self.refused(self.tar(
            (member("top/x/", tarfile.DIRTYPE, 0o755), b""),
            (member("top/x/s", tarfile.SYMTYPE, link="."), b""),
            (member("top/x/t", tarfile.SYMTYPE, link="s/../../.."), b"")),
            "top/x/t -> s/../../.. leads out of the tree")

    def test_a_file_listed_under_a_symlink_isnt_written_through_it(self):
        self.refused(self.tar(
            (member("top/link", tarfile.SYMTYPE, link="../.."), b""),
            (member("top/link/pwned"), b"written outside")), "File exists")

    def test_zip_members_that_leave_or_arent_plain(self):
        for why, name in {"an absolute path": str(self.dir / "pwned"),
                          "a .. path": "../../pwned"}.items():
            with self.subTest(why):
                self.refused(make_zip(self.src / "evil.zip", {"ninja": (b"fine", 0o755),
                                                              name: (b"x", 0o644)}),
                             "is outside the tree")
        link = zipfile.ZipInfo("link")
        link.external_attr = 0o120777 << 16
        with zipfile.ZipFile(self.src / "link.zip", "w") as zf:
            zf.writestr(link, "/etc")
        self.refused(self.src / "link.zip", "'link' is a symlink")

    def test_a_failed_extraction_keeps_the_tree_of_an_earlier_good_run(self):
        self.assertEqual(self.fetch("ninja")[0], 0)
        bad = make_zip(self.src / "ninja-mac.zip", {"../pwned": (b"x", 0o644)})
        pins = write_file(self.dir, "bad.txt", line("ninja", "1.2.3", bad))
        self.assertEqual(self.fetch(pins=pins)[0], 1)
        self.assertEqual(sorted(p.name for p in (self.dest / "ninja-1.2.3").iterdir()), ["ninja"])
        self.assertFalse((self.dest / "ninja-1.2.3.partial").exists())

    def test_a_tarball_with_a_dot_directory_extracts(self):
        tarball = make_tarball(self.src / "dot.tar.gz", [
            (member("./", tarfile.DIRTYPE, 0o755), b""), (member("./top/a"), b"fine")])
        pins = write_file(self.dir, "dot.txt", line("dot", "1", tarball))
        self.assertEqual(self.fetch(pins=pins)[0], 0)
        self.assertEqual((self.dest / "dot-1" / "top" / "a").read_bytes(), b"fine")


if __name__ == "__main__":
    unittest.main()
