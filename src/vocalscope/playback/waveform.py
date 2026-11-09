# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Bounded waveform overview; presentation only, never a playback clock."""
import numpy as np
import soundfile as sf
from functools import lru_cache
from pathlib import Path


def overview(path,bins=2000):
    """Read-only arrays, bounded four-source cache; invoke off the GTK thread."""
    if type(bins) is not int or not 1<=bins<=10000:raise ValueError('Waveform bins must be within [1,10000].')
    path=Path(path).resolve();stat=path.stat()
    return _overview((str(path),stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns),bins)


@lru_cache(maxsize=4)
def _overview(identity,bins):
    path=identity[0]
    with sf.SoundFile(path) as stream:
        width=max(1,int(np.ceil(stream.frames/bins)));times=[];low=[];high=[];position=0
        while True:
            block=stream.read(width,dtype='float32',always_2d=True)
            if not len(block):break
            times.append((position+len(block)/2)/stream.samplerate);low.append(float(block.min()));high.append(float(block.max()));position+=len(block)
    result=tuple(np.asarray(v) for v in (times,low,high))
    for array in result:array.flags.writeable=False
    return result
