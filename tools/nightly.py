#!/usr/bin/env python3
"""Run every player check on the real game, one game at a time, and say what changed since last time.

Usage: nightly.py run [--only STEP ...] [--routes ROUTE ...] [--build DIR] [--last REPORT]
                      [--soak-minutes M] [--menu-runs N] [--seed N] [--scheduled]
       nightly.py install-agent [--dir DIR] [--clone CLONE] [--print]
       nightly.py uninstall-agent [--dir DIR]

run plays the steps in order, or the --only ones (nightly_steps.py says what each plays and
checks): frames, dolphin, audio, shaders, timed and soak. Each step runs as a child process of
its own, `nightly.py step NAME`, at nice 19 but timed, which runs at the default priority. The
whole run
holds `caffeinate -i`, so the Mac doesn't sleep while it plays. Before every game process the
step asks `pmset -g batt` for AC power. On battery the step stops, the report is written with it
marked skipped-battery and the steps after it not-run, and run exits 2.

The report goes in build/nightly/YYYY-MM-DD-HHMM/: summary.txt, one screen, and report.json, the
same for tools (nightly_report.py says what's in them). A check is compared with the same check
in --last, a report.json or its directory, which defaults to the newest earlier report in
build/nightly/. One that doesn't read as a report is said so in the summary's head and nothing
is compared. Dumps are kept only for checks that failed, under dumps/, dolphin/, audio/,
shaders/ and logs/, and dolphin/ also keeps an improved checkpoint's. The dolphin step keeps
Dolphin's runs in build/nightly/dolphin-cache/ between nights. Nothing in tests/ or docs/ is
written.

A run holds build/nightly/run.lock and doesn't start while another holds it or a dragoon or
dragoon_bench process runs (nightly_start.py). --scheduled is launchd's run: it's skipped
outside 01:00 to 06:00, and otherwise fast-forwards this clone to origin/main, builds dragoon
and dragoon_bench and runs again as that code, refusing a tree with changes or off origin/main.

--routes plays only those manifest routes in frames, dolphin, audio and shaders. --build DIR
plays the game in DIR (DIR/dragoon, and DIR/dragoon_bench for audio) through probe.sh's --bin,
for a tree with no
build of its own. --soak-minutes sets each of the four soaks' wall time (30 by default),
--menu-runs the menu's opens (21 by default), and --seed the soaks' seed (by default the run's
date and time, so a night's soaks differ from the last's and the report names the seed).

install-agent writes the launchd job that runs CLONE's `nightly.py run --scheduled` at 01:30
daily into DIR, ~/Library/LaunchAgents by default, and prints it. CLONE is the dragoon-nightly
clone beside this one by default. It doesn't load the job, and --print only prints it.
uninstall-agent removes it.

Exits 0 when every check but a known issue passed and nothing got slower, and when a launchd run
is skipped outside its hours. 1 when a check failed or a timed number got slower, 2 on a bad
argument, a step that couldn't run, a run that refused to start or a stop on battery.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import bot_record
import nightly_agent
import nightly_report
import nightly_start
import nightly_steps
import power
from nightly_report import NOT_RUN, SKIPPED_BATTERY, Check, from_json, to_json

ROOT = Path(__file__).resolve().parents[1]
NIGHTLY = ROOT / "build" / "nightly"
STOPPED_ON_BATTERY = 3  # a step child's exit when it stopped on battery
NICE = ["nice", "-n", "19"]


def new_run_dir(nightly: Path, now: float) -> Path:
    stamp = time.strftime("%Y-%m-%d-%H%M", time.localtime(now))
    out, n = nightly / stamp, 2
    while out.exists():
        out, n = nightly / f"{stamp}-{n}", n + 1
    return out


def default_seed(now: float) -> int:
    return int(time.strftime("%y%m%d%H%M", time.localtime(now))) % 1_000_000


def step_args(args: argparse.Namespace) -> list[str]:
    out = ["--soak-minutes", f"{args.soak_minutes:g}", "--menu-runs", str(args.menu_runs), "--seed", str(args.seed)]
    if args.routes:
        out += ["--routes", *args.routes]
    if args.build:
        out += ["--build", str(args.build)]
    if args.pmset:
        out += ["--pmset", args.pmset]
    return out


def child(step: str, report: Path, extra: list[str]) -> int:
    """Run STEP as a child process, at nice 19 unless it's timed, its output in work/STEP.log."""
    work = report / "work"
    work.mkdir(parents=True, exist_ok=True)
    cmd = [*([] if step in nightly_steps.TIMED else NICE), sys.executable, str(Path(__file__).resolve()),
           "step", step, "--dir", str(report), *extra]
    with (work / f"{step}.log").open("w") as log:
        return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode


def step_result(report: Path, step: str) -> dict:
    path = report / "work" / f"{step}.json"
    if not path.is_file():
        return {"checks": [], "stopped": None}
    return json.loads(path.read_text())


def run_steps(steps: list[str], report: Path, require_ac: Callable[[], None],
              launch: Callable[[str], int]) -> tuple[list[Check], dict, Optional[str]]:
    """Play STEPS in order through LAUNCH, each after REQUIRE_AC. Returns the checks, each step's
    time and load, and why the run stopped short, None when it didn't."""
    checks: list[Check] = []
    steps_info: dict = {}
    stopped = None
    for i, step in enumerate(steps):
        began, load = time.monotonic(), os.getloadavg()[0]
        try:
            require_ac()
            code = launch(step)
        except (power.OnBattery, ValueError) as e:  # a pmset that can't say is no AC either
            code, why = STOPPED_ON_BATTERY, str(e)
        else:
            why = None
        result = step_result(report, step)
        checks += from_json(result["checks"])
        steps_info[step] = {"seconds": round(time.monotonic() - began), "load": [load, os.getloadavg()[0]],
                            "exit": code, "built": result.get("built")}
        if code == STOPPED_ON_BATTERY:
            why = why or result.get("stopped") or "on battery"
            checks.append(Check(step, step, SKIPPED_BATTERY, detail=f"before a game process: {why}"))
            checks += [Check(rest, rest, NOT_RUN, detail="after the stop on battery") for rest in steps[i + 1:]]
            stopped = f"{step} stopped on battery: {why}"
            break
        if code != 0:
            checks.append(Check(step, step, nightly_report.FAIL, kind="couldn't run",
                                detail=result.get("stopped") or f"the step exited {code}, see work/{step}.log"))
    return checks, steps_info, stopped


def prune(report: Path, checks: list[Check], kept: set[str]) -> None:
    """Delete the logs under logs/ no failed or regressed check points at, and work/."""
    wanted = {c.dump for c in checks if c.status == nightly_report.FAIL or c.id in kept}
    wanted |= {p.dump for c in checks if c.status == nightly_report.FAIL or c.id in kept for p in c.problems}
    logs = report / "logs"
    if logs.is_dir():
        for f in logs.iterdir():
            if str(f.relative_to(report)) not in wanted:
                f.unlink()
        if not any(logs.iterdir()):
            logs.rmdir()
    if (report / "work").exists():
        shutil.rmtree(report / "work")


def minutes(seconds: float) -> str:
    m = round(seconds / 60)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


def finish(report: Path, checks: list[Check], steps_info: dict, stopped: Optional[str], began: float,
           loads: list[float], last_path: Optional[Path], root: Path, say: Callable[[str], None] = print,
           last_note: Optional[str] = None) -> int:
    """Write the report. LAST_PATH is a report nightly_report.readable passed, and LAST_NOTE why
    there's none when one was given but couldn't be read."""
    last = nightly_report.read(last_path) if last_path else None
    found = nightly_report.changes(checks, last)
    regressions = sorted(k for k, v in found.items() if v != ["same"])
    failed = nightly_report.failing(checks)
    commits = bot_record.commits(root)
    # What the game says it was built from wins over the checkout's HEAD, which may not be it.
    built = next((i["built"] for i in steps_info.values() if i.get("built")), None)
    wall = time.time() - began
    result = "stopped on battery" if stopped else "pass" if not failed and not regressions else "fail"
    engine = (f"built {built[:7]}{'-dirty' if built.endswith('-dirty') else ''}" if built
              else (commits["engine"] or "?")[:7])
    head = [f"Dragoon nightly {report.name}, Dragoon {(commits['dragoon'] or '?')[:7]}, gcn-recomp "
            f"{engine}, {minutes(wall)}, load {loads[0]:.1f} to {loads[1]:.1f}",
            f"Result: {result}, {len(regressions)} regressions, {len(failed)} failing, "
            f"{sum(c.status == nightly_report.PASS for c in checks)} passing. Last report: "
            f"{last_path.parent.name if last_path else 'none'}",
            "Steps: " + ", ".join(f"{s} {minutes(i['seconds'])}" for s, i in steps_info.items())]
    if last_note:
        head.append(f"Last: {last_note}")
    if stopped:
        head.append(f"Stopped: {stopped}")
    info = {"started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(began)), "wall_seconds": round(wall),
            "load": loads, "commits": {**commits, "engine_built": built}, "result": result, "stopped": stopped,
            "steps": steps_info, "last": str(last_path) if last_path else None, "last_note": last_note}
    text = nightly_report.write(report, head, info, checks, last)
    prune(report, checks, set(regressions))
    say(text.rstrip("\n"))
    say(f"report: {report}")
    if stopped:
        return 2
    return 0 if result == "pass" else 1


def may_start(args: argparse.Namespace, argv: list[str]) -> int:
    """The lock's descriptor once nothing stops the run. A launchd run (--scheduled) not yet
    --updated fast-forwards and builds this clone, then runs again as the new code."""
    lock = nightly_start.take_lock(NIGHTLY)
    try:
        running = nightly_start.games_running(args.pgrep.split() if args.pgrep else ("pgrep", "-x"))
        if running:
            raise nightly_start.Refused(f"{' and '.join(running)} is running, and a run plays one game at a time")
        if args.scheduled and not args.updated:
            nightly_start.update(ROOT)
            os.close(lock)
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *argv, "--updated"])
        if args.scheduled:
            nightly_start.checked(ROOT)
    except nightly_start.Refused:
        os.close(lock)
        raise
    return lock


def run(args: argparse.Namespace, argv: list[str]) -> int:
    began = time.time()
    if args.scheduled and not nightly_start.in_window(time.localtime(began).tm_hour):
        print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(began))}: skipped, since a launchd run starts "
              f"from {nightly_start.WINDOW[0]:02d}:00 to {nightly_start.WINDOW[1]:02d}:00", flush=True)
        return 0
    try:
        lock = may_start(args, argv)
    except nightly_start.Refused as e:
        print(f"nightly: not started: {e}", file=sys.stderr, flush=True)
        return 2
    if args.seed is None:
        args.seed = default_seed(began)
    report = new_run_dir(NIGHTLY, began)
    last_path, last_note = nightly_report.readable(args.last or nightly_report.last_report(NIGHTLY, report))
    report.mkdir(parents=True)
    awake = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    pmset = args.pmset.split() if args.pmset else power.PMSET
    try:
        loads = [os.getloadavg()[0]]
        checks, steps_info, stopped = run_steps(args.only or list(nightly_steps.STEPS), report,
                                                lambda: power.require_ac(pmset),
                                                lambda step: child(step, report, step_args(args)))
        loads.append(os.getloadavg()[0])
        return finish(report, checks, steps_info, stopped, began, loads, last_path, ROOT, last_note=last_note)
    finally:
        awake.terminate()
        awake.wait()
        os.close(lock)


def step(args: argparse.Namespace) -> int:
    """One step, in the run's child process."""
    pmset = args.pmset.split() if args.pmset else power.PMSET
    ctx = nightly_steps.Context(ROOT, args.dir, before=lambda: power.require_ac(pmset), routes=args.routes or [],
                                build=args.build, soak_minutes=args.soak_minutes, menu_runs=args.menu_runs,
                                seed=args.seed, say=lambda text: print(text, flush=True))
    return play_step(args.name, ctx)


def play_step(name: str, ctx: nightly_steps.Context) -> int:
    """Play step NAME in CTX. Its checks go to work/NAME.json as each is made, with why it
    stopped when it did. Returns the step child's exit code."""
    out = ctx.work / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    checks: list[Check] = []

    def save(stopped: Optional[str] = None) -> None:
        out.write_text(json.dumps({"checks": to_json(checks), "stopped": stopped, "built": ctx.built}, indent=1))

    def done(c: Check) -> None:
        checks.append(c)
        ctx.say(nightly_report.line(c, []))
        save()

    save()
    try:
        nightly_steps.STEPS[name](ctx, done)
    except power.OnBattery as e:
        save(str(e))
        return STOPPED_ON_BATTERY
    except (OSError, ValueError) as e:
        save(f"{type(e).__name__}: {e}")
        print(e, file=sys.stderr)
        return 2
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("run", "step"):
        p = sub.add_parser(name)
        if name == "step":
            p.add_argument("name", choices=list(nightly_steps.STEPS))
            p.add_argument("--dir", type=Path, required=True)
        else:
            p.add_argument("--only", nargs="+", choices=list(nightly_steps.STEPS), metavar="STEP")
            p.add_argument("--last", type=Path, metavar="REPORT")
            p.add_argument("--scheduled", action="store_true")
            p.add_argument("--updated", action="store_true", help=argparse.SUPPRESS)  # after --scheduled's update
            p.add_argument("--pgrep", help=argparse.SUPPRESS)  # a stand-in for pgrep -x, for a test
        p.add_argument("--routes", nargs="+", metavar="ROUTE")
        p.add_argument("--build", type=Path, metavar="DIR")
        p.add_argument("--soak-minutes", type=float, default=nightly_steps.SOAK_MINUTES, metavar="M")
        p.add_argument("--menu-runs", type=int, default=nightly_steps.timed_bars.MENU_RUNS, metavar="N")
        p.add_argument("--seed", type=int, metavar="N")
        p.add_argument("--pmset", help=argparse.SUPPRESS)  # a stand-in for pmset -g batt, for a test
    for name in ("install-agent", "uninstall-agent"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, default=nightly_agent.AGENTS)
        if name == "install-agent":
            p.add_argument("--clone", type=Path, default=nightly_agent.CLONE)
            p.add_argument("--print", action="store_true", dest="print_only")
    args = ap.parse_args(argv)
    if args.command == "install-agent":
        job = nightly_agent.plist(args.clone.resolve())
        print(job.decode(), end="")
        if args.print_only:
            return 0
        target = nightly_agent.install(job, args.dir)
        print(f"wrote {target}, which isn't loaded. launchctl bootstrap gui/{os.getuid()} {target} loads it")
        return 0
    if args.command == "uninstall-agent":
        print(f"removed {nightly_agent.path(args.dir)}" if nightly_agent.uninstall(args.dir)
              else f"no {nightly_agent.path(args.dir)}")
        return 0
    if args.soak_minutes <= 0 or args.menu_runs < 1:
        ap.error("--soak-minutes is above 0 and --menu-runs 1 or more")
    if args.build is not None:
        args.build = args.build.resolve()
        if not (args.build / "dragoon").is_file():
            ap.error(f"--build: no {args.build / 'dragoon'}")
    if args.command == "step":
        if args.seed is None:
            ap.error("step takes --seed")
        return step(args)
    return run(args, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
