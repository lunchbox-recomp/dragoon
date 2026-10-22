import json
import tempfile
import unittest
from pathlib import Path

import source_info
from testutil import write_file

GOOD = {"dragoon": "d" * 40, "gcn-recomp": "e" * 40, "disc_id": "GKYE01", "dol_sha1": "a" * 40}


class ReadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_gives_the_four_fields(self):
        path = write_file(self.dir, source_info.NAME, json.dumps({**GOOD, "extra": 1}))
        self.assertEqual(source_info.read(path), GOOD)

    def test_a_malformed_file_names_its_path(self):
        cases = {
            "not JSON": "{",
            "not an object": "[]",
            "a missing field": json.dumps({k: v for k, v in GOOD.items() if k != "gcn-recomp"}),
            "a commit that isn't a string": json.dumps({**GOOD, "dragoon": 7}),
            "a short commit": json.dumps({**GOOD, "gcn-recomp": "e" * 39}),
            "an upper-case commit": json.dumps({**GOOD, "gcn-recomp": "E" * 40}),
            "a disc ID of 5": json.dumps({**GOOD, "disc_id": "GKYE0"}),
            "a lower-case disc ID": json.dumps({**GOOD, "disc_id": "gkye01"}),
            "a SHA-1 that isn't hex": json.dumps({**GOOD, "dol_sha1": "g" * 40}),
        }
        for name, text in cases.items():
            with self.subTest(name):
                path = write_file(self.dir, source_info.NAME, text)
                with self.assertRaises(ValueError) as caught:
                    source_info.read(path)
                self.assertIn(str(path), str(caught.exception))

    def test_write_round_trips_and_refuses_a_bad_field(self):
        path = self.dir / source_info.NAME
        source_info.write(path, GOOD)
        self.assertEqual(source_info.read(path), GOOD)
        with self.assertRaises(ValueError):
            source_info.write(self.dir / "other.json", {**GOOD, "disc_id": "x"})
        self.assertFalse((self.dir / "other.json").exists())

    def test_a_missing_file_raises_os_error(self):
        with self.assertRaises(OSError):
            source_info.read(self.dir / source_info.NAME)


if __name__ == "__main__":
    unittest.main()
