# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Continuous equal-temperament conversions, with configurable concert A."""

import math
import re

import numpy as np
from numpy.typing import ArrayLike, NDArray

_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _tuning(a4_hz: float) -> None:
    if not math.isfinite(a4_hz) or a4_hz <= 0:
        raise ValueError("A4 tuning must be a positive finite frequency in Hz.")


def hz_to_midi(frequency: ArrayLike, a4_hz: float = 440.0) -> NDArray[np.float64]:
    """Return continuous MIDI; NaN denotes missing F0. Reject invalid frequencies."""
    _tuning(a4_hz)
    f = np.asarray(frequency, dtype=np.float64)
    if np.any(np.isinf(f) | (f <= 0)):
        raise ValueError("Frequencies must be positive and finite, or NaN for missing F0.")
    return 69.0 + 12.0 * np.log2(f / a4_hz)


def midi_to_hz(midi: ArrayLike, a4_hz: float = 440.0) -> NDArray[np.float64]:
    _tuning(a4_hz)
    return a4_hz * np.exp2((np.asarray(midi, dtype=np.float64) - 69.0) / 12.0)


def note_name(midi: int) -> str:
    """Scientific pitch notation, sharps, C4 = MIDI 60."""
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def note_measurements(midi: NDArray[np.float64]) -> tuple[list[str | None], NDArray[np.float64]]:
    """Nearest note and signed cents; exact halfway ties use NumPy ties-to-even."""
    rounded = np.rint(midi)
    return [note_name(int(m)) if np.isfinite(m) else None for m in rounded], 100.0 * (midi - rounded)


def parse_frequency(value: str, a4_hz: float = 440.0) -> float:
    """Accept positive Hz or scientific note names, e.g. C2, Bb3, F#4."""
    _tuning(a4_hz)
    value = value.strip()
    try:
        hz = float(value)
    except ValueError:
        match = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", value)
        if not match:
            raise ValueError(f"Invalid frequency {value!r}; use Hz or a note such as C2 or Bb3.") from None
        letter, accidental, octave = match.groups()
        midi = 12 * (int(octave) + 1) + _SEMITONES[letter.upper()] + {"": 0, "#": 1, "b": -1}[accidental]
        try:
            hz = a4_hz * 2.0 ** ((midi - 69) / 12)
        except OverflowError:
            raise ValueError("Note frequency is out of range.") from None
    if not math.isfinite(hz) or hz <= 0:
        raise ValueError("Frequency must be positive and finite.")
    return hz

