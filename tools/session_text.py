"""How session_report.py's result reads as text. It has no command line."""
from __future__ import annotations

from aid_blocks import plural


def _times(items: list[str], limit: int) -> list[str]:
    shown = [f"    {item}" for item in items[:limit]]
    if len(items) > limit:
        shown.append(f"    and {len(items) - limit} more")
    return shown


def _stats(name: str, s: dict, over: int) -> str:
    if not s.get("n"):
        return f"  {name:7} no frames"
    return (f"  {name:7} n {s['n']}  mean {s['mean']:.2f}  p95 {s['p95']:.2f}  p99 {s['p99']:.2f}"
            f"  worst {s['worst']:.2f} ms, {over} over 33 ms")


def session(s: dict) -> list[str]:
    lines = [f"session  {s['dir']}"]
    if s["seconds"] is not None:
        minutes, secs = divmod(round(s["seconds"]), 60)
        lines.append(f"  length  {s['seconds']:.1f} s ({minutes} min {secs} s), started {s['start']}")
    host = s["host"] or {}
    display = f"a {host['refresh_hz']:g} Hz display" if host.get("refresh_hz") else "display rate unknown"
    lines.append(f"  host    {host.get('os') or 'OS unknown'}, {host.get('cpu') or 'CPU unknown'}, {display}")
    lines.append(f"  engine  {s['engine_sha'] or 'unknown'}")
    if s["missing"]:
        lines.append(f"  missing or empty  {', '.join(s['missing'])}")
    if s["next_run"]:
        lines.append(f"  the game reset the console, which ended this run, and the next is in {s['next_run']}/")
    elif s["reset"]:
        lines.append("  the game shut the console down, which ended this run")
    return lines


def device(d: dict, limit: int) -> list[str]:
    dev = d["device"]
    if dev:
        period = 1000 * dev["buffer"] / dev["rate"] if dev["rate"] else 0
        lines = [f"device   {dev['driver']}, {dev['rate']} Hz, {dev['channels']} channels, "
                 f"{dev['buffer']} frames a period ({period:.2f} ms)"]
    else:
        lines = ["device   unknown: no [audio] device line, and none in session.json"]
    if cb := d["callbacks"]:
        lines.append(f"  callbacks  {cb['n']} at the last count, {cb['period_ms']:.2f} ms apart and "
                     f"{cb['worst_ms']:.1f} ms at most over the last 400")
    lines.append(f"  late       {len(d['late'])}")
    lines += _times([f"{x['at']:.3f} s, {x['gap_ms']:.1f} ms after the last" for x in d["late"]], limit)
    lines.append(f"  underruns  {d['short_pulls']} pulls short, in {len(d['underruns'])} stretches")
    lines += _times([f"{x['at']:.3f} s, {x['ms']:.1f} ms" for x in d["underruns"]], limit)
    lines.append(f"  cuts       {len(d['cuts'])}")
    lines += _times([f"{x['at']:.3f} s, {x['frames']} ring frames" for x in d["cuts"]], limit)
    return lines


def sound(s: dict) -> list[str]:
    lines = ["sound    stage   file     clicks/min  gaps/min  clipped/min"]
    for stage, name in (("device", "out.wav"), ("mixer", "aid.raw")):
        if r := s[stage]:
            pm = r["per_minute"]
            lines.append(f"         {stage:7} {name:8} {pm['clicks']:10.1f} {pm['gaps']:9.1f} {pm['clipped']:12.1f}")
        else:
            lines.append(f"         {stage:7} {name:8} missing")
    return lines


def stages(st: dict | None, limit: int) -> list[str]:
    if st is None:
        return ["stages   need out.wav, aid.raw and stdout.txt"]
    c = st["counts"]
    lines = [f"stages   of {sum(c.values())} device clicks: " + ", ".join(f"{k} {n}" for k, n in c.items())]
    lines += _times([f"{p['at']:.3f} s  {p['stage']}, {p['why']}" for p in st["clicks"]], limit)
    return lines


def noise(n: dict | None, limit: int) -> list[str]:
    if n is None:
        return ["noise    aid.raw missing"]
    if not n["stretches"]:
        return ["noise    none in aid.raw"]
    lines = [f"noise    {plural(len(n['stretches']), 'stretch', 'stretches')} in aid.raw, "
             f"{n['noisy_seconds']:.2f} s of {n['seconds']:.2f} s noise-like"]
    return lines + _times([f"{s['start']:.3f} s to {s['end']:.3f} s, {plural(s['blocks'], 'block')}"
                           for s in n["stretches"]], limit)


def pacing(p: dict | None) -> list[str]:
    if p is None:
        return ["pacing   no [ft] or [rt] lines in stdout.txt"]
    return [f"pacing   from frame {p['from']}", _stats("guest", p["guest"], p["guest_over"]),
            _stats("render", p["render"], p["render_over"])]


def shaders(p: dict | None, background: int) -> list[str]:
    compiled = (f"{p['compiled']} compiled on the render thread, {p['compiled_ms']:.0f} ms in all, the "
                f"longest {p['compiled_worst_ms']:.0f} ms" if p else "none counted on the render thread")
    return [f"shaders  {compiled}, and {background} built in the background"]


def crashes(lines: list[str], limit: int) -> list[str]:
    return ["crashes  none"] if not lines else [f"crashes  {len(lines)}"] + _times(lines, limit)


def system_log(s: dict | None) -> list[str]:
    if s is None:
        return []
    if "error" in s:
        return [f"system log  not read: {s['error']}"]
    by = ", ".join(f"{name} {n}" for name, n in s["by_process"].items())
    return [f"system log  {s['overloads']} Core Audio overloads from {s['start']} to {s['end']}"
            + (f" ({by})" if by else ""),
            f"  matched: {s['matched']}"]


def render(r: dict, limit: int) -> list[str]:
    return [*session(r["session"]), *device(r["device"], limit), *sound(r["sound"]), *stages(r["stages"], limit),
            *noise(r["noise"], limit), *pacing(r["pacing"]), *shaders(r["pacing"], r["shaders_background"]),
            *crashes(r["crashes"], limit), *system_log(r["system_log"])]
