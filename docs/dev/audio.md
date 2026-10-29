# Audio: the AX ucode

Kirby Air Ride boots Nintendo's AX ucode, build `07F88145`. gcn-recomp's AX HLE was written
for the 2001 build (`4E8A8B21`). At gcn-recomp `fd1f6a8` it takes the ucode's hash and reads
the PB mixer control word with the 2001 layout for that hash only. Every other hash, this one
included, gets the later layout. The compressor command runs on the same hash test, so at the
pinned gcn-recomp (since `b839cf6`) it follows the ucode hash alone and `GCN_AX_LAYOUT` leaves
it be. The newer build's low-pass filter still isn't applied. The `ax.cpp` line numbers below
are at gcn-recomp `fd1f6a8`. The pin is now `b5ec329`, where `compress` still starts at line
573 and `ax_init` at 617.

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
- `ax_init` (`ax.cpp:421-431`) gives the 2001 hash the 2001 mixer control layout and every
  other hash the later one. The choice is made once, when AX starts. `--log=dsp` logs it
  (`AX: later mixer layout, ucode hash=07F88145`). `GCN_AX_LAYOUT=2001` or
  `GCN_AX_LAYOUT=later` overrides the layout, for comparing how the two decode the mixer
  control word. It doesn't change the compressor.
- `ax.cpp` mixes with the decoder the layout picks (`:298-300`). It runs command `12` for any
  hash but the 2001 one (`:472-478` at `fd1f6a8`, where the gate read the layout and not the
  hash).
- In a 30-second run at an earlier gcn-recomp (`67a7e30`) the game sent 5,834 command lists,
  about 29 seconds of 5 ms frames. Each got `DCD10002` back (`dsp_hle.cpp:98-99`). The ten
  runs in `status.md` counted 484,400 lists and none had an unknown command.
- The sound was listened to once, before the source type 2 fix. It crackled. Nobody has
  listened since. `GCN_AXSTATS` counts levels and `GCN_WAV` captures
  the output, and both are environment switches. On the later layout a voice reaches main
  left only when its mixer control sets `0001` and main right only when it sets `0002`
  (`:247-255`, `:298-300`).
  `status.md` has the levels measured on the race route.

## What the game sends

The list builder at 0x803EC9F8 (`salBuildCommandList` in `analysis/symbols.txt`) writes one
list per 5 ms frame. This is from reading the DOL, not from a trace.

| Command | Sent when | gcn-recomp |
|---|---|---|
| `00` setup | every frame | `ax.cpp:442`, `:362-370` |
| `07` main L and R from one buffer | stereo mode | `:451` |
| `11` the same with left inverted | surround mode | `:471` |
| `02` PB address, `03` process | every frame | `:444-445` |
| `04` AuxA, `05` AuxB | not DPL2 and that bus has a callback | `:446-449` |
| `13` send aux and mix, `10` AuxB L and R | DPL2 mode (`13` only with an AuxA callback) | `:479-488`, `:464-470` |
| `12` compressor | the compressor is on | runs for any hash but the 2001 one (`:472-478`), skipped on that one |
| `0E` output, `0F` end | every frame | `:462`, `:463` |

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
and `:299-300` mixes each bus by its own flags.

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
the next `yn1`. Since gcn-recomp `3056588` the runtime reads and writes all 97 words on every
build but the 2001 one and takes parameter updates up to word 96, but it doesn't apply the
filter. The game didn't turn it on in the twelve audio-hash runs at `b97c019`.
`tools/ax_stats.py` over their logs counts 0 voice-milliseconds with word 93 set, out of
46,540,374 in 1,449 windows.

### Compressor

Command `12` carries a threshold, a release length in lists and the address of a gain table
in main RAM. The table holds 160-entry ramps of unsigned 16-bit gains with 0x8000 as 1.0:
11 attack ramps, then the release ramps. For any hash but the 2001 one, `compress` (`ax.cpp:372-396`)
checks whether any main L or R sample in the list is over the threshold. If so, both
channels are scaled by the attack ramp numbered by the release count left from the earlier
lists (0 when none), and the count restarts at the release length. Otherwise, while the
count is nonzero, it steps down and both channels are scaled by release ramp 11 plus the
count. Surround is never touched. The count is kept from list to list and reset when AX
starts (`:424`). The 2001 build has no such command, so on that hash the four words are
skipped and counted as skipped (`:476`). The game sent it in every list of the ten runs in
`status.md`. The threshold and release it sends weren't logged.

### Gaps every AX build has

These aren't version differences. They separate the runtime from Dolphin for `4E8A8B21`
too, and none of them silences a game.

| Gap | Where |
|---|---|
| Polyphase resampling (`src_type` 0) runs through three coefficient sets the runtime works out when AX starts, because the console's come from the DSP's ROM, which the runtime doesn't have. The output differs from a console's by however much those sets differ from the ROM's | `make_polyphase` at `e1016b8` |
| Dolphin bumps the loop counter each time a stream loops. The runtime doesn't | `ax.cpp:178-186` |
| Dolphin reads the volume envelope as signed on GameCube. The runtime reads it unsigned, which differs only at `0x8000` and up | `ax.cpp:292-296` |
| The initial time delay block (words 27 to 33) is ignored. Dolphin ignores it too | none |

## Clicks where the blocks join

The output clicked. `tools/audio_clicks.py` counts a click wherever a sample's second
difference stands over 8 times the RMS second difference around it. On the title route the
DMA's own blocks (`GCN_AIDWAV`, 32 kHz, before the audio ring) had 928 clicks in 89 seconds,
and 575 of them fell within 2 samples of a 160-sample block join, where chance gives 29.

Source type 2 (PB word 4) was the cause. It means no rate conversion, so the ucode reads one
sample from the accelerator for every sample out and ignores the ratio. Dolphin's
`AXVoice.h` does the same. The runtime stepped through the input by the ratio and held the
newest sample, so a type 2 voice played at the ratio's speed as a staircase. A PCM16 stereo
pair the game refills every list fell behind its refills and jumped at each join.
`ax.cpp:269-273` now takes a sample for every sample out. The counts before and after are in
`status.md`.

[`scorecard.md`](scorecard.md) measures the five routes at both stages on gcn-recomp `caf12a2`,
which has none of this work, and on `b848158`, with `tools/audio_scorecard.py`. The tool
scores the mixer stage from unpaced runs and the device stage from real-time ones, and has
done so for both builds. Over the five routes, 324 s in all, the unpaced mixer stage made 132
clicks at `caf12a2` and 136 at `b848158`, and its clipped runs fell from 208 to 25. The audio
work didn't reduce the mixer stage's clicks over those seconds. Rescored with
`audio_scorecard.py --no-run`, the title's first 91 s (`--margin 75`) went from 1,085 clicks to
19 and the mode select's first 170 s (`--margin 150`) from 118 to 16, so on those two routes the
clicks that fell are past the scored seconds, in the same recordings. In the scored seconds what
it cut was clipping.

## What the move to gcn-recomp `e1016b8` changed

The pin moved from gcn-recomp `b848158` to `e1016b8`, 87 commits. These are the ones that
change what the mixer or the AI DMA makes. All of them come by `b97c019`, 66 commits in, and
none of the 21 after it touches the audio files under `runtime/`.

| Commit | Change |
|---|---|
| `3056588` | `GCN_AXSTATS` counts voices with the filter on and ramped voices, and splits voice time by resampler type and coefficient set. The PB is 97 words on every build but the 2001 one |
| `3b025ac` | Each bus a voice mixes into leaves the voice's last sample in the PB's depop words, 41 to 49 |
| `cce9fbc`, `795ccc4` | Source type 0 resamples through a four-tap polyphase filter of 128 phases, from three sets worked out when AX starts |
| `84471cc` | A bus the setup command starts at zero stays silent whatever its slope |
| `2b7ae75` | A sample mixed into a bus clamps at -32,768 instead of -32,767 |
| `3d4fe9b` | Command `0E` clamps its output at -32,768 instead of -32,767 |
| `6def94c` | The ADPCM decoder saturates at -32,768 instead of -32,767, and the history the next sample reads carries it |
| `a87ab06`, `3c55458` | A catch-up jump no longer ends a block the guest hasn't queued after, so the DMA doesn't play that buffer twice. A held block ends once the guest queues |

`tools/audio_hashes.py check` at `b97c019`, against the goldens on `main`, failed every row
of all twelve routes, 24 rows in all. The hashes cover the whole mix since boot, so they say
each route's sound changed and not which commit changed it. The goldens were recorded again
at `b97c019`, and at `e1016b8` the check matched them on all twelve routes (`status.md`).

In those twelve runs `tools/ax_stats.py` counts 46,540,374 voice-milliseconds. 46,043,984 of
them, 98.9%, were source type 0 with coefficient set 0, and the other 496,390 were type 2. So
nearly all the voice time the game plays now goes through the polyphase filter. 25 setup
commands started a bus off zero in the 1,449 windows.

## Music that stopped

In the playtest on 2026-10-27 the menu music played for a few seconds and stopped, while the
sound effects carried on. The game streams music through HAL's sound library, the one Melee's
decompilation calls `HSD_Synth`. Two ADPCM voices play 32 KB a channel from 64 KB slots in
ARAM, and `HSD_SynthPStreamMasterClockCallback` moves their end and loop addresses from slot
to slot as the music plays.

The voices need the loop flag from the stream's header, which the header callback sets with
`AXSetVoiceAddr`. The first data callback then sets the loop, end and current addresses one at
a time. The SDK's `__AXServiceVPB` copies those fields alone when any of them is marked and
copies the whole address with its loop flag only when none is, so the two callbacks have to
land in different 5 ms audio frames.

On a console the disc read between them takes tens of milliseconds. gcn-recomp read the disc
at 64 MB/s, so both callbacks often landed in one frame, and the voices played their first
slot (1.79 s) and ended. Replays of two playtest sessions showed it on every stream, not only
the menu's.

gcn-recomp `04c025f` times disc reads as a console's drive does, with Dolphin's model, and
`f19f98d` moves DIMAR and DILENGTH when a read completes. `GCN_AXVOICES` (`1b25342`) logs each
voice's start, changes, loops and end, which is how this was traced.

Two more fixes came out of the trace. `1f5e5a3` loops or stops a voice only on the sample at
its end address, which ends a 10 ms stall on a slot's first sample at some slot changes.
`ac8a1f4` wraps an ADPCM voice whose end address is on a frame's header byte to its loop
address, without stopping it or loading the loop's predictor, as Dolphin's hardware tests
show the DSP does.

The menu route was run at gcn-recomp `f11c013`, whose runtime differs from `bad7160`'s only
in when `GCN_AXVOICES` prints a loop line. Its menu stream starts at list 4,476 with its loop
flag set and is still playing at list 17,000, 85 s in, with peaks of 12,289 and 12,479. The
Melee native port traced the same stop to the same merged address update, and fixed the same
end check
([its notes](https://github.com/HexDump0/melee/blob/main/native/AI/handoffs/2026-09-13-P-648-menu-bgm.md)).

## Music at fast reads

Since gcn-recomp `b5ec329` the disc reads fast by default (`22bc2c8`, `7968abc`). Every block
reads as one the drive has read ahead, so a read costs 600 us and its length at 32 MiB/s, as
Dolphin's "Speed up disc transfer rate" has it. `disc console` in `settings.txt` or
`--disc=console` keeps the console's timing above, and `status.md` has the menu route's loads at
both speeds.

The two callbacks still land in different audio frames. With the drive code `b5ec329` has, each
of the twenty-four routes in `tests/hashes/manifest.txt` ran once at each speed under
`GCN_AXVOICES=1`. `tools/stream_voices.py` found no stream voice that ended early in any of the
48 runs, and a separate pass over every voice at a stream address found none that started
without its loop flag or that the mixer ended.

| Menu route | `fast` | `console` |
|---|---|---|
| Stream start (80579F88 and 8057A074) | list 3,555, `looping=1` | list 4,476, `looping=1` |
| Loops, with no `end` | 52 | 50 |
| 80579F88's `run` and `set` lines through list 19,400 | 2 lists apart all 46 times | 16 gaps of 2 to 44 lists |

At `fast` the paired updates leave one audio frame more than the loop flag needs. Nineteen
routes played as many stream voices at each speed. Four-player City Trial, the Sand, Fire and
Light Top Ride routes and `top-ride-courses` each had two more at `fast`, from a track change
further along before the run's time ran out.

In the four-player City Trial run at `fast`, the stream pair 8057938C and 80579478 faded to a
peak of 0 by list 27,400 with `cur` frozen and its loop flag set. A new pair had started at list
27,189, and nothing stopped the old pair before the log ended at list 36,385. The console run
never reached that scene.

`tools/audio_hashes.py` plays the routes on `dragoon_bench`, which reads neither `settings.txt`
nor `--disc`, so the audio goldens are recorded at fast reads. At `b5ec329` all 48 rows changed
and were recorded again (`status.md`).

## What was done and what is left

Generic runtime work in `runtime/hw/`.

| Change | Where | State |
|---|---|---|
| Hand the hash to AX and keep the 2001 behavior for `4E8A8B21` only | `dsp_hle.cpp:65`, `ax.h`, `ax.cpp:417-431` | Done |
| Decode both mixer layouts into per-bus enable and ramp flags, then mix each of the nine buses by its own flags | `ax.cpp:209-256`, `:299-300` | Done |
| Compressor | `ax.cpp:372-396`, `:472-478` | Done |
| Source type 2 with no rate conversion | `ax.cpp:269-273` | Done |
| PB layout with the filter's four words, 97 words on every build but the 2001 one | `PB_WORDS_LATER`, `pb_words` at `e1016b8` | Done in `3056588` |
| Low-pass filter | after the volume envelope, `ax.cpp:292-296` | Not done |
| Depop words | `mix_add` at `e1016b8` | Done in `3b025ac` |
| Polyphase resampling through worked-out coefficient sets | `make_polyphase`, `resample_polyphase` at `e1016b8` | Done in `cce9fbc` and `795ccc4` |
| Loop counter and signed envelope | `ax.cpp:178-186`, `:292-296` | Not done |
| Loop or stop a voice only on the sample at its end address | `Accel::sample` | Done in `1f5e5a3` |
| Wrap an ADPCM voice whose end is on a frame's header to its loop address | `Accel::sample` | Done in `ac8a1f4`, logged as a loop since `545c784` |
| Disc reads timed as a console's drive times them | `drive.h`, `di.cpp` | Done in `04c025f` and `f19f98d`. Since `b5ec329` it's `disc console` |
| Disc reads at the read-ahead rate by default | `drive.h`, `di.cpp`, `main.cpp` | Done in `22bc2c8` and `7968abc` |
| A log of each voice's start, changes, loops and end | `GCN_AXVOICES` | Done in `1b25342` |

The polyphase sets aren't the console's own, which need the DSP's ROM.

The change is generic. It keys on the ucode hash the way `jaudio.cpp:68-69` keys on
JAudio's, and it names no game. Metroid Prime boots `4E8A8B21` (upstream commit `ddc05c0`),
so a switch on that hash leaves it as it is. gcn-recomp doesn't record which hash Metroid
Prime 2 or Wave Race boots, and if either boots a newer build its aux routing changes too.
