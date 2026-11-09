# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""libsndfile ingestion, bounded decoding and explicit diagnostics."""

from pathlib import Path
from math import gcd

import numpy as np
import soundfile as sf

from .errors import AudioError
from .models import AnalysisConfig, AudioData, AudioMetadata
from .preprocessing import resample_audio


def load_audio(path: str | Path, config: AnalysisConfig | None = None) -> AudioData:
    """Read mono/stereo without changing the source; stereo uses arithmetic mean.

    Opposite-polarity channels can cancel. Diagnose that case, never choose a
    channel silently. Non-finite samples are rejected rather than repaired.
    """
    config = config or AnalysisConfig()
    path = Path(path).expanduser().resolve()
    try:
        with sf.SoundFile(path) as stream:
            n, sr, channels = stream.frames, stream.samplerate, stream.channels
            if n <= 0:
                raise AudioError("Audio is empty (zero sample frames).")
            if channels not in (1, 2):
                raise AudioError(f"Expected mono or stereo audio; found {channels} channels.")
            if sr <= 0:
                raise AudioError("Audio has an invalid sample rate.")
            target_n = (n * config.sample_rate + sr - 1) // sr
            config.validate_resources(target_n)
            if n * 8 > config.max_memory_mb * 1024**2 / 2:
                raise AudioError("Decoded source mono buffer would exceed half the memory budget; shorten the file.")
            if sr != config.sample_rate:
                ratio = max(sr, config.sample_rate) // gcd(sr, config.sample_rate)
                # SciPy's default FIR has 20*max(up, down)+1 taps. Include
                # coefficient/workspace copies to catch pathological rate ratios.
                resample_bytes = 8 * (n + target_n) + 64 * (20 * ratio + 1)
                if resample_bytes > config.max_memory_mb * 1024**2:
                    raise AudioError("Resampling filter/workspace estimate exceeds the memory budget; use a conventional source rate or raise --max-memory-mb.")
            mono = np.empty(n, dtype=np.float64)
            peak, clipped, channel_energy, offset = 0.0, 0, 0.0, 0
            safe_peak = np.sqrt(np.finfo(np.float64).max / max(8 * n * channels, 64 * config.frame_length**2))
            for block in stream.blocks(blocksize=65536, dtype="float64", always_2d=True):
                if not np.all(np.isfinite(block)):
                    raise AudioError("Audio contains non-finite samples (NaN or infinity).")
                if np.max(np.abs(block)) > safe_peak:
                    raise AudioError("Audio amplitude is too large for safe numerical analysis.")
                peak = max(peak, float(np.max(np.abs(block))))
                clipped += int(np.count_nonzero(np.abs(block) >= 0.999))
                channel_energy += float(np.sum(block * block))
                count = len(block)
                mono[offset:offset + count] = block.mean(axis=1)
                offset += count
            if offset != n:
                raise AudioError(f"Decoder returned {offset} frames, but file declares {n}; file may be truncated.")
            format_name, subtype = stream.format, stream.subtype
    except (sf.LibsndfileError, OSError, ValueError) as exc:
        raise AudioError(f"Cannot decode {path.name}: {exc}") from exc
    rms = float(np.sqrt(np.mean(mono * mono)))
    warnings: list[str] = []
    if peak == 0:
        warnings.append("Digital silence: all decoded samples are zero.")
    elif peak < 1e-4:
        warnings.append("Very low amplitude (peak below -80 dBFS); no automatic gain or silence gate applied.")
    if clipped:
        warnings.append("Samples near or above full scale detected; possible clipping. Audio was not limited or repaired.")
    channel_rms = np.sqrt(channel_energy / (n * channels))
    if channels == 2 and channel_rms > 0 and rms < 0.1 * channel_rms:
        warnings.append("Strong stereo cancellation during arithmetic-mean downmix; inspect channel polarity.")
    metadata = AudioMetadata(
        path=str(path), filename=path.name, original_sample_rate=sr,
        channels=channels, original_frames=n, duration_seconds=n / sr,
        format=format_name, subtype=subtype,
        downmix="arithmetic_mean" if channels == 2 else "none",
        peak_amplitude=peak, rms_amplitude=rms,
        clipped_sample_fraction=clipped / (n * channels), warnings=tuple(warnings),
    )
    samples = resample_audio(mono, sr, config.sample_rate)
    if not np.all(np.isfinite(samples)):
        raise AudioError("Resampling produced non-finite values; check input amplitude.")
    samples.setflags(write=False)
    return AudioData(samples, config.sample_rate, metadata)

