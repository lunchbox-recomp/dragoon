import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_no_game_data
from testutil import GIT_ENV, git, run_main

MOD_SUFFIXES = (".dat", ".hps", ".bnr", ".elf", ".gct")


class ViolationsTest(unittest.TestCase):
    def test_clean_tree_passes(self):
        paths = ["CMakeLists.txt", "build.sh", "rom/README.md", "recomp/hle.txt", "docs/diagram.png"]
        self.assertEqual(check_no_game_data.violations(paths), [])

    def test_disc_images_fail(self):
        paths = ["rom/game.iso", "kar.GCM", "x.ciso", "y.rvz", "main.dol"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_build_output_and_saves_fail(self):
        paths = ["build/gen/recomp_0.c", "build-nodisc/x.o", "saves/memcard_a.raw"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_playtest_sessions_fail(self):
        session = "build/playtest/20261022-160000/"
        paths = [session + name for name in ("session.json", "out.wav", "aid.raw", "aid.raw.txt", "stdout.txt",
                                             "inputs/inputs.txt", "inputs/memcard_a.raw", "run-2/out.wav")]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_a_session_written_outside_build_fails(self):
        paths = ["session.json", "x/AID.RAW.TXT", "x/inputs/inputs.txt", "x/inputs/sram.raw", "x/run-2/session.json"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_anything_else_in_rom_fails(self):
        self.assertEqual(check_no_game_data.violations(["rom/notes.txt"]), ["rom/notes.txt"])

    def test_what_the_tools_make_fails(self):
        paths = ["tools/keys.bin", "old-keys.bin", "x/saves/notes.txt", "x/frame_00060.png",
                 "x/output_00060.png", "x/stdout.txt", "panic.txt"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_wav_recordings_fail_anywhere(self):
        paths = ["out.wav", "tools/x/out.WAV", "docs/clip.wav"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_mod_files_fail_anywhere(self):
        for suffix in MOD_SUFFIXES:
            with self.subTest(suffix=suffix):
                paths = [f"mod{suffix}", f"tools/x/Mod{suffix.upper()}", f"docs/a mod{suffix}"]
                self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_anything_under_a_top_level_mods_fails(self):
        paths = ["mods/README.md", "mods/Some Mod/patches.txt", "mods/a/b/c.txt"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_a_mods_folder_below_the_top_passes(self):
        paths = ["tests/mods/patches.txt", "tests/mods/Some Mod/list.txt", "docs/mods/guide.md", "x/mods/a.txt"]
        self.assertEqual(check_no_game_data.violations(paths), [])

    def test_lookalikes_pass(self):
        paths = ["x/frame_00060.png.bak", "x/xframe_00060.png", "x/output_00060.png.bak",
                 "x/xoutput_00060.png", "x/saves.txt", "x/stdout.txt.md", "x/session.json.md", "x/inputs.txt.md",
                 "x/aid.raw.txt.md", "x/my-session.json", "x/inputs/inputs.txt.bak"]
        self.assertEqual(check_no_game_data.violations(paths), [])

    def test_mod_file_lookalikes_pass(self):
        paths = ["x/dat", "x/data", "x/notes.dat.md", "x/hps", "x/notes.hps.txt", "x/bnr", "x/notes.bnr.txt",
                 "x/shelf", "x/elf", "x/notes.elf.md", "x/gct", "x/notes.gct.md",
                 "mods", "modsy/a.txt", "my-mods/a.txt", "x/mods", "mods.txt"]
        self.assertEqual(check_no_game_data.violations(paths), [])


class GitignoreTest(unittest.TestCase):
    """The mod rules in .gitignore, as git reads them. The repository's own .gitignore is
    copied into a fresh repository, so nothing of the user's or the system's applies."""

    def ignored(self, paths: list[str]) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            git(Path(tmp), "init", "-q")
            shutil.copy(check_no_game_data.ROOT / ".gitignore", Path(tmp, ".gitignore"))
            done = subprocess.run(["git", "-C", tmp, "check-ignore", "--stdin", "-z"],
                                  env={**os.environ, **GIT_ENV}, input="\0".join(paths),
                                  capture_output=True, text=True)
        self.assertIn(done.returncode, (0, 1), done.stderr)
        return done.stdout.split("\0")[:-1]

    def test_mod_files_are_ignored_anywhere(self):
        paths = [f"mod{suffix}" for suffix in MOD_SUFFIXES] + [f"tools/x/a mod{suffix}" for suffix in MOD_SUFFIXES]
        self.assertEqual(self.ignored(paths), paths)

    def test_a_top_level_mods_folder_is_ignored(self):
        paths = ["mods/README.md", "mods/Some Mod/patches.txt", "mods/a/b/c.txt"]
        self.assertEqual(self.ignored(paths), paths)

    def test_a_mods_folder_below_the_top_is_not(self):
        paths = ["tests/mods/patches.txt", "tests/mods/Some Mod/list.txt", "docs/mods/guide.md"]
        self.assertEqual(self.ignored(paths), [])


class MainTest(unittest.TestCase):
    def ls_files(self, listing: str):
        return mock.patch.object(check_no_game_data.subprocess, "run",
                                 return_value=mock.Mock(stdout=listing))

    def test_clean_tree_exits_0_and_prints_nothing(self):
        with self.ls_files("a.txt\n"):
            self.assertEqual(run_main(check_no_game_data.main), (0, "", ""))

    def test_tracked_game_data_exits_1_listing_it(self):
        with self.ls_files("a.txt\nrom/game.iso\n"):
            code, out, _ = run_main(check_no_game_data.main)
        self.assertEqual((code, out), (1, "game data tracked: rom/game.iso\n"))

    def test_failing_git_exits_2(self):
        failure = check_no_game_data.subprocess.CalledProcessError(128, "git", stderr="not a repo")
        with mock.patch.object(check_no_game_data.subprocess, "run", side_effect=failure):
            code, _, err = run_main(check_no_game_data.main)
        self.assertEqual(code, 2)
        self.assertIn("not a repo", err)

    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = run_main(check_no_game_data.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
