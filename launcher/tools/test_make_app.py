from __future__ import annotations

import contextlib
import io
import os
import plistlib
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import make_app
# make_app puts the repo's tools/ on the path. The modules below live there.
import bundle_manifest
import bundle_tree
import export_source
import launcher_build
import source_info

ENGINE = "e" * 40
OTHER_ENGINE = "f" * 40
DRAGOON = "d" * 40
VERSION = "1.2.3"
APP = "Dragoon.app"
KIT_DIR = "Contents/Resources/kit/"
SOURCE_DIR = "Contents/Resources/source"
LAUNCHER = b"\xcf\xfa\xed\xfe the launcher"
LICENSE = b"Dragoon's own license\n"
MANIFEST = bundle_manifest.read(make_app.MANIFEST)
# What the manifest says the kit holds, read here so the fake kit can't drift from it.
KIT_FILES = sorted(p[len(KIT_DIR):] for p in MANIFEST.files | MANIFEST.objects if p.startswith(KIT_DIR))

# The fake codesign is one shell script that all the tests share. macOS scans a new executable
# the first time it runs, which costs more than the script does, so each test gets its own
# records file and switches through the environment. A call is recorded to $FAKE_RECORDS as
# "call", one "arg X" per argument, one "file X" per file under its last argument as it ran,
# and "end". A file named "fail codesign" in $FAKE_SWITCHES makes it fail. A file named "another
# run" makes it write a finished Dragoon.app into the output directory first, as a second run
# sharing that directory would. Otherwise it seals the app the way codesign does, with
# Contents/_CodeSignature/CodeResources.
FAKE_CODESIGN = r"""#!/bin/sh
last=
{
  echo call
  for arg in "$@"; do
    printf 'arg %s\n' "$arg"
    last=$arg
  done
  find "$last" -type f | sed 's/^/file /'
  echo end
} >> "$FAKE_RECORDS"
if [ -e "$FAKE_SWITCHES/another run" ]; then
  # Another run sharing the output directory finishes its app while this one is signing.
  out=${last%/*/*}
  mkdir -p "$out/Dragoon.app/Contents"
  echo theirs > "$out/Dragoon.app/Contents/theirs.txt"
fi
if [ -e "$FAKE_SWITCHES/fail codesign" ]; then
  echo "fake codesign: refused to seal the app" >&2
  exit 1
fi
mkdir -p "$last/Contents/_CodeSignature"
echo sealed > "$last/Contents/_CodeSignature/CodeResources"
"""
FAKES: dict[str, str] = {}


def setUpModule() -> None:
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    directory = Path(tmp.name) / "fake tools"
    directory.mkdir()
    path = directory / "codesign"
    path.write_text(FAKE_CODESIGN)
    path.chmod(0o755)
    FAKES["codesign"] = str(path)


def tree(root: Path) -> dict[str, object]:
    """Everything under ROOT by relative path: a file's bytes, a symlink's target and "dir"."""
    found: dict[str, object] = {}
    for parent, dirs, names in os.walk(root):
        for name in dirs + names:
            path = Path(parent, name)
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                found[rel] = ("link", os.readlink(path))
            elif path.is_file():
                try:
                    found[rel] = path.read_bytes()
                except PermissionError:
                    found[rel] = "unreadable"
            else:
                found[rel] = "dir"
    return found


def children(files: dict[str, object], parent: str) -> list[str]:
    """The entries of FILES directly inside the directory PARENT, which is "" for the top."""
    prefix = parent + "/" if parent else ""
    return sorted(p for p in files if p.startswith(prefix) and "/" not in p[len(prefix):])


def make_kit(path: Path, commit: str = ENGINE, src_sha: str = "0" * 64) -> Path:
    """A kit holding what the manifest lists, with a kit.mk that names COMMIT and the src/
    digest SRC_SHA."""
    for rel in KIT_FILES:
        file = path / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"\xcf\xfa\xed\xfe " + rel.encode() + b"\0\xff")
    (path / "kit.mk").write_text(f"GAME_CFLAGS := -O2\nENGINE_COMMIT := {commit}\nSRC_SHA256 := {src_sha}\n")
    return path


def make_source(path: Path, engine: str = ENGINE) -> Path:
    """A snapshot as export_source.py writes one: files, a symlink, source-info.json for ENGINE
    and source-manifest.txt."""
    files = {"LICENSE": LICENSE, "README.md": b"read me\n", "tools/with space.py": b"print('hi')\n",
             "gcn-recomp/LICENSE": b"the engine's license\n", "analysis/table.dat": bytes(range(256)),
             "src/hooks.cpp": b"// the game's hooks\n"}
    for rel, data in files.items():
        file = path / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    os.symlink("../README.md", path / "tools" / "read me link")
    source_info.write(path / source_info.NAME, {"dragoon": DRAGOON, "gcn-recomp": engine,
                                                "disc_id": "ABCD01", "dol_sha1": "a" * 40})
    write_listing(path)
    return path


def write_listing(path: Path) -> None:
    """The source-manifest.txt export_source.py writes for the files under PATH."""
    (path / export_source.MANIFEST).write_text(export_source.format_manifest(export_source.manifest(path)))


class AppTestCase(unittest.TestCase):
    """The fake codesign, a records file and a switches directory of this test's own, and
    inputs for a good run, all at paths with spaces."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.records = self.dir / "records.txt"
        self.switches = self.dir / "fake switches"
        self.switches.mkdir()
        env = mock.patch.dict(os.environ, {"FAKE_RECORDS": str(self.records),
                                           "FAKE_SWITCHES": str(self.switches)})
        env.start()
        self.addCleanup(env.stop)
        patch = mock.patch.object(make_app, "CODESIGN", FAKES["codesign"])
        patch.start()
        self.addCleanup(patch.stop)
        self.out = self.dir / "out dir"
        self.out.mkdir()
        self.version = VERSION
        self.launcher = self.dir / "built launcher"
        self.launcher.write_bytes(LAUNCHER)
        self.launcher.chmod(0o644)
        self.source = make_source(self.dir / "dragoon source")
        self.kit = make_kit(self.dir / "engine kit", src_sha=export_source.src_digest(self.source))

    def switch(self, *names: str) -> None:
        for name in names:
            (self.switches / name).write_text("")

    def run_tool(self, without: str = "", extra: tuple[str, ...] = ()) -> tuple[int, str, str]:
        """Run the tool on the inputs, leaving out the flag WITHOUT and adding EXTRA words."""
        flags = {"--out": str(self.out), "--version": self.version, "--launcher": str(self.launcher),
                 "--kit": str(self.kit), "--source": str(self.source)}
        flags.pop(without, None)
        argv = [word for pair in flags.items() for word in pair] + list(extra)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = make_app.main(argv)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def build(self) -> Path:
        """A good run, which prints the app's path."""
        code, out, err = self.run_tool()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, f"{self.out / APP}\n")
        return self.out / APP

    def calls(self) -> list[dict]:
        """What the fake codesign recorded: argv and the files it found under the app."""
        calls: list[dict] = []
        if not self.records.exists():
            return calls
        for line in self.records.read_text().splitlines():
            key, _, value = line.partition(" ")
            if key == "call":
                calls.append({"argv": [], "files": []})
            elif key == "arg":
                calls[-1]["argv"].append(value)
            elif key == "file":
                calls[-1]["files"].append(value)
        return calls

    def everything(self) -> dict[str, object]:
        """All that the test directory holds, but for what the fakes record."""
        found = tree(self.dir)
        found.pop("records.txt", None)
        return found


class ManifestTest(unittest.TestCase):
    def test_the_manifest_lists_a_kit_to_make_the_fake_from(self):
        self.assertIn("engine.o", KIT_FILES)
        self.assertIn("kit.mk", KIT_FILES)

    def test_the_commit_check_is_the_launchers_own(self):
        self.assertIs(make_app.kit_problem, launcher_build.kit_problem)


class LayoutTest(AppTestCase):
    def test_a_run_makes_the_app_and_nothing_else_in_out(self):
        self.build()
        self.assertEqual(os.listdir(self.out), [APP])

    def test_the_app_holds_the_launcher_the_kit_the_snapshot_and_a_license_and_is_sealed(self):
        files = tree(self.build())
        self.assertEqual(children(files, ""), ["Contents"])
        self.assertEqual(children(files, "Contents"), ["Contents/Info.plist", "Contents/MacOS",
                                                       "Contents/Resources", "Contents/_CodeSignature"])
        self.assertEqual(children(files, "Contents/MacOS"), ["Contents/MacOS/Dragoon"])
        self.assertEqual(children(files, "Contents/Resources"),
                         ["Contents/Resources/kit", "Contents/Resources/licenses",
                          "Contents/Resources/source"])
        self.assertEqual(children(files, "Contents/_CodeSignature"),
                         ["Contents/_CodeSignature/CodeResources"])

    def test_the_launcher_is_there_with_mode_0755(self):
        app = self.build()
        launcher = app / "Contents" / "MacOS" / "Dragoon"
        self.assertEqual(launcher.read_bytes(), LAUNCHER)
        self.assertEqual(stat.S_IMODE(launcher.stat().st_mode), 0o755)

    def test_the_kit_arrives_byte_for_byte(self):
        before = tree(self.kit)
        app = self.build()
        self.assertEqual(tree(app / KIT_DIR), before)
        self.assertEqual(tree(self.kit), before)

    def test_the_snapshot_arrives_byte_for_byte_symlink_and_all(self):
        before = tree(self.source)
        app = self.build()
        self.assertEqual(tree(app / SOURCE_DIR), before)
        self.assertEqual(tree(self.source), before)
        self.assertEqual(before["tools/read me link"], ("link", "../README.md"))

    def test_the_licenses_hold_dragoons_own_and_nothing_else(self):
        app = self.build()
        self.assertEqual(tree(app / "Contents/Resources/licenses"), {"Dragoon.txt": LICENSE})

    def test_every_file_outside_the_snapshot_is_one_the_manifest_allows(self):
        app = self.build()
        found = bundle_tree.scan(app)
        outside = [p for p in found.files if not p.startswith(SOURCE_DIR + "/")]
        self.assertGreater(len(outside), len(KIT_FILES))
        for path in outside:
            with self.subTest(path):
                self.assertTrue(MANIFEST.allows_file(path))
        self.assertEqual([p for p in found.links if not p.startswith(SOURCE_DIR + "/")], [])
        self.assertEqual([p for p in found.empty_dirs if not p.startswith(SOURCE_DIR + "/")], [])
        self.assertEqual(found.others, [])

    def test_an_out_directory_that_is_missing_is_made(self):
        self.out = self.dir / "not yet" / "out dir"
        self.build()
        self.assertTrue((self.out / APP).is_dir())

    def test_other_files_in_out_are_left_alone(self):
        (self.out / "earlier build.txt").write_text("x")
        self.build()
        self.assertEqual(sorted(os.listdir(self.out)), [APP, "earlier build.txt"])
        self.assertEqual((self.out / "earlier build.txt").read_text(), "x")


class PlistTest(AppTestCase):
    def plist(self, app: Path) -> dict:
        with (app / "Contents" / "Info.plist").open("rb") as f:
            return plistlib.load(f)

    def test_the_plist_has_the_template_and_the_version_and_nothing_else(self):
        self.assertEqual(self.plist(self.build()), {
            "CFBundleIdentifier": "io.github.lunchbox-recomp.dragoon",
            "CFBundleExecutable": "Dragoon",
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": "Dragoon",
            "CFBundlePackageType": "APPL",
            "LSMinimumSystemVersion": "14.0",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
        })

    def test_the_version_goes_into_both_version_keys(self):
        for version in ("1", "0.1", "10.20.30"):
            with self.subTest(version):
                self.version = version
                self.out = self.dir / f"out {version}"
                plist = self.plist(self.build())
                self.assertEqual((plist["CFBundleShortVersionString"], plist["CFBundleVersion"]),
                                 (version, version))

    def test_the_template_has_no_version_of_its_own_and_no_icon(self):
        with make_app.TEMPLATE.open("rb") as f:
            template = plistlib.load(f)
        self.assertNotIn("CFBundleShortVersionString", template)
        self.assertNotIn("CFBundleVersion", template)
        self.assertEqual([k for k in template if "Icon" in k], [])


class SealTest(AppTestCase):
    def test_codesign_seals_the_whole_app_ad_hoc_once(self):
        self.build()
        (call,) = self.calls()
        self.assertEqual(call["argv"][:3], ["--force", "--sign", "-"])
        self.assertEqual(len(call["argv"]), 4)  # no --deep, no -o runtime, no --timestamp

    def test_the_app_is_built_under_a_temporary_name_in_out_then_renamed(self):
        app = self.build()
        (call,) = self.calls()
        built = Path(call["argv"][-1])
        self.assertNotEqual(built, app)
        self.assertEqual(built.parent.parent, self.out)
        self.assertFalse(built.exists(), "the temporary app is still there")
        sealed = f"{built}/Contents/_CodeSignature/CodeResources"
        want = sorted(f"{built}/{p}" for p, v in tree(app).items()
                      if isinstance(v, bytes) and p != "Contents/_CodeSignature/CodeResources")
        self.assertNotIn(sealed, call["files"])
        self.assertEqual(sorted(call["files"]), sorted(want))  # all in place when codesign ran


class RefusalTest(AppTestCase):
    def assert_refused(self, why: str, **kwargs) -> None:
        """Exit 2 with one line on stderr that holds WHY, and nothing written or run."""
        before = self.everything()
        code, out, err = self.run_tool(**kwargs)
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.count("\n"), 1, err)
        self.assertTrue(err.startswith("make_app.py: "), err)
        self.assertIn(why, err)
        self.assertEqual(self.calls(), [], "codesign ran")
        self.assertEqual(self.everything(), before)

    def test_each_argument_is_needed(self):
        for flag in ("--out", "--version", "--launcher", "--kit", "--source"):
            with self.subTest(flag):
                self.assert_refused(flag, without=flag)

    def test_an_argument_it_does_not_know(self):
        self.assert_refused("--bogus", extra=("--bogus",))

    def test_a_version_that_is_not_one_to_three_numbers(self):
        for version in ("", "v1", "1.2.3.4", "1.x", "1..2", "1.2-beta", " 1"):
            with self.subTest(version):
                self.version = version
                self.assert_refused("--version")

    def test_a_launcher_that_is_missing_or_a_directory(self):
        self.launcher.unlink()
        self.assert_refused(str(self.launcher))
        self.launcher.mkdir()
        self.assert_refused(str(self.launcher))

    def test_a_kit_or_snapshot_that_is_not_a_directory(self):
        self.kit = self.launcher
        self.assert_refused("--kit")
        self.kit = make_kit(self.dir / "other kit")
        self.source = self.launcher
        self.assert_refused("--source")

    def test_an_out_that_is_a_file(self):
        self.out.rmdir()
        self.out.write_text("x")
        self.assert_refused(str(self.out))

    def test_an_out_inside_the_kit_or_the_snapshot(self):
        # The last two are below a directory that is there, so a guard that stopped at the
        # nearest ancestor that exists would let them through.
        for out in (self.kit / "dist", self.source / "dist", self.kit / "include" / "dist",
                    self.source / "tools" / "dist", self.kit / "include" / "dist" / "deeper"):
            with self.subTest(out.relative_to(self.dir).as_posix()):
                self.out = out
                self.assert_refused("inside")

    def test_an_out_that_reaches_the_kit_or_the_snapshot_through_a_symlink(self):
        os.symlink(self.kit, self.dir / "kit link")
        os.symlink(self.source, self.dir / "source link")
        for link in ("kit link", "source link"):
            with self.subTest(link):
                self.out = self.dir / link / "dist"
                self.assert_refused("inside")

    def test_an_out_inside_the_kit_or_the_snapshot_spelled_in_another_case(self):
        for original in (self.kit, self.source):
            shouted = Path(str(original).upper())
            if not shouted.exists():
                self.skipTest("this volume tells names apart by case")
            with self.subTest(original.name):
                self.out = shouted / "dist"
                self.assert_refused("inside")
                self.out = shouted / "dist" / "deeper"
                self.assert_refused("inside")

    def test_an_app_that_is_already_there(self):
        (self.out / APP / "Contents").mkdir(parents=True)
        (self.out / APP / "Contents" / "mine.txt").write_text("keep")
        self.assert_refused(str(self.out / APP))
        self.assertEqual((self.out / APP / "Contents" / "mine.txt").read_text(), "keep")

    def test_a_link_where_the_app_goes(self):
        os.symlink("nowhere", self.out / APP)
        self.assert_refused(str(self.out / APP))

    def test_a_kit_missing_any_file_the_manifest_lists(self):
        for rel in KIT_FILES:
            with self.subTest(rel):
                file = self.kit / rel
                data = file.read_bytes()
                file.unlink()
                self.assert_refused(rel)
                file.write_bytes(data)

    def test_a_kit_with_a_file_the_manifest_does_not_list(self):
        (self.kit / "extra file.txt").write_text("x")
        self.assert_refused("extra file.txt")
        (self.kit / "extra file.txt").unlink()
        (self.kit / "include" / "empty dir").mkdir()
        self.assert_refused("empty dir")
        (self.kit / "include" / "empty dir").rmdir()
        os.symlink("kit.mk", self.kit / "a link")
        self.assert_refused("a link")

    def test_a_kit_from_another_gcn_recomp_commit(self):
        self.kit = make_kit(self.dir / "old kit", commit=OTHER_ENGINE)
        self.assert_refused(OTHER_ENGINE)
        self.assert_refused(ENGINE)

    def test_a_kit_that_names_no_commit(self):
        (self.kit / "kit.mk").write_text("GAME_CFLAGS := -O2\n")
        self.assert_refused("kit.mk")

    def test_a_kit_built_from_another_src(self):
        self.kit = make_kit(self.dir / "other kit")
        self.assert_refused("the kit's src/ has SHA-256 " + "0" * 64)

    def test_a_snapshot_missing_any_of_its_own_files(self):
        for rel in (source_info.NAME, export_source.MANIFEST, "LICENSE", "README.md",
                    "tools/with space.py", "tools/read me link", "gcn-recomp/LICENSE"):
            with self.subTest(rel):
                file = self.source / rel
                keep = file.read_bytes() if not file.is_symlink() else os.readlink(file)
                file.unlink()
                self.assert_refused(rel)
                if isinstance(keep, bytes):
                    file.write_bytes(keep)
                else:
                    os.symlink(keep, file)

    def test_a_snapshot_with_a_file_edited_since_its_listing_was_written(self):
        (self.source / "README.md").write_text("read me, but different\n")
        self.assert_refused(f"differs from its {export_source.MANIFEST} at README.md")
        (self.source / "README.md").write_text("read me\n")
        (self.source / "tools" / "with space.py").write_text("print('bye')\n")
        self.assert_refused("tools/with space.py")

    def test_a_snapshot_with_a_file_its_listing_does_not_have(self):
        (self.source / "extra file.txt").write_text("x")
        self.assert_refused(f"differs from its {export_source.MANIFEST} at extra file.txt")
        (self.source / "extra file.txt").unlink()
        os.symlink("README.md", self.source / "extra link")
        self.assert_refused("extra link")

    def test_a_snapshot_whose_listing_is_edited(self):
        listing = self.source / export_source.MANIFEST
        listing.write_text(listing.read_text() + "\n")
        self.assert_refused(f"differs from its {export_source.MANIFEST}")

    def test_a_snapshot_whose_source_info_cannot_be_read(self):
        (self.source / source_info.NAME).write_text("{}")
        write_listing(self.source)  # so the listing matches and the file itself is what's wrong
        self.assert_refused(source_info.NAME)

    def test_a_snapshot_of_another_commit_than_the_kits(self):
        self.source = make_source(self.dir / "newer source", engine=OTHER_ENGINE)
        self.assert_refused(OTHER_ENGINE)

    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = self.run_tool(extra=("--help",))
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)
        self.assertEqual(self.calls(), [])


class FailureTest(AppTestCase):
    def assert_failed(self, why: str) -> None:
        """Exit 1 with one line on stderr that holds WHY, and no app and nothing else left."""
        before = self.everything()
        code, out, err = self.run_tool()
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err.count("\n"), 1, err)
        self.assertTrue(err.startswith("make_app.py: "), err)
        self.assertIn(why, err)
        self.assertEqual(self.everything(), before)  # no app, no temporary directory, no new directory

    def test_a_failing_codesign_leaves_no_app(self):
        self.switch("fail codesign")
        self.assert_failed("refused to seal the app")
        (call,) = self.calls()
        self.assertTrue(call["files"], "codesign had nothing to seal")

    def test_a_failing_codesign_removes_the_directories_it_made_for_out_and_no_more(self):
        self.switch("fail codesign")
        for out in (self.dir / "new", self.dir / "not yet" / "deeper" / "out dir", self.out / "below"):
            with self.subTest(out.relative_to(self.dir).as_posix()):
                self.out = out
                self.assert_failed("refused to seal the app")
        self.assertTrue((self.dir / "out dir").is_dir())  # it was there before, so it stays

    def test_a_failing_run_leaves_the_app_a_second_run_finished_in_the_same_out(self):
        self.switch("fail codesign", "another run")
        for out in (self.dir / "not yet" / "deeper" / "out dir", self.dir / "new", self.out):
            with self.subTest(out.relative_to(self.dir).as_posix()):
                self.out = out
                code, _, err = self.run_tool()
                self.assertEqual(code, 1)
                self.assertIn("refused to seal the app", err)
                self.assertEqual(os.listdir(out), [APP])  # their app, and not this run's work
                self.assertEqual((out / APP / "Contents" / "theirs.txt").read_text(), "theirs\n")

    def test_a_failing_codesign_says_it_exited_1(self):
        self.switch("fail codesign")
        _, _, err = self.run_tool()
        self.assertIn("codesign exited 1", err)

    def test_a_launcher_that_cannot_be_read_leaves_no_app(self):
        self.launcher.chmod(0)
        self.addCleanup(self.launcher.chmod, 0o644)
        self.assert_failed(str(self.launcher))
        self.assertEqual(self.calls(), [])

    def test_a_codesign_that_is_not_there(self):
        with mock.patch.object(make_app, "CODESIGN", str(self.dir / "no codesign")):
            self.assert_failed("no codesign")

    def test_a_run_after_a_failed_one_works(self):
        self.switch("fail codesign")
        self.assertEqual(self.run_tool()[0], 1)
        (self.switches / "fail codesign").unlink()
        self.build()
        self.assertEqual(os.listdir(self.out), [APP])


if __name__ == "__main__":
    unittest.main()
