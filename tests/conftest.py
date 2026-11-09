# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from pathlib import Path

import pytest
import soundfile as sf


def pytest_addoption(parser):
    parser.addoption('--run-output',action='store_true',default=False,help='Allow a short low-gain output test on the existing PipeWire session.')
    parser.addoption('--soundfont',default=None,help='Explicit local SoundFont for optional real synthesis tests; never downloads.')
    parser.addoption('--run-neural',action='store_true',default=False,help='Run optional installed-model CPU tests; never downloads weights.')


def pytest_collection_modifyitems(config,items):
    if not config.getoption('--run-output'):
        for item in items:
            if 'audio_output' in item.keywords:item.add_marker(pytest.mark.skip(reason='Real output requires --run-output.'))
    if not config.getoption('--run-neural'):
        for item in items:
            if 'neural' in item.keywords:
                item.add_marker(pytest.mark.skip(reason='Optional neural integration: run with --run-neural (no downloads).'))

from vocalscope.models import AnalysisConfig
from vocalscope.pitch import analyze_file
from vocalscope.validation import make_case


@pytest.fixture(scope="session")
def analyzed_case(tmp_path_factory):
    """Cache real pYIN runs per deterministic signal across scientific/export tests."""
    directory = tmp_path_factory.mktemp("signals")
    cache = {}

    def get(name: str):
        if name not in cache:
            case = make_case(name, duration=3 if name == "silence_gap" else 2)
            path = directory / f"{name}.wav"
            sf.write(path, case.samples, case.sample_rate, subtype="FLOAT")
            cache[name] = case, analyze_file(path, AnalysisConfig())
        return cache[name]

    return get



@pytest.fixture(scope="session")
def soundfont_path(request):
    import importlib.util,ctypes.util
    if importlib.util.find_spec('fluidsynth') is None or ctypes.util.find_library('fluidsynth') is None:
        pytest.skip('Optional pyfluidsynth/libfluidsynth not installed')
    explicit=request.config.getoption('--soundfont')
    if explicit:
        path=Path(explicit)
        if not path.is_file():pytest.fail(f'Explicit SoundFont is missing: {path}')
        return path.resolve()
    from vocalscope.synthesis.soundfont import resolve_soundfont
    from vocalscope.synthesis.models import SynthesisError
    try:return resolve_soundfont()
    except SynthesisError as exc:pytest.skip('Real synthesis requires --soundfont: '+str(exc))
