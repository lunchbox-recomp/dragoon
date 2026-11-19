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
# ControllerState's bitfield from Movie.h, from the lowest bit of its first byte.
STATE_BITS = ("Start", "A", "B", "X", "Y", "Z", "DPadUp", "DPadDown", "DPadLeft", "DPadRight",
              "L", "R", "disc", "reset", "is_connected", "get_origin")
ROUTE_NAMES = {"Start": "START", "DPadUp": "UP", "DPadDown": "DOWN", "DPadLeft": "LEFT",
               "DPadRight": "RIGHT"}


def field_at(data: bytes, name: str):
    offset, fmt = OFFSETS[name]
    return struct.unpack_from(fmt, data, offset)[0]


def controller(chunk: bytes) -> dict:
    """One ControllerState read by hand: the 16 bits, then TriggerL, TriggerR, the main stick
    and the C stick, a byte each."""
    bits = chunk[0] | chunk[1] << 8
    state = {name: bits >> i & 1 for i, name in enumerate(STATE_BITS)}
    state.update(zip(("TriggerL", "TriggerR", "StickX", "StickY", "CStickX", "CStickY"),
                     chunk[2:8]))
    return state


def polls_of(data: bytes) -> list[bytes]:
    return [data[i:i + 8] for i in range(256, len(data), 8)]


def down(data: bytes, key: str = "A") -> list[int]:
    return [i for i, chunk in enumerate(polls_of(data)) if controller(chunk)[key]]


def ram(rows: list[dict]) -> list[str]:
    """A ram.txt watching dtm.WATCH, from 1, each row giving some words by address."""
    lines = ["frame " + " ".join(f"{a:08X}" for a in dtm.WATCH)]
    for n, row in enumerate(rows, 1):
        lines.append(f"{n} " + " ".join(f"{row.get(a, 0):08X}" for a in dtm.WATCH))
    return lines


def queue_row(write: int, word: int, triggers: int = 0, renew: int = 0) -> dict:
    """A row whose queue's latest entry, the one before WRITE, holds WORD and TRIGGERS."""
    k = (write - 1) % dtm.QUEUE_LENGTH
    return {dtm.PAD_STATE: dtm.QUEUE_LENGTH << 24 | write << 8, dtm.BUTTON_WORDS[k]: word,
            dtm.TRIGGER_WORDS[k]: triggers, dtm.RENEW: renew}


class AddressTest(unittest.TestCase):
    def test_the_words_come_from_kar_ram_json(self):
        self.assertEqual((dtm.SCENE_WORD, dtm.PAD_STATE, dtm.QUEUE, dtm.QUEUE_ENTRY, dtm.RENEW),
                         (0x805361AC, 0x8058B080, 0x80535300, 0x34, 0x805DE2CC))
        self.assertEqual(dtm.QUEUE_LENGTH, 5)
        self.assertEqual(dtm.TRIGGER_WORDS[1], 0x80535338)


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
    def test_each_button_sets_its_own_bit_and_no_other(self):
        for i, name in enumerate(STATE_BITS[:12]):
            button = ROUTE_NAMES.get(name, name)
            state = controller(dtm.Pad({button}).pack())
            with self.subTest(button=button):
                self.assertEqual([k for k in STATE_BITS if state[k]], [name, "is_connected"])
                self.assertEqual(dtm.Pad({button}).pack()[:2],
                                 struct.pack("<H", 1 << i | 1 << 14))

    def test_a_pad_at_rest_is_centred_connected_with_its_triggers_up(self):
        state = controller(dtm.Pad().pack())
        self.assertEqual([state[k] for k in ("StickX", "StickY", "CStickX", "CStickY",
                                             "TriggerL", "TriggerR")],
                         [0x80, 0x80, 0x80, 0x80, 0, 0])
        self.assertEqual([k for k in STATE_BITS if state[k]], ["is_connected"])
        self.assertEqual(controller(dtm.Pad(connected=False).pack())["is_connected"], 0)

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

    def test_a_push_of_0_leaves_an_earlier_push_as_the_engine_does(self):
        presses = dtm.parse_route("10:SL:5,11:SR0:2")
        self.assertEqual(dtm.pad_at(presses, 0, 11).stick_x, 0x80 - 100)

    def test_unpack_undoes_pack(self):
        pad = dtm.Pad({"A", "DOWN"}, 1, 2, 3, 4, 5, 6)
        self.assertEqual(dtm.unpack(pad.pack()), pad)


class RouteTest(unittest.TestCase):
    def test_a_press_holds_from_its_frame_for_its_duration(self):
        presses = dtm.parse_route("300:A:5")
        self.assertEqual([bool(dtm.pad_at(presses, 0, f).buttons) for f in range(299, 306)],
                         [False, True, True, True, True, True, False])

    def test_a_route_file_drops_its_comments(self):
        self.assertEqual(dtm.route_script("# a\n120:A:5,\n# b\n300:A:5\n"), "120:A:5,300:A:5")

    def test_a_press_on_another_port_is_refused(self):
        with self.assertRaisesRegex(dtm.Bad, "pad 1 only"):
            dtm.make("2/100:A:5", 200)

    def test_a_bad_item_is_refused(self):
        with self.assertRaisesRegex(dtm.Bad, "no button Q"):
            dtm.make("100:Q:5", 200)

    def test_a_press_past_the_last_read_is_refused(self):
        with self.assertRaisesRegex(dtm.Bad, "after game frame 199"):
            dtm.make("195:A:5", 200)
        dtm.make("194:A:5", 200)


class PollMappingTest(unittest.TestCase):
    def test_two_polls_a_field_with_the_boots_shift(self):
        self.assertEqual([dtm.poll_field(i) for i in (0, 1, 2, 50, 51, 52)],
                         [23, 23, 24, 48, 48, 49])

    def test_a_fields_last_poll_is_read_in_the_next_field(self):
        self.assertEqual([dtm.read_field(i) for i in (50, 51, 52, 53)], [48, 49, 49, 50])

    def test_without_a_timeline_a_read_gets_the_frame_of_the_field_before(self):
        data = dtm.make("100:A:2", 200)
        self.assertEqual(down(data), [155, 156, 157, 158])
        self.assertEqual({dtm.read_field(i) - 1 for i in down(data)}, {100, 101})

    def test_with_a_timeline_a_read_gets_the_frame_the_field_before_reached(self):
        timeline = [0] * 100 + list(range(1, 101))
        self.assertEqual([dtm.frame_of(f, timeline) for f in (0, 100, 150, 210)], [0, 0, 50, 110])
        data = dtm.make("50:A:1", 200, timeline)
        self.assertEqual({dtm.read_field(i) for i in down(data)}, {151})

    def test_counted_polls_put_the_number_in_the_triggers_under_padclamps_floor(self):
        chunks = polls_of(dtm.make("", 600, count_polls=True))
        for i in (0, 29, 30, 899, 900, 1000):
            state = controller(chunks[i])
            with self.subTest(poll=i):
                self.assertEqual((state["TriggerL"], state["TriggerR"]), (i // 30 % 30, i % 30))
                self.assertLessEqual(max(state["TriggerL"], state["TriggerR"]), 30)

    def test_game_frames_add_up_renew_across_its_resets(self):
        # Field 4 resets the count and shows a frame, field 5 another.
        lines = ["frame 805DE2CC", "1 00000000", "2 00000001", "3 00000003", "4 00000001",
                 "5 00000002"]
        self.assertEqual(dtm.game_frames(lines), [0, 1, 3, 4, 5])

    def test_latest_is_the_entry_before_the_write_place(self):
        state = 0x05020300  # length 5, read place 2, write place 3, none waiting
        self.assertEqual(dtm.latest(state, [1, 2, 3, 4, 5]), 3)
        self.assertEqual(dtm.latest(0x05020000, [1, 2, 3, 4, 5]), 5)
        self.assertIsNone(dtm.latest(state, [0] * 5))
        self.assertIsNone(dtm.latest(0, [1, 2, 3, 4, 5]))

    def test_poll_steps_count_the_polls_between_reads_past_the_counts_wrap(self):
        rows = [{} for _ in range(439)]
        for n in range(440, 481):
            write = n % 5 + 1
            row = {dtm.PAD_STATE: 5 << 24 | write << 8, dtm.SCENE_WORD: 0x02000000}
            for j in range(5):  # the queue holds the last five reads, the newest before WRITE
                poll = 2 * (n - j) - dtm.POLL_SHIFT
                row[dtm.TRIGGER_WORDS[(write - 1 - j) % 5]] = poll // 30 % 30 << 8 | poll % 30
            rows.append(row)
        lines = ram(rows)
        self.assertEqual(dtm.reads(lines)[-1], (480, 914, 0x02000000))
        self.assertEqual(dtm.poll_steps(lines), [(441, 480, 0x02000000, 2, 0)])


class PressReadTest(unittest.TestCase):
    """A fake run where the game shows one frame a field from field 11 and reads port 1 once a
    field, the movie's input made from that timeline."""

    def run_of(self, script: str, shift: int = 0) -> list[str]:
        presses = dtm.parse_route(script)
        rows = []
        for n in range(1, 101):
            given = max(0, n - 1 - 10)  # the frames shown by the field before
            pad = dtm.pad_at(presses, 0, given + shift)
            word = sum(dtm.PAD_BITS[b] for b in pad.buttons) << 16
            rows.append(queue_row(n % 5 + 1, word, renew=max(0, n - 10)))
        return ram(rows)

    def test_each_press_is_read_on_its_frame(self):
        lines = self.run_of("20:A:3,40:START+DOWN:2,60:A:1")
        found = dtm.press_reads(dtm.parse_route("20:A:3,40:START+DOWN:2,60:A:1"), lines)
        self.assertEqual([(p.at, field_, frame) for p, field_, frame in found],
                         [(20, 31, 20), (40, 51, 40), (60, 71, 60)])

    def test_a_press_read_a_frame_early_shows_as_off(self):
        route = temp_dir(self) / "r.txt"
        route.write_text("20:A:3\n")
        path = temp_dir(self) / "ram.txt"
        path.write_text("\n".join(self.run_of("20:A:3", shift=1)) + "\n")
        code, out, err = run_main(dtm.main, "presses", str(route), str(path))
        self.assertEqual(code, 1)
        self.assertEqual(out, "20:A: read at field 30, given at game frame 19, -1 frames off\n")

    def test_a_press_never_read_is_named(self):
        found = dtm.press_reads(dtm.parse_route("200:B:3"), self.run_of(""))
        self.assertEqual([(p.at, f, g) for p, f, g in found], [(200, -1, -1)])


class ConvergeTest(unittest.TestCase):
    """converge against a fake Dolphin that shows no frame for the first SLOW fields."""

    def play(self, slow):
        def run(movie: Path, out: Path) -> int:
            self.played.append(movie.name)
            out.mkdir()
            rows = [{dtm.RENEW: max(0, n - slow(len(self.played)))} for n in range(1, 301)]
            (out / "ram.txt").write_text("\n".join(ram(rows)) + "\n")
            return 0
        return run

    def setUp(self):
        self.folder = temp_dir(self)
        self.played: list[str] = []

    def test_it_stops_at_the_movie_its_run_gives_back(self):
        n, path = dtm.converge("150:A:5", 300, self.folder, self.play(lambda run: 40))
        self.assertEqual((n, path.name), (2, "movie-2.dtm"))
        self.assertEqual(self.played, ["movie-1.dtm", "movie-2.dtm"])
        timeline = dtm.game_frames((self.folder / "run-2" / "ram.txt").read_text().splitlines())
        self.assertEqual(path.read_bytes(), dtm.make("150:A:5", 300, timeline))

    def test_it_gives_up_after_its_cap(self):
        n, path = dtm.converge("150:A:5", 300, self.folder, self.play(lambda run: 30 + run),
                               most=3)
        self.assertEqual((n, path.name, len(self.played)), (None, "movie-3.dtm", 3))

    def test_a_run_that_fails_stops_it(self):
        with self.assertRaisesRegex(dtm.Bad, "didn't play all 300 fields"):
            dtm.converge("150:A:5", 300, self.folder, lambda movie, out: 1)

    def test_the_run_plays_the_movie_watching_the_queue(self):
        cmd = dtm.boot_command(Path("/d.iso"), Path("/m.dtm"), 300, Path("/out"), "fast")
        self.assertEqual(cmd[3:12], ["boot", "/d.iso", "--frames", "300", "--movie", "/m.dtm",
                                     "--disc", "fast", "--watch"])
        self.assertEqual(cmd[cmd.index("--out") + 1], "/out")
        self.assertEqual(cmd[12:-2:2], [f"{a:08X}" for a in dtm.WATCH])


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
        self.assertEqual(out.splitlines()[1:], ["poll 0: nothing", "poll 155: A",
                                                "poll 161: nothing", "poll 235: START DOWN",
                                                "poll 239: nothing"])

    def test_steps_prints_each_scene_change_with_its_field_and_frame(self):
        ram_txt = temp_dir(self) / "ram.txt"
        ram_txt.write_text("frame 805361AC 805DE2CC\n1 00000000 00000000\n2 12000000 00000001\n"
                           "3 12000000 00000002\n4 05000013 00000003\n")
        code, out, err = run_main(dtm.main, "steps", str(ram_txt), "--at", "2", "--at", "9")
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
