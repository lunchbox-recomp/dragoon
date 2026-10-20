#!/bin/sh
# Run the game in a hidden window with nobody at the controls and dump frames.
# Usage: tools/probe.sh NAME SECONDS [INPUT_SCRIPT [DUMP_EVERY [SETTING ...]]]
#   NAME          frames, stdout, the memory card and any panic.txt go to build/probe/NAME/
#   SECONDS       wall-clock seconds before the game is stopped, a whole number
#   INPUT_SCRIPT  presses in gcn-recomp's input_script.h syntax, e.g. "900:START:10", or
#                 "2/900:A:10" for a press on port 2, or a route file holding one
#                 (tests/routes/), whose # lines are comments
#   DUMP_EVERY    dump every Nth presented frame (default 60)
#   SETTING       any number of these:
#     GCN_*=value   any of gcn-recomp's GCN_* diagnostics (its docs/diagnostics.md), e.g.
#                   GCN_DRAWLOG=3600
#     --pads=N      controllers plugged in on ports 1 to N, 1 to 4 (default 1)
#     --real-time   run at the game's own speed instead of as fast as it goes, for frame
#                   pacing (with GCN_FRAMETIME=1 or GCN_CLOCKLOG=1)
#     --renderer=gl  accepted and passed on as nothing, since GL is the only renderer
#     --scale=N     render at N times 640x480, 1 to 9 (default 1)
#     --bench       run build/dragoon_bench for SECONDS instead: no window and no frames,
#                   and stdout.txt holds its report of frames per second
# The game runs inside build/probe/NAME/, so a new NAME starts from a blank memory card and
# a NAME that's run again keeps the card its last run left behind.
# Exits 0 once the run ends, 2 on a bad argument.
set -e
case ${1:-} in -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac
if [ $# -lt 2 ]; then
  echo "usage: tools/probe.sh NAME SECONDS [INPUT_SCRIPT [DUMP_EVERY [SETTING ...]]] (--help for more)" >&2
  exit 2
fi
case $2 in ''|*[!0-9]*) echo "SECONDS is a whole number of seconds: $2" >&2; exit 2 ;; esac
root=$(cd "$(dirname "$0")/.." && pwd)
out=$root/build/probe/$1
seconds=$2
input=${3:-}
if [ -f "$input" ]; then input=$(grep -v '^#' "$input" | tr -d ' \n'); fi
every=${4:-60}
shift $(($# < 4 ? $# : 4))
pads=1
fast=--fast
bench=
scale=1
# Keeps the GCN_ settings in "$@" and takes the rest out.
for s in "$@"; do
  shift
  case $s in
    GCN_*=*) set -- "$@" "$s" ;;
    --pads=[1-4]) pads=${s#--pads=} ;;
    --real-time) fast= ;;
    --bench) bench=1 ;;
    --renderer=gl) ;;  # GL is the engine's only renderer, and it takes no --renderer flag
    --renderer=*) echo "the engine has only the GL renderer: $s" >&2; exit 2 ;;
    --scale=[1-9]) scale=${s#--scale=} ;;
    *) echo "not a setting (see tools/probe.sh --help): $s" >&2; exit 2 ;;
  esac
done
mkdir -p "$out"
cd "$out"
if [ -n "$bench" ]; then
  env GCN_INPUT="$input" GCN_INPUT_LOG=1 "$@" "$root/build/dragoon_bench" --seconds="$seconds" \
    --pads="$pads" >"$out/stdout.txt" 2>&1
  grep -A2 '^whole run' "$out/stdout.txt"
  exit 0
fi
# At --scale=1 a dump is 640x480 and 1.2 MB, uncompressed; N times each side at --scale=N.
env SDL_AUDIO_DRIVER=dummy GCN_INPUT="$input" GCN_INPUT_LOG=1 "$@" "$root/build/dragoon" --hidden $fast --no-input-log \
  --pads="$pads" --scale="$scale" --dump-dir="$out" --dump-every="$every" >"$out/stdout.txt" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null' EXIT
trap 'exit 130' INT TERM
sleep "$seconds"
kill "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
echo "$out: $(ls "$out" | grep -c png) frames"
