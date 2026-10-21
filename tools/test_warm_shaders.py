import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import routes
import warm_shaders
from testutil import run_main, write_file

ENGINE_REV = warm_shaders.engine_rev
MANIFEST = "# comment\ntitle 20 60 60,960\ncity-trial-4p 30 60 2700,3480 --pads=4\n"
TITLE_FRAMES = 960 + warm_shaders.ROUTE_TAIL_FRAMES
FOUR_FRAMES = 3480 + warm_shaders.ROUTE_TAIL_FRAMES
TITLE_EXIT = f"--exit-after={TITLE_FRAMES}"
FOUR_EXIT = f"--exit-after={FOUR_FRAMES}"
FAKE_GAME = f"""#!{sys.executable}
import os, sys
os.makedirs("saves", exist_ok=True)
line = " ".join(sys.argv[1:]) + " SDL=" + os.environ.get("SDL_AUDIO_DRIVER", "") + " INPUT=" + os.environ.get("GCN_INPUT", "-")
line += " CARD=" + str(os.path.exists("saves/memcard_a.raw"))
with open("saves/shaders.bin", "ab") as f:
    f.write((line + "\\n").encode())
with open("saves/memcard_a.raw", "wb") as f:
    f.write(b"scratch card")
if os.environ.get("FAKE_SLEEP_ON") and os.environ["FAKE_SLEEP_ON"] in line:
    import time
    time.sleep(30)
if os.environ.get("FAKE_FAIL_ON") and os.environ["FAKE_FAIL_ON"] in line:
    sys.exit(1)
"""


class WarmTestCase(unittest.TestCase):
    """A fake game, two routes, a player's saves/ and a patched engine revision, all in a temp dir."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.game = write_file(self.dir, "fake_game", FAKE_GAME)
        self.game.chmod(self.game.stat().st_mode | stat.S_IXUSR)
        self.manifest = write_file(self.dir, "manifest.txt", MANIFEST)
        self.routes = self.dir / "routes"
        self.routes.mkdir()
        write_file(self.routes, "title.txt", "# comment\n120:A:5, 300:A:5\n")
        write_file(self.routes, "city-trial-4p.txt", "2/900:A:10\n")
        self.saves = self.dir / "saves"
        self.rev = "rev1"
        self.tool = "tool1"
        for patch in (mock.patch.object(warm_shaders, "tool_sha", lambda: self.tool),
                      mock.patch.object(warm_shaders, "MANIFEST", self.manifest),
                      mock.patch.object(routes, "ROUTES", self.routes),
                      mock.patch.object(warm_shaders, "engine_rev", lambda: self.rev),
                      mock.patch.dict(os.environ, {"GCN_INPUT": "999:B:1"})):
            patch.start()
            self.addCleanup(patch.stop)

    def warm(self, *extra: str) -> tuple[int, str, str]:
        return run_main(warm_shaders.main, "--game", str(self.game), "--saves", str(self.saves), *extra)

    def cache_lines(self) -> list[str]:
        return (self.saves / "shaders.bin").read_text().splitlines()

    def snapshot(self) -> dict[str, bytes]:
        if not self.saves.exists():
            return {}
        return {p.name: p.read_bytes() for p in sorted(self.saves.iterdir())}


class ScriptTextTest(unittest.TestCase):
    def test_drops_comments_spaces_and_newlines(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_file(Path(d), "r.txt", "# a comment\n120:A:5, 300:A:5,\n\n# more\n900 : A : 5\n")
            self.assertEqual(warm_shaders.script_text(path), "120:A:5,300:A:5,900:A:5")


class PassesTest(unittest.TestCase):
    def test_one_pass_per_route_run_15_s_past_its_last_frame(self):
        ps = warm_shaders.passes(routes.parse_manifest(MANIFEST))
        self.assertEqual([p.name for p in ps], ["title", "city-trial-4p"])
        self.assertEqual([p.exit_after for p in ps], [TITLE_FRAMES, FOUR_FRAMES])
        self.assertEqual([p.pads for p in ps], [1, 4])
        self.assertEqual(ps[0].route_file, routes.ROUTES / "title.txt")


class WarmTest(WarmTestCase):
    def test_seeded_cache_is_a_prefix_of_the_installed_one(self):
        self.saves.mkdir()
        old = b"WRSC old keys\n"
        write_file(self.saves, "shaders.bin", old)
        code, _, _ = self.warm()
        self.assertEqual(code, 0)
        new = (self.saves / "shaders.bin").read_bytes()
        self.assertTrue(new.startswith(old))
        self.assertEqual(len(self.cache_lines()), 1 + 2)  # the old line, then one per pass

    def test_blank_start_installs_every_pass(self):
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.cache_lines()), 2)
        self.assertIn("2 passes", out)

    def test_memory_card_and_other_saves_are_untouched(self):
        self.saves.mkdir()
        write_file(self.saves, "memcard_a.raw", b"the player's card")
        write_file(self.saves, "controls.cfg", b"x")
        before = self.snapshot()
        self.assertEqual(self.warm()[0], 0)
        after = self.snapshot()
        self.assertEqual({k: v for k, v in after.items() if k in before and k != "shaders.bin"},
                         {k: v for k, v in before.items() if k != "shaders.bin"})
        self.assertEqual(set(after) - set(before), {"shaders.bin", ".shader-warmup"})

    def test_children_are_hidden_fast_silent_and_run_in_scratch(self):
        self.assertEqual(self.warm()[0], 0)
        title, four = self.cache_lines()
        for line in (title, four):
            for flag in ("--hidden", "--fast", "--no-input-log"):
                self.assertIn(flag, line.split())
            self.assertIn("SDL=dummy", line.split())
            self.assertNotIn("INPUT=999:B:1", line.split())  # the parent's GCN_INPUT never reaches it
        # The scratch cwd, not saves/, took the fake's memory card.
        self.assertFalse((self.saves / "memcard_a.raw").exists())
        self.assertIn("INPUT=120:A:5,300:A:5", title.split())
        self.assertIn("--pads=4", four.split())
        self.assertIn(FOUR_EXIT, four.split())

    def test_failing_pass_leaves_saves_identical_and_exits_non_zero(self):
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", b"old\n")
        write_file(self.saves, "memcard_a.raw", b"card")
        before = self.snapshot()
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": FOUR_EXIT}):  # the last pass
            code, _, err = self.warm()
        self.assertNotEqual(code, 0)
        self.assertIn("city-trial-4p", err)
        self.assertEqual(self.snapshot(), before)

    def test_failing_pass_creates_nothing_when_there_were_no_saves(self):
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": TITLE_EXIT}):  # the first pass
            code, _, _ = self.warm()
        self.assertNotEqual(code, 0)
        self.assertFalse(self.saves.exists())

    def test_missing_game_exits_2(self):
        self.game.unlink()
        self.assertEqual(self.warm()[0], 2)

    def test_stamp_skips_a_second_run_unless_forced(self):
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 2)
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertIn("current", out)
        self.assertEqual(len(self.cache_lines()), 2)
        self.assertEqual(self.warm("--force")[0], 0)
        self.assertEqual(len(self.cache_lines()), 4)

    def assert_runs_again(self) -> None:
        """After a warm-up, run again: the stamp no longer matches, so both passes play."""
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 2)
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertIn("current", out)

    def test_new_engine_revision_runs_again(self):
        self.assert_runs_again()
        self.rev = "rev2"
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 4)

    def test_new_manifest_runs_again(self):
        self.assert_runs_again()
        write_file(self.dir, "manifest.txt", MANIFEST + "menu 20 60 1200\n")
        write_file(self.routes, "menu.txt", "1:A:1\n")
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 2 + 3)

    def test_edited_route_file_runs_again(self):
        self.assert_runs_again()
        write_file(self.routes, "title.txt", "# comment\n120:A:5, 300:A:5, 500:B:5\n")
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 4)
        self.assertIn("INPUT=120:A:5,300:A:5,500:B:5", self.cache_lines()[2].split())

    def test_comment_only_edit_to_a_route_file_stays_current(self):
        self.assert_runs_again()
        write_file(self.routes, "title.txt", "# another comment\n120:A:5,\n300:A:5\n")
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertIn("current", out)

    def test_new_tool_runs_again(self):
        self.assert_runs_again()
        self.tool = "tool2"
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 4)

    def test_empty_gcn_recomp_directory_exits_2_with_the_hint(self):
        (self.dir / "gcn-recomp").mkdir()
        with mock.patch.object(warm_shaders, "ROOT", self.dir), \
                mock.patch.object(warm_shaders, "engine_rev", ENGINE_REV):
            code, _, err = self.warm()
        self.assertEqual(code, 2)
        self.assertIn("gcn-recomp", err)
        self.assertTrue(err.strip().endswith("-DDRAGOON_WARMUP=OFF to skip the warm-up)"))
        self.assertFalse(self.saves.exists())

    def test_failed_run_does_not_write_the_stamp(self):
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": TITLE_EXIT}):
            self.warm()
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 2)

    def test_every_pass_starts_from_a_blank_card(self):
        # The fake leaves a card behind, as the game does; a route that found it would take
        # the "load" menus instead of the "make a new file" ones the manifest's routes assume.
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual([l.split()[-1] for l in self.cache_lines()], ["CARD=False", "CARD=False"])

    def test_deleted_cache_warms_again_despite_a_current_stamp(self):
        self.assertEqual(self.warm()[0], 0)
        (self.saves / "shaders.bin").unlink()
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertNotIn("current", out)
        self.assertEqual(len(self.cache_lines()), 2)

    def test_hung_game_is_killed_and_fails_the_pass(self):
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", b"old\n")
        before = self.snapshot()
        with mock.patch.dict(os.environ, {"FAKE_SLEEP_ON": TITLE_EXIT}), \
                mock.patch.object(warm_shaders, "pass_timeout", lambda n: 1):
            code, _, err = self.warm()
        self.assertNotEqual(code, 0)
        self.assertIn("title", err)
        self.assertIn("within 1 s", err)
        self.assertIn("-DDRAGOON_WARMUP=OFF", err)
        self.assertEqual(self.snapshot(), before)

    def test_missing_route_file_exits_2_and_leaves_saves_alone(self):
        (self.routes / "city-trial-4p.txt").unlink()
        code, _, err = self.warm()
        self.assertEqual(code, 2)
        self.assertIn("city-trial-4p.txt", err)
        self.assertFalse(self.saves.exists())

    def test_game_that_writes_no_cache_fails(self):
        write_file(self.dir, "fake_game", f"#!{sys.executable}\n")
        code, _, err = self.warm()
        self.assertNotEqual(code, 0)
        self.assertIn("shaders.bin", err)
        self.assertFalse(self.saves.exists())


if __name__ == "__main__":
    unittest.main()
