# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Versioned, atomic, non-executable prediction caches; timing provenance retained."""

from dataclasses import asdict
from functools import lru_cache
import hashlib
from importlib.metadata import version, PackageNotFoundError
from importlib.util import find_spec
import json
import os
from pathlib import Path
import tempfile
import numpy as np
from . import __version__
from .backends import EstimatorConfig, EstimatorOutput
from .models import AnalysisConfig
from .datasets import digest


@lru_cache(maxsize=8)
def _model_digest(path: str, size: int, mtime: int) -> str:
    return digest(Path(path))


def prediction_key(audio_sha256: str, config: AnalysisConfig, settings: EstimatorConfig) -> str:
    modules = ['numpy','scipy','librosa','numba']
    identity = {}
    if settings.estimator_id == 'crepe':
        modules += ['torch','torchaudio','torchcrepe']
        spec = find_spec('torchcrepe')
        asset = Path(spec.origin).parent/'assets'/f'{settings.crepe_model}.pth' if spec else None
        if asset is not None and asset.exists():
            stat = asset.stat()
            identity['model_sha256'] = _model_digest(str(asset),stat.st_size,stat.st_mtime_ns)
    for name in modules:
        try: identity[name] = version(name)
        except PackageNotFoundError: identity[name] = 'unavailable'
    root = Path(__file__).parent
    code = [root/n for n in ('audio.py','preprocessing.py','models.py','pitch.py')]
    code += sorted((root/'backends').glob('*.py'))
    payload = {'cache_schema':1,'software':__version__,'audio_sha256':audio_sha256,
               'analysis':asdict(config),'estimator':asdict(settings),'versions':identity,
               'code':{p.name:digest(p) for p in code}}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()


class PredictionCache:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True,exist_ok=True)

    def path(self,key: str) -> Path:
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid cache key.')
        return self.directory/f'{key}.npz'

    def load(self,key: str) -> tuple[EstimatorOutput,dict] | None:
        try:
            with np.load(self.path(key),allow_pickle=False) as z:
                info=json.loads(str(z['metadata']))
                output=EstimatorOutput(times=z['times'],candidates=z['candidates'],voiced=z['voiced'],score=z['score'],**info['output'])
                return output,info['timing']
        except (OSError,ValueError,KeyError,EOFError):
            return None

    def save(self,key: str,output: EstimatorOutput,timing: dict) -> None:
        metadata={name:getattr(output,name) for name in ('estimator_id','estimator_version','confidence_type','sample_rate','initialization_seconds','inference_seconds','metadata')}
        descriptor, temporary = tempfile.mkstemp(prefix='.prediction-',suffix='.npz',dir=self.directory)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                np.savez_compressed(stream,times=output.times,candidates=output.candidates,voiced=output.voiced,score=output.score,
                                    metadata=np.asarray(json.dumps({'output':metadata,'timing':timing},allow_nan=False)))
            os.replace(temporary,self.path(key))
        finally:
            Path(temporary).unlink(missing_ok=True)

