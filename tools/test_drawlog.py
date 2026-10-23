import tempfile
import unittest
from pathlib import Path

import drawlog
from testutil import run_main, write_file

# A world draw, a HUD draw in a 64 by 48 frame and a minimap draw, as GCN_DRAWLOG with
# GCN_DRAWLOG_VERBOSE=1 prints them. The viewport line follows its draw.
WORLD = ("[draw] 0 verts=6 st=0 texgens=1 proj=p,0.9838,0.0000,1.2350,0.0000,-1.52588e-06,-0.05 "
         "z=-1.00..-1.00 x=0.00..1.00 y=0.00..1.00 band=0.00000..1.00000 origin=0 slivers=0")
FULL_VP = "        viewport=320.0,-240.0,16777215.0 662.0,582.0,16777215.0 scissor=156156 3D5335 offset=02ACAB"
HUD = ("[draw] 1 verts=4 st=1 texgens=1 proj=o,0.0312,-1.0000,0.0417,1.0000,-0.01,-0.99 "
       "z=-1.00..-1.00 x=0.00..1.00 y=0.00..1.00 band=0.00000..1.00000 origin=0 slivers=0")
MAP = ("[draw] 2 verts=4 st=2 texgens=1 proj=p,3.5819,0.0000,4.5107,0.0000,-0.01,-0.99 "
       "z=-1.00..-1.00 x=0.00..1.00 y=0.00..1.00 band=0.00000..1.00000 origin=0 slivers=0")
MAP_VP = "        viewport=53.5,-40.0,16777215.0 918.5,417.0,16777215.0 scissor=156156 3D5335 offset=02ACAB"

CENSUS_WORLD = ("[census] f=4200 cam=81424A80 type=persp p=78.005,1.25538 vp=0,640,0,480 "
                "cb=800B04A8 cls=3 via=set")
CENSUS_WORLD_DRAW = ("[census] f=4200 cam=81424A80 type=persp p=78.005,1.25538 vp=0,640,0,480 "
                     "cb=801C6E84 cls=16 via=draw")
CENSUS_HUD = ("[census] f=4200 cam=812C5260 type=ortho p=0,-48,0,64 vp=0,640,0,480 "
              "cb=8011F8F4 cls=27 via=draw")
CENSUS_MAP = ("[census] f=4200 cam=81431D80 type=persp p=25,1.2593 vp=523,630,35,115 "
              "cb=8011500C cls=27 via=draw")

SYMBOLS = """\
kar_objalloc__near_800b04a8 = .text:0x800B04A8; // type:function size:0x314
fn_801C6E84 = .text:0x801C6E84; // type:function size:0x324
some_data = .data:0x80499618; // type:object size:0x4
"""


def census(frame: int, cam: str, aspect: float, vp: str = "0,640,0,480") -> str:
    return f"[census] f={frame} cam={cam} type=persp p=78.005,{aspect} vp={vp} cb=800B04A8 cls=3 via=set"


class ParseTest(unittest.TestCase):
    def test_viewport_line_belongs_to_the_draw_before_it(self):
        draws, _ = drawlog.parse([WORLD, FULL_VP, HUD])
        self.assertEqual(draws[0].viewport, (0.0, 0.0, 640.0, 480.0))
        self.assertIsNone(draws[1].viewport)

    def test_viewport_is_taken_off_the_scissor_offset(self):
        draws, _ = drawlog.parse([MAP, MAP_VP])
        self.assertEqual(draws[0].viewport, (523.0, 35.0, 107.0, 80.0))

    def test_census_lines_parse(self):
        _, cams = drawlog.parse([CENSUS_WORLD, CENSUS_HUD])
        self.assertEqual(cams[0].frame, 4200)
        self.assertEqual(cams[0].cam, 0x81424A80)
        self.assertEqual(cams[0].proj, (78.005, 1.25538))
        self.assertEqual(cams[0].viewport, (0.0, 0.0, 640.0, 480.0))
        self.assertEqual((cams[0].cb, cams[0].via), (0x800B04A8, "set"))
        self.assertEqual(cams[1].kind, "ortho")

    def test_census_line_at_the_end_of_a_viewport_line_counts_for_both(self):
        draws, cams = drawlog.parse([WORLD, FULL_VP + CENSUS_HUD])
        self.assertEqual(draws[0].viewport, (0.0, 0.0, 640.0, 480.0))
        self.assertEqual([c.cam for c in cams], [0x812C5260])

    def test_cut_off_lines_are_skipped(self):
        draws, cams = drawlog.parse([WORLD[:60], CENSUS_WORLD[:50]])
        self.assertEqual((draws, cams), ([], []))


class GroupTest(unittest.TestCase):
    def test_perspective_group_gives_aspect_fov_and_ratio(self):
        draws, _ = drawlog.parse([WORLD, FULL_VP, WORLD, FULL_VP])
        [g] = drawlog.group(draws)
        self.assertEqual(g.count, 2)
        self.assertAlmostEqual(g.aspect, 1.2553, places=4)
        self.assertAlmostEqual(g.fov, 78.0, places=1)
        self.assertAlmostEqual(g.ratio, 1.0621, places=4)

    def test_orthographic_group_gives_its_frame(self):
        draws, _ = drawlog.parse([HUD, FULL_VP])
        [g] = drawlog.group(draws)
        self.assertAlmostEqual(g.frame[0], 64.1, places=1)
        self.assertAlmostEqual(g.frame[1], 48.0, places=1)

    def test_groups_keep_draw_order(self):
        draws, _ = drawlog.parse([HUD, FULL_VP, WORLD, FULL_VP, HUD, FULL_VP])
        self.assertEqual([g.kind for g in drawlog.group(draws)], ["ortho", "persp"])

    def test_same_projection_in_another_viewport_is_another_group(self):
        draws, _ = drawlog.parse([WORLD, FULL_VP, WORLD, MAP_VP])
        self.assertEqual(len(drawlog.group(draws)), 2)


class MatchTest(unittest.TestCase):
    def setUp(self):
        draws, self.cams = drawlog.parse([WORLD, FULL_VP, HUD, FULL_VP, MAP, MAP_VP, CENSUS_WORLD,
                                          CENSUS_WORLD_DRAW, CENSUS_HUD, CENSUS_MAP])
        self.groups = drawlog.group(draws)

    def test_each_camera_finds_its_draws(self):
        world, hud, minimap = (drawlog.matching(g, self.cams) for g in self.groups)
        self.assertEqual({c.cam for c in world}, {0x81424A80})
        self.assertEqual({c.cam for c in hud}, {0x812C5260})
        self.assertEqual({c.cam for c in minimap}, {0x81431D80})

    def test_widened_projection_still_matches_its_camera_by_fov(self):
        widened = WORLD.replace("p,0.9838,", "p,0.7378,")
        draws, _ = drawlog.parse([widened, FULL_VP])
        [g] = drawlog.group(draws)
        self.assertEqual({c.cam for c in drawlog.matching(g, self.cams)}, {0x81424A80})


class CamerasCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def log(self, *lines: str) -> str:
        return str(write_file(self.dir, "stdout.txt", "\n".join(lines) + "\n"))

    def test_line_per_projection_with_named_callbacks(self):
        symbols = str(write_file(self.dir, "symbols.txt", SYMBOLS))
        code, out, _ = run_main(drawlog.main, "cameras",
                                self.log(WORLD, FULL_VP, CENSUS_WORLD, CENSUS_WORLD_DRAW),
                                "--symbols", symbols)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "persp aspect 1.2553 fov 78.0  vp 0,0 640x480  ratio 1.062  draws 1  cams 81424A80"
            "  stored 1.25538  set by kar_objalloc__near_800b04a8  drawn by fn_801C6E84"])

    def test_without_symbols_callbacks_print_as_addresses(self):
        code, out, _ = run_main(drawlog.main, "cameras", self.log(HUD, FULL_VP, CENSUS_HUD))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "ortho frame 64x48  vp 0,0 640x480  ratio 1.000  draws 1  cams 812C5260"
            "  drawn by 8011F8F4"])

    def test_orthographic_frame_with_no_camera_comes_from_the_projection(self):
        code, out, _ = run_main(drawlog.main, "cameras", self.log(HUD, FULL_VP))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["ortho frame 64.1x48.0  vp 0,0 640x480  ratio 0.998  draws 1"])

    def test_camera_with_no_draws_is_listed_after(self):
        code, out, _ = run_main(drawlog.main, "cameras", self.log(HUD, FULL_VP, CENSUS_HUD, CENSUS_MAP))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1],
                         "no draws: persp fov 25.0 vp 523,35 107x80  cams 81431D80  stored 1.2593"
                         "  drawn by 8011500C")

    def test_camera_set_outside_any_object_says_so(self):
        text = CENSUS_HUD.replace("cb=8011F8F4", "cb=00000000").replace("via=draw", "via=set")
        code, out, _ = run_main(drawlog.main, "cameras", self.log(HUD, FULL_VP, text))
        self.assertEqual(code, 0)
        self.assertTrue(out.rstrip().endswith("set by no object"), out)

    def test_orthographic_camera_with_no_draws_gives_its_frame(self):
        text = CENSUS_HUD.replace("p=0,-48,0,64", "p=-20,500,-20,660")
        code, out, _ = run_main(drawlog.main, "cameras", self.log(WORLD, FULL_VP, text))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1],
                         "no draws: ortho frame 680x520 vp 0,0 640x480  cams 812C5260  drawn by 8011F8F4")

    def test_frame_picks_census_lines(self):
        later = CENSUS_WORLD_DRAW.replace("f=4200", "f=4300").replace("801C6E84", "8018FEA4")
        code, out, _ = run_main(drawlog.main, "cameras",
                                self.log(WORLD, FULL_VP, CENSUS_WORLD_DRAW, later), "--frame", "4300")
        self.assertEqual(code, 0)
        self.assertIn("drawn by 8018FEA4", out)
        self.assertNotIn("801C6E84", out)

    def test_draw_with_no_viewport_line_says_so(self):
        code, out, _ = run_main(drawlog.main, "cameras", self.log(WORLD))
        self.assertEqual(code, 0)
        self.assertIn("vp ?", out)
        self.assertIn("ratio ?", out)

    def test_log_with_no_draws_exits_2(self):
        code, _, err = run_main(drawlog.main, "cameras", self.log(CENSUS_WORLD))
        self.assertEqual(code, 2)
        self.assertIn("GCN_DRAWLOG", err)

    def test_missing_log_exits_2(self):
        code, _, err = run_main(drawlog.main, "cameras", str(self.dir / "nope.txt"))
        self.assertEqual(code, 2)
        self.assertIn("nope.txt", err)


class AspectsCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def log(self, *lines: str) -> str:
        return str(write_file(self.dir, "stdout.txt", "\n".join(lines) + "\n"))

    def test_steady_camera_exits_0(self):
        lines = [census(f, "81424A80", 1.67384) for f in range(100, 700)]
        code, out, _ = run_main(drawlog.main, "aspects", self.log(*lines))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "81424A80 vp 0,0 640x480 fov 78.0  aspect 1.67384 in frames 100..699 (600 frames)"])

    def test_aspect_that_grows_exits_1(self):
        lines = [census(100, "81424A80", 1.67384), census(101, "81424A80", 2.23179)]
        code, out, _ = run_main(drawlog.main, "aspects", self.log(*lines))
        self.assertEqual(code, 1)
        self.assertIn("aspect 1.67384 in frames 100..100 (1 frames)", out)
        self.assertIn("aspect 2.23179 in frames 101..101 (1 frames)", out)
        self.assertIn("changed", out)

    def test_new_viewport_is_a_new_camera_use(self):
        lines = [census(100, "81424A80", 1.25538),
                 census(101, "81424A80", 1.39418, vp="0,308,0,208")]
        code, _, _ = run_main(drawlog.main, "aspects", self.log(*lines))
        self.assertEqual(code, 0)

    def test_window_leaves_out_other_frames(self):
        lines = [census(100, "81424A80", 1.25538), census(200, "81424A80", 1.67384)]
        code, out, _ = run_main(drawlog.main, "aspects", self.log(*lines), "--from", "150", "--to", "250")
        self.assertEqual(code, 0)
        self.assertNotIn("1.25538", out)

    def test_orthographic_cameras_are_left_out(self):
        code, out, _ = run_main(drawlog.main, "aspects", self.log(CENSUS_HUD, census(1, "81424A80", 1.2)))
        self.assertEqual(code, 0)
        self.assertNotIn("812C5260", out)

    def test_log_with_no_census_exits_2(self):
        code, _, err = run_main(drawlog.main, "aspects", self.log(WORLD))
        self.assertEqual(code, 2)
        self.assertIn("DRAGOON_CENSUS", err)


class HelpTest(unittest.TestCase):
    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = run_main(drawlog.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)

    def test_no_command_exits_2(self):
        code, _, _ = run_main(drawlog.main)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
