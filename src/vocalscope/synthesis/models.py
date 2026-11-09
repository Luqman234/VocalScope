# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Validated renderer configuration and result metadata."""
from dataclasses import dataclass
import math
from ..errors import VocalScopeError


class SynthesisError(VocalScopeError):
    """Actionable synthesis, resource, or native-backend failure."""


class RenderCancelled(SynthesisError):
    """No completed output should be published for this cancelled job."""


@dataclass(frozen=True)
class RenderConfig:
    sample_rate: int = 44100
    gain: float = .2
    tail_seconds: float = 1.5
    bank: int = 0
    preset: int = 0
    polyphony: int = 256
    reverb: bool = False
    chorus: bool = False
    interpolation: int = 4
    normalize_peak: bool = False
    peak_target: float = .98
    chunk_frames: int = 4096
    max_duration_seconds: float = 3600.
    max_soundfont_mb: float = 512.
    max_notes: int = 100_000
    max_buffer_mb: float = 64.

    def __post_init__(self):
        if type(self.sample_rate) is not int or self.sample_rate not in (22050,44100,48000,88200,96000):
            raise ValueError('Sample rate must be 22050, 44100, 48000, 88200 or 96000 Hz.')
        for key,low,high in [('gain',0.,10.),('tail_seconds',0.,30.),('peak_target',.01,1.),('max_duration_seconds',.01,3600.),('max_soundfont_mb',.01,2048.),('max_buffer_mb',.01,1024.)]:
            value=getattr(self,key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
                raise ValueError(f'{key} must be finite and within [{low}, {high}].')
        if self.gain<=0 or self.peak_target>=1:raise ValueError('Gain must be positive; normalization target must be below 1.')
        for key,low,high in [('bank',0,16383),('preset',0,127),('polyphony',16,4096),('chunk_frames',64,65536),('max_notes',1,100_000)]:
            v=getattr(self,key)
            if type(v) is not int or not low<=v<=high:raise ValueError(f'{key} must be an integer in [{low}, {high}].')
        for key in ('reverb','chorus','normalize_peak'):
            if type(getattr(self,key)) is not bool:raise ValueError(f'{key} must be boolean.')
        if self.interpolation not in (0,1,4,7):raise ValueError('Interpolation must be 0, 1, 4 or 7.')


def check_cancelled(cancelled):
    if cancelled is not None and cancelled.is_set():raise RenderCancelled('Rendering cancelled; no completed output was published.')
