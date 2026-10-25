#!/usr/bin/env python3
"""What happened to the sound and the pacing in a playtest session?

Usage: session_report.py DIR [--system-log] [--list N] [--json]

DIR is a session directory that tools/playtest.sh made (GCN_SESSION in gcn-recomp's
docs/diagnostics.md), and nothing outside it is read: session.json, out.wav (what went to the
sound device, at 48 kHz), aid.raw (the DMA's blocks before the audio ring, at 32 kHz) and
stdout.txt. It prints:

  session  its length (out.wav's), start, host, display and engine commit
  device   the sound device's driver, rate, channels and buffer, its callbacks, the ones that
           came late, the pulls the ring couldn't fill and the ring's cuts
  sound    clicks, gaps and clipped runs a minute in out.wav (the device stage) and aid.raw
           (the mixer stage), as audio_clicks.py finds them
  stages   each device-stage click put down to the mixer, the ring, the device or nothing,
           as click_stages.py explains
  pacing   the guest's interval between frames and the renderer's time from frame 300 (mean,
           p95, p99, worst) and the frames over 33 ms, as frametime.py reads them
  shaders  the programs compiled while it ran, on the render thread and in the background
  crashes  every panic, FATAL or FAULT line

--system-log also counts the Core Audio overloads macOS logged over the session's wall-clock
window, through a read-only `log show` (core_audio_log.py says how they're matched).
--list N caps the times printed for each list (default 10). --json prints the whole result.

A run-N directory inside a session, made when the game reset the console and relaunched,
reads its own part of the session's stdout.txt.

Exits 0 once it has read the session, 2 on a bad argument or a directory without a readable
session.json. A section whose file is missing or empty says so, and the rest still print.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import audio_clicks
import click_stages
import core_audio_log
import frametime
import session_log
import session_text
from aid_blocks import RATE as DMA_RATE  # aid.raw's rate

PACING_FROM = 300     # the first frame the pacing counts, past boot
OVER_MS = 33.0        # a frame this long missed two refreshes at 60 Hz
LOG_MARGIN_S = 5      # how far past out.wav's end the system log is read


def read_session(directory: Path) -> dict:
    path = directory / "session.json"
    try:
        return json.loads(path.read_text())
    except OSError as e:
        raise ValueError(f"{path}: {e.strerror}; is {directory} a session directory?") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: not JSON ({e})") from None


def stage_sound(path: Path, raw_rate: int | None) -> audio_clicks.Report | None:
    """The recording's clicks, gaps and clipping, or None when it's missing or has no sound,
    as when the game stopped before the device first played."""
    if not path.is_file():
        return None
    try:
        rec = audio_clicks.read_raw(path, raw_rate) if raw_rate else audio_clicks.read_wav(path)
    except ValueError:
        return None
    return audio_clicks.analyse_long(rec)


def sound_summary(r: audio_clicks.Report) -> dict:
    minutes = r.seconds / 60
    return {"seconds": r.seconds, "rate": r.rate, "clicks": len(r.clicks), "gaps": len(r.gaps),
            "clipped": len(r.clipped),
            "per_minute": {k: n / minutes for k, n in
                           (("clicks", len(r.clicks)), ("gaps", len(r.gaps)), ("clipped", len(r.clipped)))},
            "click_times": [c.at for c in r.clicks], "gap_times": [g.at for g in r.gaps]}


def pacing(lines: list[str]) -> dict | None:
    frames = frametime.parse(lines)
    if not frames:
        return None
    later = [f for n, f in frames.items() if n >= PACING_FROM]
    compiles = [ms for f in frames.values() for ms in f.compiles]
    return {"from": PACING_FROM, **frametime.summary(frames, PACING_FROM),
            "guest_over": sum(f.guest_ms is not None and f.guest_ms > OVER_MS for f in later),
            "render_over": len(frametime.slow(frames, PACING_FROM, OVER_MS)),
            "compiled": len(compiles), "compiled_ms": sum(compiles), "compiled_worst_ms": max(compiles, default=0.0)}


def system_log(start_epoch: int, seconds: float, run=subprocess.run) -> dict:
    start = datetime.fromtimestamp(start_epoch)
    end = start + timedelta(seconds=seconds + LOG_MARGIN_S)
    cmd = core_audio_log.command(start, end)
    result = {"command": cmd, "start": start.isoformat(" ", "seconds"), "end": end.isoformat(" ", "seconds"),
              "matched": f"subsystem {core_audio_log.SUBSYSTEM}, '{core_audio_log.WORD}' in the message"}
    try:
        out = run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {**result, "error": str(e)}
    if out.returncode != 0:
        return {**result, "error": f"log show exited {out.returncode}: {out.stderr.strip()}"}
    found = core_audio_log.overloads(out.stdout)
    return {**result, "overloads": sum(found.values()), "by_process": dict(found)}


def build(directory: Path, with_system_log: bool, run=subprocess.run) -> dict:
    """Everything the report says, as one dict."""
    info = read_session(directory)
    device_sound = stage_sound(directory / "out.wav", None)
    mixer_sound = stage_sound(directory / "aid.raw", DMA_RATE)
    found = session_log.run_lines(directory)
    lines, log_path = found if found else ([], None)
    missing = [name for name, there in (("out.wav", device_sound), ("aid.raw", mixer_sound), ("stdout.txt", found))
               if not there]
    log = session_log.parse(lines)
    seconds = device_sound.seconds if device_sound else mixer_sound.seconds if mixer_sound else None
    device = asdict(log.device) if log.device else info.get("audio_device")
    spans = click_stages.silent_spans(log.underruns)
    out_rate = device_sound.rate if device_sound else 48000
    result = {
        "session": {"dir": str(directory), "seconds": seconds, "start": info.get("start"),
                    "host": info.get("host"), "engine_sha": info.get("engine_sha"),
                    "command_line": info.get("command_line"), "log": str(log_path) if log_path else None,
                    "reset": log.reset, "missing": missing},
        "device": {"device": device, "callbacks": asdict(log.callbacks) if log.callbacks else None,
                   "late": [{"at": f / out_rate, "gap_ms": g} for f, g in log.late],
                   "short_pulls": len(log.underruns),
                   "underruns": [{"at": s / out_rate, "ms": (e - s) * 1000 / out_rate} for s, e in spans],
                   "cuts": [{"at": f / out_rate, "frames": n} for f, n in log.cuts]},
        "sound": {"device": sound_summary(device_sound) if device_sound else None,
                  "mixer": sound_summary(mixer_sound) if mixer_sound else None},
        "stages": None,
        "pacing": pacing(lines),
        "shaders_background": len(log.background_ms),
        "crashes": log.fatal,
        "system_log": None,
    }
    if device_sound and mixer_sound and lines:
        placed = click_stages.place([c.at for c in device_sound.clicks], [c.at for c in mixer_sound.clicks],
                                    log, device_sound.rate, DMA_RATE)
        result["stages"] = {"counts": click_stages.counts(placed), "clicks": [asdict(p) for p in placed]}
    if with_system_log:
        if seconds is None or "start_epoch" not in info:
            result["system_log"] = {"error": "needs session.json's start_epoch and a recording's length"}
        else:
            result["system_log"] = system_log(info["start_epoch"], seconds, run)
    return result


def main(argv: list[str], run=subprocess.run) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--system-log", action="store_true")
    ap.add_argument("--list", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.list < 0:
        ap.error("--list can't be negative")
    try:
        result = build(args.dir, args.system_log, run)
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    for name in result["session"]["missing"]:
        print(f"{args.dir / name}: missing or empty, so the sections that read it are left out", file=sys.stderr)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        print("\n".join(session_text.render(result, args.list)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
