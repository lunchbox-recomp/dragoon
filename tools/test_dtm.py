from __future__ import annotations

import struct
import unittest
from pathlib import Path

import dtm
from testutil import run_main, temp_dir

ROUTES = Path(__file__).resolve().parent.parent / "tests" / "routes"

# DTMHeader's fields at the byte offsets Movie.h's packed struct gives them at Dolphin 2609a,
# worked out by hand from its declarations: (offset, struct format).
OFFSETS = {
    "filetype": (0, "4s"), "gameID": (4, "6s"), "bWii": (10, "B"), "controllers": (11, "B"),
    "bFromSaveState": (12, "B"), "frameCount": (13, "<Q"), "inputCount": (21, "<Q"),
    "lagCount": (29, "<Q"), "uniqueID": (37, "<Q"), "numRerecords": (45, "<I"),
    "author": (49, "32s"), "videoBackend": (81, "16s"), "audioEmulator": (97, "16s"),
    "md5": (113, "16s"), "recordingStartTime": (129, "<Q"), "bSaveConfig": (137, "B"),
    "bDSPHLE": (141, "B"), "CPUCore": (143, "B"), "memcards": (151, "B"),
    "bClearSave": (152, "B"), "bongos": (153, "B"), "bNetPlay": (155, "B"),
    "GBAControllers": (161, "B"), "discChange": (169, "40s"), "revision": (209, "20s"),
    "DSPiromHash": (229, "<I"), "DSPcoefHash": (233, "<I"), "tickCount": (237, "<Q"),
    "reserved2": (245, "11s"),
}


def field_at(data: bytes, name: str):
    offset, fmt = OFFSETS[name]
    return struct.unpack_from(fmt, data, offset)[0]


def controller(chunk: bytes) -> dict:
    """One ControllerState read by hand: the bitfield's first byte holds Start, A, B, X, Y, Z,
    DPadUp and DPadDown from its lowest bit, the second DPadLeft, DPadRight, L, R, disc, reset,
    is_connected and get_origin, then TriggerL, TriggerR, the main stick and the C stick."""
    lo, hi = chunk[0], chunk[1]
    return {"Start": lo & 1, "A": lo >> 1 & 1, "B": lo >> 2 & 1, "Z": lo >> 5 & 1,
            "DPadUp": lo >> 6 & 1, "DPadDown": lo >> 7 & 1, "DPadRight": hi >> 1 & 1,
            "L": hi >> 2 & 1, "R": hi >> 3 & 1, "is_connected": hi >> 6 & 1,
            "get_origin": hi >> 7 & 1, "TriggerL": chunk[2], "TriggerR": chunk[3],
            "StickX": chunk[4], "StickY": chunk[5], "CStickX": chunk[6], "CStickY": chunk[7]}


def polls_of(data: bytes) -> list[bytes]:
    return [data[i:i + 8] for i in range(256, len(data), 8)]


class HeaderTest(unittest.TestCase):
    def setUp(self):
        self.data = dtm.make("100:A:5", 200)

    def test_the_header_is_256_bytes_then_8_a_poll(self):
        self.assertEqual(len(self.data), 256 + 8 * field_at(self.data, "inputCount"))
        self.assertEqual(field_at(self.data, "inputCount"), 201 * 2 - 46)

    def test_it_boots_gkye01_from_power_on_on_pad_1_with_the_runs_config(self):
        self.assertEqual(field_at(self.data, "filetype"), b"DTM\x1a")
        self.assertEqual(field_at(self.data, "gameID"), b"GKYE01")
        self.assertEqual(field_at(self.data, "bWii"), 0)
        self.assertEqual(field_at(self.data, "controllers"), 1)
        self.assertEqual(field_at(self.data, "bFromSaveState"), 0)
        self.assertEqual(field_at(self.data, "bSaveConfig"), 0)
        self.assertEqual(field_at(self.data, "md5"), bytes(16))
        self.assertEqual(field_at(self.data, "frameCount"), 200)

    def test_the_rtc_is_the_configs_and_the_ticks_run_past_the_end(self):
        self.assertEqual(field_at(self.data, "recordingStartTime"), 946684800)
        fields_ticks = 200 * 486_000_000 * 1001 // 60000
        self.assertEqual(field_at(self.data, "tickCount"), 2 * fields_ticks)

    def test_everything_else_is_zero(self):
        for name in ("lagCount", "uniqueID", "numRerecords", "author", "videoBackend",
                     "audioEmulator", "bDSPHLE", "CPUCore", "memcards", "bClearSave", "bongos",
                     "bNetPlay", "GBAControllers", "discChange", "revision", "DSPiromHash",
                     "DSPcoefHash", "reserved2"):
            value = field_at(self.data, name)
            with self.subTest(name=name):
                self.assertEqual(value, bytes(len(value)) if isinstance(value, bytes) else 0)

    def test_read_header_reads_what_make_wrote(self):
        h = dtm.read_header(self.data)
        for name in OFFSETS:
            with self.subTest(name=name):
                self.assertEqual(h[name], field_at(self.data, name))

    def test_a_file_that_isnt_a_movie_is_refused(self):
        for data in (b"", b"XTM\x1a" + bytes(252), self.data + b"x"):
            with self.subTest(size=len(data)), self.assertRaises(dtm.Bad):
                dtm.read_header(data)


class PadTest(unittest.TestCase):
    def test_each_button_sets_its_bit_and_the_pad_is_connected(self):
        for name, key in (("START", "Start"), ("A", "A"), ("B", "B"), ("Z", "Z"),
                          ("UP", "DPadUp"), ("DOWN", "DPadDown"), ("RIGHT", "DPadRight"),
                          ("L", "L"), ("R", "R")):
            state = controller(dtm.Pad({name}).pack())
            with self.subTest(name=name):
                self.assertEqual([k for k in ("Start", "A", "B", "Z", "DPadUp", "DPadDown",
                                              "DPadRight", "L", "R") if state[k]], [key])
                self.assertEqual((state["is_connected"], state["get_origin"]), (1, 0))

    def test_a_pad_at_rest_is_centred_with_its_triggers_up(self):
        state = controller(dtm.Pad().pack())
        self.assertEqual([state[k] for k in ("StickX", "StickY", "CStickX", "CStickY",
                                             "TriggerL", "TriggerR")],
                         [0x80, 0x80, 0x80, 0x80, 0, 0])

    def test_l_and_r_press_their_triggers_all_the_way(self):
        presses = dtm.parse_route("10:L+R:5")
        state = controller(dtm.pad_at(presses, 0, 12).pack())
        self.assertEqual((state["L"], state["R"], state["TriggerL"], state["TriggerR"]),
                         (1, 1, 0xFF, 0xFF))

    def test_a_stick_push_moves_its_axis_from_the_centre(self):
        presses = dtm.parse_route("10:SR+SD40:5,12:A:1")
        state = controller(dtm.pad_at(presses, 0, 12).pack())
        self.assertEqual((state["StickX"], state["StickY"], state["A"]), (0x80 + 100, 0x80 - 40, 1))
        self.assertEqual(dtm.pad_at(presses, 0, 15), dtm.Pad())

    def test_unpack_undoes_pack(self):
        pad = dtm.Pad({"A", "DOWN"}, 1, 2, 3, 4, 5, 6)
        self.assertEqual(dtm.unpack(pad.pack()), pad)


class RouteTest(unittest.TestCase):
    def test_a_press_holds_from_its_frame_for_its_duration(self):
        presses = dtm.parse_route("300:A:5")
        self.assertEqual([bool(dtm.pad_at(presses, 0, f).buttons) for f in range(299, 306)],
                         [False, True, True, True, True, True, False])

    def test_bad_items_are_refused(self):
        for script in ("300:A", "300:Q:5", "300:A:0", "x:A:5", "5/300:A:5", "300:SRx:5",
                       "1:A:2:3"):
            with self.subTest(script=script), self.assertRaises(dtm.Bad):
                dtm.parse_route(script)

    def test_a_route_file_drops_its_comments(self):
        self.assertEqual(dtm.route_script("# a\n120:A:5,\n# b\n300:A:5\n"), "120:A:5,300:A:5")

    def test_every_route_on_pad_1_reads(self):
        for path in sorted(ROUTES.glob("*.txt")):
            with self.subTest(route=path.name):
                dtm.parse_route(dtm.route_script(path.read_text(encoding="utf-8")))

    def test_a_press_on_another_port_is_refused(self):
        with self.assertRaisesRegex(dtm.Bad, "pad 1 only"):
            dtm.make("2/100:A:5", 200)

    def test_a_press_past_the_movies_end_is_refused(self):
        with self.assertRaisesRegex(dtm.Bad, "after game frame 200"):
            dtm.make("196:A:5", 200)
        dtm.make("195:A:5", 200)


class PollMappingTest(unittest.TestCase):
    def test_two_polls_a_field_with_the_boots_shift(self):
        self.assertEqual([dtm.poll_field(i) for i in (0, 1, 2, 48, 49, 50)],
                         [23, 23, 24, 47, 47, 48])

    def test_without_a_timeline_a_field_is_a_frame(self):
        data = dtm.make("100:A:2", 200)
        down = [i for i, chunk in enumerate(polls_of(data)) if controller(chunk)["A"]]
        self.assertEqual(down, [154, 155, 156, 157])
        self.assertEqual({dtm.poll_field(i) for i in down}, {100, 101})

    def test_with_a_timeline_a_poll_gets_the_frame_its_field_reached(self):
        timeline = [0] * 100 + list(range(1, 101))
        self.assertEqual(dtm.frame_of(100, timeline), 0)
        self.assertEqual(dtm.frame_of(150, timeline), 50)
        self.assertEqual(dtm.frame_of(210, timeline), 110)
        data = dtm.make("50:A:1", 200, timeline)
        down = [i for i, chunk in enumerate(polls_of(data)) if controller(chunk)["A"]]
        self.assertEqual({dtm.poll_field(i) for i in down}, {150})

    def test_counted_polls_put_the_number_in_the_triggers_under_padclamps_floor(self):
        chunks = polls_of(dtm.make("", 600, count_polls=True))
        for i in (0, 29, 30, 899):
            if i < len(chunks):
                state = controller(chunks[i])
                with self.subTest(poll=i):
                    self.assertEqual((state["TriggerL"], state["TriggerR"]), (i // 30 % 30, i % 30))
                    self.assertLessEqual(max(state["TriggerL"], state["TriggerR"]), 30)

    def test_game_frames_add_up_renew_across_its_resets(self):
        # Field 4 resets the count and shows a frame, field 5 another.
        lines = ["frame 805DE2CC", "1 00000000", "2 00000001", "3 00000003", "4 00000001",
                 "5 00000002"]
        self.assertEqual(dtm.game_frames(lines), [0, 1, 3, 4, 5])

    def test_polls_reads_the_entry_the_game_wrote_last(self):
        state = 0x05020300  # length 5, read place 2, write place 3, none waiting
        entries = [0, 0, dtm.COUNT_BASE * 2 + 7, 0, 0]
        self.assertEqual(dtm.latest_poll(state, entries), 67)
        self.assertIsNone(dtm.latest_poll(state, [0] * 5))
        self.assertIsNone(dtm.latest_poll(0, entries))

    def test_poll_steps_count_the_polls_between_reads(self):
        head = "frame " + " ".join(f"{a:08X}" for a in (dtm.SCENE_WORD, *dtm.COUNT_WATCH))
        lines = [head]
        for n in range(50, 56):
            poll = 2 * n - dtm.POLL_SHIFT
            write = (n % 5) + 1
            entries = [0] * 5
            entries[write - 1] = poll // 30 % 30 << 8 | poll % 30
            words = [0x02000000, 0x05000000 | write << 8, *entries]
            lines.append(f"{n} " + " ".join(f"{w:08X}" for w in words))
        self.assertEqual(dtm.poll_steps(lines), [(51, 55, 0x02000000, 2, 0)])


class RoundTripTest(unittest.TestCase):
    def test_a_route_comes_back_from_its_movie(self):
        path = temp_dir(self) / "m.dtm"
        route = temp_dir(self) / "r.txt"
        route.write_text("# test\n100:A:3,\n140:START+DOWN:2\n")
        code, out, err = run_main(dtm.main, "make", str(route), "--out", str(path),
                                  "--fields", "200")
        self.assertEqual((code, err), (0, ""))
        data = path.read_bytes()
        self.assertEqual(len(data), 256 + 8 * (201 * 2 - 46))
        code, out, err = run_main(dtm.main, "read", str(path))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[1:], ["poll 0: nothing", "poll 154: A",
                                                "poll 160: nothing", "poll 234: START DOWN",
                                                "poll 238: nothing"])

    def test_steps_prints_each_scene_change_with_its_field_and_frame(self):
        ram = temp_dir(self) / "ram.txt"
        ram.write_text("frame 805361AC 805DE2CC\n1 00000000 00000000\n2 12000000 00000001\n"
                       "3 12000000 00000002\n4 05000013 00000003\n")
        code, out, err = run_main(dtm.main, "steps", str(ram), "--at", "2", "--at", "9")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "field 1 game frame 0: scene.major 0 scene.minor 0",
            "field 2 game frame 1: scene.major 18 scene.minor 0",
            "field 4 game frame 3: scene.major 5 scene.minor 19",
            "game frame 2: field 3", "game frame 9: not reached by field 4"])

    def test_a_bad_route_exits_2(self):
        route = temp_dir(self) / "r.txt"
        route.write_text("100:Q:3\n")
        code, out, err = run_main(dtm.main, "make", str(route), "--out",
                                  str(temp_dir(self) / "m.dtm"), "--fields", "200")
        self.assertEqual(code, 2)
        self.assertIn("no button Q", err)


if __name__ == "__main__":
    unittest.main()
