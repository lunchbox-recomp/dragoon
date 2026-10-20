import unittest

from check_no_game_data import violations


class ViolationsTest(unittest.TestCase):
    def test_clean_tree_passes(self):
        paths = ["CMakeLists.txt", "build.sh", "rom/README.md", "recomp/hle.txt"]
        self.assertEqual(violations(paths), [])

    def test_disc_images_fail(self):
        paths = ["rom/game.iso", "kar.GCM", "x.ciso", "y.rvz", "main.dol"]
        self.assertEqual(violations(paths), paths)

    def test_build_output_and_saves_fail(self):
        paths = ["build/gen/recomp_0.c", "build-nodisc/x.o", "saves/memcard_a.raw"]
        self.assertEqual(violations(paths), paths)

    def test_anything_else_in_rom_fails(self):
        self.assertEqual(violations(["rom/notes.txt"]), ["rom/notes.txt"])


if __name__ == "__main__":
    unittest.main()
