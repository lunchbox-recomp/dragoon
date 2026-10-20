import tempfile
import unittest
from pathlib import Path

import frame_dumps


class FrameFilesTest(unittest.TestCase):
    def test_only_whole_frame_names_count(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("frame_00060.png", "frame_00060.png.bak", "xframe_00120.png", "stdout.txt"):
                Path(d, name).write_bytes(b"x")
            self.assertEqual(frame_dumps.frame_files(Path(d)), {60: Path(d, "frame_00060.png")})


if __name__ == "__main__":
    unittest.main()
