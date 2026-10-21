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
        self.assertEqual((r.name, r.seconds, r.dump_every, r.required, r.extra),
                         ("city-trial-4p", 30, 60, [2700, 3480], ["--pads=4"]))


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
