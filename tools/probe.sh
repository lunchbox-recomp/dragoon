#!/bin/sh
# Run the game in a hidden window with nobody at the controls and dump frames.
# Usage: tools/probe.sh NAME SECONDS [INPUT_SCRIPT [DUMP_EVERY [SETTING ...]]]
#   NAME          frames, stdout, the memory card and any panic.txt go to build/probe/NAME/
#   SECONDS       wall-clock seconds before the game is stopped, a whole number. A game that
#                 exits sooner ends the run sooner
#   INPUT_SCRIPT  presses in gcn-recomp's input_script.h syntax, e.g. "900:START:10", or
#                 "2/900:A:10" for a press on port 2, or a route file holding one
#                 (tests/routes/), whose # lines are comments
#   DUMP_EVERY    dump every Nth presented frame (default 60)
#   SETTING       any number of these:
#     GCN_*=value   any of gcn-recomp's GCN_* diagnostics (its docs/diagnostics.md), e.g.
#                   GCN_DRAWLOG=3600. GCN_SESSION=DIR (from build/probe/NAME/ unless it's
#                   absolute) keeps the input log in DIR/inputs, which a run otherwise doesn't
#     DRAGOON_*=value  Dragoon's own switches in src/, e.g. DRAGOON_CENSUS=1 (the camera
#                   census, docs/dev/widescreen.md)
#     --pads=N      controllers plugged in on ports 1 to N, 1 to 4 (default 1)
#     --real-time   run at the game's own speed instead of as fast as it goes, for frame
#                   pacing (with GCN_FRAMETIME=1 or GCN_CLOCKLOG=1)
#     --scale=N     render at N times 640x480, 1 to 9 (default 1)
#     --bench       run build/dragoon_bench for SECONDS instead: no window and no frames,
#                   and stdout.txt holds its report of frames per second
#     --log=LIST    turn on gcn-recomp's log categories, e.g. --log=dsp,ai (the list is in
#                   its docs/diagnostics.md). Windowed runs only. dragoon_bench takes no
#                   --log, so --log with --bench exits 2. An unknown category stops the
#                   game at once; stdout.txt names it
#     --disc=PATH   the disc image to play. A game built from the engine kit has no disc
#                   of its own, so it needs one
#     --aspect=W:H  stretch the picture to aspect W:H, e.g. --aspect=16:9, or follow the
#                   window with --aspect=window (gcn-recomp's --aspect). Windowed runs
#                   only. The game refuses a bad one at once; stdout.txt says why
#     --output      also dump what the window shows, as output_NNNNN.png beside each
#                   frame (gcn-recomp's --dump-output). Windowed runs only
#     --replay=DIR  play back the input log in DIR (DIR/inputs.txt), as tools/replay_session.py
#                   does. A relative DIR is taken from where probe.sh was run, like --disc.
#                   Windowed runs only
#     --exit-after=N  quit once N frames have been presented. Windowed runs only
# The game runs inside build/probe/NAME/, so a new NAME starts from a blank memory card and
# a NAME that's run again keeps the card its last run left behind.
# Exits 0 once the run ends, 1 when the bench printed no report, 2 on a bad argument, a
# --disc that isn't a file, a --replay without an inputs.txt or when the game binary
# (build/dragoon, or build/dragoon_bench under --bench) isn't built.
set -e
case ${1:-} in -h|--help) sed -n '2,42p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac
if [ $# -lt 2 ]; then
  echo "usage: tools/probe.sh NAME SECONDS [INPUT_SCRIPT [DUMP_EVERY [SETTING ...]]] (--help for more)" >&2
  exit 2
fi
case $2 in ''|*[!0-9]*) echo "SECONDS is a whole number of seconds: $2" >&2; exit 2 ;; esac
root=$(cd "$(dirname "$0")/.." && pwd)
out=$root/build/probe/$1
seconds=$2
input=${3:-}
if [ -f "$input" ]; then input=$(grep -v '^#' "$input" | tr -d ' \r\n'); fi
every=${4:-60}
shift $(($# < 4 ? $# : 4))
pads=1
fast=--fast
bench=
scale=1
log=
disc=
aspect=
output=
replay=
exit_after=
no_input_log=--no-input-log
# Keeps the GCN_ and DRAGOON_ settings in "$@" and takes the rest out.
for s in "$@"; do
  shift
  case $s in
    GCN_SESSION=?*) no_input_log=; set -- "$@" "$s" ;;
    GCN_*=*|DRAGOON_*=*) set -- "$@" "$s" ;;
    --pads=[1-4]) pads=${s#--pads=} ;;
    --real-time) fast= ;;
    --bench) bench=1 ;;
    --scale=[1-9]) scale=${s#--scale=} ;;
    --log=?*) log=$s ;;
    --disc=?*) disc=${s#--disc=} ;;
    --aspect=?*) aspect=$s ;;
    --output) output=$s ;;
    --replay=?*) replay=${s#--replay=} ;;
    --exit-after=[1-9]*)
      case ${s#--exit-after=} in *[!0-9]*) echo "not a setting (see tools/probe.sh --help): $s" >&2; exit 2 ;; esac
      exit_after=$s ;;
    *) echo "not a setting (see tools/probe.sh --help): $s" >&2; exit 2 ;;
  esac
done
# The game runs in the run's directory, so a relative path is taken from here first.
case $disc in ''|/*) ;; *) disc=$PWD/$disc ;; esac
case $replay in ''|/*) ;; *) replay=$PWD/$replay ;; esac
if [ -n "$disc" ] && [ ! -f "$disc" ]; then echo "no disc image at $disc" >&2; exit 2; fi
if [ -n "$log" ] && [ -n "$bench" ]; then
  echo "$log needs a windowed run; dragoon_bench takes no --log" >&2
  exit 2
fi
if [ -n "$aspect$output" ] && [ -n "$bench" ]; then
  echo "${aspect:-$output} needs a windowed run; dragoon_bench has no window" >&2
  exit 2
fi
if [ -n "$replay$exit_after" ] && [ -n "$bench" ]; then
  windowed=--exit-after
  if [ -n "$replay" ]; then windowed=--replay; fi
  echo "$windowed needs a windowed run; dragoon_bench takes no $windowed" >&2
  exit 2
fi
if [ -n "$replay" ] && [ ! -f "$replay/inputs.txt" ]; then echo "no input log at $replay/inputs.txt" >&2; exit 2; fi
game=$root/build/dragoon
if [ -n "$bench" ]; then game=${game}_bench; fi
if [ ! -x "$game" ]; then echo "no $game; build the game first" >&2; exit 2; fi
mkdir -p "$out"
cd "$out"
if [ -n "$bench" ]; then
  env GCN_INPUT="$input" GCN_INPUT_LOG=1 "$@" "$game" --seconds="$seconds" \
    --pads="$pads" ${disc:+"$disc"} >"$out/stdout.txt" 2>&1 || true
  grep -A2 '^whole run' "$out/stdout.txt"
  exit 0
fi
# At --scale=1 a dump is 640x480 and 1.2 MB, uncompressed; N times each side at --scale=N.
env SDL_AUDIO_DRIVER=dummy GCN_INPUT="$input" GCN_INPUT_LOG=1 "$@" "$game" --hidden $fast $no_input_log \
  ${log:+"$log"} ${aspect:+"$aspect"} ${output:+--dump-output} ${replay:+--replay="$replay"} \
  ${exit_after:+"$exit_after"} --pads="$pads" --scale="$scale" \
  --dump-dir="$out" --dump-every="$every" ${disc:+"$disc"} >"$out/stdout.txt" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM
waited=0
while [ "$waited" -lt "$seconds" ] && kill -0 "$pid" 2>/dev/null; do
  sleep 1
  waited=$((waited + 1))
done
kill "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
echo "$out: $(ls "$out" | grep -c '^frame_.*png$') frames"
