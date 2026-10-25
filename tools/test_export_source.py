import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import export_source
import source_info
from testutil import GIT_ENV, commit, git, run_main, write_file

SHA1 = "0123456789abcdef0123456789abcdef01234567"
CMAKE = f"""add_subdirectory(gcn-recomp)
# gcn_add_game(NAME old DISC_ID OLD001 DOL_SHA1 {"f" * 40})
gcn_add_game(
  NAME test
  TITLE "A Test Game"
  DISC_ID TEST01
  DOL_SHA1 {SHA1}
  SYMBOLS ${{CMAKE_SOURCE_DIR}}/analysis/symbols.txt
  FPS 60)
"""
# Extracts like the system tar the first time it runs and fails the second, as a full disk does.
FAKE_TAR = """#!{python}
import os, subprocess, sys
if os.path.exists({marker!r}):
    print("tar: No space left on device", file=sys.stderr)
    sys.exit(1)
open({marker!r}, "w").close()
sys.exit(subprocess.run([{tar!r}, *sys.argv[1:]]).returncode)
"""


class ExportTestCase(unittest.TestCase):
    """A Dragoon-shaped repository whose gcn-recomp is pinned to the older of its two commits,
    with the ignored files a developer's tree has, all under paths with spaces."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.dict(os.environ, GIT_ENV)
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = Path(tmp.name)
        self.repo = self.dir / "Dragoon repo"
        self.engine = self.repo / "gcn-recomp"
        self.pin = commit(self.engine, {"CMakeLists.txt": "engine one\n", "runtime/a file.cpp": "int a;\n"})
        self.newer = commit(self.engine, {"CMakeLists.txt": "engine two\n"})
        git(self.engine, "checkout", "-q", "--detach", self.pin)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "update-index", "--add", "--cacheinfo", f"160000,{self.pin},gcn-recomp")
        self.head = commit(self.repo, {
            ".gitignore": "rom/*\n!rom/README.md\nbuild*/\nsaves/\n",
            ".gitmodules": '[submodule "gcn-recomp"]\n\tpath = gcn-recomp\n\turl = https://example.com/gcn-recomp\n',
            "CMakeLists.txt": CMAKE,
            "rom/README.md": "Put your disc here.\n",
            "tools/a tool.py": "print('hi')\n",
        })
        for name, data in (("rom/game.iso", b"disc"), ("build/gen/f0.c", b"code"),
                           ("saves/memcard_a.raw", b"card")):
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            write_file(self.repo, name, data)
        self.out = self.dir / "the snapshot"

    def export(self) -> tuple[int, str, str]:
        return run_main(export_source.main, str(self.out), "--repo", str(self.repo))

    def files(self) -> list[str]:
        return sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())


class ExportTest(ExportTestCase):
    def test_holds_both_trees_at_their_commits_and_nothing_ignored(self):
        self.assertEqual(self.export()[0], 0)
        self.assertEqual(self.files(), [
            ".gitignore", ".gitmodules", "CMakeLists.txt", "gcn-recomp/CMakeLists.txt",
            "gcn-recomp/runtime/a file.cpp", "rom/README.md", source_info.NAME,
            export_source.MANIFEST, "tools/a tool.py"])
        self.assertEqual((self.out / "CMakeLists.txt").read_text(), CMAKE)
        self.assertEqual((self.out / "gcn-recomp" / "CMakeLists.txt").read_text(), "engine one\n")

    def test_source_info_names_the_commits_and_the_disc(self):
        self.assertEqual(self.export()[0], 0)
        self.assertEqual(source_info.read(self.out / source_info.NAME), {
            "dragoon": self.head, "gcn-recomp": self.pin, "disc_id": "TEST01", "dol_sha1": SHA1})

    def test_the_manifest_lists_every_other_file_by_sha256(self):
        self.assertEqual(self.export()[0], 0)
        want = "".join(f"{hashlib.sha256((self.out / p).read_bytes()).hexdigest()}  {p}\n"
                       for p in self.files() if p != export_source.MANIFEST)
        self.assertEqual((self.out / export_source.MANIFEST).read_text(), want)

    def test_the_snapshots_src_digest_is_the_checkouts(self):
        commit(self.repo, {"src/hooks.cpp": "void hook(void) {}\n", "src/hooks.h": "void hook(void);\n"})
        self.assertEqual(self.export()[0], 0)
        self.assertEqual(export_source.src_digest(self.out), export_source.src_digest(self.repo))

    def test_an_untracked_file_neither_refuses_nor_ships(self):
        write_file(self.repo, "notes.txt", "mine")
        self.assertEqual(self.export()[0], 0)
        self.assertNotIn("notes.txt", self.files())

    def test_a_missing_out_is_made(self):
        self.out = self.dir / "deeper" / "the snapshot"
        self.assertEqual(self.export()[0], 0)
        self.assertIn("CMakeLists.txt", self.files())

    def test_the_systems_tar_extracts_whatever_else_is_on_the_path(self):
        other = self.dir / "other bin"  # where a GNU tar from Homebrew would be
        other.mkdir()
        write_file(other, "tar", "#!/bin/sh\nexit 1\n").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{other}:{os.environ['PATH']}"}):
            self.assertEqual(self.export()[0], 0)
        self.assertIn("CMakeLists.txt", self.files())


class RefusalTest(ExportTestCase):
    def assert_refused(self, why: str) -> None:
        code, out, err = self.export()
        self.assertEqual(code, 2)
        self.assertIn(why, err)
        self.assertEqual(out, "")
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_a_changed_file_in_dragoon(self):
        write_file(self.repo, "CMakeLists.txt", CMAKE + "# edited\n")
        self.assert_refused("CMakeLists.txt")

    def test_a_changed_file_in_gcn_recomp(self):
        write_file(self.engine, "CMakeLists.txt", "edited\n")
        self.assert_refused("CMakeLists.txt")

    def test_gcn_recomp_away_from_its_pin(self):
        git(self.engine, "checkout", "-q", "--detach", self.newer)
        self.assert_refused(self.pin)

    def test_gcn_recomp_not_checked_out(self):
        os.rename(self.engine / ".git", self.dir / "moved.git")
        self.assert_refused("gcn-recomp isn't checked out")

    def test_an_out_that_is_not_empty(self):
        self.out.mkdir()
        write_file(self.out, "left over", "x")
        code, _, err = self.export()
        self.assertEqual(code, 2)
        self.assertIn(str(self.out), err)
        self.assertEqual(os.listdir(self.out), ["left over"])

    def test_a_cmakelists_without_the_disc(self):
        commit(self.repo, {"CMakeLists.txt": "add_subdirectory(gcn-recomp)\n"})
        self.assert_refused("gcn_add_game")

    def export_failing_on_the_engine(self) -> tuple[int, str, str]:
        """Export with the second tar, the engine's, failing as a full disk would."""
        marker = self.dir / "first tar ran"
        fake = write_file(self.dir, "fake tar", FAKE_TAR.format(
            python=sys.executable, tar=export_source.TAR, marker=str(marker)))
        fake.chmod(0o755)
        with mock.patch.object(export_source, "TAR", str(fake)):
            result = self.export()
        self.assertTrue(marker.exists())  # the first tree was written by then
        return result

    def test_a_failing_tar_says_why(self):
        code, out, err = self.export_failing_on_the_engine()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("tar: No space left on device", err)
        self.assertNotIn("non-zero exit status", err)

    def export_with_git_archive_failing(self, returncode: int, stderr: bytes
                                        ) -> tuple[int, str, str]:
        """Export with the engine's git archive failing the way a run of git can."""
        real = subprocess.run

        def run(cmd, *args, **kwargs):
            if cmd[3:4] == ["archive"] and Path(cmd[2]).name == "gcn-recomp":
                raise subprocess.CalledProcessError(returncode, cmd, stderr=stderr)
            return real(cmd, *args, **kwargs)

        with mock.patch.object(export_source.subprocess, "run", run):
            return self.export()

    def test_a_failing_git_archive_says_why(self):
        code, out, err = self.export_with_git_archive_failing(128, b"fatal: not a tree object\n")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("fatal: not a tree object", err)
        self.assertNotIn("non-zero exit status", err)
        self.assertFalse(self.out.exists())

    def test_a_failing_git_archive_that_prints_nothing_gives_its_exit_status(self):
        code, out, err = self.export_with_git_archive_failing(-9, b"")  # killed by a signal
        self.assertEqual((code, out), (2, ""))
        self.assertIn("gcn-recomp archive --format=tar", err)
        self.assertTrue(err.rstrip().endswith("failed: exit -9"), err)
        self.assertFalse(self.out.exists())

    def test_a_failing_git_that_prints_nothing_gives_its_exit_status(self):
        other = self.dir / "other bin"
        other.mkdir()
        write_file(other, "git", "#!/bin/sh\nexit 3\n").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{other}:{os.environ['PATH']}"}):
            code, out, err = self.export()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("git rev-parse --verify", err)
        self.assertTrue(err.rstrip().endswith("failed: exit 3"), err)
        self.assertFalse(self.out.exists())

    def test_a_failure_part_way_leaves_no_out_and_the_next_run_works(self):
        self.assertEqual(self.export_failing_on_the_engine()[0], 2)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.export()[0], 0)
        self.assertIn("gcn-recomp/CMakeLists.txt", self.files())

    def test_a_failure_part_way_empties_an_out_that_was_there(self):
        self.out.mkdir()
        self.assertEqual(self.export_failing_on_the_engine()[0], 2)
        self.assertEqual(os.listdir(self.out), [])
        self.assertEqual(self.export()[0], 0)


class GameIdsTest(unittest.TestCase):
    def test_finds_the_disc_in_the_real_cmakelists(self):
        text = (export_source.ROOT / "CMakeLists.txt").read_text()
        self.assertEqual(export_source.game_ids(text),
                         ("GKYE01", "977533bb96e6a16e127946396489be1b4164ac42"))

    def test_skips_comments(self):
        self.assertEqual(export_source.game_ids(CMAKE), ("TEST01", SHA1))

    def test_refuses_a_missing_or_malformed_value(self):
        for text in ("gcn_add_game(NAME x)", f"gcn_add_game(DISC_ID TEST01 DOL_SHA1 {SHA1[:-1]})",
                     f"gcn_add_game(DISC_ID TEST1 DOL_SHA1 {SHA1})", CMAKE + CMAKE):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    export_source.game_ids(text)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_sorted_relative_paths_with_symlinks_unfollowed(self):
        (self.root / "a dir").mkdir()
        write_file(self.root / "a dir", "b.txt", b"bee")
        write_file(self.root, "a.txt", b"ay")
        write_file(self.root, export_source.MANIFEST, b"left out")
        os.symlink("/nowhere/game.iso", self.root / "link")
        self.assertEqual(export_source.manifest(self.root), [
            ("a dir/b.txt", hashlib.sha256(b"bee").hexdigest()),
            ("a.txt", hashlib.sha256(b"ay").hexdigest()),
            ("link", hashlib.sha256(b"/nowhere/game.iso").hexdigest()),
        ])


class SrcDigestTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "src" / "a dir").mkdir(parents=True)
        write_file(self.root / "src", "hooks.cpp", b"hooks")
        write_file(self.root / "src" / "a dir", "b.h", b"bee")
        write_file(self.root, "README.md", b"read me")

    def test_is_the_sha256_of_srcs_manifest_lines(self):
        lines = (f"{hashlib.sha256(b'bee').hexdigest()}  src/a dir/b.h\n"
                 f"{hashlib.sha256(b'hooks').hexdigest()}  src/hooks.cpp\n")
        self.assertEqual(export_source.src_digest(self.root), hashlib.sha256(lines.encode()).hexdigest())

    def test_changes_with_a_file_in_src_and_not_with_one_outside(self):
        before = export_source.src_digest(self.root)
        write_file(self.root, "README.md", b"read me again")
        self.assertEqual(export_source.src_digest(self.root), before)
        write_file(self.root / "src", "hooks.cpp", b"other hooks")
        self.assertNotEqual(export_source.src_digest(self.root), before)


if __name__ == "__main__":
    unittest.main()
