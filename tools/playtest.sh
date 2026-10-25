#!/bin/sh
# Play the game with sound while it records a developer playtest session.
# Usage: tools/playtest.sh [SETTING ...]
#   SETTING       any number of these:
#     --pads=N      controllers plugged in on ports 1 to N, 1 to 4 (default 1)
#     --scale=N     render at N times 640x480, 1 to 9 (default the game's own, 2)
#     GCN_*=value   any of gcn-recomp's GCN_* diagnostics (its docs/diagnostics.md). One the
#                   session sets itself, like GCN_WAV, takes the value given here instead
#     --dry-run     print the session directory and the command, and run nothing
# The game opens in a window with sound, as it does for players, with GCN_SESSION set to
# build/playtest/<date>-<time>/. That directory gets what went to the sound device
# (out.wav), the mixer's blocks before it (aid.raw), the inputs, the frame times, the sound
# device's timing and session.json (gcn-recomp's docs/diagnostics.md lists them). All the
# game prints goes to the terminal and to stdout.txt there as well. Quit the game as usual
# or press Ctrl+C in this terminal, and playtest.sh prints the directory. The directory stays
# in build/, which git ignores. tools/session_report.py reads it there.
# Exits with the game's status, or 2 on a bad argument, when GCN_SESSION is already set or
# when build/dragoon isn't built.
set -e
case ${1:-} in -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac
root=$(cd "$(dirname "$0")/.." && pwd)
pads=
scale=
dry=
# Keeps the GCN_ settings in "$@" and takes the rest out.
for s in "$@"; do
  shift
  case $s in
    GCN_SESSION=*) echo "playtest.sh picks the session directory itself, so it takes no $s" >&2; exit 2 ;;
    GCN_*=*) set -- "$@" "$s" ;;
    --pads=[1-4]) pads=$s ;;
    --scale=[1-9]) scale=$s ;;
    --dry-run) dry=1 ;;
    *) echo "not a setting (see tools/playtest.sh --help): $s" >&2; exit 2 ;;
  esac
done
if [ -n "${GCN_SESSION:-}" ]; then
  echo "GCN_SESSION is set to $GCN_SESSION; playtest.sh picks the session directory itself" >&2
  exit 2
fi
game=$root/build/dragoon
if [ ! -x "$game" ]; then echo "no $game; build the game first" >&2; exit 2; fi
dir=$root/build/playtest/$(date +%Y%m%d-%H%M%S)
if [ -n "$dry" ]; then
  echo "session $dir"
  echo "in $root: env GCN_SESSION=$dir $* $game${pads:+ $pads}${scale:+ $scale} 2>&1 | tee $dir/stdout.txt"
  exit 0
fi
mkdir -p "$dir"
cd "$root"
(set -o pipefail) 2>/dev/null && set -o pipefail
# Ctrl+C reaches the game, which quits as if its window closed. tee ignores it and keeps
# writing until the game's last line, and so does this script, which prints the directory.
trap 'echo' INT
status=0
env GCN_SESSION="$dir" "$@" "$game" ${pads:+"$pads"} ${scale:+"$scale"} 2>&1 \
  | (trap '' INT && exec tee "$dir/stdout.txt") || status=$?
echo "session $dir"
echo "read it with: tools/session_report.py $dir"
exit "$status"
