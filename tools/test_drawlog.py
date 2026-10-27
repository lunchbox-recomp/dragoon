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
# The HUD's 3D camera, with the world's viewport and the minimap's field of view, and an
# orthographic camera framing the whole screen.
CENSUS_HUD3D = ("[census] f=4200 cam=812C51C0 type=persp p=25,1.25538 vp=0,640,0,480 "
                "cb=80114F1C cls=27 via=draw")
CENSUS_SCREEN = ("[census] f=4200 cam=812C5300 type=ortho p=0,-480,0,640 vp=0,640,0,480 "
                 "cb=8011F8F4 cls=27 via=draw")

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

    def test_camera_with_another_fov_in_the_same_viewport_is_left_out(self):
        _, cams = drawlog.parse([CENSUS_WORLD, CENSUS_HUD3D])
        world = drawlog.matching(self.groups[0], cams)
        self.assertEqual({c.cam for c in world}, {0x81424A80})

    def test_camera_with_the_same_fov_in_another_viewport_is_left_out(self):
        _, cams = drawlog.parse([CENSUS_HUD3D, CENSUS_MAP])
        minimap = drawlog.matching(self.groups[2], cams)
        self.assertEqual({c.cam for c in minimap}, {0x81431D80})

    def test_orthographic_camera_with_another_frame_is_left_out(self):
        _, cams = drawlog.parse([CENSUS_SCREEN, CENSUS_HUD])
        hud = drawlog.matching(self.groups[1], cams)
        self.assertEqual({c.cam for c in hud}, {0x812C5260})

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

    def test_without_frame_every_census_line_of_a_drawn_camera_counts_as_drawn(self):
        later = CENSUS_HUD.replace("f=4200", "f=4201")
        code, out, _ = run_main(drawlog.main, "cameras", self.log(HUD, FULL_VP, CENSUS_MAP, CENSUS_HUD, later))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "ortho frame 64x48  vp 0,0 640x480  ratio 1.000  draws 1  cams 812C5260  drawn by 8011F8F4",
            "no draws: persp fov 25.0 vp 523,35 107x80  cams 81431D80  stored 1.2593  drawn by 8011500C"])

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

    def test_window_takes_its_first_and_last_frames(self):
        lines = [census(149, "81424A80", 1.25538), census(150, "81424A80", 1.67384),
                 census(250, "81424A80", 1.67384), census(251, "81424A80", 2.23179)]
        code, out, _ = run_main(drawlog.main, "aspects", self.log(*lines), "--from", "150", "--to", "250")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "81424A80 vp 0,0 640x480 fov 78.0  aspect 1.67384 in frames 150..250 (2 frames)"])

    def test_orthographic_cameras_are_left_out(self):
        code, out, _ = run_main(drawlog.main, "aspects", self.log(CENSUS_HUD, census(1, "81424A80", 1.2)))
        self.assertEqual(code, 0)
        self.assertNotIn("812C5260", out)

    def test_log_with_no_census_exits_2(self):
        code, _, err = run_main(drawlog.main, "aspects", self.log(WORLD))
        self.assertEqual(code, 2)
        self.assertIn("DRAGOON_CENSUS", err)


def setter(frame: int, cam: str = "81424A80", lr: str = "800C2884", lr2: str = "800C1F00",
           given: str = "1.25538", stored: str = "1.67383") -> str:
    return f"[aspect] f={frame} cam={cam} lr={lr} lr2={lr2} given={given} stored={stored}"


class SettersCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def log(self, *lines: str) -> str:
        return str(write_file(self.dir, "stdout.txt", "\n".join(lines) + "\n"))

    def test_calls_from_one_place_with_one_aspect_make_one_line(self):
        code, out, _ = run_main(drawlog.main, "setters", self.log(setter(100), setter(101), setter(102)))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "81424A80  from 800C2884  called from 800C1F00  given 1.25538 stored 1.67383"
            "  in frames 100..102 (3 frames)"])

    def test_another_caller_or_aspect_is_another_line(self):
        lines = [setter(100), setter(101, lr="80066E4C", stored="1.25538"), setter(102, given="1.39419"),
                 setter(103, lr2="8011586C")]
        code, out, _ = run_main(drawlog.main, "setters", self.log(*lines))
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 4)
        self.assertIn("from 80066E4C  called from 800C1F00  given 1.25538 stored 1.25538", out)
        self.assertIn("given 1.39419", out)
        self.assertIn("called from 8011586C", out)

    def test_symbols_name_the_function_and_offset(self):
        symbols = str(write_file(self.dir, "symbols.txt",
                                 "kar_cmreplay__near_800c24e8 = .text:0x800C24E8; // type:function size:0x400\n"
                                 "fn_80066E00 = .text:0x80066E00; // type:function size:0x80\n"))
        lines = [setter(100, lr2="80066E10"), setter(101, lr="80001000")]
        code, out, _ = run_main(drawlog.main, "setters", self.log(*lines), "--symbols", symbols)
        self.assertEqual(code, 0)
        self.assertIn("from 800C2884 kar_cmreplay__near_800c24e8+0x39C  called from 80066E10 fn_80066E00+0x10  given",
                      out)
        self.assertIn("from 80001000  called from", out)

    def test_a_call_that_ends_a_function_is_named_by_that_function(self):
        symbols = str(write_file(self.dir, "symbols.txt",
                                 "fn_A = .text:0x80066E00; // type:function size:0x4C\n"
                                 "fn_B = .text:0x80066E4C; // type:function size:0x80\n"))
        lines = [setter(100, lr="80066E4C", lr2="80066E50")]
        code, out, _ = run_main(drawlog.main, "setters", self.log(*lines), "--symbols", symbols)
        self.assertEqual(code, 0)
        self.assertIn("from 80066E4C fn_A+0x4C  called from 80066E50 fn_B+0x4  given", out)

    def test_an_address_past_the_last_function_is_left_unnamed(self):
        symbols = str(write_file(self.dir, "symbols.txt",
                                 "fn_B = .text:0x80066E4C; // type:function size:0x80\n"))
        code, out, _ = run_main(drawlog.main, "setters", self.log(setter(100, lr2="80066E50")), "--symbols", symbols)
        self.assertEqual(code, 0)
        self.assertIn("from 800C2884  called from 80066E50 fn_B+0x4  given", out)

    def test_a_function_with_no_size_ends_at_the_next(self):
        symbols = str(write_file(self.dir, "symbols.txt",
                                 "fn_A = .text:0x80066E00;\n"
                                 "fn_B = .text:0x80066F00; // type:function size:0x10\n"))
        lines = [setter(100, lr="80066EFC", lr2="80066F04")]
        code, out, _ = run_main(drawlog.main, "setters", self.log(*lines), "--symbols", symbols)
        self.assertEqual(code, 0)
        self.assertIn("from 80066EFC fn_A+0xFC  called from 80066F04 fn_B+0x4  given", out)

    def test_window_and_camera_pick_lines(self):
        lines = [setter(99), setter(100), setter(100, cam="812C51C0"), setter(201)]
        code, out, _ = run_main(drawlog.main, "setters", self.log(*lines),
                                "--from", "100", "--to", "200", "--cam", "81424a80")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "81424A80  from 800C2884  called from 800C1F00  given 1.25538 stored 1.67383"
            "  in frames 100..100 (1 frames)"])

    def test_infinite_and_undefined_aspects_are_listed(self):
        lines = [setter(100), setter(101, given="inf", stored="inf"), setter(102, given="nan", stored="-nan"),
                 setter(200)]
        code, out, _ = run_main(drawlog.main, "setters", self.log(*lines))
        self.assertEqual(code, 0)
        self.assertIn("given 1.25538 stored 1.67383  in frames 100..200 (2 frames)", out)
        self.assertIn("given inf stored inf  in frames 101..101 (1 frames)", out)
        self.assertIn("given nan stored -nan  in frames 102..102 (1 frames)", out)

    def test_a_log_of_only_infinite_aspects_is_read(self):
        code, out, _ = run_main(drawlog.main, "setters", self.log(setter(101, given="-inf", stored="-inf")))
        self.assertEqual(code, 0)
        self.assertIn("given -inf stored -inf", out)

    def test_a_camera_with_no_aspect_stores_none(self):
        code, out, _ = run_main(drawlog.main, "setters", self.log(setter(100, cam="812C5260", stored="none")))
        self.assertEqual(code, 0)
        self.assertIn("812C5260  from 800C2884  called from 800C1F00  given 1.25538 stored none", out)

    def test_line_at_the_end_of_a_renderer_line_counts(self):
        code, out, _ = run_main(drawlog.main, "setters", self.log(FULL_VP + setter(100)))
        self.assertEqual(code, 0)
        self.assertIn("81424A80", out)

    def test_log_with_no_aspect_lines_exits_2(self):
        code, _, err = run_main(drawlog.main, "setters", self.log(CENSUS_WORLD))
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
