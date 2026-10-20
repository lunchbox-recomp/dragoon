import struct
import tempfile
import unittest
from pathlib import Path

import shader_cache
from testutil import run_main, write_file

KEY_SIZE = 8
FORMAT = 3 << 16 | KEY_SIZE
CACHE_MAGIC = 0x43535257
LIST_MAGIC = 0x4B534347
CACHE_HEADER = 16
RECORD_TAIL = 16


def key(n: int) -> bytes:
    return bytes([n]) * KEY_SIZE


def record_size(binary_length: int) -> int:
    return KEY_SIZE + RECORD_TAIL + binary_length


def cache_bytes(keys, binary: bytes = b"", fmt: int = FORMAT, magic: int = CACHE_MAGIC) -> bytes:
    out = struct.pack("<IIQ", magic, fmt, 0xD00D)
    for k in keys:
        out += k + struct.pack("<QII", 0xABC, 0x8E21 if binary else 0, len(binary)) + binary
    return out


def list_bytes(keys, fmt: int = FORMAT) -> bytes:
    return struct.pack("<II", LIST_MAGIC, fmt) + b"".join(keys)


class ShaderCacheTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name: str, data: bytes) -> Path:
        return write_file(self.dir, name, data)

    def keys(self, name: str, data: bytes) -> list[bytes]:
        return shader_cache.load(self.write(name, data)).keys

    def test_cache_keys_come_in_file_order(self):
        data = cache_bytes([key(3), key(1), key(2)], binary=b"\xaa" * 40)
        self.assertEqual(self.keys("c.bin", data), [key(3), key(1), key(2)])

    def test_key_list_keys_come_in_file_order(self):
        self.assertEqual(self.keys("k.bin", list_bytes([key(5), key(4)])), [key(5), key(4)])

    def test_record_length_field_read_after_key_and_hash(self):
        data = cache_bytes([key(1), key(2)], binary=b"\x01\x02\x03\x04")
        self.assertEqual(self.keys("c.bin", data), [key(1), key(2)])

    def test_records_with_no_binary_follow_each_other(self):
        self.assertEqual(self.keys("c.bin", cache_bytes([key(1), key(2)])), [key(1), key(2)])

    def test_key_size_comes_from_format_word(self):
        k = b"\x07" * 12
        self.assertEqual(self.keys("c.bin", cache_bytes([k], fmt=9 << 16 | 12)), [k])

    def test_count_cache(self):
        path = self.write("c.bin", cache_bytes([key(1), key(2), key(1)], binary=b"xy"))
        code, out, _ = run_main(shader_cache.main, "count", str(path))
        self.assertEqual(code, 0)
        self.assertIn("version 3", out)
        self.assertIn("key size 8", out)
        self.assertIn("records 3", out)
        self.assertIn("distinct 2", out)
        self.assertIn("ignored 0", out)

    def test_count_key_list(self):
        path = self.write("k.bin", list_bytes([key(1), key(2)]))
        code, out, _ = run_main(shader_cache.main, "count", str(path))
        self.assertEqual(code, 0)
        self.assertIn("records 2", out)
        self.assertIn("distinct 2", out)

    def test_truncated_last_record_is_skipped_and_reported(self):
        full = cache_bytes([key(1), key(2)], binary=b"\xee" * 10)
        for cut in (1, 5, 10, 20, 27):
            path = self.write("c.bin", full[:-cut])
            with self.subTest(cut=cut):
                self.assertEqual(shader_cache.load(path).keys, [key(1)])
                code, out, _ = run_main(shader_cache.main, "count", str(path))
                self.assertEqual(code, 0)
                self.assertIn("records 1", out)
                self.assertIn(f"ignored {len(full) - cut - (CACHE_HEADER + record_size(10))}", out)

    def test_truncated_key_list_tail_is_reported(self):
        path = self.write("k.bin", list_bytes([key(1), key(2)]) + b"\x09\x09\x09")
        self.assertEqual(shader_cache.load(path).keys, [key(1), key(2)])
        _, out, _ = run_main(shader_cache.main, "count", str(path))
        self.assertIn("ignored 3", out)

    def test_diff_counts_distinct_keys_new_only(self):
        old = self.write("old.bin", cache_bytes([key(1), key(2)]))
        new = self.write("new.bin", list_bytes([key(2), key(3), key(4), key(3)]))
        code, out, _ = run_main(shader_cache.main, "diff", str(old), str(new))
        self.assertEqual(code, 0)
        self.assertIn("2 of 3 keys in NEW are not in OLD", out)
        self.assertIn("66.7%", out)

    def test_diff_identical_files(self):
        a = self.write("a.bin", list_bytes([key(1)]))
        _, out, _ = run_main(shader_cache.main, "diff", str(a), str(a))
        self.assertIn("0 of 1", out)

    def test_diff_empty_new(self):
        a = self.write("a.bin", list_bytes([key(1)]))
        b = self.write("b.bin", list_bytes([]))
        code, out, _ = run_main(shader_cache.main, "diff", str(a), str(b))
        self.assertEqual(code, 0)
        self.assertIn("0 of 0", out)

    def test_diff_refuses_different_formats(self):
        a = self.write("a.bin", list_bytes([key(1)]))
        b = self.write("b.bin", list_bytes([b"\x01" * 12], fmt=4 << 16 | 12))
        code, _, err = run_main(shader_cache.main, "diff", str(a), str(b))
        self.assertEqual(code, 2)
        self.assertIn("00030008", err)
        self.assertIn("0004000c", err)

    def test_unknown_magic_is_refused_naming_it(self):
        path = self.write("x.bin", struct.pack("<IIQ", 0x12345678, FORMAT, 0))
        code, _, err = run_main(shader_cache.main, "count", str(path))
        self.assertEqual(code, 2)
        self.assertIn("12345678", err)
        with self.assertRaises(ValueError):
            shader_cache.load(path)

    def test_zero_key_size_is_refused(self):
        path = self.write("x.bin", cache_bytes([], fmt=3 << 16))
        code, _, err = run_main(shader_cache.main, "count", str(path))
        self.assertEqual(code, 2)
        self.assertIn("key size 0", err)

    def test_file_too_short_for_a_header_is_refused(self):
        cases = (("empty", b"", "unknown magic"),
                 ("magic only", b"WRSC", "too short"),
                 ("cache header cut", struct.pack("<II", CACHE_MAGIC, FORMAT), "too short"))
        for name, data, message in cases:
            path = self.write(name, data)
            with self.subTest(name):
                code, _, err = run_main(shader_cache.main, "count", str(path))
                self.assertEqual(code, 2)
                self.assertIn(message, err)

    def test_other_version_is_read_and_printed(self):
        k = b"\x02" * 8
        path = self.write("c.bin", cache_bytes([k], fmt=7 << 16 | 8))
        _, out, _ = run_main(shader_cache.main, "count", str(path))
        self.assertIn("version 7", out)
        self.assertEqual(shader_cache.load(path).keys, [k])

    def test_missing_file_exits_2_with_one_line_naming_it(self):
        code, _, err = run_main(shader_cache.main, "count", str(self.dir / "nope.bin"))
        self.assertEqual(code, 2)
        self.assertIn("nope.bin", err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_help_exits_0_and_prints_usage(self):
        code, out, _ = run_main(shader_cache.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)


if __name__ == "__main__":
    unittest.main()
