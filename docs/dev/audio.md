# Audio: the AX ucode

Kirby Air Ride boots Nintendo's AX ucode, build `07F88145`. gcn-recomp's AX HLE was written
for the 2001 build (`4E8A8B21`) and keeps that build's mixer control layout for its hash alone,
so every other hash, this one included, gets the later layout and the compressor command. The
newer build's low-pass filter isn't applied.

Files cited by name alone, such as `ax.cpp`, are gcn-recomp's, under `runtime/`. Their line
numbers are at the pin `95e1c6b`.

## The ucode

| | |
|---|---|
| Fingerprint | `07F88145`, from `ucode_hash` (`runtime/hw/dsp_hle.cpp:39-44`), the same function as Dolphin's `HashEctor` |
| Size | 0x1F20 bytes (7,968), the value of `__AXDspCodeSize` in `analysis/symbols.txt` |
| Location | 0x804FEA00 in the DOL (`lbl_804FEA00` in `analysis/symbols.txt`), started at DSP address 0x0010 |
| AX library | `<< Dolphin SDK - AX release build: Mar 11 2003 11:19:39 (0x2301) >>` |
| Game build | Aug 18 2003, from the game's own boot banner |
| Dolphin | `AXUCode`. `07f88145` sits in `UCodes.cpp` beside F-Zero GX, Ikaruga, Soul Calibur 2 and Viewtiful Joe, with no Kirby comment |

Dolphin's AX HLE treats `4E8A8B21` one way and every other GameCube build another, so this
one gets the newer behavior.

The hash was taken over the 0x1F20 bytes at 0x804FEA00 in a DOL extracted with
`gcn-recomp/recomp/extract_dol.py`. A 30-second run with `--hidden --no-input-log --log=dsp,ai`
logs the same at boot.

```
[DSP] boot ucode: iram mm=804FEA00 dsp=0000 len=1F20 dram=0 start=0010 hash=07F88145
```

## What the runtime does with it

- `dsp_hle.cpp:51-65` takes the first ucode a game boots that isn't JAudio as AX, remembers
  its IRAM length and passes its hash to `ax_init` (`:65`). The hash is logged (`:47-48`)
  and checked against JAudio's (`:52`).
- `ax_init` (`ax.cpp:617-632`) runs when AX starts and gives the 2001 hash the 2001 mixer
  control layout and every other hash the later one. `--log=dsp` logs the choice
  (`AX: later mixer layout, ucode hash=07F88145`). `GCN_AX_LAYOUT=2001` or
  `GCN_AX_LAYOUT=later` overrides the layout but not the compressor, for comparing how the two
  decode the mixer control word.
- `ax.cpp` mixes with the decoder the layout picks (`:442-443`, `:485-487`). It runs command
  `12` for any hash but the 2001 one (`:673-679`).
- In a 30-second run at an earlier gcn-recomp (`67a7e30`) the game sent 5,834 command lists,
  about 29 seconds of 5 ms frames. Each command list gets `DCD10002` back
  (`dsp_hle.cpp:98-99`). The ten runs in `status.md` counted 484,400 lists and none had an
  unknown command.
- The sound crackled the one time it was listened to, before the source type 2 fix.
  `GCN_AXSTATS` counts levels and `GCN_WAV` captures the output. `status.md` has the levels
  measured on the race route.

## What the game sends

The list builder at 0x803EC9F8 (`salBuildCommandList` in `analysis/symbols.txt`) writes one
list per 5 ms frame. This is from reading the DOL, not from a trace.

| Command | Sent when | gcn-recomp |
|---|---|---|
| `00` setup | every frame | `ax.cpp:643`, `:552-566` |
| `07` main L and R from one buffer | stereo mode | `:652` |
| `11` the same with left inverted | surround mode | `:672` |
| `02` PB address, `03` process | every frame | `:645-646` |
| `04` AuxA, `05` AuxB | not DPL2 and that bus has a callback | `:647-650` |
| `13` send aux and mix, `10` AuxB L and R | DPL2 mode (`13` only with an AuxA callback) | `:680-689`, `:665-671` |
| `12` compressor | the compressor is on | runs for any hash but the 2001 one (`:673-679`), skipped on that one |
| `0E` output, `0F` end | every frame | `:663`, `:664` |

Every argument count in `ax.cpp` matches what the game writes, so no list is cut short. The
builder never writes `01`, `08`, `09` or `0A` to `0D`. In the ten runs in `status.md`, `04`
and `05` came in every list (except two in the first window), and `12` in every list.

In the twelve audio-hash runs at gcn-recomp `b97c019`, `tools/ax_stats.py` counts 46,540,374
voice-milliseconds in 1,449 windows. Source type 0 with coefficient set 0, which goes through
the polyphase filter, made 46,043,984 of them (98.9%) and type 2 the other 496,390. None of
them had the low-pass filter's on word (93) set, and 25 setup commands started a bus off zero.

## The differences

Dolphin's AX HLE (`AX.cpp`, `AXVoice.h` and `AXStructs.h`, GPL, read for facts and not
copied) checks the ucode's hash in three places, each time `4E8A8B21` against everything
else. The runtime handles the mixer control and the compressor, and not the low-pass filter.

### Mixer control

The PB's mixer control word (word 6) has a different bit layout in the newer build. It gives
every bus its own enable bit and ramps by group. `ax.cpp:238-286` decodes the word into an
enable flag and a ramp flag for each of the nine buses, with one decoder for each layout,
and `:485-487` mixes each bus by its own flags.

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
  send is lost.

On the race route the later layout took AuxA sound from 22 of 257 windows to 97 and AuxB from
none to 20 (`status.md`).

Dolphin leaves bit `4000` unmapped, with a TODO saying it selects Dolby Pro Logic II.

### Low-pass filter

The newer PB has a one-pole low-pass filter at words 93 to 96 (on, `yn1`, `a0`, `b0`), which
moves the loop counter from word 93 to 97. When the filter is on, each sample after the
volume envelope becomes `(a0 * x + b0 * yn1) >> 15` clamped to 16 bits, and that result is
the next `yn1`.

The runtime reads and writes all 97 words on every build but the 2001 one and takes parameter
updates up to word 96 (`ax.cpp:42`, `:53-60`, `:504`), but it doesn't apply the filter. The
game didn't turn it on in the twelve runs counted under "What the game sends".

### Compressor

Command `12` carries a threshold, a release length in lists and the address of a gain table
in main RAM. The table holds 160-entry ramps of unsigned 16-bit gains, with 0x8000 as 1.0. The
first 11 are attack ramps and the rest release ramps.

For any hash but the 2001 one, `compress` (`ax.cpp:568-592`) checks whether any main L or R
sample in the list is over the threshold. If one is, both channels are scaled by the attack ramp
numbered by the release count left from earlier lists (0 when none), and the count restarts at
the release length. Otherwise, while the count is nonzero, it steps down and both channels are
scaled by the table's ramp 11 plus the count, one of the release ramps.

Surround is never touched. The count carries from list to list and resets when AX starts
(`:624`). On the 2001 hash the command's four words are skipped (`:673-679`).

The game sent it in every list of the ten runs in `status.md`, with a threshold and release
that weren't logged.

### Gaps every AX build has

These aren't version differences. They separate the runtime from Dolphin for `4E8A8B21`
too, and none of them silences a game.

| Gap | Where |
|---|---|
| Polyphase resampling (`src_type` 0) runs through three coefficient sets the runtime works out when AX starts, because the console's come from the DSP's ROM, which the runtime doesn't have. The output differs from a console's by however much those sets differ from the ROM's | `ax.cpp:332-362` |
| Dolphin bumps the loop counter each time a stream loops. The runtime doesn't | `ax.cpp:198-216` |
| Dolphin reads the volume envelope as signed on GameCube. The runtime reads it unsigned, which differs only at `0x8000` and up | `ax.cpp:474-479` |
| The initial time delay block (words 27 to 33) is ignored. Dolphin ignores it too | none |

## Clicks where the blocks join

`tools/audio_clicks.py` counts a click wherever a sample's second difference is over 8 times
the RMS second difference of the 5 ms either side, and at least 128. On the title route the
DMA's blocks (`GCN_AIDWAV`, 32 kHz, before the audio ring) had 928 clicks in 89 s, 575 of them
within 2 samples of a 160-sample block join, where chance gives 29.

Source type 2 (PB word 4) was the cause. It means no rate conversion, so the ucode reads one
sample for every sample out and ignores the ratio, as Dolphin's `AXVoice.h` and
`ax.cpp:448-453` do. The runtime used to step through a type 2 voice's input by the ratio, so a
PCM16 stereo pair the game refills every list fell behind its refills and jumped at each join.

`status.md` has the counts after.

[`scorecard.md`](scorecard.md) scores five routes with `tools/audio_scorecard.py` on later pins
and on gcn-recomp `caf12a2`, from before the audio work. Unpaced, over 324 s, the mixer stage's
clipped runs fell from 208 to 25 by `b848158` while its clicks went from 132 to 136. Its clicks
fell to 94 at `b97c019`.

`scorecard.md` rescores the same recordings with `--no-run` and finds that on the title and the
mode select the clicks `b848158` removed sat past the scored seconds.

## Stream music and disc timing

The game streams music through HAL's sound library, the one Melee's decompilation calls
`HSD_Synth`. Two ADPCM voices play 32 KB a channel from 64 KB slots in ARAM, and
`HSD_SynthPStreamMasterClockCallback` moves their end and loop addresses from slot to slot as
the music plays.

The voices need the loop flag from the stream's header, which the header callback sets with
`AXSetVoiceAddr`. The first data callback then sets the loop, end and current addresses one at
a time. The SDK's `__AXServiceVPB` copies those fields alone when any of them is marked and
copies the whole address with its loop flag only when none is, so the two callbacks have to
land in different 5 ms audio frames.

On a console the disc read between them takes tens of milliseconds. Before gcn-recomp `04c025f`
a read took 100 us and its length at 64 MiB/s, so both callbacks often landed in one frame. The
voices then played their first slot (1.79 s) and ended, as the menu music did in the playtest on
2026-10-27.

The Melee native port traced the same stop to the same merged address update
([its notes](https://github.com/HexDump0/melee/blob/main/native/AI/handoffs/2026-09-13-P-648-menu-bgm.md)).

## Music at fast reads

Since gcn-recomp `7968abc` the disc reads fast by default. At `fast` every block reads as one
the drive has read ahead (`22bc2c8`), so a read costs 600 us and its length at 32 MiB/s, as
Dolphin's "Speed up disc transfer rate" has it. `disc console` in `settings.txt` or
`--disc=console` keeps Dolphin's model of the console's drive (`04c025f`), and `status.md` has
the menu route's loads at both speeds under "Disc reads".

The two callbacks still land in different audio frames. At gcn-recomp `b5ec329`, each of the
twenty-four routes in `tests/hashes/manifest.txt` ran once at each speed under
`GCN_AXVOICES=1`. `tools/stream_voices.py` found no stream voice that ended early in any of the
48 runs, and a separate pass over every voice at a stream address found none that started
without its loop flag or that the mixer ended.

| Menu route | `fast` | `console` |
|---|---|---|
| Stream start (80579F88 and 8057A074) | list 3,555, `looping=1` | list 4,476, `looping=1` |
| Loops, with no `end` | 52 | 50 |
| 80579F88's `run` and `set` lines | 2 lists apart all 46 times through list 19,400 | 16 under 50 lists, from 2 to 44 |

At `fast` 80579F88's `set` line came 2 lists after its `run` line all 46 times, and each start
had its loop flag.
Four-player City Trial, the Sand, Fire and Light Top Ride routes and `top-ride-courses` each had
two more stream voices at `fast`, because each fast run reached a later track change before its
time ran out. The other nineteen matched, but the title and Top Ride's Sky course differed in
the check's first pass and matched in this one, so some of the difference is from run to run.

In the four-player City Trial run at `fast`, the stream pair 8057938C and 80579478 faded to a
peak of 0 by list 27,400 with `cur` frozen and its loop flag set. A new pair had started at list
27,189, and nothing stopped the old pair before the log ended at list 36,385. The console run
never reached that scene.

`tools/audio_hashes.py` plays the routes on `dragoon_bench`, which reads neither `settings.txt`
nor `--disc`, so the audio goldens are recorded at fast reads.

## What was done and what is left

Generic runtime work in `runtime/`.

| Change | Where | State |
|---|---|---|
| Hand the hash to AX and keep the 2001 behavior for `4E8A8B21` only | `dsp_hle.cpp:65`, `ax.h`, `ax.cpp:613-632` | Done |
| Decode both mixer layouts into per-bus enable and ramp flags, then mix each of the nine buses by its own flags | `ax.cpp:238-286`, `:485-487` | Done |
| Compressor | `ax.cpp:568-592`, `:673-679` | Done |
| Source types 2 and up with no rate conversion | `ax.cpp:448-453` | Done |
| PB layout with the filter's four words, 97 words on every build but the 2001 one | `ax.cpp:40-42`, `:53` | Done in `3056588` |
| Low-pass filter | after the volume envelope, `ax.cpp:474-479` | Not done |
| Depop words | `ax.cpp:225-236` | Done in `3b025ac` |
| Polyphase resampling through worked-out coefficient sets | `ax.cpp:332-384` | Done in `cce9fbc` and `795ccc4` |
| A bus the setup command starts at zero stays silent | `ax.cpp:552-566` | Done in `84471cc` |
| Mixing, `0E` and the ADPCM decoder clamp at -32,768 | `ax.cpp:230`, `:604`, `:163` | Done in `2b7ae75`, `3d4fe9b` and `6def94c` |
| An AI DMA block that comes due before the guest has run a quarter block since it started, not counting clock jumps, waits until the guest has run that long or has queued the next buffer. A block comes due that early only while the DMA catches up or after the clock jumps. Otherwise it ends when due, queued or not | `dsp.cpp:185-193`, `:236-243`, `:326` | Done in `a87ab06` and `3c55458` |
| Loop counter and signed envelope | `ax.cpp:198-216`, `:474-479` | Not done |
| Loop or stop a voice only on the sample at its end address | `ax.cpp:198-216` | Done in `1f5e5a3` |
| Wrap an ADPCM voice whose end is on a frame's header to its loop address | `ax.cpp:167-179` | Done in `ac8a1f4`, logged as a loop since `545c784` |
| Disc reads timed as a console's drive times them | `drive.h`, `di.cpp` | Done in `04c025f` and `f19f98d`. Since `7968abc` it's `disc console` |
| Disc reads at the read-ahead rate by default | `drive.h`, `di.cpp`, `main.cpp` | Done in `22bc2c8` and `7968abc` |
| A log of each voice's start, changes, loops and end | `GCN_AXVOICES` | Done in `1b25342` |

`b97c019` holds every commit from `3056588` to `3c55458` above, and `b848158` none of them. No
audio file under `runtime/` changes from `b97c019` to `e1016b8`.

The polyphase sets aren't the console's own, which need the DSP's ROM.

The change keys on the ucode hash the way `jaudio.cpp:68-69` keys on JAudio's, and names no
game. Metroid Prime boots `4E8A8B21` (upstream commit `ddc05c0`), so it's left as it was.
gcn-recomp doesn't record which hash Metroid Prime 2 or Wave Race boots, and if either boots a
newer build its aux routing changes too.
