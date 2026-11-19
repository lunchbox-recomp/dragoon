#!/usr/bin/env python3
"""How do we get a Dolphin we can trust as the reference, and run it offline?

Usage: dolphin_ref.py [--root DIR] fetch
       dolphin_ref.py [--root DIR] patch
       dolphin_ref.py audit-notes
       dolphin_ref.py [--root DIR] build
       dolphin_ref.py boot ISO --frames N [--movie DTM | --press SCRIPT] [--disc SPEED]
                      [--dump] [--watch ADDR]... [--out DIR] [--timeout SECONDS]

Dolphin is the reference for the game's logic and its 4:3 picture. ROOT is dolphin-ref beside
this clone unless --root names another. It holds src/ (the pinned tag), build/ and user/. boot
refuses a user folder that doesn't resolve inside dolphin-ref beside this clone, so a run never
gets ~/Library/Application Support/Dolphin or any other.

fetch clones PIN's tag with its submodules into ROOT/src, from source only, refuses a ROOT/src
that's already there and applies PATCH. patch applies PATCH to a ROOT/src that's clean at the
pin, and does nothing to one it's already applied to. PATCH is the one change made to Dolphin,
and only to the headless frontend (PATCH_SCOPE): it plays -m's movie before boot, the way
DolphinQt's MainWindow does, where the tag's headless frontend takes -m and never plays it, and
it opts out of relaunch at login (below). audit-notes prints what the
audit of that tree found and what each finding became. build configures with CMAKE_OPTIONS into
ROOT/build and builds TARGETS with Ninja, links the tree's Data/Sys where the binary looks for it
and records the tree's commit and PATCH's sha256 in BUILT. boot writes CONFIG into
ROOT/user/Config and plays ISO headless on Metal under `caffeinate -i` and `nice -n 19`, on a
fresh console with a blank card in slot A. It reads the disc where it is and never copies it.

build and boot refuse a ROOT/src whose HEAD isn't PIN's commit, whose submodules at any depth
aren't at the commits it pins, or whose `git diff` isn't PATCH byte for byte. `git status` may
list PATCH's files as changed in the work tree and nothing else, so an untracked or ignored
file, a staged change or an edit anywhere else, submodules included, is refused. git runs
without the user's and the system's config, and a tree is refused when it could hide a change
from git all the same: an assume-unchanged or skip-worktree file, a non-empty info/attributes,
or a filter or attributes file in its local config. boot also refuses a build that BUILT
doesn't say came from that commit with that PATCH.

cmake and ninja run under `sandbox-exec` with build_profile, and Dolphin with run_profile. Both
deny all network, so a DNS lookup fails too. build_profile lets cmake and ninja write only
ROOT/build, and run_profile lets Dolphin write only ROOT/user, so neither can change src/ and
Dolphin can't change build/. Both may also write this user's temp and cache folders (USER_DIRS)
and /dev/null. Dolphin's profile allows one more thing, sending to a Unix socket inside
ROOT/user, which is the memory watcher's. --out needs no allowance, since boot itself moves the
dumps there once Dolphin has stopped. Every denial goes to the unified log with DENIED, but only
live: `log show` can miss them afterwards. To see what a run was refused, start
  log stream --style compact --predicate 'eventMessage CONTAINS "dolphin-ref" AND
    eventMessage CONTAINS "deny("'
(on one line) before it and stop it after. The second half leaves out lines that only name a
dolphin-ref path, such as tccd's. Each process's write to /dev/dtracehelper is among the
denials, which only stops it offering DTrace probes.

The Metal backend asks AppKit about the screen, which checks Dolphin in with the window server.
loginwindow then adds it to the apps it would reopen at login, in the snapshot it writes every
few seconds while it runs. A reopened Dolphin would start by its path with no arguments,
outside the sandbox and without -u, though with no arguments it only prints its help. PATCH
also has the headless frontend call NSApplication's disableRelaunchOnLogin, and loginwindow
then logs "app wantsToSuppressRelaunch" for it and leaves it out. -ApplePersistenceIgnoreState
YES after a -- didn't: loginwindow still listed the run.

boot counts frames by Dolphin's memory watcher, which sends one datagram over that socket at
the end of every video field. Each datagram lists the watched words that changed, so --watch
reads guest RAM every frame, a 32-bit word at an aligned hex address or the word holding a
kar_ram.json name at a fixed address. By default it's the word holding scene.major. Once N frames have ended it sends SIGINT to the run's
process group, which Dolphin takes as a request to shut down, and SIGKILL to whatever is left
30 s later.

--movie plays a .dtm (dtm.py makes one from a route) through -m, poll by poll, and turns on
Dolphin's determinism mode, which it has only for a movie or NetPlay. boot refuses a movie
whose game ID isn't the disc's, which would play on with its input ignored. Without one,
--press writes port 1's buttons, in a route's syntax (routes.parse_route) counted in
Dolphin's frames, into a pipe the pad reads (PIPE). Every press has to end by frame N. A press goes in as its frame's datagram comes, while Dolphin may already be a
frame or more on, so a press isn't frame-exact. A run takes one or the other.

With --dump Dolphin writes a PNG each time the game shows a new picture, so a field that repeats
the last picture adds none, and the dumps lag the frames a little when the run stops. --out DIR
gets ram.txt (one line per frame: the frame and each watched word), frames.txt (each dump's
sha256 and name), the dumps in DIR/frames/ and run.json (the command, the frames and the wall
time). Without --out the dumps are deleted when the run ends.

--disc picks how fast the disc reads (DISC): fast is Dolphin's "Speed up disc transfer rate",
which Dragoon's fast reads follow, and console a console's drive. The default, DEFAULT_DISC,
is the one Q4c compares with Dragoon (docs/dev/status.md, Dolphin reference).

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
import routes


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
# The one change to the tag: the headless frontend plays -m's movie. It may touch only files
# under PATCH_SCOPE.
PATCH = Path(__file__).resolve().parent / "dolphin-ref" / "headless-movie.patch"
PATCH_SCOPE = "Source/Core/DolphinNoGUI/"
# git diff with every option that could change its text spelled out, so a user's git config
# (colour, prefixes, abbreviated hashes) can't.
DIFF = ("diff", "--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "--full-index",
        "--src-prefix=a/", "--dst-prefix=b/")
GIT_ISOLATION = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
# git status, flagged so it lists every untracked and ignored file and every submodule change.
STATUS = ("status", "--porcelain", "--ignore-submodules=none", "--untracked-files=all",
          "--ignored")
# Local config keys that change what git status and git diff see of the work tree.
HIDING_KEYS = ("filter.", "core.attributesfile")
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
# What each denial the profiles make carries into the unified log, for `log stream` to catch. A
# deny rule without a message logs nothing.
DENIED = "dolphin-ref"
CAFFEINATE = ("/usr/bin/caffeinate", "-i")
NICE = ("/usr/bin/nice", "-n", "19")
BUILD_NICE = ("/usr/bin/nice", "-n", "10")
GRACE = 30.0  # seconds a stopped run gets to shut down before SIGKILL

# What the user folder's config holds. Online features are off, and the rest keeps a run
# deterministic: one CPU thread, a fixed clock, a blank card in slot A and no audio device.
# dtm.py's movies leave bSaveConfig off, so this config, not the movie, picks the CPU core (4,
# the ARM64 JIT), the DSP and the cards, and boot's --disc the disc speed.
CONFIG = {
    "Dolphin.ini": {
        "General": {"UseDiscordPresence": "False", "UseGameCovers": "False", "GDBPort": "-1",
                    "GDBSocket": ""},
        "Analytics": {"Enabled": "False", "PermissionAsked": "True", "ID": ""},
        "AutoUpdate": {"UpdateTrack": "", "HashOverride": ""},
        "Core": {"GFXBackend": "Metal", "CPUCore": "4", "CPUThread": "False", "DSPHLE": "True",
                 "SyncGPU": "False",
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
# --disc: how fast Dolphin reads the disc, as Dragoon's --disc names its speeds. fast is
# Dolphin's "Speed up disc transfer rate", which Dragoon's fast reads follow.
DISC = {"fast": "Dolphin.Core.FastDiscSpeed=True",
        "console": "Dolphin.Core.FastDiscSpeed=False"}
DEFAULT_DISC = "console"
GAME_ID = 6  # the bytes of the game ID at the start of a disc and at 4 in a .dtm
MOVIE_GAME_ID = 4
WORD = 4  # the memory watcher reads 32-bit words
SUN_PATH_MAX = 103  # sockaddr_un's 104 bytes on macOS, less the NUL
WATCHER = Path("MemoryWatcher")
PIPE = Path("Pipes") / "pad1"
# Slot A's card when MemcardAPath is empty, the card a movie plays on instead when there's none,
# and the console's SRAM. Each boot deletes all three, so the game starts on a fresh console with
# a blank card, as a route does.
FRESH = (Path("GC") / "MemoryCardA.USA.raw", Path("GC") / "MovieA.raw", Path("GC") / "SRAM.raw")
# What the pipe calls the route buttons it names differently.
PIPE_NAMES = {"UP": "D_UP", "DOWN": "D_DOWN", "LEFT": "D_LEFT", "RIGHT": "D_RIGHT"}

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


def git_env() -> dict[str, str]:
    """This environment with the user's and the system's git config left out (GIT_ISOLATION),
    so only the tree's own config, which check_tree vets, can change what git reports."""
    return {**os.environ, **GIT_ISOLATION}


def git(src: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(src), *args], capture_output=True, text=True,
                         env=git_env())
    if out.returncode:
        raise Refused(f"{src}: git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def submodule_drift(status: str) -> list[str]:
    """The lines of `git submodule status` for a submodule that isn't checked out at the commit
    the tree pins: `-` for one not checked out, `+` for another commit, `U` for a conflict."""
    return [line for line in status.splitlines() if line and line[0] != " "]


def patch_paths(patch: str, scope: str = PATCH_SCOPE) -> list[str]:
    """The files PATCH changes, refused unless each is one already there under SCOPE, changed in
    place with no rename, mode change, new or deleted file."""
    paths = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            a, _, b = line[len("diff --git "):].partition(" ")
            if not a.startswith("a/") or b != "b/" + a[2:]:
                raise Refused(f"patch: {line!r} isn't one file changed in place")
            paths.append(a[2:])
        elif line.startswith(("new file", "deleted file", "rename ", "copy ", "old mode",
                              "new mode", "similarity", "Binary files")):
            raise Refused(f"patch: {line!r} isn't a change in place")
    outside = [p for p in paths if not p.startswith(scope)]
    if outside:
        raise Refused(f"patch: {', '.join(outside)} outside {scope}")
    return paths


def check_unhidden(repo: Path) -> None:
    """Refuse REPO when its own git settings could hide a change from git status and git diff:
    an info/attributes file with anything in it, or a local filter or attributes file."""
    attributes = Path(git(repo, "rev-parse", "--git-path", "info/attributes").strip())
    if not attributes.is_absolute():
        attributes = repo / attributes
    if attributes.is_file() and attributes.read_text(encoding="utf-8", errors="replace").strip():
        raise Refused(f"{repo}: {attributes} isn't empty")
    keys = [key for key in git(repo, "config", "--local", "--list", "--name-only").splitlines()
            if key.lower().startswith(HIDING_KEYS)]
    if keys:
        raise Refused(f"{repo}: local git config sets {', '.join(keys)}")


def check_tree(src: Path, sha: str = PIN.sha, patch: Optional[str] = None) -> str:
    """SRC's HEAD, refused unless it's SHA, every submodule at any depth is at its pinned commit
    and the work tree differs from HEAD by PATCH (PATCH's text by default) and nothing else.
    git status may list only PATCH's files, as changed in the work tree, so an untracked or
    ignored file, a staged change or an edit in a submodule is refused. With PATCH "" the tree
    has to be clean. git runs without the user's and the system's config, and check_unhidden and
    ls-files -v refuse what could still hide a change from it: an assume-unchanged or
    skip-worktree file, info/attributes or a local filter."""
    if patch is None:
        patch = PATCH.read_text(encoding="utf-8")
    if not (src / ".git").exists():
        raise Refused(f"{src}: not a git checkout")
    head = git(src, "rev-parse", "HEAD").strip()
    if head != sha:
        raise Refused(f"{src}: HEAD is {head}, not the pinned {sha}")
    modules = git(src, "submodule", "status", "--recursive")
    drift = submodule_drift(modules)
    if drift:
        raise Refused(f"{src}: submodules off their pins: {'; '.join(drift)}")
    for repo in [src, *(src / line.split()[1] for line in modules.splitlines() if line)]:
        check_unhidden(repo)
    hidden = [line for line in git(src, "ls-files", "-v", "--recurse-submodules").splitlines()
              if not line.startswith("H ")]
    if hidden:
        raise Refused(f"{src}: files git status doesn't look at (assume-unchanged or "
                      f"skip-worktree): {'; '.join(hidden[:3])}")
    allowed = {f" M {path}" for path in patch_paths(patch)}
    changed = git(src, *STATUS).splitlines()
    other = [line for line in changed if line not in allowed]
    if other:
        more = f" and {len(other) - 3} more" if len(other) > 3 else ""
        raise Refused(f"{src}: changed or untracked: {'; '.join(other[:3])}{more}")
    if git(src, *DIFF) != patch:
        raise Refused(f"{src}: git diff isn't {PATCH.name}" if patch else
                      f"{src}: git diff isn't empty")
    return head


def patch_sha(patch: Optional[str] = None) -> str:
    text = PATCH.read_text(encoding="utf-8") if patch is None else patch
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_build(build: Path, head: str, patch: Optional[str] = None) -> None:
    """Refuse BUILD unless BUILT there says it was built from HEAD with PATCH (by its sha256)."""
    try:
        record = json.loads((build / BUILT).read_text(encoding="utf-8"))
        built, patched = record["src"], record.get("patch")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Refused(f"{build / BUILT}: no record of the commit it was built from") from None
    if built != head:
        raise Refused(f"{build}: built from {built}, not {head}")
    if patched != patch_sha(patch):
        raise Refused(f"{build}: built with patch {patched}, not {PATCH.name}")


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


def boot_command(root: Path, user: Path, iso: Path, dump: bool = False,
                 movie: Optional[Path] = None, disc: str = DEFAULT_DISC) -> list[str]:
    cmd = [str(root / "build" / NOGUI), "-u", str(user), "-p", "headless", "-v", "Metal"]
    for setting in (DISC[disc], *(DUMP_ON if dump else ())):
        cmd += ["-C", setting]
    if movie is not None:
        cmd += ["-m", str(movie)]
    cmd += ["-e", str(iso)]
    return [*CAFFEINATE, *NICE, *sandboxed(run_profile(root), cmd)]


def parse_presses(script: str, frames: int) -> dict[int, list[str]]:
    """The pipe commands to send after each frame, from port 1's buttons in a route's syntax
    (routes.parse_route): PRESS after the press's frame and RELEASE after frame + duration,
    which has to be by FRAMES. The pipe has no frame 0 and this takes no stick or other port."""
    try:
        presses = routes.parse_route(script)
    except ValueError as e:
        raise Refused(f"--press {e}") from None
    commands: dict[int, list[str]] = {}
    for p in presses:
        if p.port or p.stick != (0, 0) or p.at < 1:
            raise Refused(f"--press {p.at}: only port 1's buttons, from frame 1")
        if p.at + p.duration > frames:
            raise Refused(f"--press {p.at}: ends after frame {frames}, the run's last")
        for button in sorted(p.buttons, key=routes.BUTTONS.index):
            name = PIPE_NAMES.get(button, button)
            commands.setdefault(p.at, []).append(f"PRESS {name}")
            commands.setdefault(p.at + p.duration, []).append(f"RELEASE {name}")
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
    return watch_address("scene.major")


def word_of(name: str, table: Optional[dict] = None) -> int:
    """The aligned word holding kar_ram.json's NAME, a value at a fixed address."""
    entry = (table or kar_ram.load())[name]
    if entry.path:
        raise KeyError(f"{name} is behind a pointer")
    return entry.address & ~(WORD - 1)


def watch_address(text: str) -> str:
    """TEXT's word to watch: a name in kar_ram.json, for the aligned word holding it, or a hex
    address."""
    table = kar_ram.load()
    if text in table:
        try:
            return f"{word_of(text, table):08X}"
        except KeyError:
            raise argparse.ArgumentTypeError(f"{text!r} is behind a pointer") from None
    try:
        value = int(text, 16)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a hex address or a kar_ram.json "
                                         "name") from None
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
    print(f"{src}: {PIN.tag} at {PIN.sha}")
    return cmd_patch(root)


def apply_command(src: Path, patch: Path = PATCH) -> list[str]:
    return ["git", "-C", str(src), "apply", "--whitespace=nowarn", str(patch)]


def cmd_patch(root: Path, sha: str = PIN.sha, patch: Path = PATCH) -> int:
    """Apply PATCH to ROOT/src, clean at SHA, and check the tree is then exactly that."""
    src = root / "src"
    text = patch.read_text(encoding="utf-8")
    try:
        check_tree(src, sha, text)
        print(f"{src}: {patch.name} already applied")
        return 0
    except Refused:
        check_tree(src, sha, "")
    if subprocess.run(apply_command(src, patch), env=git_env()).returncode:
        print(f"{src}: git apply {patch.name} failed", file=sys.stderr)
        return 2
    check_tree(src, sha, text)
    print(f"{src}: {patch.name} applied")
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
    (build / BUILT).write_text(json.dumps({"src": head, "patch": patch_sha()}) + "\n",
                               encoding="utf-8")
    print(build / NOGUI)
    return 0


def cmd_boot(root: Path, args: argparse.Namespace) -> int:
    check_build(root / "build", check_tree(root / "src"))
    if not args.iso.is_file():
        raise Refused(f"{args.iso}: no such disc")
    if args.movie is not None:
        if args.press:
            raise Refused("--movie and --press: a run takes one or the other")
        if not args.movie.is_file():
            raise Refused(f"{args.movie}: no such movie")
        check_game(args.iso, args.movie)
    user = check_user(root)
    commands = parse_presses(args.press, args.frames)
    watched = args.watch or [default_watch()]
    write_config(user)
    pipe = Pipe(fresh_console(user, watched), commands)
    dumps = clear_dumps(user)
    movie = args.movie.resolve() if args.movie is not None else None
    cmd = boot_command(root, user, args.iso, args.dump, movie, args.disc)
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


def check_game(iso: Path, movie: Path) -> None:
    """Refuse a MOVIE made for another game than the disc ISO, which would play on with its
    input ignored."""
    with open(iso, "rb") as f:
        disc = f.read(GAME_ID)
    want = movie.read_bytes()[MOVIE_GAME_ID:MOVIE_GAME_ID + GAME_ID]
    if disc != want:
        raise Refused(f"{movie}: a movie for {want.decode('ascii', 'replace')}, not "
                      f"{disc.decode('ascii', 'replace')}, the disc's game")


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
    sub.add_parser("fetch", help="clone the pinned tag with its submodules and patch it")
    sub.add_parser("patch", help="apply the headless movie patch to a clean tree")
    sub.add_parser("audit-notes", help="print the audit's findings and decisions")
    sub.add_parser("build", help="configure and build offline")
    boot = sub.add_parser("boot", help="play a disc headless for N frames")
    boot.add_argument("iso", type=Path, metavar="ISO")
    boot.add_argument("--frames", type=frame_count, required=True, metavar="N")
    boot.add_argument("--movie", type=Path, metavar="DTM",
                      help="a .dtm to play from power-on, such as dtm.py makes")
    boot.add_argument("--press", default="", metavar="SCRIPT",
                      help="port 1's presses in the routes' syntax, by Dolphin's frames")
    boot.add_argument("--disc", choices=sorted(DISC), default=DEFAULT_DISC,
                      help=f"how fast the disc reads (default {DEFAULT_DISC})")
    boot.add_argument("--dump", action="store_true", help="dump every frame as a PNG")
    boot.add_argument("--watch", type=watch_address, action="append", metavar="ADDR",
                      help="a word of guest RAM to read every frame, by hex address or "
                           "kar_ram.json name (default: the word holding scene.major)")
    boot.add_argument("--out", type=Path, metavar="DIR")
    boot.add_argument("--timeout", type=float, default=60.0, metavar="SECONDS",
                      help="stop when no frame ends for this long (default 60)")
    args = ap.parse_args(argv)
    root = (args.root or default_root()).resolve()
    try:
        if args.command == "fetch":
            return cmd_fetch(root)
        if args.command == "patch":
            return cmd_patch(root)
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
