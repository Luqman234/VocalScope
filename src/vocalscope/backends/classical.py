# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""pYIN reference and related YIN baseline with explicit correlation voicing."""

from importlib.metadata import version
from time import perf_counter
import warnings
import librosa
import numpy as np
from .base import EstimatorConfig, EstimatorOutput
from ..models import AnalysisConfig, AudioData


def correlation_scores(y: np.ndarray, f0: np.ndarray, config: AnalysisConfig) -> np.ndarray:
    """Normalized autocorrelation at each YIN candidate period; not a probability.

    Mean removal and overlap-energy normalization avoid an RMS/amplitude gate.
    Only exact zero-energy frames necessarily score zero. No reference is used.
    """
    padded = np.pad(y, config.frame_length // 2)
    frames = librosa.util.frame(padded, frame_length=config.frame_length, hop_length=config.hop_length)
    scores = np.zeros(len(f0), dtype=np.float64)
    for i, hz in enumerate(f0):
        if not np.isfinite(hz) or hz <= 0:
            continue
        lag = min(max(round(config.sample_rate / hz), 1), config.frame_length - 1)
        frame = frames[:, i] - np.mean(frames[:, i])
        left, right = frame[:-lag], frame[lag:]
        denominator = np.sqrt(np.dot(left, left) * np.dot(right, right))
        if denominator > np.finfo(float).tiny:
            scores[i] = np.clip(np.dot(left, right) / denominator, 0, 1)
    return scores


class ClassicalEstimator:
    def __init__(self, identifier: str):
        self.identifier = identifier

    def analyze(self, audio: AudioData, config: AnalysisConfig, settings: EstimatorConfig) -> EstimatorOutput:
        start = perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", UserWarning)
            common = dict(sr=config.sample_rate, fmin=config.fmin, fmax=config.fmax,
                          frame_length=config.frame_length, hop_length=config.hop_length,
                          center=True, pad_mode="constant")
            if self.identifier == "pyin":
                candidate, voiced, score = librosa.pyin(
                    audio.samples, **common, resolution=config.resolution,
                    switch_prob=config.switch_prob, no_trough_prob=config.no_trough_prob,
                    max_transition_rate=config.max_transition_rate, fill_na=np.nan)
                if settings.pyin_voicing_threshold is not None:
                    voiced = voiced & (score >= settings.pyin_voicing_threshold)
                confidence = "pyin_voicing_probability"
                policy = "pYIN Viterbi flags; optional score threshold can only reject Viterbi-voiced frames"
            else:
                candidate = librosa.yin(audio.samples, **common, trough_threshold=settings.yin_trough_threshold)
                score = correlation_scores(audio.samples, candidate, config)
                voiced = (score >= settings.yin_voicing_threshold) & (score > 0)
                confidence = "normalized_autocorrelation"
                policy = "overlap-normalized autocorrelation at YIN candidate lag >= threshold, strictly positive energy"
        times = np.arange(len(candidate), dtype=np.float64) * config.hop_length / config.sample_rate
        return EstimatorOutput(self.identifier, version("librosa"), times, candidate, voiced.astype(bool), score,
                               confidence, config.sample_rate, 0.0, perf_counter() - start,
                               {"algorithm": f"librosa.{self.identifier}", "voicing_policy": policy,
                                "center": True, "pad_mode": "constant", "hop_length": config.hop_length,
                                "warnings": [str(w.message) for w in caught]})

