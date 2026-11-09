#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Run each backend in a separate process invocation for synthetic stress evidence."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import resource
import tempfile
import numpy as np
import soundfile as sf
from vocalscope.backends import EstimatorConfig
from vocalscope.evaluation import align_frames,metrics
from vocalscope.models import AnalysisConfig
from vocalscope.pitch import analyze_file,library_versions
from vocalscope.stress import stress_cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--estimator',choices=('pyin','yin','crepe'),required=True)
    parser.add_argument('--model',choices=('tiny','full'),default='tiny')
    parser.add_argument('--no-trough-prob',type=float,default=.001)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    config=AnalysisConfig(no_trough_prob=args.no_trough_prob)
    settings=EstimatorConfig(estimator_id=args.estimator,crepe_model=args.model)
    cases=stress_cases();report={'status':'running','signal_count':len(cases),'seeds':[7,91,20261109],
                               'analysis':asdict(config),'settings':asdict(settings),'versions':library_versions(),'cases':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vocalscope-stress-') as directory:
        path=Path(directory)/'synthetic.wav'
        for case in cases:
            sf.write(path,case.samples,case.sample_rate,subtype='FLOAT')
            try:
                result=analyze_file(path,config,settings)
                duration=len(case.samples)/case.sample_rate
                reference_times=np.arange(0,duration,.01)
                truth=np.nan_to_num(case.truth_hz(reference_times),nan=0.)
                f0,voiced,coverage=align_frames(result.time_seconds,result.f0_hz,result.voiced,reference_times,duration)
                interior=case.evaluation_mask(reference_times)
                row={'case':case.name,'description':case.description,'status':'ok','duration_seconds':duration,
                     'full_clip':metrics(truth,f0,voiced),'interior':metrics(truth[interior],f0[interior],voiced[interior]),
                     'initialization_seconds':result.initialization_seconds,'inference_seconds':result.runtime_seconds,
                     'peak_process_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
                common=interior&voiced&(truth>0)
                if case.name.startswith('vibrato') and common.sum()>3:
                    rate=3 if '3hz' in case.name else 5
                    x=reference_times[common]
                    cents=1200*np.log2(f0[common]/440)
                    reference=1200*np.log2(truth[common]/440)
                    design=np.column_stack([np.sin(2*np.pi*rate*x),np.cos(2*np.pi*rate*x),np.ones_like(x)])
                    coefficients=np.linalg.lstsq(design,cents,rcond=None)[0]
                    row['vibrato_fitted_amplitude_ratio']=float(np.hypot(*coefficients[:2])/50)
                    row['vibrato_std_ratio']=float(cents.std()/reference.std())
                    row['vibrato_fitted_lag_seconds']=float(-np.arctan2(coefficients[1],coefficients[0])/(2*np.pi*rate))
                if 'glissando' in case.name and common.any():
                    shifts=np.arange(-.1,.1001,.002)
                    errors=[np.median(np.abs(1200*np.log2(f0[common]/case.truth_hz(reference_times[common]-shift)))) for shift in shifts]
                    row['glissando_best_fit_lag_seconds']=float(shifts[int(np.argmin(errors))])
                    row['lag_diagnostic_semantics']='Analytic reference shifted for diagnostic only; headline metrics use original timestamps'
            except Exception as exc:
                row={'case':case.name,'status':'failed','error':f'{type(exc).__name__}: {exc}'}
            report['cases'].append(row)
            args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
            print(f'{args.estimator}: {case.name}: {row["status"]}',flush=True)
    report['status']='partial' if any(r['status']!='ok' for r in report['cases']) else 'complete'
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()

