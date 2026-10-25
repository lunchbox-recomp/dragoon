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

    def test_the_last_warm_frame_wins(self):
        self.assertEqual(routes.parse_manifest("sky 25 60 4200 warm=7000 warm=7300\n")[0].warm, 7300)


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
