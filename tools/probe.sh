#!/bin/sh
# Run the game in a hidden window with nobody at the controls and dump frames.
# Usage: tools/probe.sh NAME SECONDS [INPUT_SCRIPT [DUMP_EVERY [SETTING ...]]]
#   NAME          frames, stdout, the memory card and any panic.txt go to build/probe/NAME/
#   SECONDS       wall-clock seconds before the game is stopped
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
#     --renderer=NAME  pick the renderer (omit for the default)
#     --scale=N     render at N times 640x480, 1 to 9 (default 1)
#     --bench       run build/dragoon_bench for SECONDS instead: no window and no frames,
#                   and stdout.txt holds its report of frames per second
# The game runs inside build/probe/NAME/, so a new NAME starts from a blank memory card and
# a NAME that's run again keeps the card its last run left behind.
set -e
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
renderer=
scale=--scale=1
# Keeps the GCN_ settings in "$@" and takes the rest out.
for s in "$@"; do
  shift
  case $s in
    GCN_*=*) set -- "$@" "$s" ;;
    --pads=[1-4]) pads=${s#--pads=} ;;
    --real-time) fast= ;;
    --bench) bench=1 ;;
    --renderer=gl) ;;
    --renderer=*) renderer=$s ;;
    --scale=[1-9]) scale=$s ;;
    *) echo "not a GCN_ setting, --pads=1 to 4, --real-time, --bench, --renderer=NAME or --scale=1 to 9: $s" >&2; exit 1 ;;
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
# --scale=1 renders at 640x480; the dumps are uncompressed, 1.2 MB each at that size.
env GCN_INPUT="$input" GCN_INPUT_LOG=1 "$@" "$root/build/dragoon" --hidden $fast --no-input-log \
  --pads="$pads" $scale $renderer --dump-dir="$out" --dump-every="$every" >"$out/stdout.txt" 2>&1 &
pid=$!
sleep "$seconds"
kill "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
echo "$out: $(ls "$out" | grep -c png) frames"
