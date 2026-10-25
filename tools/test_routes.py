import tempfile
import unittest
from pathlib import Path

import routes
import warm_shaders
from testutil import write_file


class ManifestTest(unittest.TestCase):
    def test_parses_routes_and_extra_args(self):
        parsed = routes.parse_manifest("# comment\n\ncity-trial-4p 30 60 2700,3480 --pads=4\n")
        self.assertEqual(len(parsed), 1)
        r = parsed[0]
        self.assertEqual((r.name, r.seconds, r.dump_every, r.required, r.extra, r.warm),
                         ("city-trial-4p", 30, 60, [2700, 3480], ["--pads=4"], None))

    def test_warm_frame_is_kept_out_of_the_probe_settings(self):
        parsed = routes.parse_manifest("sky 25 60 4200 --pads=2 warm=14400 GCN_FRAMETIME=1\n")
        self.assertEqual((parsed[0].extra, parsed[0].warm), (["--pads=2", "GCN_FRAMETIME=1"], 14400))

    def refused(self, settings: str, required: str = "60,4200") -> str:
        """The message parse_manifest refuses a sky route with SETTINGS with, on line 2."""
        with self.assertRaises(ValueError) as caught:
            routes.parse_manifest(f"# comment\nsky 25 60 {required} {settings}\n")
        self.assertTrue(str(caught.exception).startswith("manifest line 2, route sky: "),
                        caught.exception)
        return str(caught.exception)

    def test_a_warm_frame_that_isnt_plain_ascii_digits_is_refused(self):
        for value in ("", "abc", "-5", "0", "+7000", "7_000", "７０００", "7０００", "07000", "7000x"):
            with self.subTest(value=value):
                self.assertIn(f"warm={value} isn't a whole frame number", self.refused(f"warm={value}"))

    def test_a_warm_frame_at_or_before_the_last_required_frame_is_refused(self):
        for value in ("100", "4200"):  # past the first required frame, but not the last
            with self.subTest(value=value):
                self.assertIn("past the last required frame, 4200", self.refused(f"warm={value}"))
        self.assertEqual(routes.parse_manifest("sky 25 60 60,4200 warm=4201\n")[0].warm, 4201)

    def test_a_second_warm_is_refused(self):
        self.assertIn("warm=7300 is a second warm=", self.refused("warm=7000 warm=7300"))

    def test_a_misspelled_warm_is_refused_not_passed_to_probe_sh(self):
        for setting in ("WARM=7000", "warm:7000", "--warm=7000", "Warm=7000", "warm",
                        "WARM-FROM=meadows", "warm_from=meadows", "--warm-from=meadows",
                        "warmfrom=meadows", "warm-from:meadows"):
            with self.subTest(setting=setting):
                self.assertIn(f"{setting} isn't a setting", self.refused(f"--pads=2 {setting}"))

    def test_warm_from_names_the_route_whose_pass_plays_this_one_and_stays_out_of_probe(self):
        parsed = routes.parse_manifest("meadows 30 60 6000 warm=7000\n"
                                       "valley 25 60 4200 --pads=2 warm-from=meadows GCN_X=1\n")
        self.assertEqual([(r.name, r.warm, r.warm_from) for r in parsed],
                         [("meadows", 7000, None), ("valley", None, "meadows")])
        self.assertEqual(parsed[1].extra, ["--pads=2", "GCN_X=1"])

    def test_warm_from_may_name_a_route_further_down(self):
        parsed = routes.parse_manifest("valley 25 60 4200 warm-from=tour\ntour 90 60 4200,9000\n")
        self.assertEqual(parsed[0].warm_from, "tour")

    def test_a_second_or_empty_warm_from_is_refused(self):
        self.assertIn("warm-from=b is a second warm-from=", self.refused("warm-from=a warm-from=b"))
        self.assertIn("warm-from= names no route", self.refused("warm-from="))

    def test_warm_and_warm_from_on_one_route_are_refused(self):
        for settings in ("warm=7000 warm-from=meadows", "warm-from=meadows warm=7000"):
            with self.subTest(settings=settings):
                self.assertIn("warm=7000 and warm-from=meadows together", self.refused(settings))

    def test_warm_from_has_to_name_another_route_with_a_pass_of_its_own(self):
        cases = (("valley 25 60 4200 warm-from=nowhere\n", 1, "valley",
                  "warm-from=nowhere names no other route in the manifest"),
                 ("# c\nvalley 25 60 4200 warm-from=valley\n", 2, "valley",
                  "warm-from=valley names no other route in the manifest"),
                 ("tour 90 60 9000\nsky 25 60 4200 warm-from=tour\nvalley 25 60 4200 warm-from=sky\n",
                  3, "valley", "warm-from=sky names a route that tour's pass plays"))
        for text, line, name, why in cases:
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as caught:
                    routes.parse_manifest(text)
                self.assertEqual(str(caught.exception), f"manifest line {line}, route {name}: {why}")


def presses(name: str) -> list[str]:
    """The presses of route NAME's file, in order."""
    return warm_shaders.script_text(routes.route_file(name)).split(",")


def press_frame(press: str) -> int:
    return int(press.split(":")[0].split("/")[-1])


class RealManifestTest(unittest.TestCase):
    """tests/hashes/manifest.txt itself."""

    # The last frame each route compiled a program in, played unpaced to frame 16,000 from a
    # warm-up whose passes stopped 900 frames past their last required frames. Sky Sands draws the
    # late programs of air-ride-race, air-ride-celestial-valley and air-ride-beanstalk-park by its
    # own last one. docs/dev/status.md has the runs, under "Longer course passes". Checker Knights
    # compiled none there. Its frame is the last compile of its own pass from an empty cache, since
    # raced after Magma Flows it missed three programs ("Chained course passes").
    LAST_COMPILE = {"air-ride-sky-sands": 14186, "air-ride-magma-flows": 12525,
                    "air-ride-frozen-hillside": 5752, "air-ride-checker-knights": 5005}

    def setUp(self):
        self.routes = routes.parse_manifest(routes.MANIFEST.read_text())
        self.by_name = {r.name: r for r in self.routes}

    def test_every_route_parses_with_a_route_file_and_no_warm_among_its_probe_settings(self):
        self.assertGreater(len(self.routes), 0)
        for r in self.routes:
            with self.subTest(route=r.name):
                self.assertTrue(routes.route_file(r.name).is_file())
                self.assertEqual([s for s in r.extra if "warm" in s.lower()], [])

    def test_the_routes_that_compile_late_are_raced_first_and_past_their_last_compile(self):
        # A race that follows another starts from another state of the game, and such races
        # missed programs these three built late. So the pass that builds a route's programs
        # opens with that route's own presses, and presses nothing more until it's past the frame.
        for name, frame in self.LAST_COMPILE.items():
            with self.subTest(route=name):
                source = self.by_name[self.by_name[name].warm_from or name]
                own, played = presses(name), presses(source.name)
                self.assertEqual(played[:len(own)], own)
                self.assertEqual([p for p in played[len(own):] if press_frame(p) <= frame], [])
                self.assertGreater(warm_shaders.pass_frames(source), frame)


class SelectRoutesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.manifest = write_file(Path(tmp.name), "manifest.txt", "title 20 60 120\nmenu 20 60 1200\n")

    def test_no_names_gives_every_route_in_manifest_order(self):
        self.assertEqual([r.name for r in routes.select_routes([], self.manifest)], ["title", "menu"])

    def test_names_pick_their_routes(self):
        self.assertEqual([r.name for r in routes.select_routes(["menu"], self.manifest)], ["menu"])

    def test_a_name_not_in_the_manifest_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not in the manifest: \\['nope'\\]"):
            routes.select_routes(["menu", "nope"], self.manifest)


class RouteFileTest(unittest.TestCase):
    def test_is_the_named_file_in_tests_routes(self):
        self.assertEqual(routes.route_file("title"), routes.ROOT / "tests" / "routes" / "title.txt")


if __name__ == "__main__":
    unittest.main()
