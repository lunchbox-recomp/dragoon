# Audio: the AX ucode

Kirby Air Ride boots Nintendo's AX ucode, build `07F88145`. gcn-recomp's AX HLE was written
for the 2001 build (`4E8A8B21`). At gcn-recomp `bf31b7b` it takes the ucode's hash and reads
the PB mixer control word with the 2001 layout for that hash only. Every other hash, this one
included, gets the later layout. The compressor command runs on the later layout. The newer
build's low-pass filter is still missing. Line numbers are at gcn-recomp `bf31b7b`.

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

- `dsp_hle.cpp:51-65` takes the first ucode a game boots that isn't JAudio as AX, remembers
  its IRAM length and passes its hash to `ax_init` (`:65`). The hash is logged (`:47-48`)
  and checked against JAudio's (`:52`).
- `ax_init` (`ax.cpp:416-426`) gives the 2001 hash the 2001 mixer control layout and every
  other hash the later one. The choice is made once, when AX starts. `--log=dsp` logs it
  (`AX: later mixer layout, ucode hash=07F88145`). `GCN_AX_LAYOUT=2001` or
  `GCN_AX_LAYOUT=later` overrides it, for comparing the two.
- `ax.cpp` mixes with the decoder the layout picks (`:293-295`), and runs command `12` on the
  later layout only (`:467-473`).
- In a 30-second run at an earlier gcn-recomp (`67a7e30`) the game sent 5,834 command lists,
  about 29 seconds of 5 ms frames. Each got `DCD10002` back (`dsp_hle.cpp:98-99`). The ten
  runs in `status.md` counted 484,400 lists and none had an unknown command.
- Audibility hasn't been judged by ear. `GCN_AXSTATS` counts levels and `GCN_WAV` captures
  the output, and both are environment switches. On the later layout a voice reaches main
  left only when its mixer control sets `0001` and main right only when it sets `0002`
  (`:247-255`, `:293-295`).
  `status.md` has the levels measured on the race route.

## What the game sends

The list builder at 0x803EC9F8 (`salBuildCommandList` in `analysis/symbols.txt`) writes one
list per 5 ms frame. This is from reading the DOL, not from a trace.

| Command | Sent when | gcn-recomp |
|---|---|---|
| `00` setup | every frame | `ax.cpp:437`, `:357-365` |
| `07` main L and R from one buffer | stereo mode | `:446` |
| `11` the same with left inverted | surround mode | `:466` |
| `02` PB address, `03` process | every frame | `:439-440` |
| `04` AuxA, `05` AuxB | not DPL2 and that bus has a callback | `:441-444` |
| `13` send aux and mix, `10` AuxB L and R | DPL2 mode (`13` only with an AuxA callback) | `:474-483`, `:459-465` |
| `12` compressor | the compressor is on | runs on the later layout (`:467-473`), skipped on the 2001 one |
| `0E` output, `0F` end | every frame | `:457`, `:458` |

Every argument count in `ax.cpp` matches what the game writes, so no list is cut short. The
builder never writes `01`, `08`, `09` or `0A` to `0D`. In the ten runs in `status.md`, `04`
and `05` came in every list (except two in the first window), and `12` in every list.

## The differences

Dolphin's AX HLE (`AX.cpp`, `AXVoice.h` and `AXStructs.h`, GPL, read for facts and not
copied) checks the ucode's hash in three places, each time `4E8A8B21` against everything
else. Those three places were the gap. The mixer control and the compressor are now handled
here. The low-pass filter isn't.

### Mixer control

The PB's mixer control word (word 6) has a different bit layout in the newer build. It gives
every bus its own enable bit and ramps by group. `ax.cpp:209-256` decodes the word into an
enable flag and a ramp flag for each of the nine buses, with one decoder for each layout,
and `:294-295` mixes each bus by its own flags.

| Bit | Later layout (default for `07F88145`, `decode_mixer_later`) | 2001 layout (`4E8A8B21`, or `GCN_AX_LAYOUT=2001`, `decode_mixer_2001`) |
|---|---|---|
| `0001` | main L | AuxA on (L and R) |
| `0002` | main R | AuxB on (L and R) |
| `0004` | main S | surround on: main S, AuxA S when AuxA is on, AuxB S when AuxB is on |
| `0008` | ramps on main L, R and S | ramps on every bus |
| `0010` | AuxA L | Dolby Pro Logic II reading: AuxB when `0002` and `0004` are clear, AuxA when the low three bits are `001`, with AuxA S on then, surround off |
| `0020` | AuxA R | nothing |
| `0040` | ramps on AuxA L and R | nothing |
| `0080` | AuxA S | nothing |
| `0100` | ramp on AuxA S | nothing |
| `0200` | AuxB L | nothing |
| `0400` | AuxB R | nothing |
| `0800` | ramps on AuxB L and R | nothing |
| `1000` | AuxB S | nothing |
| `2000` | ramp on AuxB S | nothing |
| none | a bus mixes only when its enable bit is set, main L and R included | main L and R always mix |

What that does to typical voices:

- On the later layout a dry stereo voice (`0003`) goes to main L and R only, and a voice with
  an AuxA reverb send (`0033`) goes to main L and R and to AuxA L and R. Ramps follow the
  groups.
- On the 2001 layout a `0003` voice also goes to both aux buses at whatever aux volumes its
  PB holds, and a `0033` voice sets `0010`, so the runtime takes the DPL2 reading and the
  send is lost. Before the layout was chosen by hash, this was what ran for `07F88145`.

On the race route the later layout took AuxA sound from 22 of 257 windows to 97 and AuxB from
none to 20 (`status.md`).

Dolphin leaves bit `4000` unmapped, with a TODO saying it selects Dolby Pro Logic II.

### Low-pass filter

The newer PB has a one-pole low-pass filter at words 93 to 96 (on, `yn1`, `a0`, `b0`), which
moves the loop counter from word 93 to 97. When the filter is on, each sample after the
volume envelope becomes `(a0 * x + b0 * yn1) >> 15` clamped to 16 bits, and that result is
the next `yn1`. The runtime still reads and writes 93 words (`ax.cpp:35`, `:44-49`) and drops
parameter updates past word 92 (`:310`). Whether the game turns the filter on isn't known
yet.

### Compressor

Command `12` carries a threshold, a release length in lists and the address of a gain table
in main RAM. The table holds 160-entry ramps of unsigned 16-bit gains with 0x8000 as 1.0:
11 attack ramps, then the release ramps. On the later layout `compress` (`ax.cpp:367-391`)
checks whether any main L or R sample in the list is over the threshold. If so, both
channels are scaled by the attack ramp numbered by the release count left from the earlier
lists (0 when none), and the count restarts at the release length. Otherwise, while the
count is nonzero, it steps down and both channels are scaled by release ramp 11 plus the
count. Surround is never touched. The count is kept from list to list and reset when AX
starts (`:419`). The 2001 build has no such command, so on that layout the four words are
skipped and counted as skipped (`:471`). The game sent it in every list of the ten runs in
`status.md`. The threshold and release it sends weren't logged.

### Gaps every AX build has

These aren't version differences. They separate the runtime from Dolphin for `4E8A8B21`
too, and none of them silences a game.

| Gap | Where |
|---|---|
| Polyphase resampling (`src_type` 0) runs as linear interpolation. The real filter needs a 0x800-entry coefficient table from the DSP's ROM, which the runtime doesn't have | `ax.cpp:268-283` |
| Dolphin writes each bus's last mixed sample into the PB's depop words (41 to 49). The runtime doesn't | `ax.cpp:198-207` |
| Dolphin bumps the loop counter each time a stream loops. The runtime doesn't | `ax.cpp:178-186` |
| Dolphin reads the volume envelope as signed on GameCube. The runtime reads it unsigned, which differs only at `0x8000` and up | `ax.cpp:287-291` |
| Resampler type 2 reads the last sample without interpolating | `ax.cpp:275` |
| The initial time delay block (words 27 to 33) is ignored. Dolphin ignores it too | none |

## What was done and what is left

Generic runtime work in `runtime/hw/`.

| Change | Where | State |
|---|---|---|
| Hand the hash to AX and keep the 2001 behavior for `4E8A8B21` only | `dsp_hle.cpp:65`, `ax.h`, `ax.cpp:412-426` | Done |
| Decode both mixer layouts into per-bus enable and ramp flags, then mix each of the nine buses by its own flags | `ax.cpp:209-256`, `:294-295` | Done |
| Compressor | `ax.cpp:367-391`, `:467-473` | Done |
| PB layout with the filter and the loop counter | `ax.cpp:22-45`, `:310` | Not done |
| Low-pass filter | after the volume envelope, `ax.cpp:287-291` | Not done |
| Depop words, loop counter and signed envelope | `ax.cpp:178-207`, `:287-291` | Not done |

Polyphase resampling isn't counted, since it needs ROM data before it needs code.

The change is generic. It keys on the ucode hash the way `jaudio.cpp:68-69` keys on
JAudio's, and it names no game. Metroid Prime boots `4E8A8B21` (upstream commit `ddc05c0`),
so a switch on that hash leaves it as it is. gcn-recomp doesn't record which hash Metroid
Prime 2 or Wave Race boots, and if either boots a newer build its aux routing changes too.
