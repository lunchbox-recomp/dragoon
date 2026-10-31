from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

import kar_ram
from kar_ram import Entry, decode, follow, in_ram, load, read
from testutil import write_file

ROUTES = Path(__file__).resolve().parent.parent / "tests" / "routes"


class FakeRam:
    """Guest RAM for a test: the bytes put at addresses, zero elsewhere, read as Link.read does."""

    def __init__(self, frame: int = 0) -> None:
        self.frame = frame
        self.bytes: dict[int, int] = {}
        self.reads: list[tuple[int, int]] = []

    def put(self, address: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.bytes[address + i] = b

    def pointer(self, address: int, to: int) -> None:
        self.put(address, struct.pack(">I", to))

    def read(self, address: int, length: int) -> bytes:
        assert 1 <= length <= kar_ram.READ_MAX and in_ram(address, length), (hex(address), length)
        self.reads.append((address, length))
        return bytes(self.bytes.get(address + i, 0) for i in range(length))


def entry(type_: str = "u8", length: int | None = None, path: tuple[int, ...] = (),
          values: dict[int, str] | None = None) -> Entry:
    return Entry("made.up", 0x80001000, type_, length if length is not None else kar_ram.size(type_),
                 "a made-up value", values or {}, "menu.txt", (1, 2), path)


GOOD = {
    "address": "80001000",
    "type": "u8",
    "means": "a made-up value",
    "values": {"0": "off", "1": "on"},
    "route": "menu.txt",
    "frames": [10, 20],
}


class TableCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def table(self, entries: dict[str, object]) -> Path:
        return write_file(self.dir, "table.json", json.dumps(entries))

    def refused(self, fields: dict[str, object], name: str = "made.up") -> str:
        path = self.table({name: fields})
        with self.assertRaises(ValueError) as caught:
            load(path)
        message = str(caught.exception)
        self.assertTrue(message.startswith(f"{path}: {name}: "), message)
        return message


class DecodeTest(unittest.TestCase):
    def test_ints_are_big_endian(self) -> None:
        self.assertEqual(decode(entry("u8"), b"\xfe"), 254)
        self.assertEqual(decode(entry("s8"), b"\xfe"), -2)
        self.assertEqual(decode(entry("u16"), b"\x12\x34"), 0x1234)
        self.assertEqual(decode(entry("s16"), b"\xff\xfe"), -2)
        self.assertEqual(decode(entry("u32"), b"\x12\x34\x56\x78"), 0x12345678)
        self.assertEqual(decode(entry("s32"), b"\xff\xff\xff\xfd"), -3)

    def test_a_float(self) -> None:
        self.assertEqual(decode(entry("f32"), struct.pack(">f", 6.25)), 6.25)

    def test_a_run_of_bytes_comes_back_as_bytes(self) -> None:
        self.assertEqual(decode(entry("bytes", 3), bytearray(b"abc")), b"abc")

    def test_the_wrong_length_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            decode(entry("u16"), b"\x01")
        with self.assertRaises(ValueError):
            decode(entry("bytes", 3), b"abcd")

    def test_a_meaning_is_for_a_whole_number_the_table_names(self) -> None:
        e = entry(values={1: "on"})
        self.assertEqual(e.meaning(1), "on")
        self.assertIsNone(e.meaning(2))
        self.assertIsNone(e.meaning(None))
        self.assertIsNone(e.meaning(b"\x01"))


class RamTest(unittest.TestCase):
    def test_main_ram_runs_from_80000000_to_817fffff(self) -> None:
        self.assertTrue(in_ram(0x80000000, 1))
        self.assertTrue(in_ram(0x817FFFFC, 4))
        self.assertFalse(in_ram(0x817FFFFD, 4))
        self.assertFalse(in_ram(0x7FFFFFFF, 1))
        self.assertFalse(in_ram(0, 1))


class FollowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ram = FakeRam()

    def test_no_path_is_the_address_itself(self) -> None:
        self.assertEqual(follow(self.ram, 0x80001000, (), 4), 0x80001000)
        self.assertEqual(self.ram.reads, [])

    def test_no_path_outside_ram_leads_nowhere(self) -> None:
        self.assertIsNone(follow(self.ram, 0x81800000, (), 1))
        self.assertIsNone(follow(self.ram, 0x817FFFFE, (), 4))
        self.assertEqual(self.ram.reads, [])

    def test_each_offset_is_added_to_the_pointer_read_before_it(self) -> None:
        self.ram.pointer(0x80001000, 0x81000000)
        self.ram.pointer(0x8100001C, 0x81200000)
        self.assertEqual(follow(self.ram, 0x80001000, (0x1C, 0x240), 4), 0x81200240)
        self.assertEqual(self.ram.reads, [(0x80001000, 4), (0x8100001C, 4)])

    def test_a_null_pointer_leads_nowhere(self) -> None:
        self.assertIsNone(follow(self.ram, 0x80001000, (0x1C, 0x240), 4))
        self.assertEqual(self.ram.reads, [(0x80001000, 4)])
        self.ram.pointer(0x80001000, 0x81000000)
        self.assertIsNone(follow(self.ram, 0x80001000, (0x1C, 0x240), 4))
        self.assertEqual(self.ram.reads, [(0x80001000, 4), (0x80001000, 4), (0x8100001C, 4)])

    def test_a_null_pointer_with_an_offset_into_ram_still_leads_nowhere(self) -> None:
        self.assertIsNone(follow(self.ram, 0x80001000, (0x80000000,), 4))

    def test_a_pointer_past_ram_leads_nowhere(self) -> None:
        self.ram.pointer(0x80001000, 0x81800000)
        self.assertIsNone(follow(self.ram, 0x80001000, (0,), 1))

    def test_a_value_that_runs_past_ram_leads_nowhere(self) -> None:
        self.ram.pointer(0x80001000, 0x817FFFF0)
        self.assertEqual(follow(self.ram, 0x80001000, (0xC,), 4), 0x817FFFFC)
        self.assertIsNone(follow(self.ram, 0x80001000, (0xD,), 4))

    def test_a_pointer_on_the_way_has_to_fit_too(self) -> None:
        self.ram.pointer(0x80001000, 0x817FFFF0)
        self.assertIsNone(follow(self.ram, 0x80001000, (0xE, 0), 1))
        self.assertEqual(self.ram.reads, [(0x80001000, 4)])


class ReadTest(TableCase):
    def setUp(self) -> None:
        super().setUp()
        self.ram = FakeRam()
        self.made_up = load(self.table({
            "made.flag": GOOD,
            "made.where": {"address": "80002000", "path": ["1C", "240"], "type": "f32",
                           "means": "a made-up position", "route": "menu.txt", "frames": [1, 2]},
            "made.name": {"address": "80003000", "type": "bytes", "length": 4,
                          "means": "a made-up name", "route": "menu.txt", "frames": [1, 2]},
        }))

    def test_a_value_at_a_fixed_address(self) -> None:
        self.ram.put(0x80001000, b"\x01")
        self.assertEqual(read(self.ram, "made.flag", self.made_up), 1)

    def test_a_value_behind_pointers(self) -> None:
        self.ram.pointer(0x80002000, 0x81000000)
        self.ram.pointer(0x8100001C, 0x81100000)
        self.ram.put(0x81100240, struct.pack(">f", 7.75))
        self.assertEqual(read(self.ram, "made.where", self.made_up), 7.75)

    def test_a_value_behind_a_null_pointer_is_none(self) -> None:
        self.assertIsNone(read(self.ram, "made.where", self.made_up))

    def test_a_run_of_bytes(self) -> None:
        self.ram.put(0x80003000, b"KIRB")
        self.assertEqual(read(self.ram, "made.name", self.made_up), b"KIRB")

    def test_an_unknown_name_is_a_key_error(self) -> None:
        with self.assertRaises(KeyError):
            read(self.ram, "made.nothing", self.made_up)

    def test_the_default_table_is_kar_ram_json(self) -> None:
        address = load()["scene.major"].address
        self.ram.put(address, b"\x5a")
        self.assertEqual(read(self.ram, "scene.major"), 0x5A)


class LoadTest(TableCase):
    def test_an_entry_comes_back_as_an_entry(self) -> None:
        table = load(self.table({"made.flag": GOOD, "made.where": {
            "address": "80012340", "path": ["1C", "240"], "type": "f32", "means": "a position",
            "route": "menu.txt", "frames": [5, 5]}}))
        self.assertEqual(table["made.flag"], Entry("made.flag", 0x80001000, "u8", 1, "a made-up value",
                                                   {0: "off", 1: "on"}, "menu.txt", (10, 20), ()))
        where = table["made.where"]
        self.assertEqual((where.address, where.path, where.length, where.values),
                         (0x80012340, (0x1C, 0x240), 4, {}))

    def test_a_run_of_bytes_takes_its_length(self) -> None:
        fields = {**GOOD, "type": "bytes", "length": 256}
        del fields["values"]
        self.assertEqual(load(self.table({"made.name": fields}))["made.name"].length, 256)

    def test_signed_values_can_be_negative(self) -> None:
        fields = {**GOOD, "type": "s8", "values": {"-128": "lowest", "127": "highest"}}
        self.assertEqual(load(self.table({"made.flag": fields}))["made.flag"].values,
                         {-128: "lowest", 127: "highest"})

    def test_a_malformed_name(self) -> None:
        self.refused(GOOD, "Made.Flag")
        self.refused(GOOD, "made..flag")
        self.refused(GOOD, "1made")

    def test_a_missing_or_unknown_field(self) -> None:
        for field in ("address", "type", "means", "route", "frames"):
            fields = dict(GOOD)
            del fields[field]
            self.assertIn(f"no {field}", self.refused(fields))
        self.assertIn("unknown field size", self.refused({**GOOD, "size": 1}))

    def test_an_entry_that_isnt_an_object(self) -> None:
        self.refused(["80001000", "u8"])

    def test_a_malformed_address(self) -> None:
        for address in ("8000100", "80001000a", "8000100g", "8012abcd", 0x80001000):
            self.refused({**GOOD, "address": address})

    def test_an_address_outside_main_ram(self) -> None:
        self.refused({**GOOD, "address": "7FFFFFFF"})
        self.refused({**GOOD, "address": "81800000"})
        self.refused({**GOOD, "address": "817FFFFF", "type": "u16", "values": {}})
        load(self.table({"made.flag": {**GOOD, "address": "817FFFFF"}}))

    def test_a_pointer_has_to_fit_where_a_path_starts(self) -> None:
        fields = {**GOOD, "address": "817FFFFE", "path": ["0"]}
        self.assertIn("817FFFFE to 81800001", self.refused(fields))

    def test_a_malformed_path(self) -> None:
        for path in ([], ["1c"], ["12345"], [44], "1C", ["1C", ""]):
            self.refused({**GOOD, "path": path})

    def test_a_malformed_type_or_length(self) -> None:
        self.refused({**GOOD, "type": "u64"})
        self.refused({**GOOD, "length": 1})
        self.refused({**GOOD, "type": "bytes", "values": {}})
        for length in (0, 257, "4", True):
            self.refused({**GOOD, "type": "bytes", "length": length, "values": {}})

    def test_empty_words(self) -> None:
        self.refused({**GOOD, "means": " "})
        self.refused({**GOOD, "route": ""})
        self.refused({**GOOD, "means": 1})

    def test_malformed_frames(self) -> None:
        for frames in ([20, 10], [10], [1, 2, 3], [-1, 2], [1.5, 2], [True, 2], "10-20"):
            self.refused({**GOOD, "frames": frames})

    def test_malformed_values(self) -> None:
        self.refused({**GOOD, "values": [["0", "off"]]})
        self.refused({**GOOD, "values": {"256": "too big"}})
        self.refused({**GOOD, "values": {"-1": "unsigned"}})
        self.refused({**GOOD, "values": {"01": "not decimal"}})
        self.refused({**GOOD, "values": {"0x1": "not decimal"}})
        self.refused({**GOOD, "values": {"1": ""}})
        self.refused({**GOOD, "values": {"1": 1}})
        self.refused({**GOOD, "type": "f32", "values": {"0": "a float has none"}})

    def test_a_name_given_twice(self) -> None:
        path = write_file(self.dir, "table.json", '{"made.flag": %s, "made.flag": %s}'
                          % (json.dumps(GOOD), json.dumps(GOOD)))
        with self.assertRaisesRegex(ValueError, "made.flag is named twice"):
            load(path)

    def test_a_file_that_isnt_a_table(self) -> None:
        with self.assertRaisesRegex(ValueError, "not an object"):
            load(write_file(self.dir, "table.json", "[]"))
        with self.assertRaises(ValueError):
            load(write_file(self.dir, "table.json", "{"))


class RealTableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.table = load()

    def test_every_entry_is_well_formed_and_in_main_ram(self) -> None:
        self.assertTrue(self.table)
        for name, e in self.table.items():
            with self.subTest(name):
                self.assertEqual(e.name, name)
                self.assertGreaterEqual(e.address, 0x80000000)
                self.assertLessEqual(e.address + (kar_ram.POINTER if e.path else e.length), 0x81800000)
                self.assertEqual(e.length, kar_ram.size(e.type) if e.type != kar_ram.BYTES else e.length)
                self.assertLessEqual(e.frames[0], e.frames[1])

    def test_every_route_is_one_of_the_routes(self) -> None:
        for name, e in self.table.items():
            with self.subTest(name):
                self.assertTrue((ROUTES / e.route).is_file(), e.route)

    def test_each_player_has_the_same_values(self) -> None:
        fields = {name.split(".", 1)[1] for name in self.table if name.startswith("player1.")}
        self.assertTrue(fields)
        for n in range(2, 5):
            with self.subTest(n):
                self.assertEqual({name.split(".", 1)[1] for name in self.table
                                  if name.startswith(f"player{n}.")}, fields)


if __name__ == "__main__":
    unittest.main()
