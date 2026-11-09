# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import numpy as np
import pytest

from vocalscope.validation import evaluate

pytestmark = pytest.mark.scientific


@pytest.mark.parametrize("name", ["sine_A3", "sine_A4", "sine_C5", "boundary_C2", "boundary_C6", "detuned_A4"])
def test_sine_accuracy(analyzed_case, name):
    case, result = analyzed_case(name)
    metrics = evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))
    assert metrics["median_absolute_error_cents"] < 15
    assert metrics["voiced_frame_recall"] >= 0.95
    assert metrics["raw_pitch_accuracy_50c"] >= 0.95


@pytest.mark.parametrize("name", ["harmonics", "weak_fundamental", "missing_fundamental"])
def test_fundamental_despite_stronger_harmonics(analyzed_case, name):
    case, result = analyzed_case(name)
    metrics = evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))
    assert metrics["median_absolute_error_cents"] < 15
    assert metrics["gross_octave_error_rate"] == 0
    assert metrics["raw_pitch_accuracy_50c"] >= 0.9


@pytest.mark.parametrize("name", ["silence", "silence_gap", "noise_only"])
def test_unvoiced_regions(analyzed_case, name):
    case, result = analyzed_case(name)
    metrics = evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))
    assert metrics["reference_unvoiced_frames"] > 0
    assert metrics["false_voicing_rate"] < 0.1
    assert np.all(np.isnan(result.f0_hz[~result.voiced]))
    assert np.all(np.isnan(result.midi_pitch[~result.voiced]))


@pytest.mark.parametrize("name", ["vibrato_3hz", "vibrato_5hz"])
def test_vibrato_trajectory_is_retained(analyzed_case, name):
    case, result = analyzed_case(name)
    truth = case.truth_hz(result.time_seconds)
    use = case.evaluation_mask(result.time_seconds) & result.voiced
    estimated = 1200 * np.log2(result.f0_hz[use] / 440)
    reference = 1200 * np.log2(truth[use] / 440)
    assert np.corrcoef(estimated, reference)[0, 1] > 0.8
    assert estimated.std() / reference.std() > 0.6
    metrics = evaluate(result, truth, case.evaluation_mask(result.time_seconds))
    assert metrics["median_absolute_error_cents"] < 35


def test_glissando(analyzed_case):
    case, result = analyzed_case("glissando")
    metrics = evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))
    assert metrics["median_absolute_error_cents"] < 25
    assert metrics["voiced_frame_recall"] >= 0.9


def test_rapid_transition_interiors(analyzed_case):
    case, result = analyzed_case("rapid_transition")
    metrics = evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))
    assert metrics["median_absolute_error_cents"] < 15
    assert metrics["raw_pitch_accuracy_50c"] > 0.9


@pytest.mark.parametrize("snr", [30, 20, 10, 0])
def test_noise_experiment_is_measurable(analyzed_case, snr):
    case, result = analyzed_case(f"noise_snr_{snr}")
    metrics = evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))
    assert metrics["reference_voiced_frames"] > 0
    assert 0 <= metrics["voiced_frame_recall"] <= 1
    # Only a high-SNR accuracy regression is prescribed; lower-SNR outcomes are reported, not assumed.
    if snr == 30:
        assert metrics["raw_pitch_accuracy_50c"] >= 0.9


def test_soft_tone_is_not_silence_gated(analyzed_case):
    case, result = analyzed_case("soft_A4")
    metrics = evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))
    assert metrics["voiced_frame_recall"] >= 0.9
    assert metrics["median_absolute_error_cents"] < 15
    assert any("low amplitude" in message for message in result.warnings)

