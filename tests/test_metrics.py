# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from dataclasses import replace

import numpy as np
import pytest

from vocalscope.notes import hz_to_midi, note_measurements
from vocalscope.validation import evaluate, make_case


def test_metrics_count_missed_voicing_and_octave_errors(analyzed_case):
    _, result = analyzed_case("sine_A4")
    n = len(result.voiced)
    f0 = np.full(n, 440.0)
    voiced = np.ones(n, dtype=bool)
    # Known independent errors: octave at frame 0, false unvoiced at 1, false voiced at 2.
    f0[0] = 880
    voiced[1] = False
    f0[1] = np.nan
    midi = hz_to_midi(f0)
    names, cents = note_measurements(midi)
    altered = replace(result, f0_hz=f0, voiced=voiced, midi_pitch=midi, nearest_note=names, cents_deviation=cents)
    truth = np.full(n, 440.0)
    truth[2] = np.nan
    metrics = evaluate(altered, truth)
    assert metrics["false_voicing_rate"] == 1
    assert metrics["voiced_frame_recall"] == pytest.approx((n-2)/(n-1))
    assert metrics["raw_pitch_accuracy_50c"] == pytest.approx((n-3)/(n-1))
    assert metrics["gross_octave_error_rate"] == pytest.approx(1/(n-2))


def test_phase_integration_and_reproducible_noise():
    first = make_case("noise_snr_10")
    second = make_case("noise_snr_10")
    np.testing.assert_array_equal(first.samples, second.samples)
    case = make_case("glissando")
    # Independent zero-crossing periods increase in frequency over time.
    crossings = np.flatnonzero((case.samples[:-1] <= 0) & (case.samples[1:] > 0))
    intervals = np.diff(crossings)
    assert np.median(intervals[:30]) > np.median(intervals[-30:])

