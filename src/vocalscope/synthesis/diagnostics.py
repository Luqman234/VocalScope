# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Streaming finite/peak/RMS diagnostics with bounded tail history."""
import numpy as np
from .models import SynthesisError


class WaveformDiagnostics:
    def __init__(self,sample_rate):
        self.frames=0;self.peak=0.;self.squares=0.;self.full_scale_samples=0
        self.tail_frames=max(1,round(.05*sample_rate));self.tail=np.empty((0,2),dtype=np.float32)

    def add(self,block):
        if block.ndim!=2 or block.shape[1]!=2 or not np.isfinite(block).all():raise SynthesisError('Invalid stereo PCM; rendering discarded.')
        self.frames+=len(block)
        self.peak=max(self.peak,float(np.max(np.abs(block),initial=0.)))
        self.squares+=float(np.sum(np.square(block,dtype=np.float64)))
        self.full_scale_samples+=int(np.sum(np.abs(block)>=1.))
        self.tail=np.concatenate((self.tail,block[-self.tail_frames:]))[-self.tail_frames:]

    def result(self):
        rms=float(np.sqrt(self.squares/(2*self.frames))) if self.frames else 0.
        tail_rms=float(np.sqrt(np.mean(self.tail.astype(np.float64)**2))) if len(self.tail) else 0.
        return {'frames':self.frames,'channels':2,'peak_absolute':self.peak,'rms':rms,'samples_at_or_above_full_scale':self.full_scale_samples,
            'clipping_risk':bool(self.full_scale_samples),'last_50ms_rms':tail_rms,'tail_residual_above_minus60_dbfs':tail_rms>1e-3}
