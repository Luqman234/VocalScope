# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import csv
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from vocalscope.errors import VocalScopeError
from vocalscope.export import export_bundle, result_document, result_from_document
from vocalscope.models import AnalysisConfig
from vocalscope.plotting import create_figure


def test_export_equivalence_and_no_nan(tmp_path, analyzed_case):
    _, result = analyzed_case("silence_gap")
    paths = export_bundle(result, tmp_path)
    text = paths["json"].read_text()
    document = json.loads(text, parse_constant=lambda value: pytest.fail(f"Non-standard JSON {value}"))
    restored = result_from_document(document)
    np.testing.assert_array_equal(restored.f0_hz, result.f0_hz)
    np.testing.assert_array_equal(restored.midi_pitch, result.midi_pitch)
    assert restored.config == result.config
    assert document["schema_version"] == "1.1.0"
    assert "not calibrated" in document["semantics"]["voiced_probability"]
    assert document["source"]["original_frames"] == result.metadata.original_frames
    with paths["csv"].open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(document["frames"]) == len(result.time_seconds)
    assert paths["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    for csv_row, json_row in zip(rows, document["frames"], strict=True):
        for key, value in json_row.items():
            if value is None:
                assert csv_row[key] == ""
            elif isinstance(value, bool):
                assert (csv_row[key] == "true") == value
            elif isinstance(value, (int, float)):
                assert float(csv_row[key]) == pytest.approx(value, rel=1e-14, abs=1e-14)
            else:
                assert csv_row[key] == value
    np.testing.assert_allclose([r["time_seconds"] for r in document["frames"]], result.time_seconds, atol=0, rtol=0)
    np.testing.assert_allclose(np.diff(result.time_seconds), result.config.hop_length / result.config.sample_rate)
    assert result.time_seconds[0] == 0
    assert result.time_seconds[-1] <= result.analysis_samples / result.config.sample_rate


def test_exports_protect_existing_files_and_source(tmp_path, analyzed_case):
    _, result = analyzed_case("sine_A4")
    paths = export_bundle(result, tmp_path, formats=("json",))
    with pytest.raises(VocalScopeError, match="already exists"):
        export_bundle(result, tmp_path, formats=("json",))
    export_bundle(result, tmp_path, formats=("json",), overwrite=True)
    assert json.loads(paths["json"].read_text())["frames"]
    metadata = replace(result.metadata, path=str(tmp_path / "sine_A4.json"))
    with pytest.raises(VocalScopeError, match="source recording"):
        export_bundle(replace(result, metadata=metadata), tmp_path, formats=("json",), overwrite=True)


def test_result_invariants_and_nan_serialization(analyzed_case):
    _, result = analyzed_case("sine_A4")
    with pytest.raises(ValueError, match="equally sized"):
        replace(result, voiced=result.voiced[:-1])
    bad = result.voiced_probability.copy()
    bad[0] = np.nan
    with pytest.raises(ValueError, match="probabilities"):
        replace(result, voiced_probability=bad)
    # All-silent exports use standard JSON null, never invent a pitch.
    _, silence = analyzed_case("silence")
    json.dumps(result_document(silence), allow_nan=False)


def test_plot_retains_gaps_and_fractional_pitch(analyzed_case):
    _, result = analyzed_case("silence_gap")
    figure = create_figure(result, dark=True)
    actual = figure.axes[0].lines[0].get_ydata()
    np.testing.assert_array_equal(actual, result.midi_pitch)
    assert np.any(np.isnan(actual))
    assert len(figure.axes) == 2


def test_cli_help_and_error_codes():
    for args in (["--help"], ["analyze", "--help"], ["--version"]):
        completed = subprocess.run([sys.executable, "-m", "vocalscope", *args], capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, completed.stderr
    completed = subprocess.run([sys.executable, "-m", "vocalscope", "analyze", "/nonexistent.wav"], capture_output=True, text=True, timeout=60)
    assert completed.returncode == 2
    assert "Cannot decode" in completed.stderr


def test_headless_cli_actual_analysis(tmp_path, analyzed_case):
    _, result = analyzed_case("sine_A4")
    env = {**os.environ, "DISPLAY": "", "WAYLAND_DISPLAY": "", "MPLBACKEND": "GTK4Agg"}
    code = "from vocalscope.cli import main; import sys; rc=main(sys.argv[1:]); assert 'gi' not in sys.modules; assert 'vocalscope.gui' not in sys.modules; raise SystemExit(rc)"
    completed = subprocess.run([sys.executable, "-c", code, "analyze", result.metadata.path, "--output", str(tmp_path), "--fmin", "C2", "--fmax", "C6", "--formats", "json", "csv", "png"], env=env, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert len(list(tmp_path.glob("*"))) == 3
    doc = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert doc["summary"]["voiced_frame_fraction"] > 0.9

