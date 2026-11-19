"""The nightly run's stand-ins for its tests: a pmset, a pgrep and a tree whose game is
testengine.py's fake, with goldens that match what it draws and shows."""
from __future__ import annotations

import hashlib
import json
import unittest

import nightly
import nightly_report
import nightly_steps
import state_goldens
from frame_pair import write_png
from framediff import Image
from nightly_report import Check
from testengine import make_tree, set_plan
from testutil import temp_dir, write_file

AC = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%; charged; 0:00 remaining present: true\n"
BATTERY = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t80%; discharging; 4:00 remaining\n"
# Two routes the fake game plays. It never leaves the boot screen, which is all a state check needs.
MANIFEST = "title 20 60 60,120\nmenu  20 60 120\n"


def fake_image(frame: int, blue: int = 0) -> Image:
    return Image(2, 2, 3, bytes([frame % 256, frame // 256 % 256, blue]) * 4)


def fake_frame(frame: int, blue: int = 0) -> bytes:
    """The dump testengine's fake game writes at FRAME."""
    return write_png(fake_image(frame, blue))


def booting(read_at: int) -> tuple[int, dict]:
    """The state the fake game shows at the boot screen, read at READ_AT."""
    state = {f: state_goldens.NONE if f.split(".")[-1] in "xyz" else "0" for f in state_goldens.FIELDS}
    state["scene.minor"] = "38"
    return read_at, state


class FakeScript:
    """A command as a script that prints out.txt and exits with code.txt's number, for pmset and pgrep."""

    def __init__(self, test: unittest.TestCase, name: str, text: str = "", code: int = 0) -> None:
        self.dir = temp_dir(test)
        self.script = write_file(self.dir, name, f"#!/bin/sh\ncat '{self.dir}/out.txt'\nexit $(cat '{self.dir}/code.txt')\n")
        self.script.chmod(0o755)
        self.now(text, code)

    def now(self, text: str, code: int = 0) -> None:
        write_file(self.dir, "out.txt", text)
        write_file(self.dir, "code.txt", str(code))

    def command(self) -> list[str]:
        return [str(self.script)]


class FakePmset(FakeScript):
    """pmset -g batt, saying whatever `now` was last given."""

    def __init__(self, test: unittest.TestCase, text: str = AC) -> None:
        super().__init__(test, "pmset", text)


class FakeTree:
    """A tree with testengine's fake probe.sh, a two-route manifest and goldens that match what
    the fake game draws and shows, which a test then changes."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.root = temp_dir(test)
        make_tree(self.root)
        set_plan(self.root)
        self.hashes = self.root / "tests" / "hashes"
        for d in ("gl", "gl-16x9", state_goldens.STATE, "audio"):
            (self.hashes / d).mkdir(parents=True)
        write_file(self.hashes, "manifest.txt", MANIFEST)
        for name, frames in (("title", [60, 120]), ("menu", [60, 120])):
            text = "".join(f"frame_{f:05d} {hashlib.sha1(fake_frame(f)).hexdigest()}\n" for f in frames)
            write_file(self.hashes / "gl", f"{name}.txt", text)
            write_file(self.hashes / "gl-16x9", f"{name}.txt", text)
        state = self.hashes / state_goldens.STATE
        write_file(state, "title.txt", state_goldens.format_golden("title", {60: booting(60), 120: booting(120)}))
        write_file(state, "menu.txt", state_goldens.format_golden("menu", {120: booting(120)}))
        self.report = self.root / "build" / "nightly" / "2026-11-18-0130"
        self.report.mkdir(parents=True)
        self.games = 0

    def context(self, before=None, **kw) -> nightly_steps.Context:
        def counted() -> None:
            if before is not None:
                before()
            self.games += 1
        return nightly_steps.Context(self.root, self.report, before=counted, say=lambda text: None, **kw)

    def play(self, step: str, ctx: nightly_steps.Context) -> list[Check]:
        code = nightly.play_step(step, ctx)
        if code not in (0, nightly.STOPPED_ON_BATTERY):
            raise AssertionError(f"{step} exited {code}: {(ctx.work / f'{step}.json').read_text()}")
        return nightly_report.from_json(json.loads((ctx.work / f"{step}.json").read_text())["checks"])

    def by_id(self, checks: list[Check]) -> dict[str, Check]:
        return {c.id: c for c in checks}

    def runs_left(self) -> list[str]:
        probe = self.root / "build" / "probe"
        return sorted(p.name for p in probe.iterdir()) if probe.is_dir() else []

    def known(self, text: str) -> None:
        write_file(self.hashes, "known-issues.txt", text)
