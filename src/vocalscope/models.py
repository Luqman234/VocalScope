# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Analysis contracts and validated, serializable parameter models."""

from dataclasses import dataclass, field
import math

import numpy as np
from numpy.typing import NDArray

from .errors import ConfigurationError
from .notes import parse_frequency


@dataclass(frozen=True)
class AnalysisConfig:
    fmin: float = parse_frequency("C2")
    fmax: float = parse_frequency("D6")
    sample_rate: int = 22050
    frame_length: int = 2048
    hop_length: int = 512
    resolution: float = 0.1
    switch_prob: float = 0.01
    no_trough_prob: float = 0.001
    max_transition_rate: float = 35.92
    a4_hz: float = 440.0
    max_duration_seconds: float = 300.0
    max_memory_mb: float = 1024.0

    def __post_init__(self) -> None:
        for name in ("sample_rate", "frame_length", "hop_length"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ConfigurationError(f"{name} must be a positive integer.")
        for name in ("fmin", "fmax", "a4_hz", "max_transition_rate", "max_duration_seconds", "max_memory_mb"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ConfigurationError(f"{name} must be positive and finite.")
        if not self.fmin < self.fmax < self.sample_rate / 2:
            raise ConfigurationError("Require 0 < fmin < fmax < analysis sample rate / 2 (Nyquist).")
        if self.frame_length < 32 or self.frame_length % 2:
            raise ConfigurationError("frame_length must be an even integer of at least 32 samples.")
        if self.hop_length > self.frame_length:
            raise ConfigurationError("hop_length must not exceed frame_length.")
        if self.frame_length < 2 * self.sample_rate / self.fmin + 1:
            raise ConfigurationError("frame_length must accommodate at least two periods at fmin plus one sample.")
        for name in ("resolution", "switch_prob", "no_trough_prob"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 < value < 1:
                raise ConfigurationError(f"{name} must be between 0 and 1, exclusive.")
        if self.resolution < 0.01:
            raise ConfigurationError("resolution below 0.01 semitones is unsupported due to pYIN resource cost.")
        # librosa rounds transition width to whole semitones before bin scaling.
        width = round(self.max_transition_rate * 12 * self.hop_length / self.sample_rate)
        bins = int(np.floor(12 * math.ceil(1 / self.resolution) * math.log2(self.fmax / self.fmin))) + 1
        if (width * math.ceil(1 / self.resolution) + 1) > bins:
            raise ConfigurationError("Transition rate/hop is too large for this pitch range; reduce either value.")

    def estimated_working_bytes(self, samples: int) -> int:
        """Conservative estimate of DSP arrays, excluding interpreter/JIT/library overhead."""
        frames = 1 + samples // self.hop_length
        bins = 1 + int(np.floor(12 * math.ceil(1 / self.resolution) * math.log2(self.fmax / self.fmin)))
        return int(8 * (samples * 2 + frames * (6 * self.frame_length + 12 * bins) + 12 * bins * bins))

    def validate_resources(self, samples: int) -> None:
        duration = samples / self.sample_rate
        if duration > self.max_duration_seconds:
            raise ConfigurationError(f"Audio is {duration:.2f} s; limit is {self.max_duration_seconds:g} s. Split the recording or explicitly raise --max-duration.")
        estimate = self.estimated_working_bytes(samples) / 1024**2
        if estimate > self.max_memory_mb:
            raise ConfigurationError(f"Estimated DSP working arrays need {estimate:.0f} MiB; configured budget is {self.max_memory_mb:g} MiB. Increase 'Maximum DSP memory (MiB)' in GUI Analysis parameters or use --max-memory-mb with a larger value. You can also shorten audio, increase hop or narrow pitch range. This is an estimate, not allocated process memory; allow additional RAM for Python, libraries and JIT.")


@dataclass(frozen=True)
class AudioMetadata:
    path: str
    filename: str
    original_sample_rate: int
    channels: int
    original_frames: int
    duration_seconds: float
    format: str
    subtype: str
    downmix: str
    peak_amplitude: float
    rms_amplitude: float
    clipped_sample_fraction: float
    warnings: tuple[str, ...] = ()



@dataclass(frozen=True)
class AudioData:
    samples: NDArray[np.float64]
    sample_rate: int
    metadata: AudioMetadata


@dataclass(frozen=True)
class AnalysisResult:
    metadata: AudioMetadata
    config: AnalysisConfig
    analysis_samples: int
    time_seconds: NDArray[np.float64]
    f0_hz: NDArray[np.float64]
    voiced: NDArray[np.bool_]
    voiced_probability: NDArray[np.float64]
    midi_pitch: NDArray[np.float64]
    nearest_note: list[str | None]
    cents_deviation: NDArray[np.float64]
    runtime_seconds: float
    versions: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    estimator_id: str = "pyin"
    estimator_version: str = ""
    estimator_configuration: dict = field(default_factory=dict)
    confidence_type: str = "pyin_voicing_probability"
    confidence: NDArray[np.float64] | None = None
    backend_metadata: dict = field(default_factory=dict)
    initialization_seconds: float = 0.0

    def __post_init__(self) -> None:
        arrays = (self.time_seconds, self.f0_hz, self.voiced, self.voiced_probability, self.midi_pitch, self.cents_deviation)
        n = len(self.time_seconds)
        if n == 0 or any(a.ndim != 1 or len(a) != n for a in arrays) or len(self.nearest_note) != n:
            raise ValueError("Analysis frame fields must be nonempty, one-dimensional and equally sized.")
        if self.voiced.dtype.kind != "b":
            raise ValueError("Voiced flags must have boolean dtype.")
        if not np.all(np.isfinite(self.time_seconds)) or np.any(np.diff(self.time_seconds) <= 0):
            raise ValueError("Frame timestamps must be finite and strictly increasing.")
        if self.estimator_id == "pyin":
            if not np.all(np.isfinite(self.voiced_probability)) or np.any((self.voiced_probability < 0) | (self.voiced_probability > 1)):
                raise ValueError("Voicing probabilities must be finite in [0, 1].")
        elif not np.all(np.isnan(self.voiced_probability)):
            raise ValueError("Non-pYIN backends must leave voiced_probability missing; their scores are not probabilities.")
        if self.confidence is None:
            object.__setattr__(self, "confidence", self.voiced_probability.copy())
        if self.confidence.shape != self.time_seconds.shape or not np.all(np.isfinite(self.confidence)):
            raise ValueError("Backend confidence scores must be finite and aligned with frames.")
        self.confidence.setflags(write=False)
        if np.any(self.voiced & (~np.isfinite(self.f0_hz) | (self.f0_hz <= 0))):
            raise ValueError("Voiced frames require a positive finite F0.")
        for a in (self.f0_hz, self.midi_pitch, self.cents_deviation):
            if np.any(np.isfinite(a) != self.voiced) or np.any(np.isinf(a)):
                raise ValueError("Pitch measurements must be finite exactly when voiced, and NaN otherwise.")
        if any((note is not None) != bool(v) for note, v in zip(self.nearest_note, self.voiced, strict=True)):
            raise ValueError("Note names must be present exactly when voiced.")
        if not math.isfinite(self.runtime_seconds) or self.runtime_seconds < 0:
            raise ValueError("Runtime must be finite and nonnegative.")
        for array in arrays:
            array.setflags(write=False)

    def summary(self) -> dict[str, int | float | None]:
        pitches = self.f0_hz[self.voiced]
        duration = self.metadata.duration_seconds
        return {
            "frame_count": len(self.time_seconds),
            "voiced_frame_count": int(self.voiced.sum()),
            "voiced_frame_fraction": float(self.voiced.mean()),
            "median_voiced_f0_hz": float(np.median(pitches)) if pitches.size else None,
            "min_voiced_f0_hz": float(pitches.min()) if pitches.size else None,
            "max_voiced_f0_hz": float(pitches.max()) if pitches.size else None,
            "runtime_seconds": self.runtime_seconds,
            "runtime_over_audio_duration": self.runtime_seconds / duration,
        }

