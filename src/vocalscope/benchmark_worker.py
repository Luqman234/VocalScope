# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""One persistent isolated process per backend, serial tracks, JSONL progress."""

import json
from dataclasses import asdict
from pathlib import Path
import resource
import sys
from time import perf_counter
from .audio import load_audio
from .backends import EstimatorConfig
from .datasets import digest
from .models import AnalysisConfig
from .pitch import estimate_audio
from .prediction_cache import PredictionCache, prediction_key


def main():
    request=json.load(sys.stdin)
    config=AnalysisConfig(**request['config'])
    settings=EstimatorConfig(**request['settings'])
    cache=PredictionCache(request['cache'])
    for job in request['jobs']:
        try:
            if digest(Path(job['path'])) != job['audio_sha256']:
                raise ValueError('Audio changed since the dataset manifest was validated.')
            key=prediction_key(job['audio_sha256'],config,settings)
            start=perf_counter()
            hit=cache.load(key) if request.get('resume',True) else None
            if hit is None:
                audio=load_audio(job['path'],config)
                output=estimate_audio(audio,config,settings)
                elapsed=perf_counter()-start
                timing={'total_processing_seconds':elapsed,'initialization_seconds':output.initialization_seconds,
                        'inference_seconds':output.inference_seconds,
                        'peak_process_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                        'audio_duration_over_processing_time':audio.metadata.duration_seconds/elapsed,
                        'runtime_over_audio_duration':elapsed/audio.metadata.duration_seconds,
                        'timing_semantics':'load+estimation; process RSS high water includes earlier tracks; excludes worker interpreter startup'}
                cache.save(key,output,timing)
            else:
                output,timing=hit
            row={'track_id':job['track_id'],'estimator':settings.estimator_id,'status':'ok','cache_key':key,
                 'cached':hit is not None,'cache_lookup_seconds':perf_counter()-start if hit is not None else None,
                 'timing':timing,'backend_metadata':output.metadata,'confidence_type':output.confidence_type,
                 'estimator_version':output.estimator_version,'estimator_configuration':asdict(settings)}
        except Exception as exc:
            row={'track_id':job['track_id'],'estimator':settings.estimator_id,'status':'failed',
                 'error':f'{type(exc).__name__}: {exc}'}
        print(json.dumps(row,allow_nan=False),flush=True)


if __name__=='__main__':
    main()

