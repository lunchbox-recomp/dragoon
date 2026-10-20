import contextlib
import io
import os
import struct
import tempfile
import unittest

import shader_cache as sc

KEY_SIZE = 8
FORMAT = 3 << 16 | KEY_SIZE
CACHE_MAGIC = 0x43535257
LIST_MAGIC = 0x4B534347


def key(n: int) -> bytes:
    return bytes([n]) * KEY_SIZE


def cache_bytes(keys, binary: bytes = b"", fmt: int = FORMAT, magic: int = CACHE_MAGIC) -> bytes:
    out = struct.pack("<IIQ", magic, fmt, 0xD00D)
    for k in keys:
        out += k + struct.pack("<QII", 0xABC, 0x8E21 if binary else 0, len(binary)) + binary
    return out


def list_bytes(keys, fmt: int = FORMAT) -> bytes:
    return struct.pack("<II", LIST_MAGIC, fmt) + b"".join(keys)


class ShaderCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, data: bytes) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def run_main(self, *argv: str):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = sc.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_read_keys_cache_in_file_order(self):
        path = self.write("c.bin", cache_bytes([key(3), key(1), key(2)], binary=b"\xaa" * 40))
        self.assertEqual(sc.read_keys(path), [key(3), key(1), key(2)])

    def test_read_keys_key_list(self):
        path = self.write("k.bin", list_bytes([key(5), key(4)]))
        self.assertEqual(sc.read_keys(path), [key(5), key(4)])

    def test_four_byte_binary_is_skipped_correctly(self):
        path = self.write("c.bin", cache_bytes([key(1), key(2)], binary=b"\x01\x02\x03\x04"))
        self.assertEqual(sc.read_keys(path), [key(1), key(2)])

    def test_empty_binary_records(self):
        path = self.write("c.bin", cache_bytes([key(1), key(2)]))
        self.assertEqual(sc.read_keys(path), [key(1), key(2)])

    def test_key_size_comes_from_format_word(self):
        k = b"\x07" * 12
        path = self.write("c.bin", cache_bytes([k], fmt=9 << 16 | 12))
        self.assertEqual(sc.read_keys(path), [k])

    def test_count_cache(self):
        path = self.write("c.bin", cache_bytes([key(1), key(2), key(1)], binary=b"xy"))
        code, out, _ = self.run_main("count", path)
        self.assertEqual(code, 0)
        self.assertIn("version 3", out)
        self.assertIn("key size 8", out)
        self.assertIn("records 3", out)
        self.assertIn("distinct 2", out)
        self.assertIn("ignored 0", out)

    def test_count_key_list(self):
        path = self.write("k.bin", list_bytes([key(1), key(2)]))
        code, out, _ = self.run_main("count", path)
        self.assertEqual(code, 0)
        self.assertIn("records 2", out)
        self.assertIn("distinct 2", out)

    def test_truncated_last_record_is_skipped_and_reported(self):
        full = cache_bytes([key(1), key(2)], binary=b"\xee" * 10)
        for cut in (1, 5, 10, 20, 27):
            path = self.write("c.bin", full[:-cut])
            self.assertEqual(sc.read_keys(path), [key(1)], cut)
            code, out, _ = self.run_main("count", path)
            self.assertEqual(code, 0)
            self.assertIn("records 1", out)
            self.assertIn(f"ignored {len(full) - cut - (16 + 34)}", out)

    def test_truncated_key_list_tail_is_reported(self):
        path = self.write("k.bin", list_bytes([key(1), key(2)]) + b"\x09\x09\x09")
        self.assertEqual(sc.read_keys(path), [key(1), key(2)])
        _, out, _ = self.run_main("count", path)
        self.assertIn("ignored 3", out)

    def test_diff_counts_distinct_keys_new_only(self):
        old = self.write("old.bin", cache_bytes([key(1), key(2)]))
        new = self.write("new.bin", list_bytes([key(2), key(3), key(4), key(3)]))
        code, out, _ = self.run_main("diff", old, new)
        self.assertEqual(code, 0)
        self.assertIn("2 of 3 keys in NEW are not in OLD", out)
        self.assertIn("66.7%", out)

    def test_diff_identical_files(self):
        a = self.write("a.bin", list_bytes([key(1)]))
        _, out, _ = self.run_main("diff", a, a)
        self.assertIn("0 of 1", out)

    def test_diff_empty_new(self):
        a = self.write("a.bin", list_bytes([key(1)]))
        b = self.write("b.bin", list_bytes([]))
        code, out, _ = self.run_main("diff", a, b)
        self.assertEqual(code, 0)
        self.assertIn("0 of 0", out)

    def test_diff_refuses_different_formats(self):
        a = self.write("a.bin", list_bytes([key(1)]))
        b = self.write("b.bin", list_bytes([b"\x01" * 12], fmt=4 << 16 | 12))
        code, _, err = self.run_main("diff", a, b)
        self.assertEqual(code, 1)
        self.assertIn("00030008", err)
        self.assertIn("0004000c", err)

    def test_unknown_magic_is_refused_naming_it(self):
        path = self.write("x.bin", struct.pack("<IIQ", 0x12345678, FORMAT, 0))
        code, _, err = self.run_main("count", path)
        self.assertEqual(code, 1)
        self.assertIn("12345678", err)
        with self.assertRaises(sc.FormatError):
            sc.read_keys(path)

    def test_zero_key_size_is_refused(self):
        path = self.write("x.bin", cache_bytes([], fmt=3 << 16))
        code, _, err = self.run_main("count", path)
        self.assertEqual(code, 1)
        self.assertIn("key size 0", err)

    def test_file_too_short_for_a_header_is_refused(self):
        for name, data in (("a", b""), ("b", b"WRSC"), ("c", struct.pack("<II", CACHE_MAGIC, FORMAT))):
            path = self.write(name, data)
            code, _, err = self.run_main("count", path)
            self.assertEqual(code, 1, name)
            self.assertTrue(err, name)

    def test_other_version_is_read_and_printed(self):
        k = b"\x02" * 8
        path = self.write("c.bin", cache_bytes([k], fmt=7 << 16 | 8))
        _, out, _ = self.run_main("count", path)
        self.assertIn("version 7", out)
        self.assertEqual(sc.read_keys(path), [k])


if __name__ == "__main__":
    unittest.main()
