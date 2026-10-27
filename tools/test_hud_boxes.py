import tempfile
import unittest
from pathlib import Path

import drawlog
from testutil import run_main, write_file

# A 2D draw in the HUD's 64 by 48 frame, a world draw at 4:3 and the same world draw widened
# for 16:9, as GCN_DRAWLOG prints them.
ORTHO = "o,0.0312,-1.0000,0.0417,1.0000,-0.01,-0.99"
HUD3D = "p,3.5819,0.0000,4.5107,0.0000,-0.01,-0.99"
WORLD = "p,0.9838,0.0000,1.2350,0.0000,-1.52588e-06,-0.05"
WIDE_WORLD = "p,0.7378,0.0000,1.2350,0.0000,-1.52588e-06,-0.05"
TEX = "t0=12[00000000deadbeef]"
OTHER_TEX = "t0=13[00000000cafef00d]"


def draw(i: int, box: str = "523.0..630.0,35.0..115.0", anchor: str = "R(0..640)", proj: str = ORTHO,
         tex: str = TEX, slivers: int = 0) -> str:
    line = (f"[draw] {i} verts=4 st=1 texgens=1 proj={proj} z=-1.00..-1.00 x=0.00..1.00 y=0.00..1.00 "
            f"band=0.00000..1.00000 origin=0 slivers={slivers} anchor={anchor} scr={box}")
    return line + (f" {tex}" if tex else "")


def viewport(x: float, y: float, w: float, h: float) -> str:
    """The viewport line GCN_DRAWLOG_VERBOSE=1 prints for a viewport at x, y, w by h, with the
    scissor offset of 342 the game uses."""
    return (f"        viewport={w / 2:.1f},{-h / 2:.1f},16777215.0 {x + w / 2 + 342:.1f},{y + h / 2 + 342:.1f},"
            "16777215.0 scissor=156156 3D5335 offset=02ACAB")


def world(i: int, proj: str, view=(0, 0, 640, 480)) -> list[str]:
    return [draw(i, "0.0..640.0,0.0..480.0", "S", proj, "t0=3[0000000000000001]"), viewport(*view)]


# The four views of a four-player screen.
VIEWS_4P = [(8, 16, 308, 208), (324, 16, 308, 208), (8, 256, 308, 208), (324, 256, 308, 208)]


def world_4p(proj: str) -> list[str]:
    return [line for i, view in enumerate(VIEWS_4P) for line in world(i, proj, view)]


class HudCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def hud(self, old: list[str], new: list[str], *args: str) -> tuple[int, str, str]:
        old_log = write_file(self.dir, "old.txt", "\n".join(old) + "\n")
        new_log = write_file(self.dir, "new.txt", "\n".join(new) + "\n")
        return run_main(drawlog.main, "hud", str(old_log), str(new_log), *args)

    def one_draw(self, old: str, new: str, *args: str) -> tuple[int, str]:
        """The exit code and the line for one HUD draw over a one-player world."""
        code, out, _ = self.hud([*world(0, WORLD), old], [*world(0, WIDE_WORLD), new], *args)
        return code, out.splitlines()[0]

    def test_right_anchored_draw_keeps_its_box(self):
        code, out, _ = self.hud([*world(0, WORLD), draw(1)],
                                [*world(0, WIDE_WORLD), draw(1, "552.2..632.5,35.0..115.0")],
                                "--aspect", "16:9")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "1>1 ortho R(0..640) 00000000deadbeef  4:3 523.0..630.0,35.0..115.0  "
            "16:9 736.3..843.3,35.0..115.0  ok",
            "anchored 1  failed 0  stretched 0"])

    def test_aspect_defaults_to_16_9(self):
        code, line = self.one_draw(draw(1), draw(1, "552.2..632.5,35.0..115.0"))
        self.assertEqual(code, 0)
        self.assertIn("16:9 736.3..843.3", line)

    def test_anchored_draw_left_unsqueezed_fails_its_width_and_edge(self):
        code, line = self.one_draw(draw(1), draw(1))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("16:9 697.3..840.0,35.0..115.0  FAIL width 107.0 to 142.7; "
                                      "right edge 10.0 to 13.3"), line)

    def test_left_anchored_draw_keeps_its_box(self):
        code, line = self.one_draw(draw(1, "20.0..120.0,30.0..60.0", "L(0..640)"),
                                   draw(1, "15.0..90.0,30.0..60.0", "L(0..640)"))
        self.assertEqual(code, 0)
        self.assertTrue(line.endswith("16:9 20.0..120.0,30.0..60.0  ok"), line)

    def test_left_edge_that_moves_fails(self):
        code, line = self.one_draw(draw(1, "20.0..120.0,30.0..60.0", "L(0..640)"),
                                   draw(1, "30.0..105.0,30.0..60.0", "L(0..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL left edge 20.0 to 40.0"), line)

    def test_height_that_changes_fails(self):
        code, line = self.one_draw(draw(1, "20.0..120.0,30.0..60.0", "L(0..640)"),
                                   draw(1, "15.0..90.0,30.0..62.0", "L(0..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL height 30.0 to 32.0"), line)

    def test_a_pixel_off_passes_and_more_fails(self):
        # 15.75 and 90.75 come out 1 pixel right of 20 and 120 at 16:9.
        code, _ = self.one_draw(draw(1, "20.0..120.0,30.0..60.0", "L(0..640)"),
                                draw(1, "15.7..90.7,29.0..60.0", "L(0..640)"))
        self.assertEqual(code, 0)
        code, line = self.one_draw(draw(1, "20.0..120.0,30.0..60.0", "L(0..640)"),
                                   draw(1, "15.0..91.0,30.0..60.0", "L(0..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL width 100.0 to 101.3"), line)

    def test_centered_draw_keeps_its_offset_from_the_middle(self):
        code, line = self.one_draw(draw(1, "400.0..440.0,30.0..60.0", "C(0..640)"),
                                   draw(1, "380.0..410.0,30.0..60.0", "C(0..640)"))
        self.assertEqual(code, 0)
        self.assertTrue(line.endswith("16:9 506.7..546.7,30.0..60.0  ok"), line)

    def test_centered_draw_left_unsqueezed_fails_its_middle(self):
        code, line = self.one_draw(draw(1, "400.0..440.0,30.0..60.0", "C(0..640)"),
                                   draw(1, "400.0..440.0,30.0..60.0", "C(0..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL width 40.0 to 53.3; middle 100.0 to 133.3"), line)

    def test_right_anchor_to_a_rect_inside_the_screen(self):
        code, line = self.one_draw(draw(1, "560.0..600.0,30.0..60.0", "R(320..600)"),
                                   draw(1, "570.0..600.0,30.0..60.0", "R(320..600)"))
        self.assertEqual(code, 0)
        self.assertTrue(line.endswith("16:9 760.0..800.0,30.0..60.0  ok"), line)

    def test_other_aspects_scale_the_display(self):
        # At 21:9, k is 4/7 and the display is 1120 pixels across.
        code, line = self.one_draw(draw(1, "35.0..70.0,30.0..60.0", "L(0..640)"),
                                   draw(1, "20.0..40.0,30.0..60.0", "L(0..640)"), "--aspect", "21:9")
        self.assertEqual(code, 0)
        self.assertTrue(line.endswith("21:9 35.0..70.0,30.0..60.0  ok"), line)

    def test_aspect_as_a_number(self):
        code, line = self.one_draw(draw(1), draw(1, "552.2..632.5,35.0..115.0"), "--aspect", "1.777778")
        self.assertEqual(code, 0)
        self.assertIn("1.777778 736.3..843.3", line)

    def test_bad_aspect_exits_2(self):
        for bad in ("wide", "16:0", "0", "-4:3", "nan", "inf"):
            with self.subTest(bad=bad):
                code, out, _ = self.hud([*world(0, WORLD), draw(1)], [*world(0, WIDE_WORLD), draw(1)],
                                        "--aspect", bad)
                self.assertEqual((code, out), (2, ""))

    def test_draw_in_another_view_anchored_to_the_screen_leaves_its_view(self):
        old = [*world_4p(WORLD), draw(4, "400.0..440.0,300.0..320.0", "L(0..640)")]
        new = [*world_4p(WIDE_WORLD), draw(4, "300.0..330.0,300.0..320.0", "L(0..640)")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 1)
        self.assertTrue(out.splitlines()[0].endswith("FAIL leaves its view 324,256 308x208 by 32.0"), out)

    def test_the_smallest_view_holding_a_draw_is_its_view(self):
        old = [*world(9, WORLD), *world_4p(WORLD), draw(4, "400.0..440.0,300.0..320.0", "L(0..640)")]
        new = [*world(9, WIDE_WORLD), *world_4p(WIDE_WORLD), draw(4, "300.0..330.0,300.0..320.0", "L(0..640)")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 1)
        self.assertIn("leaves its view 324,256 308x208", out)

    def test_draw_a_pixel_over_its_view_belongs_to_it(self):
        old = [*world_4p(WORLD), draw(4, "323.5..363.5,300.0..320.0", "L(0..640)")]
        new = [*world_4p(WIDE_WORLD), draw(4, "242.6..272.6,300.0..320.0", "L(0..640)")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 1)
        self.assertIn("leaves its view 324,256 308x208", out)

    def test_viewports_of_unwidened_projections_arent_views(self):
        # The minimap's own viewport isn't a view, so its draws anchor to the screen.
        minimap = "\n" + viewport(523, 35, 107, 80)
        code, line = self.one_draw(draw(1, proj=HUD3D) + minimap,
                                   draw(1, "552.2..632.5,35.0..115.0", proj=HUD3D) + minimap)
        self.assertEqual(code, 0)
        self.assertTrue(line.endswith("ok"), line)

    def test_draw_that_rises_out_of_its_view_fails(self):
        code, line = self.one_draw(draw(1, "20.0..120.0,0.0..30.0", "L(0..640)"),
                                   draw(1, "15.0..90.0,-5.0..25.0", "L(0..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL leaves its view 0,0 640x480 by 5.0"), line)

    def test_each_side_of_the_box_is_held_to_its_view(self):
        # Under the screen by 50 at both aspects, and newly 10 past its left at 16:9.
        code, line = self.one_draw(draw(1, "20.0..60.0,450.0..530.0", "L(-90..640)"),
                                   draw(1, "-7.5..22.5,450.0..530.0", "L(-90..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL leaves its view 0,0 640x480 by 10.0"), line)

    def test_draw_anchored_to_its_own_view_stays_in_it(self):
        old = [*world_4p(WORLD), draw(4, "400.0..440.0,50.0..70.0", "L(324..632)")]
        new = [*world_4p(WIDE_WORLD), draw(4, "381.0..411.0,50.0..70.0", "L(324..632)")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[0].endswith("16:9 508.0..548.0,50.0..70.0  ok"), out)

    def test_draw_across_two_views_belongs_to_the_screen(self):
        old = [*world_4p(WORLD), draw(4, "0.0..40.0,200.0..280.0", "L(0..640)")]
        new = [*world_4p(WIDE_WORLD), draw(4, "0.0..30.0,200.0..280.0", "L(0..640)")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[0].endswith("16:9 0.0..40.0,200.0..280.0  ok"), out)

    def test_draw_that_overhangs_the_screen_as_much_as_at_4_3_passes(self):
        code, line = self.one_draw(draw(1, "-20.0..40.0,30.0..60.0", "L(0..640)"),
                                   draw(1, "-15.0..30.0,30.0..60.0", "L(0..640)"))
        self.assertEqual(code, 0)
        self.assertTrue(line.endswith("ok"), line)

    def test_draw_that_overhangs_the_screen_more_fails(self):
        code, line = self.one_draw(draw(1, "560.0..640.0,30.0..60.0", "L(0..640)"),
                                   draw(1, "580.0..660.0,30.0..60.0", "L(0..640)"))
        self.assertEqual(code, 1)
        self.assertIn("leaves its view 0,0 640x480 by 26.7", line)

    def test_draws_pair_by_texture(self):
        old = [*world(0, WORLD), draw(1, "20.0..120.0,30.0..60.0", "L(0..640)"),
               draw(2, tex=OTHER_TEX)]
        new = [*world(0, WIDE_WORLD), draw(1, "552.2..632.5,35.0..115.0", tex=OTHER_TEX),
               draw(2, "15.0..90.0,30.0..60.0", "L(0..640)")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("1>2 ortho L(0..640) 00000000deadbeef  "), lines)
        self.assertTrue(lines[1].startswith("2>1 ortho R(0..640) 00000000cafef00d  "), lines)

    def test_draws_with_one_texture_pair_in_order(self):
        old = [*world(0, WORLD), draw(1, "20.0..120.0,30.0..60.0", "L(0..640)"),
               draw(2, "20.0..120.0,70.0..90.0", "L(0..640)")]
        new = [*world(0, WIDE_WORLD), draw(3, "15.0..90.0,30.0..60.0", "L(0..640)"),
               draw(5, "15.0..90.0,70.0..90.0", "L(0..640)")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 0)
        self.assertEqual([line.split()[0] for line in out.splitlines()[:2]], ["1>3", "2>5"])

    def test_another_projection_kind_doesnt_pair(self):
        old = [*world(0, WORLD), draw(1)]
        new = [*world(0, WIDE_WORLD), draw(1, "552.2..632.5,35.0..115.0", proj=HUD3D)]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), [
            "1> ortho R(0..640) 00000000deadbeef  4:3 523.0..630.0,35.0..115.0  FAIL no match at 16:9",
            ">1 persp R(0..640) 00000000deadbeef  16:9 736.3..843.3,35.0..115.0  FAIL no match at 4:3",
            "anchored 2  failed 2  stretched 0"])

    def test_another_anchor_fails(self):
        code, line = self.one_draw(draw(1), draw(1, "552.2..632.5,35.0..115.0", "L(0..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL anchor R(0..640) at 4:3, L(0..640) at 16:9"), line)

    def test_another_rect_fails(self):
        code, line = self.one_draw(draw(1), draw(1, "552.2..632.5,35.0..115.0", "R(320..640)"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("FAIL anchor R(0..640) at 4:3, R(320..640) at 16:9"), line)

    def test_draw_anchored_at_one_aspect_only_fails(self):
        code, line = self.one_draw(draw(1, anchor="S"), draw(1, "552.2..632.5,35.0..115.0"))
        self.assertEqual(code, 1)
        self.assertTrue(line.startswith("1>1 ortho R(0..640) "), line)
        self.assertTrue(line.endswith("FAIL anchor S at 4:3, R(0..640) at 16:9"), line)

    def test_stretched_hud_draw_is_listed_and_passes(self):
        code, out, _ = self.hud([*world(0, WORLD), draw(1, anchor="S")],
                                [*world(0, WIDE_WORLD), draw(1, anchor="S")])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "1>1 ortho S 00000000deadbeef  4:3 523.0..630.0,35.0..115.0  16:9 697.3..840.0,35.0..115.0  stretched",
            "anchored 0  failed 0  stretched 1"])

    def test_widened_draws_are_left_out(self):
        code, out, _ = self.hud(world(0, WORLD), world(0, WIDE_WORLD))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["anchored 0  failed 0  stretched 0"])

    def test_stretched_draw_with_no_match_is_left_out(self):
        code, out, _ = self.hud([*world(0, WORLD), draw(1, anchor="S")],
                                [*world(0, WIDE_WORLD), draw(1, anchor="S", tex=OTHER_TEX)])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["anchored 0  failed 0  stretched 0"])

    def test_texture_copy_and_untextured_draws_pair(self):
        old = [*world(0, WORLD), draw(1, tex="t0=40*"), draw(2, tex="")]
        new = [*world(0, WIDE_WORLD), draw(1, "552.2..632.5,35.0..115.0", tex="t0=41*"),
               draw(2, "552.2..632.5,35.0..115.0", tex="")]
        code, out, _ = self.hud(old, new)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("1>1 ortho R(0..640) copy  "), lines)
        self.assertTrue(lines[1].startswith("2>2 ortho R(0..640) untextured  "), lines)

    def test_two_textures_are_both_named(self):
        code, line = self.one_draw(draw(1, tex=f"{TEX} t1=13[00000000cafef00d]"),
                                   draw(1, "552.2..632.5,35.0..115.0", tex=f"{TEX} t1=13[00000000cafef00d]"))
        self.assertEqual(code, 0)
        self.assertIn(" 00000000deadbeef,00000000cafef00d  ", line)

    def test_draw_with_no_box_at_either_aspect_passes(self):
        code, line = self.one_draw(draw(1, "none"), draw(1, "none"))
        self.assertEqual(code, 0)
        self.assertTrue(line.endswith("4:3 none  16:9 none  ok"), line)

    def test_draw_with_no_box_at_one_aspect_fails(self):
        code, line = self.one_draw(draw(1), draw(1, "none"))
        self.assertEqual(code, 1)
        self.assertTrue(line.endswith("16:9 none  FAIL no box at 16:9"), line)

    def test_fields_after_a_census_line_count(self):
        census = "[census] f=4200 cam=812C5260 type=ortho p=0,-48,0,64 vp=0,640,0,480 cb=8011F8F4 cls=27 via=draw"
        head, tail = draw(1, "552.2..632.5,35.0..115.0").split(" anchor=")
        code, out, _ = self.hud([*world(0, WORLD), draw(1)],
                                [*world(0, WIDE_WORLD), head + census, " anchor=" + tail])
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[0].startswith("1>1 ortho R(0..640) 00000000deadbeef  "), out)

    def test_fields_and_textures_after_slivers_count(self):
        head = draw(1, slivers=1).split(" anchor=")[0]
        sliver = ("        sliver src d1:0 d1:1 d1:2 (0.000,0.000,0.000) (50.000,0.000,0.000) "
                  "(100.000,0.010,0.000) len=100 anchor=R(0..640) scr=552.2..632.5,35.0..115.0")
        code, out, _ = self.hud([*world(0, WORLD), draw(1)],
                                [*world(0, WIDE_WORLD), head, sliver, "        " + TEX])
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[0].startswith("1>1 ortho R(0..640) 00000000deadbeef  "), out)

    def test_verbose_lines_after_a_draw_with_no_textures_arent_textures(self):
        code, line = self.one_draw(draw(1, tex=""), draw(1, "552.2..632.5,35.0..115.0", tex="") +
                                   "\n        genmode=000410 stages=1 colors=1")
        self.assertEqual(code, 0)
        self.assertIn(" untextured  ", line)

    def test_verbose_lines_after_a_textured_draw_leave_its_textures(self):
        genmode = "\n        genmode=000410 stages=1 colors=1"
        code, line = self.one_draw(draw(1) + genmode, draw(1, "552.2..632.5,35.0..115.0") + genmode)
        self.assertEqual(code, 0)
        self.assertIn(" 00000000deadbeef  ", line)

    def test_log_with_no_draws_exits_2(self):
        code, _, err = self.hud(["[census] f=1"], world(0, WIDE_WORLD))
        self.assertEqual(code, 2)
        self.assertIn("GCN_DRAWLOG", err)

    def test_log_with_no_anchors_exits_2(self):
        old = [line.split(" anchor=")[0] if line.startswith("[draw]") else line for line in world(0, WORLD)]
        code, _, err = self.hud(old, world(0, WIDE_WORLD))
        self.assertEqual(code, 2)
        self.assertIn("anchor=", err)

    def test_log_with_no_viewports_exits_2(self):
        code, _, err = self.hud([world(0, WORLD)[0]], world(0, WIDE_WORLD))
        self.assertEqual(code, 2)
        self.assertIn("GCN_DRAWLOG_VERBOSE", err)

    def test_missing_log_exits_2(self):
        code, _, err = run_main(drawlog.main, "hud", str(self.dir / "old.txt"), str(self.dir / "new.txt"))
        self.assertEqual(code, 2)
        self.assertIn("old.txt", err)

    def test_a_byte_that_isnt_utf8_is_read_past(self):
        old = write_file(self.dir, "old.txt", "\n".join([*world(0, WORLD), draw(1)]) + "\n")
        new = self.dir / "new.txt"
        new.write_bytes(b"OSReport \xff\n" + "\n".join([*world(0, WIDE_WORLD), draw(1)]).encode() + b"\n")
        code, out, _ = run_main(drawlog.main, "hud", str(old), str(new))
        self.assertEqual(code, 1)
        self.assertIn("FAIL width", out)


if __name__ == "__main__":
    unittest.main()
