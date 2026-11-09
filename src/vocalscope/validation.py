# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Deterministic independent ground truth and explicit pitch/voicing metrics.

This module generates synthetic signals, not human-vocal accuracy claims.
The same time/voicing masks are used in pytest and the saved benchmark report.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import cumulative_trapezoid

from .models import AnalysisResult

SEED = 20261109


@dataclass(frozen=True)
class SyntheticCase:
    name: str
    samples: NDArray[np.float64]
    sample_rate: int
    truth_hz: Callable[[NDArray[np.float64]], NDArray[np.float64]]
    evaluation_mask: Callable[[NDArray[np.float64]], NDArray[np.bool_]]
    description: str


def phase_signal(frequency: NDArray[np.float64], sr: int, harmonics: tuple[float, ...] = (1.0,)) -> NDArray[np.float64]:
    """Integrate instantaneous frequency in Hz before synthesizing the carrier."""
    phase = 2 * np.pi * cumulative_trapezoid(frequency, dx=1 / sr, initial=0)
    y = sum(amplitude * np.sin((index + 1) * phase) for index, amplitude in enumerate(harmonics))
    peak = float(np.max(np.abs(y)))
    return np.asarray(0.6 * y / peak if peak else y, dtype=np.float64)


def make_case(name: str, *, duration: float = 2.0, sr: int = 22050) -> SyntheticCase:
    if duration < 1:
        raise ValueError("Validation cases require at least one second.")
    t = np.arange(round(duration * sr), dtype=np.float64) / sr
    margin = 0.25  # > half of a 4096-sample window at 22050 Hz, plus transition margin
    mask = lambda x: (x >= margin) & (x <= duration - margin)
    harmonics = (1.0,)
    description = ""
    if name in ("sine_A3", "sine_A4", "sine_C5", "boundary_C2", "boundary_C6", "detuned_A4", "soft_A4"):
        hz = {"sine_A3": 220.0, "sine_A4": 440.0, "sine_C5": 440 * 2 ** (3 / 12),
              "boundary_C2": 440 * 2 ** (-33/12), "boundary_C6": 440 * 2 ** (15/12),
              "detuned_A4": 440 * 2 ** (23.5/1200), "soft_A4": 440.0}[name]
        truth = lambda x: np.full_like(x, hz)
        description = f"{hz:.8g} Hz sinusoid"
    elif name in ("harmonics", "weak_fundamental", "missing_fundamental"):
        truth = lambda x: np.full_like(x, 220.0)
        harmonics = {"harmonics": (0.12, 0.65, 0.50), "weak_fundamental": (0.002, 0.65, 0.50), "missing_fundamental": (0.0, 0.65, 0.50)}[name]
        description = f"220 Hz periodicity, harmonic amplitudes {harmonics}"
    elif name in ("vibrato_3hz", "vibrato_5hz"):
        rate = 3 if name == "vibrato_3hz" else 5
        truth = lambda x: 440 * np.exp2(50 * np.sin(2 * np.pi * rate * x) / 1200)
        description = f"440 Hz, +/-50 cents at {rate} Hz, integrated phase"
    elif name == "glissando":
        truth = lambda x: 220 * np.exp2(x / duration)
        description = "Exponential 220 to 440 Hz slide, integrated phase"
    elif name in ("silence_gap", "rapid_transition"):
        if name == "silence_gap":
            truth = lambda x: np.where((x < duration / 3) | (x >= 2 * duration / 3), 220.0, np.nan)
            mask = lambda x: (x >= margin) & (x <= duration - margin) & (np.abs(x - duration / 3) > margin) & (np.abs(x - 2 * duration / 3) > margin)
            description = "220 Hz, equal-length exact silence gap, 220 Hz"
        else:
            truth = lambda x: np.where(x < duration / 2, 220.0, 440.0)
            mask = lambda x: (x >= margin) & (x <= duration - margin) & (np.abs(x - duration / 2) > margin)
            description = "Abrupt A3 to A4 transition (interior metrics exclude boundary)"
    elif name in ("silence", "noise_only"):
        truth = lambda x: np.full_like(x, np.nan)
        description = "Exact digital silence" if name == "silence" else "Seeded Gaussian noise, no tonal component"
    elif name.startswith("noise_snr_"):
        snr_db = float(name.removeprefix("noise_snr_"))
        truth = lambda x: np.full_like(x, 220.0)
        harmonics = (0.35, 0.65, 0.5)
        description = f"220 Hz harmonic signal plus seeded white Gaussian noise at measured {snr_db:g} dB SNR"
    else:
        raise ValueError(f"Unknown synthetic case: {name}")
    frequency = truth(t)
    y = phase_signal(np.nan_to_num(frequency, nan=220.0), sr, harmonics)
    y[~np.isfinite(frequency)] = 0
    rng = np.random.default_rng(SEED)
    if name == "noise_only":
        y = rng.normal(0, 0.1, len(t))
    elif name.startswith("noise_snr_"):
        noise = rng.normal(size=len(t))
        noise *= np.sqrt(np.mean(y * y) / np.mean(noise * noise)) * 10 ** (-snr_db / 20)
        y += noise
    elif name == "soft_A4":
        y *= 1e-5 / np.max(np.abs(y))
        description += ", peak -100 dBFS; no gain or gate"
    return SyntheticCase(name, y, sr, truth, mask, description)


CASE_NAMES = (
    "sine_A3", "sine_A4", "sine_C5", "harmonics", "weak_fundamental", "missing_fundamental",
    "silence_gap", "silence", "vibrato_3hz", "vibrato_5hz", "glissando", "rapid_transition",
    "noise_snr_30", "noise_snr_20", "noise_snr_10", "noise_snr_0", "noise_only", "soft_A4", "boundary_C2", "boundary_C6", "detuned_A4",
)


def evaluate(result: AnalysisResult, truth_hz: NDArray[np.float64], mask: NDArray[np.bool_] | None = None) -> dict[str, int | float | None]:
    """Evaluate aligned ground truth; all rates are fractions in [0, 1].

    Absolute cents errors and gross octave errors use mutually voiced frames.
    RPA50 = reference voiced frames detected voiced AND within 50 cents, divided
    by all reference voiced frames. Missed voicing counts against RPA50.
    Gross octave error = within 50 cents of a nonzero integer octave displacement.
    Also report gross pitch error > 50 cents to expose non-octave failures.
    """
    truth = np.asarray(truth_hz, dtype=np.float64)
    if truth.shape != result.f0_hz.shape:
        raise ValueError("Ground truth must align with analysis frame timestamps.")
    if np.any(np.isinf(truth) | (truth <= 0)):
        raise ValueError("Ground truth must be positive Hz or NaN for unvoiced.")
    use = np.ones_like(result.voiced) if mask is None else np.asarray(mask, dtype=bool)
    if use.shape != truth.shape:
        raise ValueError("Evaluation mask must align with frames.")
    ref_voiced = np.isfinite(truth) & use
    ref_unvoiced = ~np.isfinite(truth) & use
    common = ref_voiced & result.voiced
    signed_cents = 1200 * np.log2(result.f0_hz[common] / truth[common])
    errors = np.abs(signed_cents)
    octave = np.rint(signed_cents / 1200)
    octave_error = (octave != 0) & (np.abs(signed_cents - 1200 * octave) <= 50)
    nv, nu, nc = int(ref_voiced.sum()), int(ref_unvoiced.sum()), int(common.sum())
    return {
        "evaluated_frames": int(use.sum()), "reference_voiced_frames": nv,
        "reference_unvoiced_frames": nu, "mutually_voiced_frames": nc,
        "median_absolute_error_cents": float(np.median(errors)) if nc else None,
        "mean_absolute_error_cents": float(np.mean(errors)) if nc else None,
        "gross_octave_error_rate": float(octave_error.mean()) if nc else None,
        "gross_pitch_error_rate_50c": float(np.mean(errors > 50)) if nc else None,
        "voiced_frame_recall": nc / nv if nv else None,
        "false_voicing_rate": int((ref_unvoiced & result.voiced).sum()) / nu if nu else None,
        "raw_pitch_accuracy_50c": int(np.count_nonzero(errors <= 50)) / nv if nv else None,
    }

