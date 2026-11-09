# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Backend-independent acoustic output, before musical-note conversion."""

from dataclasses import dataclass, field
import math
from typing import Protocol, runtime_checkable
import numpy as np
from numpy.typing import NDArray
from ..errors import ConfigurationError
from ..models import AnalysisConfig, AudioData


@dataclass(frozen=True)
class EstimatorConfig:
    estimator_id: str = "pyin"
    yin_voicing_threshold: float = 0.6
    yin_trough_threshold: float = 0.1
    crepe_voicing_threshold: float = 0.5
    crepe_model: str = "full"
    crepe_batch_size: int = 128
    crepe_hop_length: int = 160
    device: str = "cpu"
    threads: int = 2
    pyin_voicing_threshold: float | None = None

    def __post_init__(self):
        if self.estimator_id not in ("pyin", "yin", "crepe"):
            raise ConfigurationError("estimator_id must be pyin, yin, or crepe.")
        if self.crepe_model not in ("tiny", "full"):
            raise ConfigurationError("CREPE model must be tiny or full.")
        if self.device != "cpu":
            raise ConfigurationError("This release supports CPU inference only.")
        for name in ("crepe_batch_size", "crepe_hop_length", "threads"):
            v = getattr(self, name)
            if type(v) is not int or v <= 0:
                raise ConfigurationError(f"{name} must be a positive integer.")
        for name in ("yin_voicing_threshold", "yin_trough_threshold", "crepe_voicing_threshold", "pyin_voicing_threshold"):
            value = getattr(self, name)
            if value is None and name == "pyin_voicing_threshold":
                continue
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ConfigurationError(f"{name} must be finite in [0, 1].")


@dataclass(frozen=True)
class EstimatorOutput:
    estimator_id: str
    estimator_version: str
    times: NDArray[np.float64]
    candidates: NDArray[np.float64]
    voiced: NDArray[np.bool_]
    score: NDArray[np.float64]
    confidence_type: str
    sample_rate: int
    initialization_seconds: float
    inference_seconds: float
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        n = len(self.times)
        arrays = (self.times, self.candidates, self.voiced, self.score)
        if not n or any(a.ndim != 1 or len(a) != n for a in arrays):
            raise ValueError("Backend fields must be nonempty, aligned one-dimensional arrays.")
        if self.voiced.dtype.kind != 'b' or np.any(np.diff(self.times) <= 0) or not np.all(np.isfinite(self.times)):
            raise ValueError("Invalid backend timestamps or voiced flags.")
        if np.any(self.voiced & (~np.isfinite(self.candidates) | (self.candidates <= 0))):
            raise ValueError("A voiced frame must have a finite positive pitch candidate.")
        if not np.all(np.isfinite(self.score)) or np.any((self.score < 0) | (self.score > 1)):
            raise ValueError("Invalid backend score; score meanings remain backend-specific.")
        for a in arrays:
            a.setflags(write=False)

    @property
    def f0_hz(self) -> NDArray[np.float64]:
        return np.where(self.voiced, self.candidates, np.nan)


@runtime_checkable
class PitchEstimator(Protocol):
    def analyze(self, audio: AudioData, config: AnalysisConfig, settings: EstimatorConfig) -> EstimatorOutput: ...

