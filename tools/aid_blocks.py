"""What GCN_AIDWAV writes: every block the DMA delivered, raw 16-bit little-endian stereo at the
DMA's 32 kHz, and beside it <file>.txt, the block log. Each line of the log is a block's start
sample, its length, its virtual time, 1 if it was delivered while the clock caught up, its
address and 1 if the guest had queued the next (gcn-recomp docs/diagnostics.md, The clock).
It has no command line."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RATE = 32000  # the DMA's rate
BLOCK = 160   # samples in one of the DMA's 5 ms blocks, and in one AX command list's output


@dataclass
class Block:
    start: int
    length: int
    caught_up: bool
    address: str


def log_path(recording: Path) -> Path:
    return recording.with_name(recording.name + ".txt")


def read_blocks(path: Path) -> list[Block]:
    """The blocks in a block log. A line without all six fields is skipped, since a run that's
    killed can leave its last line cut short."""
    blocks = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split()
        if len(fields) != 6:
            continue
        start, length, _, catch_up, address, _ = fields
        try:
            blocks.append(Block(int(start), int(length), catch_up == "1", address))
        except ValueError:
            raise ValueError(f"{path}:{n}: {line!r} isn't a block line") from None
    return blocks
