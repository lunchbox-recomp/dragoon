# Audio: the AX ucode

Kirby Air Ride boots Nintendo's AX ucode, build `07F88145`. gcn-recomp's AX HLE was written
for the 2001 build (`4E8A8B21`) and runs this one as if it were that. Every command the game
sends parses and the mixer runs, but routing to the effect buses is wrong and three features
of the newer build are missing. Line numbers are at gcn-recomp `67a7e30`.

## The ucode

| | |
|---|---|
| Fingerprint | `07F88145`, from `ucode_hash` (`runtime/hw/dsp_hle.cpp:39-44`), the same function as Dolphin's `HashEctor` |
| Size | 0x1F20 bytes (7,968), the value of `__AXDspCodeSize` in `analysis/symbols.txt` |
| Location | 0x804FEA00 in the DOL (`lbl_804FEA00` in `analysis/symbols.txt`), started at DSP address 0x0010 |
| AX library | `<< Dolphin SDK - AX release build: Mar 11 2003 11:19:39 (0x2301) >>` |
| Game build | Aug 18 2003, from the game's own boot banner |
| Dolphin | `AXUCode`. `07f88145` sits in `UCodes.cpp` beside F-Zero GX, Ikaruga, Soul Calibur 2 and Viewtiful Joe, with no Kirby comment |

It isn't a 2004 build, since the game itself was built in August 2003. Dolphin's AX HLE has
two behaviors on GameCube, one for `4E8A8B21` and one for every other build, so the year
doesn't matter for HLE purposes. This is the newer AX.

The hash was taken over the 0x1F20 bytes at 0x804FEA00 in a DOL extracted with
`recomp/extract_dol.py`. A 30-second run with `--hidden --no-input-log --log=dsp,ai` logs the
same at boot.

```
[DSP] boot ucode: iram mm=804FEA00 dsp=0000 len=1F20 dram=0 start=0010 hash=07F88145
```

## What the runtime does with it

- `dsp_hle.cpp:59-66` takes the first ucode a game boots that isn't JAudio as AX and
  remembers its IRAM length. The hash is logged (`:47-48`) and only checked against JAudio's
  (`:52`). Nothing tells one AX build from another.
- `ax.cpp` calls itself the 2001 variant (`:1`) and parses every list that way (`:279-343`).
- In the 30-second run the game sent 5,834 command lists, about 29 seconds of 5 ms frames.
  Each got `DCD10002` back (`dsp_hle.cpp:98-99`) and none logged `AX: unknown command`
  (`ax.cpp:337`).
- Audibility wasn't measured. The level counters (`GCN_AXSTATS`) and the capture (`GCN_WAV`)
  are environment switches, and the run set neither. Nothing in the path mutes it, though,
  since `ax.cpp:174-175` mixes every running voice into main left and right whatever its
  mixer control says.

## What the game sends

The list builder at 0x803EC9F8 (`salBuildCommandList` in `analysis/symbols.txt`) writes one
list per 5 ms frame. This is from reading the DOL, not from a trace.

| Command | Sent when | gcn-recomp |
|---|---|---|
| `00` setup | every frame | `ax.cpp:287`, `:249-257` |
| `07` main L and R from one buffer | stereo mode | `:296` |
| `11` the same with left inverted | surround mode | `:316` |
| `02` PB address, `03` process | every frame | `:289-290` |
| `04` AuxA, `05` AuxB | not DPL2 and that bus has a callback | `:291-294` |
| `13` send aux and mix, `10` AuxB L and R | DPL2 mode (`13` only with an AuxA callback) | `:318-327`, `:309-315` |
| `12` compressor | the compressor is on | skipped, `:317` |
| `0E` output, `0F` end | every frame | `:307-308` |

Every argument count in `ax.cpp` matches what the game writes, so no list is cut short. The
builder never writes `01`, `08`, `09` or `0A` to `0D`.

## The differences

Dolphin's AX HLE (`AX.cpp`, `AXVoice.h` and `AXStructs.h`, GPL, read for facts and not
copied) checks the ucode's hash in three places, each time `4E8A8B21` against everything
else. Those three places are the gap.

### Mixer control

The PB's mixer control word (word 6) has a different bit layout. The newer one gives every
bus its own enable bit and ramps by group. `ax.cpp:159-189` reads the 2001 layout.

| Bit | In `07F88145` | What `ax.cpp` does with it |
|---|---|---|
| `0001` | main L | sends to AuxA L and R |
| `0002` | main R | sends to AuxB L and R |
| `0004` | main S | main S, plus S on whichever aux bus is on |
| `0008` | ramps on main L, R and S | ramps on every bus |
| `0010` | AuxA L | reads the low three bits the DPL2 way and turns surround off |
| `0020` | AuxA R | nothing |
| `0040` | ramps on AuxA L and R | nothing |
| `0080` | AuxA S | nothing |
| `0100` | ramp on AuxA S | nothing |
| `0200` | AuxB L | nothing |
| `0400` | AuxB R | nothing |
| `0800` | ramps on AuxB L and R | nothing |
| `1000` | AuxB S | nothing |
| `2000` | ramp on AuxB S | nothing |
| none | main L and R mix only when `0001` and `0002` are set | main L and R always mix |

What that does to typical voices:

- A dry stereo voice (`0003`) also goes to both aux buses at whatever aux volumes its PB
  holds. At zero aux volume that's harmless.
- A voice with an AuxA reverb send (`0033`) sets `0010`, so the runtime takes the DPL2
  reading. Neither aux test passes there and the send is lost.
- Volume ramps come out as the game asked only when it ramps every bus or none.

Dolphin leaves bit `4000` unmapped, with a TODO saying it selects Dolby Pro Logic II.

### Low-pass filter

The newer PB has a one-pole low-pass filter at words 93 to 96 (on, `yn1`, `a0`, `b0`), which
moves the loop counter from word 93 to 97. When the filter is on, each sample after the
volume envelope becomes `(a0 * x + b0 * yn1) >> 15` clamped to 16 bits, and that result is
the next `yn1`. The runtime reads and writes 93 words (`ax.cpp:31`, `:40-45`) and drops
parameter updates past word 92 (`:204`). Whether the game turns the filter on isn't known
yet.

### Compressor

Command `12` carries a threshold, a release length in frames and the address of a gain table
in main RAM. If any main left or right sample in the frame is over the threshold, both
channels get an attack ramp from the table and the release count restarts. Otherwise a
release in progress steps down the table's release ramp, and surround is never touched. The
2001 build has no such command and `ax.cpp:317` skips its four words. The game sends it only
when its compressor is on, and this probe didn't check whether it is.

### Gaps every AX build has

These aren't version differences. They separate the runtime from Dolphin for `4E8A8B21`
too, and none of them silences a game.

| Gap | Where |
|---|---|
| Polyphase resampling (`src_type` 0) runs as linear interpolation. The real filter needs a 0x800-entry coefficient table from the DSP's ROM, which the runtime doesn't have | `ax.cpp:135-143` |
| Dolphin writes each bus's last mixed sample into the PB's depop words (41 to 49). The runtime doesn't | `ax.cpp:118-127` |
| Dolphin bumps the loop counter each time a stream loops. The runtime doesn't | `ax.cpp:99-111` |
| Dolphin reads the volume envelope as signed on GameCube. The runtime reads it unsigned, which differs only at `0x8000` and up | `ax.cpp:154-158` |
| The initial time delay block (words 27 to 33) is ignored. Dolphin ignores it too | none |

## Estimate

Generic runtime work in `runtime/hw/`, counted as lines added or changed:

| Change | Where | Lines |
|---|---|---|
| Hand the hash to AX and keep the 2001 behavior for `4E8A8B21` only | `dsp_hle.cpp:61-66`, `ax.h`, `ax.cpp:277` | 10 |
| Decode both mixer layouts into per-bus enable and ramp flags, then mix each of the nine buses by its own flags | `ax.cpp:118-127`, `:159-189` | 45 |
| PB layout with the filter and the loop counter | `ax.cpp:20-45`, `:204` | 15 |
| Low-pass filter | `ax.cpp:153-158` | 10 |
| Compressor | `ax.cpp:317` | 30 |
| **Version gap** | | **about 110** |
| Depop words, loop counter and signed envelope | `ax.cpp:99-189` | about 20 more |

Polyphase resampling isn't counted, since it needs ROM data before it needs code.

It fits upstream as a game-agnostic change. It keys on the ucode hash the way
`jaudio.cpp:68-69` keys on JAudio's, and it names no game. Metroid Prime boots `4E8A8B21`
(upstream commit `ddc05c0`), so a switch on that hash leaves it as it is. gcn-recomp doesn't
record which hash Metroid Prime 2 or Wave Race boots, and if either boots a newer build its
aux routing changes too.
