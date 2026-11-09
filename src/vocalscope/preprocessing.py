# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Conservative sample-rate conversion only; no gate, denoising or pitch smoothing."""

from math import gcd

import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly


def resample_audio(samples: NDArray[np.float64], source_rate: int, target_rate: int) -> NDArray[np.float64]:
    """Polyphase FIR resampling. Output length is ceil(N * target/source)."""
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("Sample rates must be positive.")
    if source_rate == target_rate:
        return samples
    factor = gcd(source_rate, target_rate)
    return np.asarray(resample_poly(samples, target_rate // factor, source_rate // factor), dtype=np.float64)

