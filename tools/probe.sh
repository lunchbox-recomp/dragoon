#!/bin/sh
# Run the game in a hidden window with nobody at the controls and dump frames.
# Usage: tools/probe.sh NAME SECONDS [INPUT_SCRIPT [DUMP_EVERY [GCN_SETTING=value ...]]]
#   NAME          frames, stdout, the memory card and any panic.txt go to build/probe/NAME/
#   SECONDS       wall-clock seconds before the game is stopped
#   INPUT_SCRIPT  presses in gcn-recomp's input_script.h syntax, e.g. "900:START:10", or a
#                 route file holding one (tests/routes/), whose # lines are comments
#   DUMP_EVERY    dump every Nth presented frame (default 60)
#   GCN_SETTING   any of gcn-recomp's GCN_* diagnostics (its docs/diagnostics.md), e.g.
#                 GCN_DRAWLOG=3600
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
for s in "$@"; do
  case $s in
    GCN_*=*) ;;
    *) echo "not a GCN_ setting: $s" >&2; exit 1 ;;
  esac
done
mkdir -p "$out"
cd "$out"
# --scale=1 renders at 640x480; the dumps are uncompressed, 1.2 MB each at that size.
env GCN_INPUT="$input" GCN_INPUT_LOG=1 "$@" "$root/build/dragoon" --hidden --fast --no-input-log \
  --scale=1 --dump-dir="$out" --dump-every="$every" >"$out/stdout.txt" 2>&1 &
pid=$!
sleep "$seconds"
kill "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
echo "$out: $(ls "$out" | grep -c png) frames"
