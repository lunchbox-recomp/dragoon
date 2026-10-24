from __future__ import annotations

import hashlib
import os
import plistlib
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fetch_third_party
import make_app
import sign_plan

sys.path.insert(0, str(make_app.ROOT / "tools"))

import source_info  # noqa: E402
from testutil import GIT_ENV, commit, git, make_tarball, run_main, tar_member as member, write_file  # noqa: E402

SHA1 = "0123456789abcdef0123456789abcdef01234567"
CMAKE = f"""add_subdirectory(gcn-recomp)
gcn_add_game(
  NAME test
  DISC_ID TEST01
  DOL_SHA1 {SHA1})
"""
SDL_CMAKE = """FetchContent_Declare(sdl3
  URL https://example.com/release/SDL3-9.9.9.tar.gz
  URL_HASH SHA256={sha}
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
"""
PINS = ("cmake 9.9.9 https://example.com/cmake-9.9.9-macos-universal.tar.gz " + "a" * 64
        + "\nninja 1.2.3 https://example.com/ninja-mac.zip " + "b" * 64 + "\n")
BUNDLE_ID = "io.github.lunchbox-recomp.dragoon"
SEP = "\x1f"

# The fakes record each call as a line of its arguments joined by SEP in $FAKE_RECORDS. A file
# named after a failure in $FAKE_SWITCHES turns that failure on. A fake binary is a text file
# whose first line is "ARCHS: x86_64 arm64" or the like, which the fake lipo reads and writes.
RECORD = r"""#!/bin/sh
{ printf '@TOOL@'; for arg in "$@"; do printf '\037%s' "$arg"; done; echo; } >> "$FAKE_RECORDS"
marker() { [ -e "$FAKE_SWITCHES/$1" ]; }
"""
BODIES = {
    "lipo": """
if marker "fail lipo"; then echo "lipo: broke" >&2; exit 1; fi
case "$1" in
  -archs) sed -n '1s/^ARCHS: //p' "$2" ;;
  -thin) { printf 'ARCHS: %s\\n' "$2"; sed 1d "$3"; } > "$5" ;;
esac
""",
    "codesign": """
if marker "fail codesign"; then echo "codesign: broke" >&2; exit 1; fi
""",
}
FAKES: dict[str, str] = {}


def setUpModule() -> None:
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    directory = Path(tmp.name) / "fake tools"
    directory.mkdir()
    for tool, body in BODIES.items():
        path = directory / tool
        path.write_text(RECORD.replace("@TOOL@", tool) + body)
        path.chmod(0o755)
        FAKES[tool] = str(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AppTestCase(unittest.TestCase):
    """Fake pieces for every input, the fake lipo and codesign, and a Dragoon repository whose
    gcn-recomp pins the fake SDL tarball, all at paths with spaces."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name).resolve()  # /var is a link, which the tool resolves
        self.records = self.dir / "records.txt"
        self.switches = self.dir / "fake switches"
        self.switches.mkdir()
        for patch in (
                mock.patch.dict(os.environ, {**GIT_ENV, "FAKE_RECORDS": str(self.records),
                                             "FAKE_SWITCHES": str(self.switches)}),
                mock.patch.object(make_app, "LIPO", FAKES["lipo"]),
                mock.patch.object(sign_plan, "CODESIGN", FAKES["codesign"])):
            patch.start()
            self.addCleanup(patch.stop)
        self.launcher = write_file(self.make_dir("swift build"), "Dragoon", "the launcher\n")
        self.pins = write_file(self.dir, "third_party.txt", PINS)
        self.tp = self.make_dir("third party")
        self.fake_pieces()
        self.sdl = make_tarball(self.tp / "SDL3-9.9.9.tar.gz", [
            (member("SDL3-9.9.9/LICENSE.txt"), b"SDL's license\n"),
            (member("SDL3-9.9.9/CMakeLists.txt"), b"project(SDL3)\n")])
        self.repo = self.make_repo()
        self.out = self.dir / "dist dir"

    def make_dir(self, name: str) -> Path:
        path = self.dir / name
        path.mkdir()
        return path

    def fake_pieces(self, cmake: str = "x86_64 arm64", ninja: str = "x86_64 arm64") -> None:
        contents = self.tp / "cmake-9.9.9" / "cmake-9.9.9-macos-universal" / "CMake.app" / "Contents"
        notices = contents / "doc" / "cmake"  # where CMake's own tarball keeps them
        for path, text in ((contents / "bin" / "cmake", f"ARCHS: {cmake}\ncmake\n"),
                           (contents / "share" / "cmake-9.9" / "Modules" / "A Module.cmake", "# module\n"),
                           (notices / "LICENSE.rst", "CMake's license\n"),
                           (notices / "CONTRIBUTORS.rst", "CMake's contributors\n"),
                           (notices / "cmlibuv" / "LICENSE", "libuv's license\n"),
                           (notices / "cmsys" / "Copyright.txt", "KWSys's license\n"),
                           (notices / "html" / "index.html", "the manual\n"),
                           (notices / "CMake.qch", "the help\n"),
                           (self.tp / "ninja-1.2.3" / "ninja", f"ARCHS: {ninja}\nninja\n")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        alias = contents / "share" / "cmake-9.9" / "Alias"
        if not alias.is_symlink():
            os.symlink("Modules", alias)

    def make_repo(self) -> Path:
        engine = self.dir / "Dragoon repo" / "gcn-recomp"
        pin = commit(engine, {"LICENSE": "gcn-recomp's license\n",
                              "CMakeLists.txt": SDL_CMAKE.format(sha=sha256(self.sdl))})
        repo = engine.parent
        git(repo, "init", "-q", "-b", "main")
        git(repo, "update-index", "--add", "--cacheinfo", f"160000,{pin},gcn-recomp")
        self.head = commit(repo, {
            "LICENSE": "Dragoon's license\n", "CMakeLists.txt": CMAKE,
            ".gitmodules": '[submodule "gcn-recomp"]\n\tpath = gcn-recomp\n\turl = https://example.com/e\n'})
        return repo

    def run_tool(self, *extra: str, version: str = "1.2.3") -> tuple[int, str, str]:
        return run_main(make_app.main, "--out", str(self.out), "--version", version,
                        "--launcher", str(self.launcher), "--third-party", str(self.tp),
                        "--pins", str(self.pins), "--repo", str(self.repo), *extra)

    def switch(self, *names: str) -> None:
        for name in names:
            write_file(self.switches, name, "")

    def calls(self, tool: str) -> list[list[str]]:
        """The arguments of each call the fake TOOL got, in order."""
        if not self.records.exists():
            return []
        rows = [line.split(SEP) for line in self.records.read_text().splitlines()]
        return [row[1:] for row in rows if row[0] == tool]

    def tree(self) -> list[str]:
        """Every file and symlink in the app outside the source snapshot, sorted."""
        app, found = self.out / "Dragoon.app", []
        for here, dirs, files in os.walk(app):
            for name in dirs + files:
                path = Path(here, name)
                if path.is_symlink() or path.is_file():
                    found.append(path.relative_to(app).as_posix())
        return sorted(p for p in found if not p.startswith("Contents/Resources/source/"))


class LayoutTest(AppTestCase):
    def test_lays_out_the_app_as_the_plan_has_it(self):
        code, out, err = self.run_tool()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, f"{self.out / 'Dragoon.app'}\n")
        self.assertEqual(self.tree(), [
            "Contents/Info.plist",
            "Contents/MacOS/Dragoon",
            "Contents/MacOS/cmake",
            "Contents/MacOS/ninja",
            "Contents/Resources/cmake/bin/cmake",
            "Contents/Resources/cmake/share/cmake-9.9/Alias",
            "Contents/Resources/cmake/share/cmake-9.9/Modules/A Module.cmake",
            "Contents/Resources/licenses/CMake/CONTRIBUTORS.rst",
            "Contents/Resources/licenses/CMake/LICENSE.rst",
            "Contents/Resources/licenses/CMake/cmlibuv/LICENSE",
            "Contents/Resources/licenses/CMake/cmsys/Copyright.txt",
            "Contents/Resources/licenses/Dragoon.txt",
            "Contents/Resources/licenses/Ninja.txt",
            "Contents/Resources/licenses/SDL.txt",
            "Contents/Resources/licenses/gcn-recomp.txt",
            "Contents/Resources/third_party/SDL3-9.9.9.tar.gz",
        ])

    def test_the_tools_are_thinned_to_arm64_and_the_launcher_is_copied(self):
        self.run_tool()
        macos = self.out / "Dragoon.app" / "Contents" / "MacOS"
        self.assertEqual((macos / "cmake").read_text(), "ARCHS: arm64\ncmake\n")
        self.assertEqual((macos / "ninja").read_text(), "ARCHS: arm64\nninja\n")
        self.assertEqual((macos / "Dragoon").read_text(), "the launcher\n")
        for name in ("Dragoon", "cmake", "ninja"):
            self.assertEqual((macos / name).stat().st_mode & 0o777, 0o755, name)

    def test_a_tool_that_is_already_arm64_is_copied_not_thinned(self):
        self.fake_pieces(ninja="arm64")
        self.run_tool()
        thins = [c for c in self.calls("lipo") if c[0] == "-thin"]
        self.assertEqual(len(thins), 1)
        self.assertTrue(thins[0][2].endswith("cmake"), thins)
        ninja = self.out / "Dragoon.app" / "Contents" / "MacOS" / "ninja"
        self.assertEqual(ninja.read_text(), "ARCHS: arm64\nninja\n")

    def test_cmake_is_reached_through_a_link_to_the_copy_in_macos(self):
        self.run_tool()
        link = self.out / "Dragoon.app" / "Contents" / "Resources" / "cmake" / "bin" / "cmake"
        self.assertEqual(os.readlink(link), "../../../MacOS/cmake")
        self.assertEqual(link.resolve(), (link.parents[3] / "MacOS" / "cmake").resolve())
        modules = link.parents[1] / "share" / "cmake-9.9"
        self.assertEqual((modules / "Modules" / "A Module.cmake").read_text(), "# module\n")
        self.assertEqual(os.readlink(modules / "Alias"), "Modules")

    def test_the_info_plist_has_the_bundle_id_the_minimum_system_and_the_version(self):
        self.run_tool(version="1.2.3")
        with (self.out / "Dragoon.app" / "Contents" / "Info.plist").open("rb") as f:
            info = plistlib.load(f)
        self.assertEqual(info["CFBundleIdentifier"], BUNDLE_ID)
        self.assertEqual(info["LSMinimumSystemVersion"], "14.0")
        self.assertEqual(info["CFBundleExecutable"], "Dragoon")
        self.assertEqual((info["CFBundleShortVersionString"], info["CFBundleVersion"]), ("1.2.3", "1.2.3"))
        self.assertFalse([k for k in info if "Icon" in k])

    def test_the_source_is_the_snapshot_of_the_repo(self):
        self.run_tool()
        source = self.out / "Dragoon.app" / "Contents" / "Resources" / "source"
        self.assertEqual(source_info.read(source / source_info.NAME)["dragoon"], self.head)
        self.assertEqual((source / "gcn-recomp" / "LICENSE").read_text(), "gcn-recomp's license\n")

    def test_the_sdl_tarball_ships_whole_and_the_licenses_come_from_each_piece(self):
        self.run_tool()
        resources = self.out / "Dragoon.app" / "Contents" / "Resources"
        self.assertEqual((resources / "third_party" / "SDL3-9.9.9.tar.gz").read_bytes(),
                         self.sdl.read_bytes())
        licenses = resources / "licenses"
        texts = {p.name: p.read_text() for p in licenses.iterdir() if p.is_file()}
        self.assertEqual(texts, {
            "SDL.txt": "SDL's license\n", "Dragoon.txt": "Dragoon's license\n",
            "gcn-recomp.txt": "gcn-recomp's license\n",
            "Ninja.txt": make_app.NINJA_LICENSE.read_text()})
        self.assertIn("Apache License", texts["Ninja.txt"])

    def test_cmakes_license_and_its_libraries_notices_ship_but_not_its_manual(self):
        self.run_tool()
        cmake = self.out / "Dragoon.app" / "Contents" / "Resources" / "licenses" / "CMake"
        self.assertEqual((cmake / "LICENSE.rst").read_text(), "CMake's license\n")
        self.assertEqual((cmake / "cmlibuv" / "LICENSE").read_text(), "libuv's license\n")
        self.assertEqual(sorted(p.name for p in cmake.iterdir()),
                         ["CONTRIBUTORS.rst", "LICENSE.rst", "cmlibuv", "cmsys"])

    def test_signs_ad_hoc_without_the_hardened_runtime_then_verifies(self):
        self.run_tool()
        app = self.out / "Dragoon.app"
        want = [cmd[1:] for cmd in sign_plan.sign_app(app, app, "-") + [sign_plan.verify_app(app)]]
        self.assertEqual(self.calls("codesign"), want)
        signing = self.calls("codesign")[:-1]
        self.assertEqual([c[-1] for c in signing], [str(app / "Contents/MacOS/cmake"),
                                                    str(app / "Contents/MacOS/ninja"), str(app)])
        self.assertIn(f"{BUNDLE_ID}.cmake", signing[0])
        for call in signing:
            self.assertEqual(call[:3], ["-f", "-s", "-"])
            self.assertIn("--timestamp=none", call)
            self.assertNotIn("runtime", call)

    def test_an_existing_empty_out_is_used(self):
        self.out.mkdir()
        self.assertEqual(self.run_tool()[0], 0)
        self.assertTrue((self.out / "Dragoon.app" / "Contents" / "Info.plist").is_file())

    def test_the_real_pins_name_what_the_layout_looks_for(self):
        pins = {i.name for i in make_app.fetch_third_party.parse_pins(
            make_app.fetch_third_party.PINS.read_text())}
        self.assertEqual(pins, {"cmake", "ninja"})
        self.assertTrue(make_app.INFO_PLIST.is_file())


class FetchedPiecesTest(unittest.TestCase):
    """The layout the fakes copy, checked against the real tarballs when fetch_third_party.py
    has fetched them."""

    @unittest.skipUnless(make_app.THIRD_PARTY.joinpath("cmake-4.4.4").is_dir(), "not fetched")
    def test_finds_cmakes_modules_and_notices_in_the_real_tree(self):
        pieces = make_app.find_pieces(make_app.THIRD_PARTY, fetch_third_party.PINS)
        self.assertEqual(pieces.modules.name, "cmake-4.4")
        self.assertTrue((pieces.modules / "Modules" / "CMakeDetermineSystem.cmake").is_file())
        self.assertIn("Redistribution and use", (pieces.cmake_notices / "LICENSE.rst").read_text())
        self.assertTrue(any(d.name.startswith("cm") for d in pieces.cmake_notices.iterdir()))

    @unittest.skipUnless(make_app.THIRD_PARTY.joinpath("SDL3-3.4.18.tar.gz").is_file(), "not fetched")
    def test_sdls_tarball_holds_its_license(self):
        tarball = make_app.THIRD_PARTY / "SDL3-3.4.18.tar.gz"
        self.assertIn(b"Permission is granted to anyone to use this software",
                      make_app.sdl_license(tarball, "SDL3-3.4.18"))


class RefusalTest(AppTestCase):
    """A bad input exits 2 with nothing written, and a step that fails exits 1 with what it
    wrote removed, down to OUT if it made that."""

    def refused(self, code: int, *words: str, **kw: str) -> None:
        got, _, err = self.run_tool(**kw)
        self.assertEqual(got, code, err)
        for word in words:
            self.assertIn(word, err)
        if self.out.exists():
            self.assertEqual(list(self.out.iterdir()), [])

    def test_a_missing_launcher_says_how_to_build_it(self):
        self.launcher.unlink()
        self.refused(2, "swift build -c release")
        self.assertFalse(self.out.exists())

    def test_a_bad_version_is_refused(self):
        for version in ("", "v1", "1 2", "../1"):
            with self.subTest(version):
                self.refused(2, "--version", version=version)

    def test_an_out_that_isnt_empty_is_left_as_it_was(self):
        write_file(self.make_dir("dist dir"), "keep.txt", "mine")
        self.assertEqual(self.run_tool()[0], 2)
        self.assertEqual([p.name for p in self.out.iterdir()], ["keep.txt"])

    def test_a_missing_tool_or_license_is_refused_before_anything_is_written(self):
        (self.tp / "ninja-1.2.3" / "ninja").unlink()
        self.refused(2, "ninja")
        self.assertFalse(self.out.exists())
        self.fake_pieces()
        next(self.tp.rglob("LICENSE.rst")).unlink()
        self.refused(2, "LICENSE.rst")
        self.assertFalse(self.out.exists())

    def test_a_pins_file_without_cmake_is_refused(self):
        write_file(self.dir, "third_party.txt", PINS.split("\n")[1] + "\n")
        self.refused(2, "pins no cmake")

    def test_a_missing_sdl_tarball_is_refused(self):
        self.sdl.unlink()
        self.refused(2, "SDL3-9.9.9.tar.gz", "fetch_third_party.py")
        self.assertFalse(self.out.exists())

    def test_an_sdl_tarball_that_differs_from_the_pin_is_refused(self):
        make_tarball(self.sdl, [(member("SDL3-9.9.9/LICENSE.txt"), b"another tarball\n")])
        self.refused(1, sha256(self.sdl), "gcn-recomp pins")
        self.assertFalse(self.out.exists())

    def test_a_tool_with_no_arm64_slice_is_refused(self):
        self.fake_pieces(cmake="x86_64")
        self.refused(1, "no arm64 slice, only x86_64")
        self.assertFalse(self.out.exists())

    def test_a_failed_lipo_is_refused(self):
        self.switch("fail lipo")
        self.refused(1, "lipo")
        self.assertFalse(self.out.exists())

    def test_a_failed_signature_removes_the_app_but_not_an_out_that_was_there(self):
        self.switch("fail codesign")
        self.refused(1, "codesign")
        self.assertFalse(self.out.exists())
        self.out.mkdir()
        self.refused(1, "codesign")
        self.assertTrue(self.out.is_dir())

    def test_a_repo_with_uncommitted_changes_is_refused(self):
        write_file(self.repo, "LICENSE", "edited\n")
        self.refused(1, "uncommitted changes")
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
