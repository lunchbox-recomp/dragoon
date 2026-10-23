import json
import os
import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import routes
import shader_cache
import source_info
import warm_shaders
from testutil import GIT_ENV, commit, run_main, write_file

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


# A game that keeps a real cache: the keys FAKE_KEYS lists for this pass's --exit-after (JSON,
# frames to key numbers) are appended unless the cache holds them, one 8-byte key, an 8-byte
# source hash that is the same number, and no binary, as the game on macOS writes. It prints
# the line the game prints once it has built what the cache held.
FAKE_CACHE_GAME = f"""#!{sys.executable}
import json, os, struct, sys
os.makedirs("saves", exist_ok=True)
path = "saves/shaders.bin"
if not os.path.exists(path):
    with open(path, "wb") as f:
        f.write(struct.pack("<IIQ", 0x43535257, 3 << 16 | 8, 0xD00D))
data = open(path, "rb").read()
held = [data[o:o + 8] for o in range(16, len(data), 24)]
if held:
    print(f"[shaders] {{len(held)}} programs from cache (0 from binaries, {{len(held)}} compiled, 0 of them from the game's key list) in 12 ms")
frames = [a for a in sys.argv if a.startswith("--exit-after=")][0].split("=")[1]
with open(path, "ab") as f:
    for n in json.loads(os.environ["FAKE_KEYS"])[frames]:
        key = bytes([n]) * 8
        if key not in held:
            f.write(key + key + struct.pack("<II", 0, 0))
            print(f"[shaders] compiled program {{n}} in 1.0 ms")
            print(f"[rt] f{{500 + n}} render   1.00ms")
"""


def shader_cache_bytes(keys: list[int]) -> bytes:
    """A cache the fake cache game would have written: the keys, each 8 bytes of its number."""
    return struct.pack("<IIQ", 0x43535257, 3 << 16 | 8, 0xD00D) + b"".join(
        bytes([n]) * 16 + struct.pack("<II", 0, 0) for n in keys)


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


class LastCompileFrameTest(unittest.TestCase):
    def test_a_program_belongs_to_the_next_render_line(self):
        log = ("[ft] f1 guest 356.11ms  fe   0.07ms\n"
               "[shaders] compiled program 1 in 1.5 ms\n"
               "[shaders] compiled program 2 in 1.9 ms\n"
               "[rt] f2 render   4.60ms (tex  0.11 vbo  0.01 copies  0.01)  applies    4  programs 2\n"
               "[rt] f3 render   0.12ms (tex  0.00 vbo  0.01 copies  0.01)  applies    4  programs 2\n"
               "[shaders] compiled program 3 in 2.0 ms\n"
               "[rt] f4 render   2.82ms (tex  0.22 vbo  0.01 copies  0.02)  applies   84  programs 3\n"
               "[rt] f5 render   0.12ms (tex  0.00 vbo  0.01 copies  0.01)  applies    4  programs 3\n")
        self.assertEqual(warm_shaders.last_compile_frame(log), 4)

    def test_a_log_without_frame_timing_is_frame_0(self):
        self.assertEqual(warm_shaders.last_compile_frame("[shaders] 70 programs from cache in 107 ms\n"), 0)


class EngineRevTest(unittest.TestCase):
    """engine_rev() in a tree that's a git checkout, a source snapshot, both or neither."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "gcn-recomp").mkdir()
        for patch in (mock.patch.object(warm_shaders, "ROOT", self.root),
                      mock.patch.dict(os.environ, GIT_ENV)):
            patch.start()
            self.addCleanup(patch.stop)

    def write_info(self, engine: str) -> Path:
        info = {"dragoon": "d" * 40, "gcn-recomp": engine, "disc_id": "GKYE01", "dol_sha1": "a" * 40}
        return write_file(self.root, source_info.NAME, json.dumps(info))

    def test_a_checkout_asks_git_even_when_the_file_disagrees(self):
        rev = commit(self.root / "gcn-recomp", {"engine.txt": "engine"})
        self.write_info("f" * 40)
        self.assertEqual(warm_shaders.engine_rev(), rev)

    def test_a_snapshot_reads_the_file(self):
        self.write_info("e" * 40)
        self.assertEqual(warm_shaders.engine_rev(), "e" * 40)

    def test_neither_raises_with_the_hint(self):
        with self.assertRaises(ValueError) as caught:
            warm_shaders.engine_rev()
        self.assertIn(source_info.NAME, str(caught.exception))
        self.assertIn("-DDRAGOON_WARMUP=OFF", str(caught.exception))

    def test_a_malformed_file_raises_with_its_path(self):
        path = self.write_info("not a commit")
        with self.assertRaises(ValueError) as caught:
            warm_shaders.engine_rev()
        self.assertIn(str(path), str(caught.exception))


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

    def test_each_pass_prints_one_pass_line(self):
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        passes = [l for l in out.splitlines() if warm_shaders.PASS_LINE.fullmatch(l)]
        self.assertEqual([l.split(":")[0] for l in passes], ["title", "city-trial-4p"])

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

    def warm_until_current(self) -> None:
        """Warm once, then check a second run is skipped as current."""
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 2)
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertIn("current", out)

    def test_new_engine_revision_runs_again(self):
        self.warm_until_current()
        self.rev = "rev2"
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 4)

    def test_new_manifest_runs_again(self):
        self.warm_until_current()
        write_file(self.dir, "manifest.txt", MANIFEST + "menu 20 60 1200\n")
        write_file(self.routes, "menu.txt", "1:A:1\n")
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 2 + 3)

    def test_edited_route_file_runs_again(self):
        self.warm_until_current()
        write_file(self.routes, "title.txt", "# comment\n120:A:5, 300:A:5, 500:B:5\n")
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.cache_lines()), 4)
        self.assertIn("INPUT=120:A:5,300:A:5,500:B:5", self.cache_lines()[2].split())

    def test_comment_only_edit_to_a_route_file_stays_current(self):
        self.warm_until_current()
        write_file(self.routes, "title.txt", "# another comment\n120:A:5,\n300:A:5\n")
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertIn("current", out)

    def test_new_tool_runs_again(self):
        self.warm_until_current()
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

    def test_a_snapshot_stamps_the_engine_its_source_info_names(self):
        (self.dir / "gcn-recomp").mkdir()
        info = {"dragoon": "d" * 40, "gcn-recomp": "e" * 40, "disc_id": "GKYE01", "dol_sha1": "a" * 40}
        write_file(self.dir, source_info.NAME, json.dumps(info))
        with mock.patch.object(warm_shaders, "ROOT", self.dir), \
                mock.patch.object(warm_shaders, "engine_rev", ENGINE_REV):
            self.assertEqual(self.warm()[0], 0)
        self.assertTrue((self.saves / ".shader-warmup").read_text().startswith("e" * 40 + " "))

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


class ReportTest(WarmTestCase):
    def setUp(self):
        super().setUp()
        write_file(self.dir, "fake_game", FAKE_CACHE_GAME)
        keys = {str(TITLE_FRAMES): [1, 2], str(FOUR_FRAMES): [2, 3, 4]}
        patch = mock.patch.dict(os.environ, {"FAKE_KEYS": json.dumps(keys)})
        patch.start()
        self.addCleanup(patch.stop)
        self.report = self.dir / "report"

    def rows(self) -> list[list[str]]:
        text = (self.report / "report.txt").read_text()
        return [line.split() for line in text.splitlines()[1:]]

    def test_each_pass_adds_the_keys_and_programs_no_earlier_pass_had(self):
        code, out, _ = self.warm("--report", str(self.report))
        self.assertEqual(code, 0)
        title, four = self.rows()
        # name, frames, s, boot programs, boot ms, +keys, +programs, keys, last frame built in
        self.assertEqual([title[0], title[1], *title[3:]],
                         ["title", str(TITLE_FRAMES), "0", "0", "2", "2", "2", "502"])
        self.assertEqual([four[0], four[1], *four[3:]],
                         ["city-trial-4p", str(FOUR_FRAMES), "2", "12", "2", "2", "4", "504"])
        self.assertIn("city-trial-4p", out.splitlines()[-2])

    def test_keys_the_players_cache_held_are_not_new(self):
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", shader_cache_bytes([1]))
        self.assertEqual(self.warm("--report", str(self.report))[0], 0)
        title, four = self.rows()
        self.assertEqual([title[3], title[5], title[7]], ["1", "1", "2"])
        self.assertEqual([four[5], four[7]], ["2", "4"])

    def test_each_pass_keeps_its_output_and_its_cache(self):
        self.assertEqual(self.warm("--report", str(self.report))[0], 0)
        self.assertEqual(sorted(p.name for p in self.report.iterdir()),
                         ["city-trial-4p.bin", "city-trial-4p.log", "report.txt", "title.bin", "title.log"])
        self.assertEqual(len(shader_cache.load(self.report / "title.bin").keys), 2)
        self.assertEqual(len(shader_cache.load(self.report / "city-trial-4p.bin").keys), 4)
        self.assertIn("2 programs from cache", (self.report / "city-trial-4p.log").read_text())

    def test_without_the_flag_nothing_is_kept(self):
        self.assertEqual(self.warm()[0], 0)
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
