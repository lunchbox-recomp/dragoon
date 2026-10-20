import tempfile
import unittest
from pathlib import Path

import frame_hashes as fh


class ManifestTest(unittest.TestCase):
    def test_parses_routes_and_extra_args(self):
        routes = fh.parse_manifest("# comment\n\ncity-trial-4p 30 60 2700,3480 --pads=4\n")
        self.assertEqual(len(routes), 1)
        r = routes[0]
        self.assertEqual((r.name, r.seconds, r.dump_every, r.required, r.extra),
                         ("city-trial-4p", 30, 60, [2700, 3480], ["--pads=4"]))


class HashTest(unittest.TestCase):
    def test_hashes_only_frame_pngs(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "frame_00060.png").write_bytes(b"a")
            Path(d, "stdout.txt").write_bytes(b"b")
            self.assertEqual(fh.hash_frames(Path(d)),
                             {60: "86f7e437faa5a7fce15d1ddcb9eaeaea377667b8"})


class GoldenTest(unittest.TestCase):
    def test_round_trip_drops_frames_past_last(self):
        text = fh.format_golden({60: "a" * 40, 120: "b" * 40, 180: "c" * 40}, 120)
        self.assertEqual(fh.read_golden(text), {60: "a" * 40, 120: "b" * 40})

    def test_compare_reports_changed_and_missing(self):
        golden = {60: "a" * 40, 120: "b" * 40}
        self.assertEqual(fh.compare(golden, dict(golden)), [])
        self.assertEqual(fh.compare(golden, {60: "c" * 40}),
                         ["frame 60: cccccccc != golden aaaaaaaa", "frame 120: not reached"])


class ReachedTest(unittest.TestCase):
    def test_reports_largest_frame_and_what_the_route_needs(self):
        self.assertEqual(fh.reached({60: "a", 5400: "b", 120: "c"}, 3300), "reached frame 5400 (needs 3300)")
        self.assertEqual(fh.reached({}, 60), "reached no frames (needs 60)")


if __name__ == "__main__":
    unittest.main()
