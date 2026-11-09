# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Same audio-to-notes engine for CLI, evaluation, and process-isolated GUI."""
from time import perf_counter
from pathlib import Path
from ..audio import load_audio
from ..pitch import analyze_audio
from ..models import AnalysisConfig
from ..backends import EstimatorConfig
from ..datasets import digest
from .models import TranscriptionConfig,TranscriptionResult
from .onsets import extract_features
from .segmentation import segments
from . import ALGORITHM_VERSION


def transcribe_analysis(audio,acoustic,config=None,*,features=None,source_sha256=None):
    config=config or TranscriptionConfig();begin=perf_counter()
    if audio.sample_rate!=acoustic.config.sample_rate or len(audio.samples)!=acoustic.analysis_samples:raise ValueError('Audio and analysis sample grids differ.')
    if abs(audio.metadata.duration_seconds-acoustic.metadata.duration_seconds)>1e-8:
        raise ValueError('Audio and acoustic analysis durations differ.')
    features=features or extract_features(audio,config.onset_threshold)
    identity=source_sha256 or digest(Path(audio.metadata.path))
    expected=acoustic.backend_metadata.get('source_sha256')
    if expected and expected!=identity:raise ValueError('Audio changed since pitch analysis.')
    notes,boundaries,timing=segments(acoustic,features,config,identity)
    timing.update(features.timings)
    timing.update({'cached_pitch_to_notes_seconds':perf_counter()-begin,'algorithm_version':ALGORITHM_VERSION,'features':features.configuration})
    return TranscriptionResult(acoustic,identity,config,notes,boundaries,timing)


def transcribe_file(path,analysis_config=None,settings=None,config=None):
    begin=perf_counter();analysis_config=analysis_config or AnalysisConfig()
    identity=digest(Path(path))
    audio=load_audio(path,analysis_config);acoustic=analyze_audio(audio,analysis_config,settings or EstimatorConfig())
    if digest(Path(path))!=identity:raise ValueError('Audio changed during transcription.')
    result=transcribe_analysis(audio,acoustic,config,source_sha256=identity)
    result.timings.update({'audio_to_notes_seconds':perf_counter()-begin,'estimator_seconds':acoustic.runtime_seconds,'model_initialization_seconds':acoustic.initialization_seconds})
    return result
