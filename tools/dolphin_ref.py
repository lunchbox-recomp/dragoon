#!/usr/bin/env python3
"""How do we get a Dolphin we can trust as the reference, and run it offline?

Usage: dolphin_ref.py [--root DIR] fetch
       dolphin_ref.py audit-notes
       dolphin_ref.py [--root DIR] build
       dolphin_ref.py boot ISO --frames N [--press SCRIPT] [--dump] [--watch ADDR]...
                      [--out DIR] [--timeout SECONDS]

Dolphin is the reference for the game's logic and its 4:3 picture. ROOT is dolphin-ref beside
this clone unless --root names another. It holds src/ (the pinned tag), build/ and user/. boot
refuses a user folder that doesn't resolve inside dolphin-ref beside this clone, so a run never
gets ~/Library/Application Support/Dolphin or any other.

fetch clones PIN's tag with its submodules into ROOT/src, from source only, and refuses a ROOT/src
that's already there. audit-notes prints what the audit of that tree found and what each finding
became. build configures with CMAKE_OPTIONS into ROOT/build and builds TARGETS with Ninja, links
the tree's Data/Sys where the binary looks for it and records the tree's commit in BUILT. boot
writes CONFIG into ROOT/user/Config and plays ISO headless on Metal under `caffeinate -i` and
`nice -n 19`, on a fresh console with a blank card in slot A. It reads the disc where it is and
never copies it.

build and boot refuse a ROOT/src whose HEAD isn't PIN's commit, whose submodules at any depth
aren't at the commits it pins, or that `git status` finds changed or untracked files in. boot
also refuses a build that BUILT doesn't say came from that commit.

cmake and ninja run under `sandbox-exec` with build_profile, and Dolphin with run_profile. Both
deny all network, so a DNS lookup fails too. build_profile lets cmake and ninja write only
ROOT/build, and run_profile lets Dolphin write only ROOT/user, so neither can change src/ and
Dolphin can't change build/. Both may also write this user's temp and cache folders (USER_DIRS)
and /dev/null. Dolphin's profile allows one more thing, sending to a Unix socket inside
ROOT/user, which is the memory watcher's. --out needs no allowance, since boot itself moves the
dumps there once Dolphin has stopped. Every denial goes into the unified log with DENIED, so
  log show --last 10m --predicate 'eventMessage CONTAINS "dolphin-ref"'
lists what a run was refused. Each process's write to /dev/dtracehelper is among them, which
only stops it offering DTrace probes.

boot counts frames by Dolphin's memory watcher, which sends one datagram over that socket at
the end of every video field. Each datagram lists the watched words that changed, so --watch
reads guest RAM every frame, a 32-bit word at an aligned hex address. By default it's the word
holding kar_ram.json's scene.major. Once N frames have ended it sends SIGINT to the run's
process group, which Dolphin takes as a request to shut down, and SIGKILL to whatever is left
30 s later.

The headless frontend takes -m but never plays the movie, so --press is the only input. It
writes port 1's presses, in the routes' `frame:BUTTON[+BUTTON]:duration` syntax counted in
Dolphin's frames, into a pipe the pad reads (PIPE). The buttons are A, B, X, Y, Z, START, L, R
and the D-pad's D_UP, D_DOWN, D_LEFT and D_RIGHT, as the pipe names them. Every press has to
end by frame N. A press goes in as its frame's datagram comes, while Dolphin may already be a
frame or more on, so a press isn't frame-exact.

With --dump Dolphin writes a PNG each time the game shows a new picture, so a field that repeats
the last picture adds none, and the dumps lag the frames a little when the run stops. --out DIR
gets ram.txt (one line per frame: the frame and each watched word), frames.txt (each dump's
sha256 and name), the dumps in DIR/frames/ and run.json (the command, the frames and the wall
time). Without --out the dumps are deleted when the run ends.

Exits 0 when the command ran, 1 when a run stopped before N frames, and 2 on a bad argument, a
refused tree, build or user folder, or a step that failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import kar_ram


@dataclass(frozen=True)
class Pin:
    tag: str
    sha: str
    url: str


# The newest release tag at least two weeks old on 2026-11-18. 2609b, tagged 2026-11-08, was
# too new.
PIN = Pin(tag="2609a", sha="409881c34357d0f105fd473167d15ab0bd9c1628",
          url="https://github.com/dolphin-emu/dolphin.git")

# Bundled libraries only, the headless frontend and dolphin-tool, and nothing that goes online.
# Vulkan is off because its MoltenVK is the only thing the build would download.
CMAKE_OPTIONS = {
    "CMAKE_BUILD_TYPE": "Release",
    "USE_SYSTEM_LIBS": "OFF",
    "ENABLE_NOGUI": "ON",
    "ENABLE_QT": "OFF",
    "ENABLE_CLI_TOOL": "ON",
    "ENABLE_AUTOUPDATE": "OFF",
    "DOLPHIN_DEFAULT_UPDATE_TRACK": "",
    "ENABLE_ANALYTICS": "OFF",
    "USE_RETRO_ACHIEVEMENTS": "OFF",
    "USE_DISCORD_PRESENCE": "OFF",
    "USE_UPNP": "OFF",
    "USE_MGBA": "OFF",
    "ENABLE_VULKAN": "OFF",
    "USE_BUNDLED_MOLTENVK": "OFF",
    "ENCODE_FRAMEDUMPS": "OFF",
    "ENABLE_TESTS": "OFF",
    "ENABLE_LLVM": "OFF",
    "ENABLE_SDL": "OFF",
}
TARGETS = ("dolphin-nogui", "dolphin-tool")
NOGUI = Path("Binaries") / "dolphin-emu-nogui"
# A binary outside an app bundle looks for Sys here, beside itself.
SYS_LINK = Path("Binaries") / "Contents" / "Resources" / "Sys"
# What build writes into ROOT/build once the targets are built: the commit they came from.
BUILT = "dolphin-ref-built.json"

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
GETCONF = "/usr/bin/getconf"
# This user's temp folder, where TMPDIR points, and cache folder, the T and C under
# /private/var/folders. Nothing else of that user's folder there.
USER_DIRS = ("DARWIN_USER_TEMP_DIR", "DARWIN_USER_CACHE_DIR")
# What each denial the profiles make carries into the unified log. A deny rule without a message
# logs nothing.
DENIED = "dolphin-ref"
CAFFEINATE = ("/usr/bin/caffeinate", "-i")
NICE = ("/usr/bin/nice", "-n", "19")
BUILD_NICE = ("/usr/bin/nice", "-n", "10")
GRACE = 30.0  # seconds a stopped run gets to shut down before SIGKILL

# What the user folder's config holds. Online features are off, and the rest keeps a run
# deterministic: one CPU thread, a fixed clock, a blank card in slot A and no audio device.
CONFIG = {
    "Dolphin.ini": {
        "General": {"UseDiscordPresence": "False", "UseGameCovers": "False", "GDBPort": "-1",
                    "GDBSocket": ""},
        "Analytics": {"Enabled": "False", "PermissionAsked": "True", "ID": ""},
        "AutoUpdate": {"UpdateTrack": "", "HashOverride": ""},
        "Core": {"GFXBackend": "Metal", "CPUThread": "False", "DSPHLE": "True",
                 "EnableCheats": "False", "EmulationSpeed": "0.00000000",
                 "EnableCustomRTC": "True", "CustomRTCValue": "946684800",
                 "SlotA": "1", "SlotB": "255", "SerialPort1": "255",
                 "WiimoteContinuousScanning": "False"},
        "BluetoothPassthrough": {"Enabled": "False"},
        "DSP": {"Backend": "No Audio Output"},
        "Interface": {"UsePanicHandlers": "False", "ConfirmStop": "False",
                      "OnScreenDisplayMessages": "False"},
        "Movie": {"PauseMovie": "False", "DumpFramesSilent": "True"},
        "Input": {"BackgroundInput": "True"},
    },
    # Port 1's pad reads the pipe PIPE names, the only input a headless run can take.
    "GCPadNew.ini": {
        "GCPad1": {"Device": "Pipe/0/pad1",
                   **{f"Buttons/{b}": f"`Button {b.upper()}`" for b in ("A", "B", "X", "Y", "Z",
                                                                        "Start")},
                   **{f"D-Pad/{d}": f"`Button D_{d.upper()}`" for d in ("Up", "Down", "Left",
                                                                       "Right")},
                   "Triggers/L": "`Button L`", "Triggers/R": "`Button R`"},
    },
    "GFX.ini": {
        "Settings": {"InternalResolution": "1", "DumpFramesAsImages": "True",
                     "FrameDumpsResolutionType": "2", "ShowFPS": "False"},
        "Hardware": {"VSync": "False"},
    },
    "DSUClient.ini": {"Server": {"Enabled": "False"}},
    "RetroAchievements.ini": {"Achievements": {"Enabled": "False"}},
}
DUMP_ON = ("Dolphin.Movie.DumpFrames=True",)
WORD = 4  # the memory watcher reads 32-bit words
SUN_PATH_MAX = 103  # sockaddr_un's 104 bytes on macOS, less the NUL
WATCHER = Path("MemoryWatcher")
PIPE = Path("Pipes") / "pad1"
# Slot A's card when MemcardAPath is empty, and the console's SRAM. Each boot deletes both, so the
# game starts on a fresh console with a blank card, as a route does.
FRESH = (Path("GC") / "MemoryCardA.USA.raw", Path("GC") / "SRAM.raw")
# The buttons --press takes, as the pipe names them.
PIPE_BUTTONS = ("A", "B", "X", "Y", "Z", "START", "L", "R", "D_UP", "D_DOWN", "D_LEFT",
                "D_RIGHT")

AUDIT_NOTES = (
    ("binary", "Externals/Qt (100 files): Qt 6.8.3 for Windows x64 and ARM64. A macOS build never "
               "uses it, and ENABLE_QT=OFF builds no Qt at all."),
    ("binary", "Externals/FFmpeg-bin (10 .lib): FFmpeg for Windows. Unused on macOS, and "
               "ENCODE_FRAMEDUMPS=OFF drops FFmpeg, so frames dump as PNG."),
    ("binary", "Externals/gettext/msgfmt.exe, VulkanMemoryAllocator's VmaSample .exe, "
               "tinygltf's premake5.exe and imgui's glfw3.lib: Windows only, never built or run "
               "here."),
    ("binary", "Data/Sys/GC/dsp_rom.bin and dsp_coef.bin: Dolphin's free DSP ROM, guest code the "
               "emulated DSP runs only under LLE. CONFIG uses HLE."),
    ("binary", "Data/Sys/codehandler.bin: the Gecko code handler, guest code loaded only with "
               "cheats on. CONFIG turns them off."),
    ("binary", "Data/Sys/GC/font_*.bin and Data/Sys/Wii/shared2/wc24/*.bin: fonts and Wii data "
               "the guest reads. Data, not host code."),
    ("binary", "Test and sample data in lz4, minizip-ng, tinygltf, zlib-ng and docs/WiiMote: "
               "never built."),
    ("updater", "Source/Core/MacUpdater, UpdaterCommon and UICommon/AutoUpdate.cpp: the "
                "updater. ENABLE_AUTOUPDATE=OFF leaves it out, DOLPHIN_DEFAULT_UPDATE_TRACK is "
                "empty and CONFIG's UpdateTrack is empty. The nogui frontend never checks."),
    ("updater", "WinUpdater, Android's sysupdate and mGBA's updater: not built here "
                "(USE_MGBA=OFF)."),
    ("net-build", "Externals/MoltenVK fetches MoltenVK from GitHub at build time. "
                  "ENABLE_VULKAN=OFF and USE_BUNDLED_MOLTENVK=OFF leave it out, and Metal draws."),
    ("net-build", "SFML's, watcher's and minizip-ng's own FetchContent calls are never reached: "
                  "Dolphin builds those with its own CMakeLists and MZ_FETCH_LIBS=OFF. build "
                  "runs cmake and ninja under build_profile, which denies all network."),
    ("net-src", "Analytics (DolphinAnalytics.cpp, to analytics.dolphin-emu.org): "
                "ENABLE_ANALYTICS=OFF, and CONFIG's Analytics.Enabled is False. Dolphin still "
                "writes an Analytics.ID into Dolphin.ini, which nothing sends."),
    ("net-src", "RetroAchievements (AchievementManager.cpp, rcheevos): "
                "USE_RETRO_ACHIEVEMENTS=OFF."),
    ("net-src", "NetPlay and its traversal client, enet: built into core with no option. Only the "
                "Qt frontend starts NetPlay, and nogui has no way to."),
    ("net-src", "UPnP (miniupnpc): USE_UPNP=OFF. Discord presence: USE_DISCORD_PRESENCE=OFF."),
    ("net-src", "Game covers from art.gametdb.com, the Redump datfile from redump.info and "
                "GeckoCodeConfig's code downloads: Qt only. CONFIG's UseGameCovers is False."),
    ("net-src", "AMMediaboard (HW/DVD): the Triforce arcade board's network, which a GameCube "
                "disc never reaches."),
    ("net-src", "The GameCube broadband adapter (EXI BBA: TAP, XLink, built-in, IPC), the Wii's "
                "IOS network and KD requests, the DSU controller client, the GDB stub, the USB "
                "Gecko, a GBA on a pad port (SI_DeviceGBA's TCP link) and real Wiimotes: off "
                "unless configured. CONFIG sets SerialPort1 to none, DSU off and GDBPort -1, "
                "and leaves every pad port but a standard pad on port 1 empty."),
    ("net-src", "libcurl (Common/HttpRequest) is always linked, for the above. run_profile "
                "denies all network, DNS included, but sends to the memory watcher's socket."),
)


class Refused(Exception):
    """A tree, folder or argument the tool won't run with."""


def default_root() -> Path:
    return Path(__file__).resolve().parents[2] / "dolphin-ref"


def profile_path(path: Path) -> str:
    """PATH, resolved as the sandbox sees it, for a profile's string literal."""
    text = str(path.resolve())
    if '"' in text or "\\" in text:
        raise Refused(f"{text}: a quote or backslash can't go in a sandbox profile")
    return text


def user_dirs() -> tuple[str, ...]:
    """This user's own temp and cache folders, as the sandbox sees them."""
    dirs = []
    for name in USER_DIRS:
        out = subprocess.run([GETCONF, name], capture_output=True, text=True)
        text = out.stdout.strip()
        if out.returncode or not text:
            raise Refused(f"getconf {name} gave no folder")
        dirs.append(profile_path(Path(text)))
    return tuple(dirs)


def profile(writable: Sequence[str], scratch: Optional[Sequence[str]]) -> str:
    """No network at all, and no file writes outside WRITABLE, SCRATCH (user_dirs by default)
    and /dev/null."""
    subpaths = " ".join(f'(subpath "{path}")'
                        for path in (*writable, *(user_dirs() if scratch is None else scratch)))
    return (f'(version 1)(allow default)(deny network* (with message "{DENIED}"))'
            f'(deny file-write* (with message "{DENIED}"))'
            f'(allow file-write* {subpaths} (literal "/dev/null"))')


def build_profile(root: Path, scratch: Optional[Sequence[str]] = None) -> str:
    """cmake's and ninja's: writes go to ROOT/build only, besides the scratch folders."""
    return profile([profile_path(root / "build")], scratch)


def run_profile(root: Path, scratch: Optional[Sequence[str]] = None) -> str:
    """Dolphin's: writes go to ROOT/user only, besides the scratch folders, and it may send to a
    Unix socket there, the memory watcher's."""
    user = profile_path(root / "user")
    return (profile([user], scratch)
            + f'(allow network-outbound (remote unix-socket (subpath "{user}")))')


def sandboxed(profile: str, cmd: Sequence[str]) -> list[str]:
    return [SANDBOX_EXEC, "-p", profile, *cmd]


def git(src: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(src), *args], capture_output=True, text=True)
    if out.returncode:
        raise Refused(f"{src}: git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def submodule_drift(status: str) -> list[str]:
    """The lines of `git submodule status` for a submodule that isn't checked out at the commit
    the tree pins: `-` for one not checked out, `+` for another commit, `U` for a conflict."""
    return [line for line in status.splitlines() if line and line[0] != " "]


def check_tree(src: Path, sha: str = PIN.sha) -> str:
    """SRC's HEAD, refused unless it's SHA, every submodule at any depth is at its pinned commit
    and git finds nothing changed or untracked, submodules included."""
    if not (src / ".git").exists():
        raise Refused(f"{src}: not a git checkout")
    head = git(src, "rev-parse", "HEAD").strip()
    if head != sha:
        raise Refused(f"{src}: HEAD is {head}, not the pinned {sha}")
    drift = submodule_drift(git(src, "submodule", "status", "--recursive"))
    if drift:
        raise Refused(f"{src}: submodules off their pins: {'; '.join(drift)}")
    changed = git(src, "status", "--porcelain", "--ignore-submodules=none").splitlines()
    if changed:
        more = f" and {len(changed) - 3} more" if len(changed) > 3 else ""
        raise Refused(f"{src}: changed or untracked: {'; '.join(changed[:3])}{more}")
    return head


def check_build(build: Path, head: str) -> None:
    """Refuse BUILD unless BUILT there says it was built from HEAD."""
    try:
        built = json.loads((build / BUILT).read_text(encoding="utf-8"))["src"]
    except (OSError, ValueError, KeyError, TypeError):
        raise Refused(f"{build / BUILT}: no record of the commit it was built from") from None
    if built != head:
        raise Refused(f"{build}: built from {built}, not {head}")


def check_user(root: Path) -> Path:
    """ROOT/user, refused unless it resolves inside dolphin-ref beside this clone."""
    user = root / "user"
    allowed = default_root().resolve()
    real = user.resolve()
    if real != allowed and allowed not in real.parents:
        raise Refused(f"{user}: resolves to {real}, outside {allowed}")
    return user


def fetch_command(src: Path, pin: Pin = PIN) -> list[str]:
    return ["git", "clone", "--depth", "1", "--branch", pin.tag, "--recurse-submodules",
            "--jobs", "8", pin.url, str(src)]


def configure_command(root: Path, options: dict = CMAKE_OPTIONS) -> list[str]:
    defines = [f"-D{key}={value}" for key, value in options.items()]
    return sandboxed(build_profile(root), ["cmake", "-S", str(root / "src"), "-B",
                                           str(root / "build"), "-G", "Ninja", *defines])


def build_command(root: Path, targets: Sequence[str] = TARGETS) -> list[str]:
    return sandboxed(build_profile(root), [*BUILD_NICE, "ninja", "-C", str(root / "build"),
                                           *targets])


def write_config(user: Path, config: dict = CONFIG) -> None:
    folder = user / "Config"
    folder.mkdir(parents=True, exist_ok=True)
    for name, sections in config.items():
        lines = []
        for section, values in sections.items():
            lines.append(f"[{section}]")
            lines.extend(f"{key} = {value}" for key, value in values.items())
        (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def boot_command(root: Path, user: Path, iso: Path, dump: bool = False) -> list[str]:
    cmd = [str(root / "build" / NOGUI), "-u", str(user), "-p", "headless", "-v", "Metal"]
    for setting in DUMP_ON if dump else ():
        cmd += ["-C", setting]
    cmd += ["-e", str(iso)]
    return [*CAFFEINATE, *NICE, *sandboxed(run_profile(root), cmd)]


def parse_presses(script: str, frames: int) -> dict[int, list[str]]:
    """The pipe commands to send after each frame, from a route's `frame:BUTTON[+BUTTON]:duration`
    presses: PRESS after FRAME and RELEASE after FRAME + duration, which has to be by FRAMES."""
    commands: dict[int, list[str]] = {}
    for item in filter(None, (part.strip() for part in script.split(","))):
        fields = item.split(":")
        try:
            frame, duration = int(fields[0]), int(fields[2])
        except (IndexError, ValueError):
            raise Refused(f"--press {item!r}: not frame:BUTTON:duration") from None
        if len(fields) != 3 or frame < 1 or duration < 1:
            raise Refused(f"--press {item!r}: not frame:BUTTON:duration")
        if frame + duration > frames:
            raise Refused(f"--press {item!r}: ends after frame {frames}, the run's last")
        for button in fields[1].upper().split("+"):
            if button not in PIPE_BUTTONS:
                raise Refused(f"--press {item!r}: no button {button}")
            commands.setdefault(frame, []).append(f"PRESS {button}")
            commands.setdefault(frame + duration, []).append(f"RELEASE {button}")
    return commands


class Pipe:
    """The writing end of the pad's pipe, opened once Dolphin has opened the reading end."""

    def __init__(self, path: Path, commands: dict[int, list[str]]) -> None:
        self.path = path
        self.commands = commands
        self.fd: Optional[int] = None

    def frame(self, n: int) -> None:
        lines = self.commands.get(n)
        if not lines:
            return
        if self.fd is None:
            self.fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        os.write(self.fd, "".join(f"{line}\n" for line in lines).encode("ascii"))

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)


def default_watch() -> str:
    """The aligned word holding kar_ram.json's scene.major."""
    entry = kar_ram.load()["scene.major"]
    return f"{entry.address & ~(WORD - 1):08X}"


def watch_address(text: str) -> str:
    try:
        value = int(text, 16)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a hex address") from None
    if not kar_ram.in_ram(value, WORD):
        raise argparse.ArgumentTypeError(f"{text!r} is outside main RAM")
    if value % WORD:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a multiple of {WORD}")
    return f"{value:08X}"


def parse_watch(message: bytes) -> dict[str, int]:
    """The words one memory-watcher datagram says changed: address lines and hex value lines in
    turn, ended by a NUL."""
    lines = message.rstrip(b"\0").decode("ascii").split("\n")
    pairs = [line for line in lines if line]
    return {pairs[i].upper(): int(pairs[i + 1], 16) for i in range(0, len(pairs) - 1, 2)}


def fresh_console(user: Path, watched: Sequence[str]) -> Path:
    """Delete FRESH's card and SRAM and the old pipe under USER, write the watcher's addresses
    and make a new pipe. Returns the pipe's path."""
    (user / WATCHER).mkdir(parents=True, exist_ok=True)
    (user / WATCHER / "Locations.txt").write_text("\n".join(watched) + "\n")
    pipe = user / PIPE
    pipe.parent.mkdir(parents=True, exist_ok=True)
    for path in (pipe, *(user / p for p in FRESH)):
        if path.exists() or path.is_symlink():
            path.unlink()
    os.mkfifo(pipe)
    return pipe


@dataclass
class Run:
    frames: int
    seconds: float
    exit: Optional[int]
    ram: list[dict[str, int]]


def stop(proc, grace: float = GRACE, killpg: Callable = os.killpg) -> None:
    """SIGINT to PROC's process group, then SIGKILL to whatever of it is left after GRACE
    seconds. PROC leads its own group, so this reaches Dolphin under caffeinate."""
    try:
        killpg(proc.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        proc.poll()  # reaps the leader, so a group of one zombie reads as gone
        try:
            killpg(proc.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def play(cmd: Sequence[str], sock_path: Path, frames: int, timeout: float,
         watched: Sequence[str], on_frame: Callable[[int], None] = lambda n: None,
         popen: Callable = subprocess.Popen, killpg: Callable = os.killpg) -> Run:
    """Start CMD in a process group of its own, count the memory watcher's datagrams on
    SOCK_PATH and stop the group once FRAMES have come or TIMEOUT seconds pass with none. Each
    frame's entry holds every watched word as it stands at that frame's end. ON_FRAME gets each
    frame's number, from 1, as its datagram comes."""
    if len(str(sock_path).encode()) > SUN_PATH_MAX:
        raise Refused(f"{sock_path}: too long for a Unix socket")
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists() or sock_path.is_symlink():
        sock_path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(str(sock_path))
    sock.settimeout(timeout)
    state = {address: 0 for address in watched}
    ram: list[dict[str, int]] = []
    start = time.monotonic()
    proc = popen(list(cmd), start_new_session=True)
    try:
        while len(ram) < frames:
            try:
                message = sock.recv(65536)
            except socket.timeout:
                break
            state.update(parse_watch(message))
            ram.append(dict(state))
            on_frame(len(ram))
    finally:
        seconds = time.monotonic() - start
        stop(proc, killpg=killpg)
        sock.close()
        sock_path.unlink()
    return Run(len(ram), seconds, proc.returncode, ram)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_index(path: Path) -> int:
    return int(path.stem.rsplit("_", 1)[1])


def save_run(out: Path, cmd: Sequence[str], run: Run, watched: Sequence[str],
             dumps: Path) -> int:
    """Write OUT's ram.txt, frames.txt and run.json and move the dumps into OUT/frames. Returns
    how many dumps there were."""
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "ram.txt", "w", encoding="utf-8") as f:
        f.write("frame " + " ".join(watched) + "\n")
        for i, words in enumerate(run.ram, 1):
            f.write(f"{i} " + " ".join(f"{words[a]:08X}" for a in watched) + "\n")
    pngs = sorted(dumps.glob("framedump_*.png"), key=dump_index) if dumps.is_dir() else []
    frames = out / "frames"
    frames.mkdir(exist_ok=True)
    with open(out / "frames.txt", "w", encoding="utf-8") as f:
        for png in pngs:
            f.write(f"{sha256(png)}  {png.name}\n")
            shutil.move(str(png), str(frames / png.name))
    (out / "run.json").write_text(json.dumps({
        "pin": PIN.tag, "sha": PIN.sha, "command": list(cmd), "frames": run.frames,
        "seconds": round(run.seconds, 2), "exit": run.exit, "dumps": len(pngs),
    }, indent=1) + "\n", encoding="utf-8")
    return len(pngs)


def clear_dumps(user: Path) -> Path:
    dumps = user / "Dump" / "Frames"
    if dumps.is_dir():
        shutil.rmtree(dumps)
    return dumps


def cmd_fetch(root: Path) -> int:
    src = root / "src"
    if src.exists():
        raise Refused(f"{src}: already there")
    root.mkdir(parents=True, exist_ok=True)
    if subprocess.run(fetch_command(src)).returncode:
        print(f"{src}: clone failed", file=sys.stderr)
        return 2
    check_tree(src)
    print(f"{src}: {PIN.tag} at {PIN.sha}")
    return 0


def cmd_build(root: Path) -> int:
    src, build = root / "src", root / "build"
    head = check_tree(src)
    for name, cmd in (("cmake", configure_command(root)), ("ninja", build_command(root))):
        if subprocess.run(cmd).returncode:
            print(f"{build}: {name} failed", file=sys.stderr)
            return 2
    link = build / SYS_LINK
    if not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(src / "Data" / "Sys")
    (build / BUILT).write_text(json.dumps({"src": head}) + "\n", encoding="utf-8")
    print(build / NOGUI)
    return 0


def cmd_boot(root: Path, args: argparse.Namespace) -> int:
    check_build(root / "build", check_tree(root / "src"))
    if not args.iso.is_file():
        raise Refused(f"{args.iso}: no such disc")
    user = check_user(root)
    commands = parse_presses(args.press, args.frames)
    watched = args.watch or [default_watch()]
    write_config(user)
    pipe = Pipe(fresh_console(user, watched), commands)
    dumps = clear_dumps(user)
    cmd = boot_command(root, user, args.iso, args.dump)
    try:
        run = play(cmd, user / WATCHER / "MemoryWatcher", args.frames, args.timeout, watched,
                   pipe.frame)
    finally:
        pipe.close()
    count = 0
    if args.out:
        count = save_run(args.out, cmd, run, watched, dumps)
    clear_dumps(user)
    last = run.ram[-1] if run.ram else {}
    words = " ".join(f"{a}={last[a]:08X}" for a in watched) if last else "no frames"
    print(f"frames {run.frames} of {args.frames} in {run.seconds:.1f} s, exit {run.exit}, "
          f"dumps {count}, last {words}")
    return 0 if run.frames >= args.frames else 1


def cmd_audit_notes() -> int:
    print(f"Dolphin {PIN.tag} ({PIN.sha}), audited on 2026-11-18 for prebuilt binaries, "
          "updaters and network calls")
    for category, note in AUDIT_NOTES:
        print(f"{category}: {note}")
    return 0


def frame_count(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a frame count") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} isn't 1 or more frames")
    return value


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="the dolphin-ref folder (default: dolphin-ref beside this clone)")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="clone the pinned tag with its submodules")
    sub.add_parser("audit-notes", help="print the audit's findings and decisions")
    sub.add_parser("build", help="configure and build offline")
    boot = sub.add_parser("boot", help="play a disc headless for N frames")
    boot.add_argument("iso", type=Path, metavar="ISO")
    boot.add_argument("--frames", type=frame_count, required=True, metavar="N")
    boot.add_argument("--press", default="", metavar="SCRIPT",
                      help="port 1's presses in the routes' syntax, by Dolphin's frames")
    boot.add_argument("--dump", action="store_true", help="dump every frame as a PNG")
    boot.add_argument("--watch", type=watch_address, action="append", metavar="ADDR",
                      help="a word of guest RAM to read every frame (default: the word "
                           "holding scene.major)")
    boot.add_argument("--out", type=Path, metavar="DIR")
    boot.add_argument("--timeout", type=float, default=60.0, metavar="SECONDS",
                      help="stop when no frame ends for this long (default 60)")
    args = ap.parse_args(argv)
    root = (args.root or default_root()).resolve()
    try:
        if args.command == "fetch":
            return cmd_fetch(root)
        if args.command == "audit-notes":
            return cmd_audit_notes()
        if args.command == "build":
            return cmd_build(root)
        return cmd_boot(root, args)
    except Refused as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
