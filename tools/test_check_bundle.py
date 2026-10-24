from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bundle_checks
import bundle_dmg
import bundle_tree
import check_bundle
import export_source
from testutil import GIT_ENV, archive, commit, compile_c, fake_hdiutil, git, run_main, write_file

MACHO = bytes.fromhex("cffaedfe")
AR_MAGIC = b"!<arch>\n"
MACHO_MAGICS = ("feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca",
                "cafebabf", "bfbafeca")
MACHO_MAGIC_BYTES = {bytes.fromhex(m) for m in MACHO_MAGICS}
DISC_MAGIC = bytes.fromhex("c2339f3d")
APP = "Dragoon.app"
SNAP = "Contents/Resources/source/"
LICENSES = "Contents/Resources/licenses/"
ENGINE = "Contents/Resources/kit/engine.o"
SDL = "Contents/Resources/kit/libSDL3.a"
# Objects compiled from C by the class's setup: the kit's two, as the engine holds the disc ID
# and leaves the game's tables to the game, a stand-in for the app's executables, two with what
# only the game defines and one with names that come close.
OBJECTS = {
    "engine.o": 'extern const unsigned g_recomp_func_count;\nconst char gcn_game_id[] = "GKYE01";\n'
                "unsigned engine_funcs(void) { return g_recomp_func_count; }\n",
    "sdl.o": "int SDL_Fake(void) { return 3; }\n",
    "tool.o": "int main(void) { return 0; }\n",
    "functions.o": "int fn_8000ABCD(int x) { return x + 1; }\nint fn_80003100(int x) { return x * 2; }\n",
    "tables.o": "const unsigned g_recomp_func_count = 0;\n",
    "near.o": "int fn_8000ABC(int x) { return x; }\nint fn_8000ABCDE(int x) { return x; }\n"
              "int my_fn_80003100(int x) { return x; }\nconst unsigned g_recompiled = 0;\n",
}
X86_OBJECTS = ("sdl.o", "functions.o")
SHA1 = "0123456789abcdef0123456789abcdef01234567"
CMAKE = f"""add_subdirectory(gcn-recomp)
gcn_add_game(
  NAME kirby
  DISC_ID GKYE01
  DOL_SHA1 {SHA1})
"""
MANIFEST = """source Contents/Resources/source
budget app 20000
budget dmg 40000
file Contents/Info.plist
file Contents/Resources/third_party/SDL3-3.4.18.tar.gz
macho Contents/MacOS/Dragoon
macho Contents/MacOS/cmake
macho Contents/MacOS/ninja
link Contents/Resources/cmake/bin/cmake ../../../MacOS/cmake
dir Contents/Resources/cmake/share/cmake-4.4/
dir Contents/Resources/licenses/
engine Contents/Resources/kit/engine.o
object Contents/Resources/kit/libSDL3.a
"""


def disc_header() -> bytes:
    return bytes(0x1C) + DISC_MAGIC + bytes(16)


def compile_objects(out: Path) -> dict[str, bytes]:
    """OBJECTS compiled into OUT, by name, and each one also as the only member of an archive
    named for it with .a. X86_OBJECTS are compiled for x86_64 too, as x86_64/NAME and its
    archive, and lipo joins each arm64 archive with each x86_64 one as fat/ARM+X86.a."""
    built = {}
    for arch, names in (("arm64", OBJECTS), ("x86_64", X86_OBJECTS)):
        prefix = "" if arch == "arm64" else "x86_64/"
        for name in names:
            obj = compile_c(OBJECTS[name], out / (prefix + name), debug=False, arch=arch)
            built[prefix + name] = obj.read_bytes()
            built[prefix + obj.stem + ".a"] = archive(obj.with_suffix(".a"), obj).read_bytes()
    for arm in X86_OBJECTS:
        for x86 in X86_OBJECTS:
            name = f"fat/{Path(arm).stem}+{Path(x86).stem}.a"
            (out / name).parent.mkdir(exist_ok=True)
            subprocess.run(["/usr/bin/lipo", "-create", str(out / Path(arm).with_suffix(".a")),
                            str(out / "x86_64" / Path(x86).with_suffix(".a")), "-output", str(out / name)],
                           check=True)
            built[name] = (out / name).read_bytes()
    return built


def ar_archive(*members: tuple[str, bytes]) -> bytes:
    """An ar archive of MEMBERS, (name, data) pairs, written byte by byte."""
    out = bytearray(AR_MAGIC)
    for name, data in members:
        out += f"{name:<16}{0:<12}{0:<6}{0:<6}{644:<8}{len(data):<10}`\n".encode() + data
        out += b"\n" * (len(out) % 2)
    return bytes(out)


def fat_file(*slices: bytes) -> bytes:
    """A fat file holding SLICES, each marked arm64 and starting on a 4096-byte boundary."""
    out = bytearray(bytes.fromhex("cafebabe") + len(slices).to_bytes(4, "big"))
    offset = 4096
    for data in slices:
        out += b"".join(n.to_bytes(4, "big") for n in (0x0100000C, 0, offset, len(data), 12))
        offset += -(-len(data) // 4096) * 4096
    for data in slices:
        out += bytes(-len(out) % 4096) + data
    return bytes(out)


def build_app(app: Path, snapshot: Path, objects: dict[str, bytes]) -> None:
    """A small app in the layout of the manifest above, holding SNAPSHOT as its source and
    the engine and SDL from OBJECTS as its kit."""
    files = {
        ENGINE: objects["engine.o"],
        SDL: objects["sdl.a"],
        "Contents/Info.plist": "<plist/>\n",
        "Contents/MacOS/Dragoon": objects["tool.o"],
        "Contents/MacOS/cmake": objects["tool.o"],
        "Contents/MacOS/ninja": objects["tool.o"],
        "Contents/Resources/cmake/share/cmake-4.4/Modules/FindThing.cmake": "find_package(Thing)\n",
        "Contents/Resources/third_party/SDL3-3.4.18.tar.gz": b"an SDL tarball",
        "Contents/Resources/licenses/CMake.txt": "BSD 3-clause\n",
    }
    for name, data in files.items():
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write_file(path.parent, path.name, data)
    (app / "Contents/Resources/cmake/bin").mkdir(parents=True)
    os.symlink("../../../MacOS/cmake", app / "Contents/Resources/cmake/bin/cmake")
    shutil.copytree(snapshot, app / SNAP.rstrip("/"), symlinks=True)


class BundleTestCase(unittest.TestCase):
    """A Dragoon-shaped repository, the snapshot export_source.py makes of it and a small app
    around that snapshot, at paths with spaces. Each test gets its own copy of the app.

    Exporting takes about 0.3 s, so a test copies the class's snapshot instead, unless its
    class sets real_export. Those run export_source.py for real."""

    real_export = False

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, GIT_ENV)
        patch.start()
        cls.addClassCleanup(patch.stop)
        cls.root = Path(tmp.name)
        cls.repo = cls.root / "Dragoon repo"
        pin = commit(cls.repo / "gcn-recomp", {"CMakeLists.txt": "engine\n", "runtime/a file.cpp": "int a;\n"})
        git(cls.repo, "init", "-q", "-b", "main")
        git(cls.repo, "update-index", "--add", "--cacheinfo", f"160000,{pin},gcn-recomp")
        cls.head = commit(cls.repo, {
            ".gitignore": "rom/*\n!rom/README.md\nbuild*/\nsaves/\n",
            ".gitmodules": '[submodule "gcn-recomp"]\n\tpath = gcn-recomp\n\turl = https://example.com/e\n',
            "CMakeLists.txt": CMAKE,
            "rom/README.md": "Put your disc here.\n",
            "tools/a tool.py": "print('hi')\n",
        })
        cls.snapshot = cls.root / "snapshot"
        cls.info = export_source.export(cls.repo, cls.snapshot)
        cls.objects = compile_objects(cls.root / "objects")
        cls.template = cls.root / "template" / APP
        build_app(cls.template, cls.snapshot, cls.objects)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.dist = self.dir / "dist dir"
        self.dist.mkdir()
        self.app = self.dist / APP
        shutil.copytree(self.template, self.app, symlinks=True)
        self.manifest = write_file(self.dir, "bundle manifest.txt", MANIFEST)

    def plant(self, name: str, data: bytes | str = b"x", app: Path | None = None) -> Path:
        """Write NAME, relative to the app, creating its directories."""
        path = (app or self.app) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return write_file(path.parent, path.name, data)

    def copy_snapshot(self, repo: Path, commit: str, out: Path) -> dict[str, str]:
        shutil.copytree(self.snapshot, out, symlinks=True)
        return self.info

    def check(self, path: Path | None = None, *extra: str) -> tuple[int, list[str], str]:
        if self.real_export:
            export = contextlib.nullcontext()
        else:
            export = mock.patch.object(check_bundle, "reference_snapshot", self.copy_snapshot)
        with export:
            code, out, err = run_main(check_bundle.main, str(path or self.app), "--commit",
                                      self.head, "--repo", str(self.repo), "--manifest",
                                      str(self.manifest), *extra)
        return code, out.splitlines(), err

    def assert_findings(self, *lines: str, path: Path | None = None) -> None:
        code, out, err = self.check(path)
        self.assertEqual((code, sorted(out), err), (1, sorted(lines), ""))


class CleanTest(BundleTestCase):
    real_export = True

    def test_a_clean_fixture_passes_and_prints_nothing(self):
        self.assertEqual(self.check(), (0, [], ""))

    def test_any_app_name_and_a_path_with_spaces_will_do(self):
        moved = self.dir / "other place" / "Dragoon Dev.app"
        moved.parent.mkdir()
        shutil.move(str(self.app), moved)
        self.assertEqual(self.check(moved), (0, [], ""))

    def test_the_fixtures_disc_is_the_one_the_real_tree_builds(self):
        text = (export_source.ROOT / "CMakeLists.txt").read_text()
        self.assertEqual(export_source.game_ids(text)[0], "GKYE01")
        self.assertEqual(export_source.game_ids(CMAKE)[0], "GKYE01")


class PlantedFileTest(BundleTestCase):
    def test_a_disc_image_in_the_snapshot(self):
        self.plant(SNAP + "rom/game.iso", disc_header())
        self.assert_findings(
            f"game data: {SNAP}rom/game.iso",
            f"disc image: {SNAP}rom/game.iso (GameCube magic at 0x1C)",
            f"extra in the source: {SNAP}rom/game.iso")

    def test_generated_code_in_the_snapshot(self):
        self.plant(SNAP + "build/gen/f0.c", "int f0(void);\n")
        self.assert_findings(f"game data: {SNAP}build/gen/f0.c",
                             f"extra in the source: {SNAP}build/gen/f0.c")

    def test_a_built_game_outside_the_snapshot(self):
        self.plant("Contents/Resources/dragoon", self.objects["tool.o"])
        self.assert_findings("not on the manifest: Contents/Resources/dragoon",
                             "executable not on the manifest: Contents/Resources/dragoon")

    def test_a_memory_card(self):
        with self.subTest("in the snapshot"):
            self.plant(SNAP + "saves/memcard_a.raw")
            self.assert_findings(f"game data: {SNAP}saves/memcard_a.raw",
                                 f"extra in the source: {SNAP}saves/memcard_a.raw")
        with self.subTest("outside it"):
            os.unlink(self.app / SNAP / "saves/memcard_a.raw")
            os.rmdir(self.app / SNAP / "saves")
            self.plant("Contents/Resources/saves/memcard_a.raw")
            self.assert_findings("not on the manifest: Contents/Resources/saves/memcard_a.raw",
                                 "game data: Contents/Resources/saves/memcard_a.raw")

    def test_an_extra_file_in_the_snapshot(self):
        self.plant(SNAP + "docs/notes.md", "mine\n")
        self.assert_findings(f"extra in the source: {SNAP}docs/notes.md")

    def test_the_disc_magic_under_a_harmless_name(self):
        self.plant(LICENSES + "notes.txt", disc_header())
        self.assert_findings(f"disc image: {LICENSES}notes.txt (GameCube magic at 0x1C)")

    def test_a_ciso_header_under_a_harmless_name(self):
        self.plant(LICENSES + "readme.txt", b"CISO" + bytes(100))
        self.assert_findings(f"disc image: {LICENSES}readme.txt (CISO header)")

    def test_the_magic_has_to_sit_at_0x1c(self):
        self.plant(LICENSES + "magic.txt", bytes(0x1D) + DISC_MAGIC)
        self.plant(LICENSES + "ciso.txt", b" CISO")
        self.assertEqual(self.check(), (0, [], ""))

    def test_a_symlink_not_on_the_manifest(self):
        os.symlink("/Users/someone/Kirby Air Ride (USA).gcm", self.app / "Contents/Resources/disc")
        self.assert_findings("symlink not on the manifest: Contents/Resources/disc "
                             "(-> /Users/someone/Kirby Air Ride (USA).gcm)")

    def test_a_file_over_budget(self):
        self.plant("Contents/Resources/third_party/SDL3-3.4.18.tar.gz", bytes(25000))
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(len(out), 1)
        self.assertRegex(out[0], rf"^over budget: {APP} \(2\d{{4}} bytes, budget 20000\)$")

    def test_a_bundle_exactly_at_its_budget_passes_and_a_byte_more_fails(self):
        tarball = "Contents/Resources/third_party/SDL3-3.4.18.tar.gz"
        room = 20000 - sum(bundle_tree.scan(self.app).files.values())  # budget app 20000
        size = (self.app / tarball).stat().st_size + room
        self.plant(tarball, bytes(size))
        self.assertEqual(self.check(), (0, [], ""))
        self.plant(tarball, bytes(size + 1))
        self.assert_findings(f"over budget: {APP} (20001 bytes, budget 20000)")

    def test_what_the_build_leaves_behind_fails_anywhere(self):
        names = ["gen/f0.c", "rels/r0.rel", "main.dol", "CMakeCache.txt", "build.ninja",
                 "memcard_a", ".shader-warmup", "inputs/p1.txt"]
        # An app on a volume that ignores case builds these the same as the names above.
        names += ["Gen/f0.c", "RELS/x", "Main.DOL", "cmakecache.txt", "Build.ninja", "MemCard_a",
                  ".Shader-Warmup", "Inputs/p1.txt"]
        for where in (LICENSES, "Contents/Resources/cmake/share/cmake-4.4/", SNAP + "gcn-recomp/"):
            for name in names:
                with self.subTest(where=where, name=name):
                    path = self.plant(where + name)
                    code, out, _ = self.check()
                    self.assertEqual(code, 1)
                    self.assertIn(f"game data: {where}{name}", out)
                    os.unlink(path)
                    for parent in path.parents:
                        if parent.name.lower() in ("gen", "rels", "inputs"):
                            os.rmdir(parent)

    def test_a_dev_trees_disc_link_and_empty_build_directory(self):
        os.symlink("/Users/someone/Kirby Air Ride (USA).gcm", self.app / SNAP / "rom/game.iso")
        (self.app / SNAP / "build").mkdir()
        self.assert_findings(f"game data: {SNAP}rom/game.iso",
                             f"extra in the source: {SNAP}rom/game.iso",
                             f"extra in the source: {SNAP}build/")


class ExecutableTest(BundleTestCase):
    def test_every_macho_magic_at_an_unlisted_path_fails_and_is_read(self):
        bench = LICENSES + "dragoon_bench"
        for magic in MACHO_MAGICS:
            with self.subTest(magic=magic):
                self.plant(bench, bytes.fromhex(magic) + b"code")
                # b"code" is no fat header's count of slices.
                why = "its fat header doesn't fit the file" if magic in ("cafebabe", "cafebabf") else "nm exited 1"
                self.assert_findings(f"executable not on the manifest: {bench}",
                                     f"unreadable object: {bench} ({why})")

    def test_a_macho_in_the_snapshot_fails(self):
        self.plant(SNAP + "tools/dragoon", self.objects["tool.o"])
        self.assert_findings(f"executable not on the manifest: {SNAP}tools/dragoon",
                             f"extra in the source: {SNAP}tools/dragoon")

    def test_a_macho_at_a_path_listed_as_a_plain_file_fails(self):
        self.plant("Contents/Resources/third_party/SDL3-3.4.18.tar.gz", self.objects["tool.o"])
        self.assert_findings(
            "executable not on the manifest: Contents/Resources/third_party/SDL3-3.4.18.tar.gz")

    def test_the_launchers_name_in_another_case_is_another_path(self):
        os.unlink(self.app / "Contents/MacOS/Dragoon")
        self.plant("Contents/MacOS/dragoon", self.objects["tool.o"])
        self.assert_findings("not on the manifest: Contents/MacOS/dragoon",
                             "executable not on the manifest: Contents/MacOS/dragoon")


class ObjectTest(BundleTestCase):
    def test_an_archive_under_any_name_needs_an_object_line(self):
        for path, data in ((LICENSES + "notes.txt", "sdl.a"), ("Contents/MacOS/ninja", "sdl.a"),
                           ("Contents/MacOS/ninja", "fat/sdl+sdl.a")):
            with self.subTest(path=path, data=data):
                self.plant(path, self.objects[data])
                self.assert_findings(f"object not on the manifest: {path}")
                os.unlink(self.app / path)

    def test_a_member_that_isnt_mach_o_makes_an_archive_unreadable(self):
        # A generic blob with the GameCube magic at 0x1C, as a disc image starts, beside an object.
        blob = ar_archive(("blob.bin", disc_header()), ("sdl.o", self.objects["sdl.o"]))
        for path, kit_file in ((SDL, "sdl.a"), (ENGINE, "engine.o")):
            with self.subTest(path=path):
                self.plant(path, blob)
                self.assertEqual(subprocess.run(["/usr/bin/nm", str(self.app / path)],
                                                capture_output=True).returncode, 0)
                findings = [f"unreadable object: {path} (its member blob.bin isn't Mach-O)"]
                if path == ENGINE:
                    findings.append(f"engine not a Mach-O object: {ENGINE}")
                self.assert_findings(*findings)
                self.plant(path, self.objects[kit_file])

    def test_a_member_in_a_fat_files_slice_is_read_too(self):
        self.plant(SDL, fat_file(ar_archive(("sdl.o", self.objects["sdl.o"]), ("blob.bin", b"generic"))))
        self.assert_findings(f"unreadable object: {SDL} (its member blob.bin isn't Mach-O)")

    def test_the_symbol_table_member_isnt_mach_o_and_passes(self):
        # ar's first member, named after its BSD header, is the symbol table.
        self.assertEqual(self.objects["sdl.a"][8:13], b"#1/20")
        self.assertTrue(self.objects["sdl.a"][68:88].startswith(b"__.SYMDEF"))
        self.assertNotIn(self.objects["sdl.a"][88:92], MACHO_MAGIC_BYTES)
        self.assertEqual(self.check(), (0, [], ""))

    def test_an_archive_or_fat_file_that_doesnt_parse_is_unreadable(self):
        cases = {
            "a cut header": (AR_MAGIC + b"sdl.o   ", "its member header at byte 8 can't be read"),
            "a member too long": (ar_archive(("sdl.o", self.objects["sdl.o"]))[:-100],
                                  "its member sdl.o runs past its end"),
            "a fat header too long": (bytes.fromhex("cafebabe") + (3).to_bytes(4, "big") + bytes(30),
                                      "its fat header doesn't fit the file"),
        }
        for why, (data, detail) in cases.items():
            with self.subTest(why):
                self.plant(SDL, data)
                self.assert_findings(f"unreadable object: {SDL} ({detail})")

    def test_the_engine_has_to_be_a_thin_mach_o_object(self):
        executable = bytearray(self.objects["engine.o"])
        executable[12] = 2  # MH_EXECUTE
        for name, data in (("an archive", self.objects["engine.a"]), ("an executable", bytes(executable)),
                           ("a fat archive", self.objects["fat/sdl+sdl.a"])):
            with self.subTest(name):
                self.plant(ENGINE, data)
                code, out, _ = self.check()
                self.assertEqual(code, 1)
                self.assertIn(f"engine not a Mach-O object: {ENGINE}", out)

    def test_a_thin_object_at_a_macho_path_is_read(self):
        self.plant("Contents/MacOS/ninja", self.objects["functions.o"])
        self.assert_findings("game code: Contents/MacOS/ninja (defines _fn_80003100 and 1 more)")

    def test_a_fat_archive_is_read_in_every_architecture(self):
        self.plant(SDL, self.objects["fat/sdl+functions.a"])
        self.assert_findings(f"game code: {SDL} (defines _fn_80003100 and 1 more)")

    def test_names_close_to_the_games_pass(self):
        self.plant(SDL, self.objects["near.a"])
        self.assertEqual(self.check(), (0, [], ""))

    def test_a_file_named_a_or_o_needs_an_object_line(self):
        for name in ("engine.o", "libgame.a", "Engine.O", "LIBGAME.A"):
            with self.subTest(name=name):
                path = self.plant(LICENSES + name, self.objects["sdl.o"])
                self.assert_findings(f"object not on the manifest: {LICENSES}{name}")
                os.unlink(path)

    def test_a_file_line_wont_do_for_an_object(self):
        write_file(self.dir, "bundle manifest.txt", MANIFEST + "file Contents/Resources/kit/sdl.o\n")
        self.plant("Contents/Resources/kit/sdl.o", self.objects["sdl.o"])
        self.assert_findings("object not on the manifest: Contents/Resources/kit/sdl.o")

    def test_an_archive_defining_the_games_functions_fails(self):
        self.plant(SDL, self.objects["functions.a"])
        self.assert_findings(f"game code: {SDL} (defines _fn_80003100 and 1 more)")

    def test_an_object_defining_the_games_tables_fails(self):
        self.plant(ENGINE, self.objects["tables.o"])
        self.assert_findings(f"game code: {ENGINE} (defines _g_recomp_func_count)")

    def test_an_unlisted_object_is_read_too(self):
        self.plant(LICENSES + "game.o", self.objects["functions.o"])
        self.assert_findings(f"object not on the manifest: {LICENSES}game.o",
                             f"game code: {LICENSES}game.o (defines _fn_80003100 and 1 more)")

    def test_an_object_nm_cant_read_fails(self):
        self.plant(SDL, "not an archive\n")
        self.assert_findings(f"unreadable object: {SDL} (nm exited 1)")

    def test_the_engine_may_use_the_games_tables(self):
        listed = subprocess.run(["/usr/bin/nm", "-j", str(self.app / ENGINE)], capture_output=True,
                                text=True, check=True).stdout.split()
        self.assertIn("_g_recomp_func_count", listed)
        self.assertEqual(self.check(), (0, [], ""))

    def test_the_engine_may_hold_the_disc_id(self):
        self.assertIn(b"GKYE01", (self.app / ENGINE).read_bytes())
        self.assertEqual(self.check(), (0, [], ""))

    def test_the_disc_id_in_another_object_fails(self):
        self.plant(SDL, self.objects["engine.a"])
        self.assert_findings(f"disc ID: {SDL} (GKYE01 outside the source)")


class ContentTest(BundleTestCase):
    def test_the_disc_id_outside_the_snapshot_fails(self):
        self.plant(LICENSES + "CMake.txt", "BSD 3-clause\nGKYE01\n")
        self.assert_findings(f"disc ID: {LICENSES}CMake.txt (GKYE01 outside the source)")

    def test_the_disc_id_inside_the_snapshot_is_fine(self):
        self.assertIn(b"GKYE01", (self.app / SNAP / "CMakeLists.txt").read_bytes())
        self.assertEqual(self.check(), (0, [], ""))

    def test_a_disc_id_inside_a_binary_fails(self):
        self.plant("Contents/MacOS/ninja", self.objects["engine.o"])
        self.assert_findings("disc ID: Contents/MacOS/ninja (GKYE01 outside the source)")


class ContainsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_finds_a_needle_across_a_block_boundary(self):
        for offset in range(0, 20):
            with self.subTest(offset=offset):
                path = write_file(self.dir, "f", bytes(offset) + b"GKYE01" + bytes(30))
                self.assertTrue(bundle_checks.contains(path, b"GKYE01", block=8))

    def test_does_not_find_what_is_not_there(self):
        path = write_file(self.dir, "f", b"GKYE0" + bytes(30) + b"1GKYE")
        self.assertFalse(bundle_checks.contains(path, b"GKYE01", block=8))
        self.assertFalse(bundle_checks.contains(write_file(self.dir, "empty", b""), b"GKYE01"))


class SourceTest(BundleTestCase):
    real_export = True

    def test_a_changed_file(self):
        self.plant(SNAP + "tools/a tool.py", "print('bye')\n")
        self.assert_findings(f"changed in the source: {SNAP}tools/a tool.py")

    def test_a_missing_file(self):
        shutil.rmtree(self.app / SNAP / "gcn-recomp/runtime")
        self.assert_findings(f"missing from the source: {SNAP}gcn-recomp/runtime/a file.cpp")

    def test_a_tampered_source_manifest(self):
        self.plant(SNAP + "source-manifest.txt", "")
        self.assert_findings(f"changed in the source: {SNAP}source-manifest.txt")

    def test_a_snapshot_from_another_commit(self):
        self.plant(SNAP + "source-info.json", "{}\n")
        self.assert_findings(f"changed in the source: {SNAP}source-info.json")

    def test_no_snapshot_at_all(self):
        shutil.rmtree(self.app / SNAP)
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn(f"missing from the source: {SNAP}CMakeLists.txt", out)

    def test_a_later_commit_makes_the_old_snapshot_stale(self):
        repo = self.dir / "repo copy"
        shutil.copytree(self.repo, repo, symlinks=True)
        head = commit(repo, {"tools/a tool.py": "print('later')\n"})
        code, out, err = run_main(check_bundle.main, str(self.app), "--commit", head, "--repo",
                                  str(repo), "--manifest", str(self.manifest))
        self.assertEqual((code, err), (1, ""))
        self.assertIn(f"changed in the source: {SNAP}tools/a tool.py", out)

    def test_a_snapshot_file_moved_out_is_missing_and_its_disc_id_shows(self):
        shutil.move(str(self.app / SNAP / "CMakeLists.txt"), self.app / LICENSES / "CMakeLists.txt")
        self.assert_findings(f"missing from the source: {SNAP}CMakeLists.txt",
                             f"disc ID: {LICENSES}CMakeLists.txt (GKYE01 outside the source)")


class SymlinkTest(BundleTestCase):
    def test_a_listed_link_with_another_target(self):
        link = self.app / "Contents/Resources/cmake/bin/cmake"
        os.unlink(link)
        os.symlink("../../../MacOS/ninja", link)
        self.assert_findings("symlink target: Contents/Resources/cmake/bin/cmake "
                             "(-> ../../../MacOS/ninja, the manifest has ../../../MacOS/cmake)")

    def test_a_link_under_an_allowed_prefix_still_has_to_be_listed(self):
        os.symlink("../../MacOS/cmake", self.app / (LICENSES + "cmake"))
        self.assert_findings(f"symlink not on the manifest: {LICENSES}cmake (-> ../../MacOS/cmake)")

    def test_a_link_is_never_followed(self):
        os.symlink("/dev/null", self.app / (SNAP + "empty"))
        self.assert_findings(f"extra in the source: {SNAP}empty")


class OddEntryTest(BundleTestCase):
    def test_an_empty_directory_outside_the_manifest(self):
        (self.app / "Contents/Resources/build").mkdir()
        self.assert_findings("not on the manifest: Contents/Resources/build/")

    def test_an_empty_snapshot_directory_is_a_missing_source_not_an_unlisted_directory(self):
        shutil.rmtree(self.app / SNAP)
        (self.app / SNAP).mkdir()
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertEqual([line for line in out if line.startswith("not on the manifest")], [])
        self.assertIn(f"missing from the source: {SNAP}CMakeLists.txt", out)

    def test_an_empty_directory_under_a_prefix_is_fine(self):
        (self.app / LICENSES / "empty").mkdir()
        (self.app / "Contents/Resources/cmake/share/cmake-4.4/Empty").mkdir()
        self.assertEqual(self.check(), (0, [], ""))

    def test_a_pipe(self):
        os.mkfifo(self.app / "Contents/Resources/pipe")
        self.assert_findings("not a file or symlink: Contents/Resources/pipe")


class DmgTest(BundleTestCase):
    """The DMG is faked. Attaching it copies <dmg>.contents into the mount point."""

    def setUp(self):
        super().setUp()
        self.records = self.dir / "records.jsonl"
        self.tools = self.dir / "fake tools"
        self.tools.mkdir()
        patch = mock.patch.object(bundle_dmg, "HDIUTIL", str(fake_hdiutil(self.tools, self.records)))
        patch.start()
        self.addCleanup(patch.stop)
        self.dmg = write_file(self.dist, "Dragoon.dmg", b"fake dmg")
        self.contents = self.dist / "Dragoon.dmg.contents"
        self.contents.mkdir()
        shutil.copytree(self.template, self.contents / APP, symlinks=True)
        os.symlink("/Applications", self.contents / "Applications")

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.records.read_text().splitlines()]

    def assert_dmg_findings(self, *lines: str) -> None:
        self.assert_findings(*lines, path=self.dmg)

    def test_a_clean_dmg_passes(self):
        self.assertEqual(self.check(self.dmg), (0, [], ""))

    def test_it_attaches_read_only_and_always_detaches(self):
        self.check(self.dmg)
        attach, detach = self.calls()
        self.assertEqual(attach[:4], ["attach", "-readonly", "-nobrowse", "-mountpoint"])
        self.assertEqual(attach[5:], [str(self.dmg)])
        self.assertEqual(detach, ["detach", attach[4]])
        self.assertFalse(Path(attach[4]).exists())

    def test_it_detaches_after_findings_too(self):
        self.plant("Contents/Resources/dragoon", MACHO, app=self.contents / APP)
        self.assertEqual(self.check(self.dmg)[0], 1)
        self.assertEqual([c[0] for c in self.calls()], ["attach", "detach"])

    def test_the_app_inside_gets_checks_1_to_5(self):
        self.plant(SNAP + "rom/game.iso", disc_header(), app=self.contents / APP)
        self.assert_dmg_findings(
            f"game data: {SNAP}rom/game.iso",
            f"disc image: {SNAP}rom/game.iso (GameCube magic at 0x1C)",
            f"extra in the source: {SNAP}rom/game.iso")

    def test_a_dmg_over_budget(self):
        write_file(self.dist, "Dragoon.dmg", bytes(41000))
        self.assert_dmg_findings("over budget: Dragoon.dmg (41000 bytes, budget 40000)")

    def test_a_dmg_exactly_at_its_budget_passes_and_a_byte_more_fails(self):
        write_file(self.dist, "Dragoon.dmg", bytes(40000))
        self.assertEqual(self.check(self.dmg), (0, [], ""))
        write_file(self.dist, "Dragoon.dmg", bytes(40001))
        self.assert_dmg_findings("over budget: Dragoon.dmg (40001 bytes, budget 40000)")

    def test_something_besides_the_app_and_the_link(self):
        write_file(self.contents, "README.txt", "read me")
        (self.contents / ".fseventsd").mkdir()
        self.assert_dmg_findings("unexpected in the DMG: .fseventsd", "unexpected in the DMG: README.txt")

    def test_no_applications_link(self):
        os.unlink(self.contents / "Applications")
        self.assert_dmg_findings("missing from the DMG: Applications")

    def test_an_applications_link_to_somewhere_else(self):
        os.unlink(self.contents / "Applications")
        os.symlink("/Users/someone/Applications", self.contents / "Applications")
        self.assert_dmg_findings("wrong Applications link: Applications (-> /Users/someone/Applications)")

    def test_an_applications_folder_instead_of_a_link(self):
        os.unlink(self.contents / "Applications")
        (self.contents / "Applications").mkdir()
        self.assert_dmg_findings("wrong Applications link: Applications (not a symlink)")

    def test_no_app(self):
        shutil.rmtree(self.contents / APP)
        self.assert_dmg_findings("missing from the DMG: Dragoon.app")

    def test_an_app_that_is_a_link_is_not_followed(self):
        shutil.rmtree(self.contents / APP)
        os.symlink("/Applications/Dragoon.app", self.contents / APP)
        self.assert_dmg_findings("missing from the DMG: Dragoon.app")

    def test_a_dmg_that_will_not_detach_still_reports_its_findings(self):
        self.plant("Contents/Resources/dragoon", MACHO, app=self.contents / APP)
        write_file(self.tools, "detach fails", "")
        code, out, err = self.check(self.dmg)
        self.assertEqual(code, 1)
        self.assertIn("executable not on the manifest: Contents/Resources/dragoon", out)
        self.assertIn("couldn't detach", err)

    def test_a_clean_dmg_that_will_not_detach_exits_2(self):
        write_file(self.tools, "detach fails", "")
        code, out, err = self.check(self.dmg)
        self.assertEqual((code, out), (2, []))
        self.assertIn("couldn't detach", err)

    def test_a_dmg_that_will_not_attach_exits_2(self):
        write_file(self.tools, "attach fails", "")
        code, out, err = self.check(self.dmg)
        self.assertEqual((code, out), (2, []))
        self.assertIn("Resource temporarily unavailable", err)


class RefusalTest(BundleTestCase):
    def assert_refused(self, why: str, *argv: str) -> None:
        code, out, err = run_main(check_bundle.main, *argv)
        self.assertEqual((code, out), (2, ""))
        self.assertIn(why, err)

    def args(self, **change: str) -> list[str]:
        values = {"path": str(self.app), "commit": self.head, "repo": str(self.repo),
                  "manifest": str(self.manifest)}
        values.update(change)
        return [values["path"], "--commit", values["commit"], "--repo", values["repo"],
                "--manifest", values["manifest"]]

    def test_a_path_that_is_not_there(self):
        gone = str(self.dist / "Gone.app")
        self.assert_refused(gone, *self.args(path=gone))

    def test_a_path_that_is_neither_an_app_nor_a_dmg(self):
        zipped = write_file(self.dist, "Dragoon.zip", "x")
        self.assert_refused("isn't a .app or a .dmg", *self.args(path=str(zipped)))

    def test_an_app_that_is_a_file(self):
        flat = write_file(self.dist, "Flat.app", "x")
        self.assert_refused("isn't a directory", *self.args(path=str(flat)))

    def test_no_commit(self):
        code, out, err = run_main(check_bundle.main, str(self.app))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--commit", err)

    def test_a_commit_the_repository_is_not_at(self):
        repo = self.dir / "repo copy"
        shutil.copytree(self.repo, repo, symlinks=True)
        commit(repo, {"tools/a tool.py": "print('later')\n"})
        self.assert_refused(self.head, *self.args(repo=str(repo)))

    def test_a_commit_that_is_not_one(self):
        self.assert_refused("0" * 40, *self.args(commit="0" * 40))

    def test_a_repository_with_uncommitted_changes(self):
        repo = self.dir / "repo copy"
        shutil.copytree(self.repo, repo, symlinks=True)
        write_file(repo, "CMakeLists.txt", CMAKE + "# edited\n")
        self.assert_refused("uncommitted changes", *self.args(repo=str(repo)))

    def test_a_manifest_that_is_not_there(self):
        gone = str(self.dir / "gone.txt")
        self.assert_refused(gone, *self.args(manifest=gone))

    def test_a_manifest_that_does_not_parse(self):
        write_file(self.dir, "bad.txt", "folder x\n")
        self.assert_refused("line 1", *self.args(manifest=str(self.dir / "bad.txt")))

    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = run_main(check_bundle.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
