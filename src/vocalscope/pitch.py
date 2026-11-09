# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Backend orchestration and note conversion; pYIN is the unchanged default."""

from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
import platform

import numpy as np

from . import __version__
from .audio import load_audio
from .backends import EstimatorConfig, EstimatorOutput, get_estimator
from .errors import ConfigurationError, VocalScopeError
from .models import AnalysisConfig, AnalysisResult, AudioData
from .notes import hz_to_midi, note_measurements


def library_versions() -> dict[str, str]:
    return {"vocalscope": __version__, "python": platform.python_version(),
            **{name: version(name) for name in ("numpy", "scipy", "librosa", "soundfile", "matplotlib", "numba")}}


def estimate_audio(audio: AudioData, config: AnalysisConfig, settings: EstimatorConfig) -> EstimatorOutput:
    if audio.sample_rate != config.sample_rate:
        raise ConfigurationError("Audio sample rate does not match analysis config; reload with the selected config.")
    y = audio.samples
    if y.ndim != 1 or not y.size or not np.all(np.isfinite(y)):
        raise VocalScopeError("Analysis requires nonempty, finite mono audio.")
    config.validate_resources(len(y))
    try:
        output = get_estimator(settings.estimator_id).analyze(audio, config, settings)
    except (ValueError, FloatingPointError) as exc:
        raise VocalScopeError(f"{settings.estimator_id} analysis failed: {exc}") from exc
    return output


def to_analysis_result(audio: AudioData, config: AnalysisConfig, settings: EstimatorConfig, output: EstimatorOutput) -> AnalysisResult:
    f0 = output.f0_hz
    midi = hz_to_midi(f0, config.a4_hz)
    names, cents = note_measurements(midi)
    notices = [*audio.metadata.warnings, *output.metadata.get("warnings", [])]
    if len(audio.samples) < config.frame_length:
        notices.append("Short clip: every centered analysis window includes zero padding; pitch is unreliable.")
    probability = output.score if output.estimator_id == "pyin" else np.full(len(f0), np.nan)
    return AnalysisResult(
        audio.metadata, config, len(audio.samples), output.times, f0, output.voiced, probability,
        midi, names, cents, output.inference_seconds, library_versions(), tuple(dict.fromkeys(notices)),
        estimator_id=output.estimator_id, estimator_version=output.estimator_version,
        estimator_configuration=asdict(settings), confidence_type=output.confidence_type,
        confidence=output.score, backend_metadata={**output.metadata, "analysis_sample_rate": output.sample_rate},
        initialization_seconds=output.initialization_seconds,
    )


def analyze_audio(audio: AudioData, config: AnalysisConfig | None = None, settings: EstimatorConfig | None = None) -> AnalysisResult:
    config = config or AnalysisConfig(sample_rate=audio.sample_rate)
    settings = settings or EstimatorConfig()
    return to_analysis_result(audio, config, settings, estimate_audio(audio, config, settings))


def analyze_file(path: str | Path, config: AnalysisConfig | None = None, settings: EstimatorConfig | None = None) -> AnalysisResult:
    config = config or AnalysisConfig()
    return analyze_audio(load_audio(path, config), config, settings)
