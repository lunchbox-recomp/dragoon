from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bot_link
import kar_ram
import ram_peek
from bot_link import Outcome, Pad
from ram_peek import Sampler, main, parse_frames, parse_item, show
from testutil import run_main, write_file


class FakeLink:
    """A Link over made-up RAM: the bytes put at addresses, zero elsewhere."""

    def __init__(self) -> None:
        self.frame = 0
        self.bytes: dict[int, int] = {}

    def put(self, address: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.bytes[address + i] = b

    def read(self, address: int, length: int) -> bytes:
        assert 1 <= length <= kar_ram.READ_MAX and kar_ram.in_ram(address, length), (hex(address), length)
        return bytes(self.bytes.get(address + i, 0) for i in range(length))


TABLE = {
    "made.flag": {"address": "80001000", "type": "u8", "means": "a made-up flag",
                  "values": {"1": "on"}, "route": "menu.txt", "frames": [1, 2]},
    "made.where": {"address": "80002000", "path": ["2C"], "type": "f32", "means": "a made-up place",
                   "route": "menu.txt", "frames": [1, 2]},
    "made.name": {"address": "80003000", "type": "bytes", "length": 2, "means": "a made-up name",
                  "route": "menu.txt", "frames": [1, 2]},
}


class ParseFramesTest(unittest.TestCase):
    def test_frames_and_ranges(self) -> None:
        self.assertEqual(parse_frames("5"), [5])
        self.assertEqual(parse_frames("1-3"), [1, 2, 3])
        self.assertEqual(parse_frames("10-20/5"), [10, 15, 20])
        self.assertEqual(parse_frames("10-19/5"), [10, 15])
        self.assertEqual(parse_frames("30,1-2,2"), [1, 2, 30])

    def test_bad_frames(self) -> None:
        for text in ("", "a", "1,", "5-3", "1-5/0", "-1", "1/2", "1-2-3"):
            with self.subTest(text), self.assertRaises(ValueError):
                parse_frames(text)


class ItemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.link = FakeLink()
        self.tmp = tempfile.TemporaryDirectory()
        self.table = kar_ram.load(write_file(Path(self.tmp.name), "table.json", json.dumps(TABLE)))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bytes_print_as_hex(self) -> None:
        self.link.put(0x80000010, b"\x01\xab")
        item = parse_item("80000010:2", None)
        self.assertEqual((item.label, item.address, item.path, item.length), ("80000010:2", 0x80000010, (), 2))
        self.assertEqual(show(self.link, item), "01ab")

    def test_typed_values_print_comma_separated(self) -> None:
        self.link.put(0x80000010, struct.pack(">Hh", 7, -2))
        self.assertEqual(show(self.link, parse_item("80000010:u16", None)), "7")
        self.assertEqual(show(self.link, parse_item("80000010:s16x2", None)), "7,-2")
        self.link.put(0x80000020, struct.pack(">ff", 1 / 3, -28.8847))
        self.assertEqual(show(self.link, parse_item("80000020:f32x2", None)), "0.3333333,-28.8847")

    def test_a_short_or_lowercase_address(self) -> None:
        self.assertEqual(parse_item("8053abcd:u8", None).address, 0x8053ABCD)

    def test_a_path_follows_pointers(self) -> None:
        self.link.put(0x80000010, struct.pack(">I", 0x81000000))
        self.link.put(0x8100002C, struct.pack(">I", 0x81100000))
        self.link.put(0x81100300, struct.pack(">f", 19.5))
        item = parse_item("80000010/2C/300:f32", None)
        self.assertEqual(item.path, (0x2C, 0x300))
        self.assertEqual(show(self.link, item), "19.5")

    def test_a_null_pointer_prints_none(self) -> None:
        self.assertEqual(show(self.link, parse_item("80000010/2C/300:f32x3", None)), "none")

    def test_bad_raw_items(self) -> None:
        for text in ("80000000:0", "80000000:257", "80000000:u64", "80000000:u32x65", "80000000:u8x0",
                     "7FFFFFFF:1", "817FFFFF:2", "817FFFFE/0:u8", "80000000/12345:u8"):
            with self.subTest(text), self.assertRaises(ValueError):
                parse_item(text, None)

    def test_a_pointer_at_the_end_of_ram_is_fine_whatever_it_leads_to(self) -> None:
        self.assertEqual(parse_item("817FFFFC/0:256", None).length, 256)

    def test_a_name_from_the_table(self) -> None:
        self.link.put(0x80001000, b"\x01")
        self.assertEqual(show(self.link, parse_item("made.flag", self.table)), "1 (on)")
        self.link.put(0x80001000, b"\x02")
        self.assertEqual(show(self.link, parse_item("made.flag", self.table)), "2")
        self.link.put(0x80003000, b"\x4b\x41")
        self.assertEqual(show(self.link, parse_item("made.name", self.table)), "4b41")

    def test_a_name_with_a_path(self) -> None:
        item = parse_item("made.where", self.table)
        self.assertEqual(show(self.link, item), "none")
        self.link.put(0x80002000, struct.pack(">I", 0x81000000))
        self.link.put(0x8100002C, struct.pack(">f", -3.5))
        self.assertEqual(show(self.link, item), "-3.5")

    def test_an_unknown_name(self) -> None:
        with self.assertRaises(ValueError):
            parse_item("made.nothing", self.table)
        with self.assertRaises(ValueError):
            parse_item("made.flag", None)


class SamplerTest(unittest.TestCase):
    def test_a_line_at_each_frame_or_the_first_one_after(self) -> None:
        link = FakeLink()
        link.put(0x80000000, b"\x07")
        out = io.StringIO()
        sampler = Sampler([parse_item("80000000:u8", None), parse_item("80000000:2", None)], [12, 10, 20, 11],
                          2, out)
        for frame in (9, 10, 13, 14, 19):
            link.frame = frame
            self.assertEqual(sampler(link), {1: Pad(), 2: Pad()})
        self.assertEqual(out.getvalue(), "frame 10  80000000:u8=7  80000000:2=0700\n"
                                         "frame 13  80000000:u8=7  80000000:2=0700\n")
        self.assertEqual(sampler.left, [20])


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.table = write_file(self.dir, "table.json", json.dumps(TABLE))
        self.link = FakeLink()
        self.link.put(0x80001000, b"\x01")
        self.frames = [1, 2, 3, 5]
        self.reason = bot_link.EXIT_AFTER
        self.calls: list[tuple] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def fake_run(self, name, seconds, bot, **kw) -> Outcome:
        self.calls.append((name, seconds, kw))
        for frame in self.frames:
            self.link.frame = frame
            self.assertEqual(bot(self.link), {port: Pad() for port in range(1, kw["pads"] + 1)})
        return Outcome(len(self.frames), self.frames[-1] if self.frames else None, self.reason,
                       "--exit-after=5", self.dir / "build" / "probe" / name, self.dir / "inputs")

    def peek(self, *argv: str) -> tuple[int, str, str]:
        with mock.patch.object(bot_link, "run", side_effect=self.fake_run):
            return run_main(main, *argv)

    def test_a_run_that_reads_every_frame(self) -> None:
        code, out, err = self.peek("--table", str(self.table), "--at", "2,4", "--pads", "3", "--script",
                                   "menu.txt", "--every", "100", "--hang", "5", "peek", "60", "made.flag",
                                   "80001000:u8x2", "--", "--exit-after=5")
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[:2], ["frame 2  made.flag=1 (on)  80001000:u8x2=1,0",
                                     "frame 5  made.flag=1 (on)  80001000:u8x2=1,0"])
        self.assertEqual(lines[2], f"{self.dir / 'build' / 'probe' / 'peek'}: exit_after, 4 frames answered, "
                                   "the last frame 5")
        self.assertEqual(lines[3:], ["  --exit-after=5", f"  input log {self.dir / 'inputs'}"])
        name, seconds, kw = self.calls[0]
        self.assertEqual((name, seconds), ("peek", 60))
        self.assertEqual(kw, {"pads": 3, "script": "menu.txt", "every": 100, "settings": ["--exit-after=5"],
                              "hang": 5.0, "probe": None})

    def test_raw_items_need_no_table(self) -> None:
        with mock.patch.object(kar_ram, "TABLE", self.dir / "missing.json"):
            code, out, err = self.peek("--at", "1", "peek", "60", "80001000:1")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("frame 1  80001000:1=01\n"), out)

    def test_hang_0_is_no_hang(self) -> None:
        self.peek("--at", "1", "--hang", "0", "peek", "60", "80001000:1")
        self.assertIsNone(self.calls[0][2]["hang"])

    def test_a_frame_never_reached(self) -> None:
        code, out, _ = self.peek("--at", "3,9,12", "peek", "60", "80001000:1")
        self.assertEqual(code, 1)
        self.assertTrue(out.endswith("  never reached 9, 12\n"), out)

    def test_a_run_that_ended_another_way(self) -> None:
        self.reason = bot_link.GAME_DIED
        code, _, _ = self.peek("--at", "1", "peek", "60", "80001000:1")
        self.assertEqual(code, 1)

    def test_a_game_that_never_connected(self) -> None:
        self.frames = []
        self.reason = bot_link.NEVER_LINKED
        code, out, err = self.peek("--at", "1", "peek", "60", "80001000:1")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("never connected", err)

    def test_bad_arguments_exit_2_before_a_run(self) -> None:
        for argv in (("--at", "x", "peek", "60", "80001000:1"),
                     ("--at", "1", "--hang", "-1", "peek", "60", "80001000:1"),
                     ("--at", "1", "--pads", "5", "peek", "60", "80001000:1"),
                     ("--at", "1", "peek", "60"),
                     ("--at", "1", "--table", str(self.table), "peek", "60", "made.nothing"),
                     ("--at", "1", "--table", str(self.dir / "missing.json"), "peek", "60", "80001000:1"),
                     ("--at", "1", "peek", "60", "7FFFFFFF:1")):
            with self.subTest(argv):
                code, _, err = self.peek(*argv)
                self.assertEqual(code, 2)
                self.assertTrue(err)
        self.assertEqual(self.calls, [])

    def test_a_table_that_wont_load(self) -> None:
        bad = write_file(self.dir, "bad.json", '{"made.flag": {"address": "1"}}')
        code, _, err = self.peek("--at", "1", "--table", str(bad), "peek", "60", "made.flag")
        self.assertEqual(code, 2)
        self.assertIn("made.flag", err)

    def test_a_run_that_couldnt_start(self) -> None:
        with mock.patch.object(bot_link, "run", side_effect=bot_link.LinkSetupError("socket taken")):
            code, _, err = run_main(main, "--at", "1", "peek", "60", "80001000:1")
        self.assertEqual(code, 2)
        self.assertIn("socket taken", err)

    def test_the_real_table_names_work(self) -> None:
        self.link.put(0x805361AC, b"\x03")
        code, out, _ = self.peek("--at", "1", "peek", "60", "scene.major", "player1.x")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("frame 1  scene.major=3 (the main menu)  player1.x=none\n"), out)


if __name__ == "__main__":
    unittest.main()
