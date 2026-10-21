import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import warm_shaders
from frame_hashes import parse_manifest
from testutil import run_main, write_file

MANIFEST = "# comment\ntitle 20 60 60,960\ncity-trial-4p 30 60 2700,3480 --pads=4\n"
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
        for patch in (mock.patch.object(warm_shaders, "MANIFEST", self.manifest),
                      mock.patch.object(warm_shaders, "ROUTES", self.routes),
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
        ps = warm_shaders.passes(parse_manifest(MANIFEST))
        self.assertEqual([p.name for p in ps], ["title", "city-trial-4p"])
        self.assertEqual([p.exit_after for p in ps], [960 + 900, 3480 + 900])
        self.assertEqual([p.pads for p in ps], [1, 4])
        self.assertEqual(ps[0].script, warm_shaders.ROUTES / "title.txt")


class StampTest(unittest.TestCase):
    def test_changes_with_engine_revision_and_manifest(self):
        base = warm_shaders.stamp("rev1", MANIFEST)
        self.assertEqual(base, warm_shaders.stamp("rev1", MANIFEST))
        self.assertNotEqual(base, warm_shaders.stamp("rev2", MANIFEST))
        self.assertNotEqual(base, warm_shaders.stamp("rev1", MANIFEST + "menu 20 60 1200\n"))


class InstallTest(WarmTestCase):
    def test_copies_through_a_temp_file_and_os_replace(self):
        # Two builds at once, or a rebuild while the game runs: a reader sees the old file or
        # the whole new one, never half of it, because the target is only ever os.replace'd.
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", b"old\n")
        src = write_file(self.dir, "scratch.bin", b"old\nnew\n")
        seen = []
        real_replace = os.replace

        def spy(a, b):
            seen.append((Path(a), Path(b), Path(a).read_bytes(), Path(b).read_bytes()))
            real_replace(a, b)

        with mock.patch.object(warm_shaders.os, "replace", spy):
            warm_shaders.install(src, self.saves)
        (tmp, target, tmp_bytes, target_bytes), = seen
        self.assertEqual(tmp.parent, self.saves)
        self.assertNotEqual(tmp, target)
        self.assertEqual((target, tmp_bytes, target_bytes),
                         (self.saves / "shaders.bin", b"old\nnew\n", b"old\n"))
        self.assertEqual(sorted(p.name for p in self.saves.iterdir()), ["shaders.bin"])


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
        self.assertIn("--exit-after=4380", four.split())

    def test_failing_pass_leaves_saves_identical_and_exits_non_zero(self):
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", b"old\n")
        write_file(self.saves, "memcard_a.raw", b"card")
        before = self.snapshot()
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": "--exit-after=4380"}):  # the last pass
            code, _, err = self.warm()
        self.assertNotEqual(code, 0)
        self.assertIn("city-trial-4p", err)
        self.assertEqual(self.snapshot(), before)

    def test_failing_pass_creates_nothing_when_there_were_no_saves(self):
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": "--exit-after=1860"}):  # the first pass
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

    def test_new_engine_revision_or_manifest_runs_again(self):
        self.assertEqual(self.warm()[0], 0)
        self.rev = "rev2"
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 4)
        write_file(self.dir, "manifest.txt", MANIFEST + "menu 20 60 1200\n")
        write_file(self.routes, "menu.txt", "1:A:1\n")
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 4 + 3)

    def test_failed_run_does_not_write_the_stamp(self):
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": "--exit-after=1860"}):
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
        with mock.patch.dict(os.environ, {"FAKE_SLEEP_ON": "--exit-after=1860"}), \
                mock.patch.object(warm_shaders, "pass_timeout", lambda n: 1):
            code, _, err = self.warm()
        self.assertNotEqual(code, 0)
        self.assertIn("title", err)
        self.assertIn("within 1 s", err)
        self.assertIn("-DDRAGOON_WARMUP=OFF", err)
        self.assertEqual(self.snapshot(), before)

    def test_pass_timeout_is_twice_real_time_plus_30_s(self):
        self.assertEqual(warm_shaders.pass_timeout(6000), 230)

    def test_no_gcn_recomp_checkout_falls_back_to_the_game_binary_hash(self):
        def no_git() -> str:
            raise ValueError("can't read the gcn-recomp commit")
        with mock.patch.object(warm_shaders, "engine_rev", no_git):
            code, _, err = self.warm()
            self.assertEqual(code, 0)
            self.assertIn("SHA-1", err)
            self.assertEqual(len(self.cache_lines()), 2)
            self.assertEqual(self.warm()[0], 0)  # the same binary is current
            self.assertEqual(len(self.cache_lines()), 2)
            self.game.write_text(FAKE_GAME + "# relinked\n")
            self.assertEqual(self.warm()[0], 0)
            self.assertEqual(len(self.cache_lines()), 4)

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
