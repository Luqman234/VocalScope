# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Robust centers in logarithmic pitch space, independent of backend scores."""
import numpy as np


def pitch_center(values):
    values=np.asarray(values,dtype=float)
    valid=values[np.isfinite(values)]
    if not len(valid):raise ValueError('A note needs at least one valid pitch frame.')
    center=float(np.median(valid))
    key=int(np.rint(center))
    if not 0 <= key <= 127:raise ValueError('Pitch center lies outside MIDI range.')
    spread=float(np.percentile(valid,90)-np.percentile(valid,10))
    flags=[]
    if spread>1.2:flags.append('wide_pitch_gesture')
    if abs(center-key)>.35:flags.append('between_keys')
    return center,key,100*(center-key),tuple(flags)
