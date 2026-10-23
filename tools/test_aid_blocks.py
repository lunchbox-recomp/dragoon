import tempfile
import unittest
from pathlib import Path

import aid_blocks
from aid_blocks import Block
from testutil import write_file

LOG = """\
0 160 21223426 0 00571E00 1
160 160 21425926 1 00572080 0
320 160 21628426 0 00572080 1
"""


class ReadBlocksTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_each_line_is_a_block(self):
        self.assertEqual(aid_blocks.read_blocks(write_file(self.dir, "aid.raw.txt", LOG)), [
            Block(0, 160, False, "00571E00"), Block(160, 160, True, "00572080"),
            Block(320, 160, False, "00572080")])

    def test_a_last_line_cut_short_is_skipped(self):
        path = write_file(self.dir, "aid.raw.txt", LOG + "480 160 21830926 0 0057")
        self.assertEqual(len(aid_blocks.read_blocks(path)), 3)

    def test_a_line_with_more_than_six_fields_is_skipped_too(self):
        path = write_file(self.dir, "aid.raw.txt", LOG + "480 160 21830926 0 00571E00 1 1\n")
        self.assertEqual(len(aid_blocks.read_blocks(path)), 3)

    def test_a_line_that_isnt_numbers_is_refused_by_line(self):
        path = write_file(self.dir, "aid.raw.txt", LOG + "a 160 1 0 00571E00 1\n")
        with self.assertRaisesRegex(ValueError, r"aid.raw.txt:4: 'a 160 1 0 00571E00 1' isn't a block line"):
            aid_blocks.read_blocks(path)

    def test_the_log_sits_beside_its_recording(self):
        self.assertEqual(aid_blocks.log_path(Path("/run/mixer.raw")), Path("/run/mixer.raw.txt"))


class PluralTest(unittest.TestCase):
    def test_only_one_is_singular(self):
        self.assertEqual([aid_blocks.plural(n, "block") for n in (0, 1, 2)], ["0 blocks", "1 block", "2 blocks"])

    def test_an_irregular_plural_can_be_given(self):
        self.assertEqual([aid_blocks.plural(n, "stretch", "stretches") for n in (1, 2)], ["1 stretch", "2 stretches"])


if __name__ == "__main__":
    unittest.main()
