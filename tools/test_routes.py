import unittest

import routes


class ManifestTest(unittest.TestCase):
    def test_parses_routes_and_extra_args(self):
        parsed = routes.parse_manifest("# comment\n\ncity-trial-4p 30 60 2700,3480 --pads=4\n")
        self.assertEqual(len(parsed), 1)
        r = parsed[0]
        self.assertEqual((r.name, r.seconds, r.dump_every, r.required, r.extra),
                         ("city-trial-4p", 30, 60, [2700, 3480], ["--pads=4"]))


class RouteFileTest(unittest.TestCase):
    def test_is_the_named_file_in_tests_routes(self):
        self.assertEqual(routes.route_file("title"), routes.ROOT / "tests" / "routes" / "title.txt")


if __name__ == "__main__":
    unittest.main()
