import tempfile
import unittest
from pathlib import Path

import routes
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
        for value in ("", "abc", "-5", "0", "+7000", "1_000", "７０００", "07000"):
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
        for setting in ("WARM=7000", "warm:7000", "--warm=7000", "Warm=7000", "warm"):
            with self.subTest(setting=setting):
                self.assertIn(f"{setting} isn't a setting", self.refused(f"--pads=2 {setting}"))


class RealManifestTest(unittest.TestCase):
    """tests/hashes/manifest.txt itself."""

    # The last frame each route compiled a program in, played unpaced to frame 16,000 from a
    # warm-up whose passes stopped 900 frames past their last required frames. The Sky Sands pass
    # also builds the late programs of air-ride-race, air-ride-celestial-valley and
    # air-ride-beanstalk-park. docs/dev/status.md has the runs, under "Longer course passes".
    LAST_COMPILE = {"air-ride-sky-sands": 14186, "air-ride-magma-flows": 12525,
                    "air-ride-frozen-hillside": 5752}

    def setUp(self):
        self.routes = routes.parse_manifest(routes.MANIFEST.read_text())

    def test_every_route_parses_with_a_route_file_and_no_warm_among_its_probe_settings(self):
        self.assertGreater(len(self.routes), 0)
        for r in self.routes:
            with self.subTest(route=r.name):
                self.assertTrue(routes.route_file(r.name).is_file())
                self.assertEqual([s for s in r.extra if "warm" in s.lower()], [])

    def test_the_routes_that_compile_late_warm_past_their_last_compile(self):
        warm = {r.name: r.warm for r in self.routes}
        for name, frame in self.LAST_COMPILE.items():
            with self.subTest(route=name):
                self.assertGreater(warm[name], frame)


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
