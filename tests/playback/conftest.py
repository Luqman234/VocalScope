# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

@pytest.fixture
def gst_available():
    try:
        from vocalscope.playback.gst import bindings
        bindings()
    except Exception as exc:pytest.skip(str(exc))

@pytest.fixture
def impulse_files(tmp_path,gst_available):
    paths=[]
    for rate,channel,extension in [(44100,0,'wav'),(48000,1,'flac')]:
        y=np.zeros((rate*3,2),dtype=np.float32)
        for second in [.25,.75,1.25,2.25]:y[round(second*rate),channel]=.25
        path=tmp_path/f'{channel}.{extension}';sf.write(path,y,rate,subtype='FLOAT' if extension=='wav' else 'PCM_24');paths.append(path)
    return paths
