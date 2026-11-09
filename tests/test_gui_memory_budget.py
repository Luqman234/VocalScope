# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Headless CLI validation and real isolated-worker DSP admission policy."""

from dataclasses import replace
import json
import subprocess
import sys
from types import ModuleType

import numpy as np
import pytest

from vocalscope.cli import main
from vocalscope.errors import ConfigurationError, VocalScopeError
from vocalscope.models import AnalysisConfig
from vocalscope.worker import analyze_in_process, transcribe_in_process


@pytest.mark.parametrize("arguments,expected", [
    ([], 1024), (["--max-memory-mb", "2048"], 2048),
    (["--max-memory-mb", "512.5"], 512.5), (["--max-memory-mb", "4096"], 4096),
])
def test_gui_cli_passes_validated_initial_budget(monkeypatch, arguments, expected):
    gui = ModuleType("vocalscope.gui")
    received = []
    gui.run = lambda **kwargs: received.append(kwargs) or 0
    monkeypatch.setitem(sys.modules, "vocalscope.gui", gui)
    assert main(["gui", *arguments]) == 0
    assert received == [{"max_memory_mb": expected}]


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_gui_cli_invalid_budget_rejected_before_gtk_import(value):
    code = ('from vocalscope.cli import main; import sys; '
            'rc=main(sys.argv[1:]); '
            'assert "vocalscope.gui" not in sys.modules; '
            'assert "gi" not in sys.modules; raise SystemExit(rc)')
    completed = subprocess.run(
        [sys.executable, "-c", code, "gui", f"--max-memory-mb={value}"],
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 2, completed.stderr
    assert "max_memory_mb must be positive and finite" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_gui_cli_help_documents_memory_policy():
    completed = subprocess.run([sys.executable, "-m", "vocalscope", "gui", "--help"],
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0
    assert "--max-memory-mb" in completed.stdout
    help_text = " ".join(completed.stdout.split())
    assert "1024" in help_text and "Not allocated memory" in help_text
    with pytest.raises(SystemExit) as exc:
        main(["gui", "--max-memory-mb", "nonsense"])
    assert exc.value.code == 2


@pytest.mark.parametrize("budget", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_memory_budget_validation_shared_with_dsp(budget):
    with pytest.raises(ConfigurationError, match="max_memory_mb must be positive and finite"):
        AnalysisConfig(max_memory_mb=budget)


def test_1522_mib_estimate_admitted_only_with_larger_budget():
    # Find the sample count mathematically; no 1.5 GiB allocation is needed.
    config = AnalysisConfig()
    low, high = 0, int(config.max_duration_seconds * config.sample_rate)
    while low < high:
        middle = (low + high) // 2
        if config.estimated_working_bytes(middle) < 1522 * 1024**2:
            low = middle + 1
        else:
            high = middle
    assert round(config.estimated_working_bytes(low) / 1024**2) == 1522
    with pytest.raises(ConfigurationError) as exc:
        config.validate_resources(low)
    message = str(exc.value)
    for text in ("1522 MiB", "1024 MiB", "Maximum DSP memory (MiB)",
                 "Analysis parameters", "--max-memory-mb", "not allocated process memory"):
        assert text in message
    replace(config, max_memory_mb=2048).validate_resources(low)


def test_actual_analysis_worker_retains_increased_budget(analyzed_case):
    _, baseline = analyzed_case("sine_A4")
    requested = replace(baseline.config, max_memory_mb=2048)
    result = analyze_in_process(baseline.metadata.path, requested)
    assert result.config == requested
    np.testing.assert_array_equal(result.f0_hz, baseline.f0_hz)
    with pytest.raises(VocalScopeError, match="configured budget is 1 MiB"):
        analyze_in_process(baseline.metadata.path, replace(requested, max_memory_mb=1))


def test_actual_note_worker_uses_current_budget_without_rewriting_f0(tmp_path, analyzed_case):
    from vocalscope.export import result_document
    from vocalscope.transcription.serialization import save_project, load_project

    _, baseline = analyzed_case("sine_A4")
    # The GUI obtains its acoustic result from this worker, including the
    # source identity which existing project construction already preserves.
    baseline = analyze_in_process(baseline.metadata.path, baseline.config)
    original = json.loads(json.dumps(result_document(baseline), allow_nan=False))
    with pytest.raises(VocalScopeError, match="configured budget is 1 MiB"):
        transcribe_in_process(baseline, max_memory_mb=1)
    result = transcribe_in_process(baseline, max_memory_mb=2048)
    assert result.timings["dsp_resource_policy"]["max_memory_mb"] == 2048
    assert "not allocated memory" in result.timings["dsp_resource_policy"]["semantics"]
    assert len(result.notes) == 1 and result.notes[0].midi_note == 69
    assert result.acoustic.config.max_memory_mb == 1024
    assert json.loads(json.dumps(result_document(result.acoustic), allow_nan=False)) == original
    assert json.loads(json.dumps(result_document(baseline), allow_nan=False)) == original
    np.testing.assert_array_equal(result.acoustic.f0_hz, baseline.f0_hz)
    save_project(result, tmp_path / "notes.json")
    restored = load_project(tmp_path / "notes.json")
    assert restored.timings["dsp_resource_policy"] == result.timings["dsp_resource_policy"]
    assert restored.notes == result.notes
    legacy = transcribe_in_process(baseline)
    assert legacy.timings["dsp_resource_policy"]["max_memory_mb"] == 1024
    for budget in (0, float("nan"), float("inf")):
        with pytest.raises(ConfigurationError, match="max_memory_mb"):
            transcribe_in_process(baseline, max_memory_mb=budget)
