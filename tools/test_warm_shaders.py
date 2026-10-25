import json
import os
import stat
import struct
import sys
import tempfile
import time
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
# The game. It logs how it was run to FAKE_LOG, leaves a memory card behind as the real one
# does, and keeps a real cache: the keys FAKE_KEYS lists for this pass's --exit-after (JSON,
# frames to key numbers) go in unless the cache holds them, each an 8-byte key, an 8-byte source
# hash that is the same number and no binary, as on macOS. It prints the lines the real game
# prints once it has built what the cache held and under GCN_FRAMETIME=1 for each program built
# in play. FAKE_SLEEP_ON and FAKE_FAIL_ON name the runs (by a part of the line logged) that hang
# or exit 1, and FAKE_MEET makes each wait until another run has started too. FAKE_HOLD_ON
# names a run that waits until every other run is done (FAKE_RELEASE is the file they make)
# and then half a second more, so it ends last.
FAKE_GAME = f"""#!{sys.executable}
import json, os, struct, sys, time
os.makedirs("saves", exist_ok=True)
frames = [a for a in sys.argv if a.startswith("--exit-after=")][0].split("=")[1]
line = " ".join(sys.argv[1:]) + " SDL=" + os.environ.get("SDL_AUDIO_DRIVER", "") + " INPUT=" + os.environ.get("GCN_INPUT", "-")
line += " GCN=" + ",".join(sorted(k for k in os.environ if k.startswith("GCN_")))
line += " CARD=" + str(os.path.exists("saves/memcard_a.raw"))
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(line + "\\n")
path = "saves/shaders.bin"
if not os.path.exists(path):
    with open(path, "wb") as f:
        f.write(struct.pack("<IIQ", 0x43535257, 3 << 16 | 8, 0xD00D))
data = open(path, "rb").read()
held = [data[o:o + 8] for o in range(16, len(data), 24)]
if held:
    print(f"[shaders] {{len(held)}} programs from cache (0 from binaries, {{len(held)}} compiled, 0 of them from the game's key list) in 12 ms")
with open(path, "ab") as f:
    for n in json.loads(os.environ["FAKE_KEYS"]).get(frames, []):
        key = bytes([n]) * 8
        if key not in held:
            f.write(key + key + struct.pack("<II", 0, 0))
            print(f"[shaders] compiled program {{n}} in 1.0 ms")
            print(f"[rt] f{{500 + n}} render   1.00ms")
with open("saves/memcard_a.raw", "wb") as f:
    f.write(b"scratch card")
if os.environ.get("FAKE_MEET"):
    open(os.path.join(os.environ["FAKE_MEET"], frames), "w").close()
    for _ in range(100):
        if len(os.listdir(os.environ["FAKE_MEET"])) > 1:
            break
        time.sleep(0.1)
    else:
        sys.exit(3)
if os.environ.get("FAKE_HOLD_ON"):
    release = os.environ["FAKE_RELEASE"]
    if os.environ["FAKE_HOLD_ON"] not in line:
        open(release, "w").close()
    else:
        for _ in range(200):
            if os.path.exists(release):
                break
            time.sleep(0.05)
        else:
            sys.exit(3)
        time.sleep(0.5)
if os.environ.get("FAKE_SLEEP_ON") and os.environ["FAKE_SLEEP_ON"] in line:
    time.sleep(30)
if os.environ.get("FAKE_FAIL_ON") and os.environ["FAKE_FAIL_ON"] in line:
    sys.exit(1)
"""


def fake_key(n: int) -> bytes:
    return bytes([n]) * 8


def fake_cache(keys: list[int]) -> bytes:
    """A cache the fake game would have written: the keys, no binaries."""
    return struct.pack("<IIQ", 0x43535257, 3 << 16 | 8, 0xD00D) + b"".join(
        fake_key(n) * 2 + struct.pack("<II", 0, 0) for n in keys)


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
        self.log = self.dir / "games.log"
        self.rev = "rev1"
        self.tool = "tool1"
        keys = {str(TITLE_FRAMES): [1], str(FOUR_FRAMES): [2]}
        for patch in (mock.patch.object(warm_shaders, "tool_sha", lambda: self.tool),
                      mock.patch.object(warm_shaders, "JOBS", 1),  # runs in the plan's order
                      mock.patch.object(warm_shaders, "MANIFEST", self.manifest),
                      mock.patch.object(routes, "ROUTES", self.routes),
                      mock.patch.object(warm_shaders, "engine_rev", lambda: self.rev),
                      mock.patch.dict(os.environ, {"GCN_INPUT": "999:B:1", "FAKE_LOG": str(self.log),
                                                   "FAKE_KEYS": json.dumps(keys)})):
            patch.start()
            self.addCleanup(patch.stop)

    def warm(self, *extra: str) -> tuple[int, str, str]:
        return run_main(warm_shaders.main, "--game", str(self.game), "--saves", str(self.saves), *extra)

    def game_lines(self) -> list[str]:
        """How the game was run, once per run, in the order the runs began."""
        return self.log.read_text().splitlines() if self.log.exists() else []

    def cache_keys(self) -> list[bytes]:
        return shader_cache.load(self.saves / "shaders.bin").keys

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

    def test_a_warm_frame_in_the_manifest_sets_the_pass_s_length(self):
        ps = warm_shaders.passes(routes.parse_manifest("sky 25 60 4200 warm=14400\nmeadows 30 60 6000\n"))
        self.assertEqual([p.exit_after for p in ps], [14400, 6000 + warm_shaders.ROUTE_TAIL_FRAMES])


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


def ft_line(frame: int, ms: float) -> str:
    """The [ft] line the game prints before it counts FRAME + 1, which took MS."""
    return (f"[ft] f{frame} guest {ms:6.2f}ms  fe   0.01ms (tex  0.00)  draws    1/   1  verts"
            f"      3  idx      3  states    0\n")


class StretchesTest(unittest.TestCase):
    def test_frames_go_to_their_stretch_and_starting_takes_the_rest(self):
        # Frames 1, 2000, 2001, 3400, 3401 and 9000: each stretch ends on its own last frame.
        log = "".join(ft_line(f, ms) for f, ms in ((0, 0), (1999, 1000), (2000, 2000),
                                                   (3399, 500), (3400, 3000), (8999, 250)))
        self.assertEqual(warm_shaders.stretches(log, 10.0), [3.25, 1.0, 2.5, 3.25])

    def test_a_log_without_frame_timing_is_all_0(self):
        self.assertEqual(warm_shaders.stretches("[rt] f2 render   4.60ms\n", 10.0), [0.0] * 4)


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
        self.assertTrue(str(caught.exception).endswith(warm_shaders.SKIP_HINT))
        for skip in ("-DDRAGOON_WARMUP=OFF", "--no-warmup in launcher_build.py"):
            self.assertIn(skip, warm_shaders.SKIP_HINT)

    def test_a_malformed_file_raises_with_its_path(self):
        path = self.write_info("not a commit")
        with self.assertRaises(ValueError) as caught:
            warm_shaders.engine_rev()
        self.assertIn(str(path), str(caught.exception))


class WarmTest(WarmTestCase):
    def test_seeded_cache_is_a_prefix_of_the_installed_one(self):
        self.saves.mkdir()
        old = fake_cache([9])
        write_file(self.saves, "shaders.bin", old)
        code, _, _ = self.warm()
        self.assertEqual(code, 0)
        new = (self.saves / "shaders.bin").read_bytes()
        self.assertTrue(new.startswith(old))
        self.assertEqual(self.cache_keys(), [fake_key(9), fake_key(1), fake_key(2)])  # then each pass's

    def test_blank_start_installs_every_pass(self):
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertEqual(self.cache_keys(), [fake_key(1), fake_key(2)])
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
        title, four = self.game_lines()
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

    def test_a_disc_reaches_every_pass_as_an_absolute_path(self):
        disc = write_file(self.dir, "Kirby Air Ride (USA).gcm", b"a disc")
        cwd = os.getcwd()
        os.chdir(self.dir)  # the passes run elsewhere, so a relative path wouldn't reach them
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(self.warm("--disc", disc.name)[0], 0)
        title, four = self.game_lines()
        self.assertTrue(title.startswith(f"--hidden --fast --no-input-log --pads=1 {TITLE_EXIT} "
                                         f"{disc.resolve()} SDL=dummy "), title)
        self.assertIn(f" {FOUR_EXIT} {disc.resolve()} SDL=dummy ", four)

    def test_without_a_disc_the_game_gets_no_path(self):
        self.assertEqual(self.warm()[0], 0)
        for line in self.game_lines():
            args = line.split(" SDL=")[0].split()
            self.assertEqual([a for a in args if not a.startswith("--")], [])

    def test_a_missing_disc_exits_2_before_any_pass(self):
        code, _, err = self.warm("--disc", str(self.dir / "no such disc.iso"))
        self.assertEqual(code, 2)
        self.assertIn("no such disc.iso", err)
        self.assertEqual(self.game_lines(), [])
        self.assertFalse(self.saves.exists())

    def test_switches_that_write_one_file_are_not_inherited(self):
        # Up to six games at once would all write the file, so only the pass's own GCN_INPUT
        # and the diagnostics that read nothing but the environment get through.
        env = {"GCN_WAV": "a.wav", "GCN_PROFILE": "p", "GCN_FEED_DUMP": "f", "GCN_SESSION": "s",
               "GCN_FRAMETIME": "1"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(self.warm()[0], 0)
        for line in self.game_lines():
            self.assertIn("GCN=GCN_FRAMETIME,GCN_INPUT", line.split())

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
        self.assertEqual(len(self.game_lines()), 2)
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertIn("current", out)
        self.assertEqual(len(self.game_lines()), 2)
        self.assertEqual(self.warm("--force")[0], 0)
        self.assertEqual(len(self.game_lines()), 4)

    def warm_until_current(self) -> None:
        """Warm once, then check a second run is skipped as current."""
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.game_lines()), 2)
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertIn("current", out)

    def test_new_engine_revision_runs_again(self):
        self.warm_until_current()
        self.rev = "rev2"
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.game_lines()), 4)

    def test_new_manifest_runs_again(self):
        self.warm_until_current()
        write_file(self.dir, "manifest.txt", MANIFEST + "menu 20 60 1200\n")
        write_file(self.routes, "menu.txt", "1:A:1\n")
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.game_lines()), 2 + 3)

    def test_edited_route_file_runs_again(self):
        self.warm_until_current()
        write_file(self.routes, "title.txt", "# comment\n120:A:5, 300:A:5, 500:B:5\n")
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual(len(self.game_lines()), 4)
        self.assertIn("INPUT=120:A:5,300:A:5,500:B:5", self.game_lines()[2].split())

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
        self.assertEqual(len(self.game_lines()), 4)

    def test_empty_gcn_recomp_directory_exits_2_with_the_hint(self):
        (self.dir / "gcn-recomp").mkdir()
        with mock.patch.object(warm_shaders, "ROOT", self.dir), \
                mock.patch.object(warm_shaders, "engine_rev", ENGINE_REV):
            code, _, err = self.warm()
        self.assertEqual(code, 2)
        self.assertIn("gcn-recomp", err)
        self.assertTrue(err.strip().endswith(warm_shaders.SKIP_HINT))
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
        self.assertEqual(len(self.cache_keys()), 2)

    def test_every_pass_starts_from_a_blank_card(self):
        # The fake leaves a card behind, as the game does; a route that found it would take
        # the "load" menus instead of the "make a new file" ones the manifest's routes assume.
        self.assertEqual(self.warm()[0], 0)
        self.assertEqual([l.split()[-1] for l in self.game_lines()], ["CARD=False", "CARD=False"])

    def test_deleted_cache_warms_again_despite_a_current_stamp(self):
        self.assertEqual(self.warm()[0], 0)
        (self.saves / "shaders.bin").unlink()
        code, out, _ = self.warm()
        self.assertEqual(code, 0)
        self.assertNotIn("current", out)
        self.assertEqual(len(self.cache_keys()), 2)

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
        self.assertTrue(err.strip().endswith(warm_shaders.SKIP_HINT))
        self.assertEqual(self.snapshot(), before)

    def test_missing_route_file_exits_2_and_leaves_saves_alone(self):
        (self.routes / "city-trial-4p.txt").unlink()
        code, _, err = self.warm()
        self.assertEqual(code, 2)
        self.assertIn("city-trial-4p.txt", err)
        self.assertFalse(self.saves.exists())

    def test_a_warm_frame_short_of_the_route_s_own_frames_exits_2_before_any_pass(self):
        write_file(self.dir, "manifest.txt", MANIFEST + "meadows 30 60 6000 warm=5000\n")
        code, _, err = self.warm()
        self.assertEqual(code, 2)
        self.assertIn("manifest line 4, route meadows: warm=5000", err)
        self.assertEqual(self.game_lines(), [])
        self.assertFalse(self.saves.exists())

    def test_game_that_writes_no_cache_fails(self):
        write_file(self.dir, "fake_game", f"#!{sys.executable}\n")
        code, _, err = self.warm()
        self.assertNotEqual(code, 0)
        self.assertIn("shaders.bin", err)
        self.assertFalse(self.saves.exists())


class ParallelTest(WarmTestCase):
    def test_passes_play_at_once_when_asked_to(self):
        meet = self.dir / "meet"
        meet.mkdir()
        # Each run waits for the other to start, which only passes that overlap can do.
        with mock.patch.dict(os.environ, {"FAKE_MEET": str(meet)}):
            code, _, err = self.warm("--jobs", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.cache_keys(), [fake_key(1), fake_key(2)])

    def test_a_later_pass_finishing_first_leaves_the_merge_in_the_plans_order(self):
        # The title is first in the manifest and holds back until the four-player pass is done,
        # so the passes finish, and start, in the reverse of the order their keys merge in.
        release = self.dir / "released"
        with mock.patch.dict(os.environ, {"FAKE_HOLD_ON": TITLE_EXIT, "FAKE_RELEASE": str(release)}):
            code, out, err = self.warm("--jobs", "2")
        self.assertEqual(code, 0, err)
        finished = [l.split(":")[0] for l in out.splitlines() if warm_shaders.PASS_LINE.fullmatch(l)]
        self.assertEqual(finished, ["city-trial-4p", "title"])
        self.assertEqual(self.cache_keys(), [fake_key(1), fake_key(2)])

    def test_the_cache_is_the_same_however_many_play_at_once(self):
        other = self.dir / "other-saves"
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", fake_cache([9, 2]))
        other.mkdir()
        write_file(other, "shaders.bin", fake_cache([9, 2]))
        self.assertEqual(self.warm("--jobs", "1")[0], 0)
        code, _, _ = run_main(warm_shaders.main, "--game", str(self.game), "--saves", str(other),
                              "--jobs", "2")
        self.assertEqual(code, 0)
        self.assertEqual((other / "shaders.bin").read_bytes(), (self.saves / "shaders.bin").read_bytes())
        self.assertEqual(self.cache_keys(), [fake_key(9), fake_key(2), fake_key(1)])

    def test_a_third_of_the_cores_play_at_once_from_1_to_6(self):
        self.assertEqual([warm_shaders.default_jobs(n) for n in (None, 1, 2, 3, 8, 16, 18, 64)],
                         [1, 1, 1, 1, 2, 5, 6, 6])

    def test_one_job_plays_the_plans_order_and_more_start_the_longest_first(self):
        plan = warm_shaders.passes(routes.parse_manifest(MANIFEST))
        self.assertEqual(warm_shaders.start_order(plan, 1), [0, 1])
        self.assertEqual(warm_shaders.start_order(plan, 2), [1, 0])
        self.assertEqual(self.warm("--jobs", "1")[0], 0)
        self.assertIn(TITLE_EXIT, self.game_lines()[0].split())

    def test_a_failing_pass_stops_the_ones_still_playing(self):
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", b"old\n")
        before = self.snapshot()
        started = time.monotonic()
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": FOUR_EXIT, "FAKE_SLEEP_ON": TITLE_EXIT}):
            code, _, err = self.warm("--jobs", "2")
        self.assertEqual(code, 1)
        self.assertIn("city-trial-4p", err)
        self.assertLess(time.monotonic() - started, 20)  # not the 30 s the sleeper sleeps
        self.assertEqual(self.snapshot(), before)

    def test_no_pass_starts_after_one_has_failed(self):
        with mock.patch.dict(os.environ, {"FAKE_FAIL_ON": TITLE_EXIT}):
            code, _, _ = self.warm("--jobs", "1")
        self.assertEqual(code, 1)
        self.assertEqual(len(self.game_lines()), 1)

    def test_caches_that_cant_be_joined_fail_the_warm_up_and_leave_saves_alone(self):
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", fake_cache([9]))
        before = self.snapshot()
        with mock.patch.object(shader_cache, "merge", side_effect=ValueError("headers differ")):
            code, _, err = self.warm()
        self.assertEqual(code, 1)
        self.assertIn("headers differ", err)
        self.assertEqual(self.snapshot(), before)

    def test_fewer_than_one_job_is_refused(self):
        code, _, err = self.warm("--jobs", "0")
        self.assertEqual(code, 2)
        self.assertIn("--jobs", err)
        self.assertFalse(self.saves.exists())


class ReportTest(WarmTestCase):
    def setUp(self):
        super().setUp()
        keys = {str(TITLE_FRAMES): [1, 2], str(FOUR_FRAMES): [2, 3, 4]}
        patch = mock.patch.dict(os.environ, {"FAKE_KEYS": json.dumps(keys)})
        patch.start()
        self.addCleanup(patch.stop)
        self.report = self.dir / "report"

    def lines(self) -> list[list[str]]:
        """The table under its header, the passes and then the all row."""
        text = (self.report / "report.txt").read_text()
        return [line.split() for line in text.splitlines()[1:]]

    def rows(self) -> list[list[str]]:
        return self.lines()[:-1]

    def test_each_pass_adds_the_keys_and_programs_no_earlier_pass_had(self):
        code, out, _ = self.warm("--report", str(self.report))
        self.assertEqual(code, 0)
        title, four = self.rows()
        # name, frames, s, boot programs, boot ms, own, +keys, +programs, keys, last frame built in
        self.assertEqual([title[0], title[1], *title[3:10]],
                         ["title", str(TITLE_FRAMES), "0", "0", "2", "2", "2", "2", "502"])
        self.assertEqual([four[0], four[1], *four[3:10]],
                         ["city-trial-4p", str(FOUR_FRAMES), "0", "0", "3", "2", "2", "4", "504"])
        self.assertEqual([line.split()[0] for line in out.splitlines()[-4:-1]],
                         ["title", "city-trial-4p", "all"])

    def test_untimed_passes_split_nothing_and_the_all_row_adds_up_their_frames(self):
        # The fake prints no [ft] lines, as the game doesn't without GCN_FRAMETIME=1.
        self.assertEqual(self.warm("--report", str(self.report))[0], 0)
        title, four, total = self.lines()
        for row in (title, four):
            self.assertEqual(row[10:], ["0.0"] * 4)
        self.assertEqual(total[:2], ["all", str(TITLE_FRAMES + FOUR_FRAMES)])
        self.assertEqual(total[3:], ["-"] * 7 + ["0.0"] * 4)

    def test_keys_the_players_cache_held_are_not_new_or_the_pass_s_own(self):
        self.saves.mkdir()
        write_file(self.saves, "shaders.bin", fake_cache([1]))
        self.assertEqual(self.warm("--report", str(self.report))[0], 0)
        title, four = self.rows()
        self.assertEqual([title[3], title[4], title[5], title[6], title[8]], ["1", "12", "1", "1", "2"])
        self.assertEqual([four[5], four[6], four[8]], ["3", "2", "4"])

    def test_each_pass_keeps_its_output_and_its_cache(self):
        self.assertEqual(self.warm("--report", str(self.report), "--jobs", "2")[0], 0)
        self.assertEqual(sorted(p.name for p in self.report.iterdir()),
                         ["city-trial-4p.bin", "city-trial-4p.log", "report.txt", "title.bin", "title.log"])
        self.assertEqual(len(shader_cache.load(self.report / "title.bin").keys), 2)
        self.assertEqual(len(shader_cache.load(self.report / "city-trial-4p.bin").keys), 3)
        self.assertIn("compiled program 4", (self.report / "city-trial-4p.log").read_text())

    def test_without_the_flag_nothing_is_kept(self):
        self.assertEqual(self.warm()[0], 0)
        self.assertFalse(self.report.exists())


class WriteReportTest(unittest.TestCase):
    """write_report on two passes whose logs and seconds the test picks."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def report(self, seconds: list[float]) -> list[str]:
        plan, scratch = [], []
        for name, frames in (("title", 1860), ("meadows", 6900)):
            plan.append(warm_shaders.Pass(name, frames, 1, self.dir / f"{name}.txt"))
            d = self.dir / name
            (d / "saves").mkdir(parents=True)
            # 0.1 s in frames to 2,000, 0.2 s in 2,001 to 3,400 and 0.4 s past 3,400
            write_file(d, "stdout.txt", ft_line(1999, 100) + ft_line(2000, 200) + ft_line(3400, 400))
            scratch.append(d)
        text = warm_shaders.write_report(self.dir / "report", plan, seconds, scratch,
                                         self.dir / "no-cache.bin")
        return text.splitlines()

    def test_the_splits_and_the_all_row_add_up_the_seconds(self):
        _, title, meadows, total = self.report([1.0, 2.5])
        self.assertEqual(title.split()[10:], ["0.3", "0.1", "0.2", "0.4"])
        self.assertEqual(meadows.split()[10:], ["1.8", "0.1", "0.2", "0.4"])
        self.assertEqual(total.split(), ["all", "8760", "3.5", *["-"] * 7, "2.1", "0.2", "0.4", "0.8"])

    def test_every_line_lines_up_under_the_header(self):
        lines = self.report([1.0, 2.5])
        self.assertEqual(lines[0].split(), ["pass", "frames", "s", "boot", "boot", "ms", "own", "+keys",
                                            "+progs", "keys", "last", "start", "0-2k", "2k-3.4k", "rest"])
        self.assertEqual({len(line) for line in lines}, {len(lines[0])})

    def test_the_table_has_a_column_for_each_share_a_pass_s_seconds_split_into(self):
        shares = warm_shaders.stretches(ft_line(1, 1), 1.0)
        self.assertEqual(len(warm_shaders.REPORT_COLUMNS), 10 + len(shares))
        self.assertEqual([label for label, _ in warm_shaders.REPORT_COLUMNS[10:]],
                         ["start", "0-2k", "2k-3.4k", "rest"])


if __name__ == "__main__":
    unittest.main()
