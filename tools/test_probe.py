import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe.sh"
NAME = "test-probe-never-run"


def probe(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(PROBE), *args], capture_output=True, text=True, timeout=10)


class ProbeArgumentsTest(unittest.TestCase):
    def tearDown(self):
        self.assertFalse((ROOT / "build" / "probe" / NAME).exists())

    def test_help_exits_0_and_prints_usage(self):
        r = probe("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout)

    def test_no_arguments_exits_2(self):
        self.assertEqual(probe().returncode, 2)

    def test_seconds_must_be_a_whole_number(self):
        r = probe(NAME, "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("SECONDS", r.stderr)

    def test_renderer_other_than_gl_exits_2(self):
        r = probe(NAME, "1", "", "60", "--renderer=metal")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--renderer=metal", r.stderr)

    def test_scale_out_of_range_exits_2(self):
        r = probe(NAME, "1", "", "60", "--scale=10")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--scale=10", r.stderr)


if __name__ == "__main__":
    unittest.main()
