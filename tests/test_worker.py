# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from threading import Event

import numpy as np
import pytest

from vocalscope.errors import VocalScopeError
from vocalscope.worker import analyze_in_process


def test_isolated_worker_round_trip(analyzed_case):
    _, reference = analyzed_case("sine_A4")
    result = analyze_in_process(reference.metadata.path, reference.config)
    assert result.config == reference.config
    assert result.metadata == reference.metadata
    np.testing.assert_array_equal(result.f0_hz, reference.f0_hz)
    np.testing.assert_array_equal(result.voiced, reference.voiced)
    np.testing.assert_array_equal(result.voiced_probability, reference.voiced_probability)


def test_isolated_worker_propagates_input_errors(tmp_path):
    from vocalscope.models import AnalysisConfig
    with pytest.raises(VocalScopeError, match="Cannot decode"):
        analyze_in_process(tmp_path / "missing.wav", AnalysisConfig())


def test_isolated_worker_cancellation(analyzed_case):
    _, reference = analyzed_case("sine_A4")
    cancelled = Event()
    cancelled.set()
    with pytest.raises(VocalScopeError, match="cancelled"):
        analyze_in_process(reference.metadata.path, reference.config, cancelled)

