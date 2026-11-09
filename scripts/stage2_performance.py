#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Cold model startup and warmed 1/5/15-second CPU runs, isolated by invocation."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import resource
import tempfile
from time import perf_counter
import soundfile as sf
from vocalscope.backends import EstimatorConfig
from vocalscope.models import AnalysisConfig
from vocalscope.pitch import analyze_file,library_versions
from vocalscope.validation import make_case


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--estimator',choices=('pyin','yin','crepe'),required=True)
    p.add_argument('--model',choices=('tiny','full'),default='tiny')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    settings=EstimatorConfig(estimator_id=args.estimator,crepe_model=args.model)
    report={'status':'running','settings':asdict(settings),'versions':library_versions(),'platform':platform.platform(),
            'memory_semantics':'Linux process peak RSS, includes imports/model/JIT/previous clips, excludes parent GUI', 'measurements':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vocalscope-performance-') as directory:
        path=Path(directory)/'harmonic.wav'
        for index,duration in enumerate((1,1,5,15)):
            case=make_case('harmonics',duration=duration)
            sf.write(path,case.samples,case.sample_rate,subtype='FLOAT')
            start=perf_counter();r=analyze_file(path,AnalysisConfig(),settings);wall=perf_counter()-start
            row={'duration_seconds':duration,'cold_first_call':index==0,'total_processing_seconds':wall,
                 'initialization_seconds':r.initialization_seconds,'inference_seconds':r.runtime_seconds,
                 'runtime_over_audio_duration':wall/duration,'audio_duration_over_processing_time':duration/wall,
                 'peak_process_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                 'backend_metadata':r.backend_metadata}
            report['measurements'].append(row);print(row,flush=True)
            args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    report['status']='complete';args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()

