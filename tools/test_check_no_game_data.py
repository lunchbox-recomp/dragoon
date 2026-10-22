import unittest
from unittest import mock

import check_no_game_data
from testutil import run_main


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

    def test_anything_else_in_rom_fails(self):
        self.assertEqual(check_no_game_data.violations(["rom/notes.txt"]), ["rom/notes.txt"])

    def test_what_the_tools_make_fails(self):
        paths = ["tools/keys.bin", "old-keys.bin", "x/saves/notes.txt", "x/frame_00060.png",
                 "x/stdout.txt", "panic.txt"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_wav_recordings_fail_anywhere(self):
        paths = ["out.wav", "tools/x/out.WAV", "docs/clip.wav"]
        self.assertEqual(check_no_game_data.violations(paths), paths)

    def test_lookalikes_pass(self):
        paths = ["x/frame_00060.png.bak", "x/xframe_00060.png", "x/saves.txt", "x/stdout.txt.md"]
        self.assertEqual(check_no_game_data.violations(paths), [])


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
