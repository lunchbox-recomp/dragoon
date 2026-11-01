"""What does the soak watch for while the bots play?

`Frozen` watches the picture, and `LogWatch` follows the game's stdout.txt for a music stream
that ends early (stream_voices.py's rule, on the `[axv]` lines) and for console resets. Each
raises `Detected` from the bot callback, which ends the run at that frame with its input log
whole. The game exiting or panicking and the game sending no frame, or no answer to a read,
are `bot_link.run`'s to tell (bot_stop.py names them). It has no command line.

The engine gives a bot no hash of the picture yet: the frames a game shows are copied on the GPU
and never written to guest RAM, and the link sends only `frame N`. `Frozen` takes its hash from a
function it's given, which by default reads `link.picture`. A Link has none, so by default
`Frozen` sees no hash and never fires.
"""
from __future__ import annotations

import os
from collections import deque
from collections.abc import Callable, Hashable, Mapping
from pathlib import Path
from typing import Optional

import session_log
import stream_voices
import warm_shaders
from bot_link import Link, Pad, is_reset

FPS = 60
FROZEN_SECONDS = 10  # game seconds the picture may stay the same while the bots' input changes
FROZEN_CHANGES = 2  # and the frames in those seconds the input has to change on, a press and its release
LOG_EVERY = 60  # frames between reads of the game's log
LOG_CHUNK = 1 << 23  # the most one read takes, so a log that grew fast is taken in pieces

FROZEN = "frozen_picture"
MUSIC = "music_cut"

Picture = Callable[[Link], Optional[Hashable]]


class Detected(Exception):
    """A watcher saw a fault. KIND is FROZEN or MUSIC, DETAIL says what and FRAME is the frame the
    bot was stepped at when it did. A fault read from the game's log also says how many console
    resets the log showed before it (RESETS) and the session directory of the process that wrote
    it (SESSION), since the read may have reached past a reset by the time it was handled."""

    def __init__(self, kind: str, detail: str, frame: int, resets: Optional[int] = None,
                 session: Optional[str] = None) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.frame = frame
        self.resets = resets
        self.session = session


def engine_picture(link: Link) -> Optional[Hashable]:
    """The hash of the picture the game last showed, from `link.picture`, or None when the link
    has none, as every Link today."""
    return getattr(link, "picture", None)


def _show(picture: Hashable) -> str:
    return picture.hex() if isinstance(picture, bytes) else str(picture)


class Frozen:
    """The same picture for SECONDS of game time while the race bots' input changes.

    `look` is given each frame's pads and whether the race bots made them. Only their frames
    count, because a menu or a loading screen can stand still while the walker presses. The
    window starts over when the picture changes, when the menus have the pads, when the link has
    no hash and when the game starts again (a new connection, or frame numbers that go back). It
    fires when the picture has stayed the same for SECONDS and the pads changed on at least
    CHANGES of the frames in the last SECONDS. Game time is the frame numbers at 60 a second,
    which can jump."""

    def __init__(self, picture: Picture = engine_picture, seconds: float = FROZEN_SECONDS,
                 changes: int = FROZEN_CHANGES) -> None:
        self._picture = picture
        self._frames = round(seconds * FPS)
        self._need = changes
        self.hashes = 0  # the frames a hash was seen on
        self._reset(0, 0)

    def _reset(self, frame: int, starts: int) -> None:
        self._starts = starts
        self._frame = frame
        self._pads: Optional[dict[int, Pad]] = None
        self._since: Optional[int] = None  # the frame the picture was last different
        self._seen: Optional[Hashable] = None
        self._changes: deque[int] = deque()  # the frames the pads changed on since then

    def look(self, link: Link, pads: Mapping[int, Pad], racing: bool) -> None:
        """Takes the pads the bots send at LINK's frame. Raises Detected when the picture is frozen."""
        frame = link.frame
        starts = getattr(link, "starts", 0)
        if starts != self._starts or frame < self._frame:
            self._reset(frame, starts)
        self._frame = frame
        changed = self._pads is not None and dict(pads) != self._pads
        self._pads = dict(pads)
        picture = self._picture(link) if racing else None
        if picture is None:
            self._since = None
            return
        self.hashes += 1
        if self._since is None or picture != self._seen:
            self._since, self._seen = frame, picture
            self._changes.clear()
            return
        if changed:
            self._changes.append(frame)
        while self._changes and self._changes[0] <= frame - self._frames:
            self._changes.popleft()
        if frame - self._since >= self._frames and len(self._changes) >= self._need:
            raise Detected(FROZEN, f"the picture's hash {_show(picture)} stayed the same from frame {self._since} "
                                   f"to frame {frame}, {(frame - self._since) / FPS:.1f} s of game time, while the "
                                   f"bots' input changed on {len(self._changes)} frames of the last "
                                   f"{self._frames / FPS:g} s", frame)


class Resets:
    """Counts the console resets in a log's lines, and keeps the `[shaders] ... in Z ms` line the
    first one's restart prints. The restart rebuilds the shader cache before the bot connects
    again, and that time counts against the hang limit. ON_SHADERS is called with that line and
    its Z once. A shutdown isn't a reset, since the game doesn't start again."""

    def __init__(self, on_shaders: Optional[Callable[[str, int], None]] = None) -> None:
        self.count = 0
        self.shaders: Optional[str] = None
        self.shaders_ms: Optional[int] = None
        self._on_shaders = on_shaders
        self._waiting = False

    def add(self, line: str) -> None:
        if is_reset(line):
            self.count += 1
            self._waiting = self.shaders is None
        elif self._waiting and (m := warm_shaders.BOOT_LINE.match(line)):
            self.shaders, self.shaders_ms, self._waiting = line, int(m[2]), False
            if self._on_shaders is not None:
                self._on_shaders(line, int(m[2]))


class LogWatch:
    """Follows the game's stdout.txt as it grows. `look` reads what the game has written since
    the last read, once every LOG_EVERY frames, and raises Detected(MUSIC) for a music stream that
    ended early. Every line of a read is handled before that, so the resets after a cut are
    counted too, and the Detected is the read's first cut, with the resets that came before it.
    A process that starts its session again (after a console reset) starts the voices over, since
    the old process's are gone. `resets` counts the resets, and `axv` says whether any `[axv]`
    line has come, which `GCN_AXVOICES=1` is for."""

    def __init__(self, path: Path, on_shaders: Optional[Callable[[str, int], None]] = None) -> None:
        self.path = path
        self.resets = Resets(on_shaders)
        self.axv = False
        self._voices = stream_voices.Tracker(keep=False)
        self._session: Optional[str] = None  # the last `[session] DIR` line's DIR
        self._cut: Optional[Detected] = None  # the first cut found since the last one was raised
        self._offset = 0
        self._partial = b""
        self._due = 0
        self._last = 0

    def look(self, frame: int) -> None:
        """Reads the log if a read is due at FRAME."""
        if frame < self._last:  # the game started again with its frames from 0
            self._due = 0
        self._last = frame
        if frame >= self._due:
            self._due = frame + LOG_EVERY
            self._take(frame, LOG_CHUNK)
            self._raise_cut()

    def finish(self, frame: int) -> None:
        """Reads all the log has now, for the run's last lines. Raises Detected as `look` does."""
        while self._take(frame, LOG_CHUNK):
            pass
        self._raise_cut()

    def _raise_cut(self) -> None:
        cut, self._cut = self._cut, None
        if cut is not None:
            raise cut

    def _take(self, frame: int, limit: int) -> bool:
        """Reads up to LIMIT bytes and handles their lines. True if there may be more to read."""
        try:
            size = os.stat(self.path).st_size
        except OSError:
            return False
        if size < self._offset:  # a log that started over
            self._offset, self._partial = 0, b""
        if size == self._offset:
            return False
        with open(self.path, "rb") as f:
            f.seek(self._offset)
            data = f.read(min(size - self._offset, limit))
        self._offset += len(data)
        *lines, self._partial = (self._partial + data).split(b"\n")
        for raw in lines:
            self._line(raw.decode("utf-8", "replace"), frame)
        return self._offset < size

    def _line(self, line: str, frame: int) -> None:
        if m := session_log.SESSION.match(line):
            self._voices = stream_voices.Tracker(keep=False)
            self._session = m[1]
        self.resets.add(line)
        voice = self._voices.add(line)
        self.axv = self.axv or self._voices.seen
        if voice is not None and self._cut is None:
            self._cut = Detected(MUSIC, f"a music stream ended early: {stream_voices.row(voice)}", frame,
                                 self.resets.count, self._session)
