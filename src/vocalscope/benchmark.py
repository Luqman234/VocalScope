# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Track-level Vocadito evaluation, development-only threshold selection and reports."""

from dataclasses import asdict, replace
import itertools
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
import numpy as np
from .backends import EstimatorConfig
from .datasets import Vocadito
from .evaluation import aggregate, align_frames, fixed_split, metrics, select_threshold
from .models import AnalysisConfig
from .pitch import library_versions
from .prediction_cache import PredictionCache


def _run_backend(jobs: list[dict], config: AnalysisConfig, settings: EstimatorConfig, cache: Path, output: Path, resume: bool) -> list[dict]:
    request={'jobs':jobs,'config':asdict(config),'settings':asdict(settings),'cache':str(cache),'resume':resume}
    rows=[]
    with (output/f'{settings.estimator_id}-worker.stderr.log').open('w') as errors:
        process=subprocess.Popen([sys.executable,'-m','vocalscope.benchmark_worker'],stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=errors,text=True)
        try:
            process.stdin.write(json.dumps(request,allow_nan=False));process.stdin.close()
            for line in process.stdout:
                try:row=json.loads(line)
                except ValueError:continue
                rows.append(row)
                with (output/'progress.jsonl').open('a') as progress:
                    progress.write(json.dumps(row,allow_nan=False)+'\n')
                print(f"{row['estimator']} track {row['track_id']}: {row['status']}"+(' (cached)' if row.get('cached') else ''),file=sys.stderr,flush=True)
            process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            process.stdout.close()
    existing={r['track_id'] for r in rows}
    rows += [{'track_id':j['track_id'],'estimator':settings.estimator_id,'status':'failed',
              'error':f'Backend worker terminated without a result (exit {process.returncode}); see worker stderr log.'}
             for j in jobs if j['track_id'] not in existing]
    return rows


def _aligned(track, prediction, threshold: float | None = None):
    if threshold is None:
        est,v,covered=align_frames(prediction.times,prediction.f0_hz,prediction.voiced,track.reference_times,track.duration_seconds)
    else:
        eligible=np.isfinite(prediction.candidates)&(prediction.candidates>0)&(prediction.score>0)
        voiced=eligible&(prediction.score>=threshold)
        est,v,covered=align_frames(prediction.times,prediction.candidates,voiced,track.reference_times,track.duration_seconds)
    return (track.reference_f0,est,v),covered


def _calibration_input(track,prediction):
    eligible=np.isfinite(prediction.candidates)&(prediction.candidates>0)&(prediction.score>0)
    candidates,_,_=align_frames(prediction.times,prediction.candidates,eligible,track.reference_times,track.duration_seconds)
    scores,_,_=align_frames(prediction.times,prediction.score,eligible,track.reference_times,track.duration_seconds)
    return track.reference_f0,candidates,scores


def paired_intervals(per_algorithm: dict[str,dict], seed: int, repetitions: int = 2000) -> list[dict]:
    rows=[]
    for a,b in itertools.combinations(per_algorithm,2):
        common=sorted(set(per_algorithm[a])&set(per_algorithm[b]))
        pairs=[(per_algorithm[a][k]['raw_pitch_accuracy_50c'],per_algorithm[b][k]['raw_pitch_accuracy_50c']) for k in common]
        differences=np.asarray([y-x for x,y in pairs if x is not None and y is not None])
        if len(differences)>=2:
            rng=np.random.default_rng(seed)
            draws=rng.choice(differences,size=(repetitions,len(differences)),replace=True).mean(axis=1)
            interval=np.percentile(draws,[2.5,97.5]).tolist()
        else:interval=None
        rows.append({'a':a,'b':b,'metric':'track-macro RPA50 difference b-a','tracks':len(differences),
                     'mean_difference':float(differences.mean()) if len(differences) else None,
                     'ci95_track_bootstrap':interval,'resamples':repetitions,'seed':seed})
    return rows


def run_benchmark(dataset_path: str | Path, output_dir: str | Path, estimators: list[str], *,
                  config: AnalysisConfig | None = None, settings: EstimatorConfig | None = None,
                  split: str = 'test', seed: int = 20261109, max_tracks: int | None = None,
                  calibrate: bool = False, cache_dir: str | Path | None = None,
                  resume: bool = True, folds: int | None = None, fold: int = 0) -> dict:
    try:
        import mir_eval
    except ImportError as exc:
        from .errors import VocalScopeError
        raise VocalScopeError('Benchmarking requires vocalscope[benchmark] (mir_eval); no predictions were started.') from exc
    if not estimators or set(estimators)-{'pyin','yin','crepe'}:
        raise ValueError('Choose one or more estimators: pyin,yin,crepe.')
    if split not in ('development','test','all') or (max_tracks is not None and max_tracks <= 0):
        raise ValueError('Invalid split or max-tracks (must be positive).')
    dataset=Vocadito(dataset_path)
    config=config or AnalysisConfig();settings=settings or EstimatorConfig()
    output=Path(output_dir).expanduser().resolve();output.mkdir(parents=True,exist_ok=True)
    cache=PredictionCache(cache_dir or output/'cache')
    splits=fixed_split(dataset.track_ids,seed,folds,fold)
    assert not set(splits['development'])&set(splits['test'])
    selected={key:values[:max_tracks] if max_tracks is not None else values
              for key,values in splits.items() if key in ('development','test')}
    wanted=set(selected['development']+selected['test']) if split=='all' or calibrate else set(selected[split])
    tracks={};invalid=[]
    for identifier in sorted(wanted):
        try:tracks[identifier]=dataset.load_track(identifier)
        except Exception as exc:invalid.append({'track_id':identifier,'status':'failed','error':str(exc)})
    manifest={**dataset.identity(),'splits':splits,'selected':selected,'split_counts':{k:len(splits[k]) for k in ('train','development','test')},
              'smoke_test':max_tracks is not None,'invalid_tracks':invalid,
              'tracks':[{'track_id':t.track_id,'singer_id':t.singer_id,'audio_path':str(t.audio_path),
                         'audio_sha256':t.audio_sha256,'annotation_sha256':t.annotation_sha256,
                         'duration_seconds':t.duration_seconds,'reference_frames':len(t.reference_times),
                         'reference_voiced_frames':int((t.reference_f0>0).sum()),
                         'annotation_start_seconds':float(t.reference_times[0]),'annotation_end_seconds':float(t.reference_times[-1])}
                        for t in tracks.values()]}
    (output/'dataset_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    report={'schema_version':'2.0.0','status':'running','dataset':manifest,'analysis':asdict(config),'settings':asdict(settings),
            'versions':{**library_versions(),'mir_eval':mir_eval.__version__},'alignment':'nearest actual frame center, ties earlier; no interpolation/extrapolation; uncovered references count as unvoiced predictions',
            'metrics_convention':'mir_eval strict <50 cents; undefined denominators null; errors/percentiles/octaves conditional on mutual voicing; RPA/RCA use all reference voiced frames',
            'cache':str(cache.directory),'predictions':[],'per_track':[],'comparisons':{},'calibration':{}}
    jobs=[{'track_id':t.track_id,'path':str(t.audio_path),'audio_sha256':t.audio_sha256} for t in tracks.values()]
    started=perf_counter()
    for estimator in dict.fromkeys(estimators):
        rows=_run_backend(jobs,config,replace(settings,estimator_id=estimator),cache.directory,output,resume)
        rows += [{'track_id':r['track_id'],'estimator':estimator,'status':'failed','error':r['error']} for r in invalid]
        report['predictions']+=rows
        (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    predictions={}
    for row in report['predictions']:
        if row['status']=='ok':
            item=cache.load(row['cache_key'])
            if item is None:
                row.update(status='failed',error='Prediction cache missing or corrupted after computation.')
            else:predictions[(row['estimator'],row['track_id'])]=item[0]
    if calibrate:
        for estimator in estimators:
            dev_ids=[identifier for identifier in selected['development'] if (estimator,identifier) in predictions]
            arrays=[_calibration_input(tracks[i],predictions[estimator,i]) for i in dev_ids]
            if arrays:
                confidence_type=predictions[estimator,dev_ids[0]].confidence_type
                calibration=select_threshold(arrays,confidence_type)
            else:calibration={'selected_threshold':None,'development_precision_recall':[],'status':'no valid development predictions'}
            report['calibration'][estimator]={**calibration,'development_track_ids':dev_ids,
                                               'test_track_ids_used_for_selection':[], 'failed_development_track_ids':sorted(set(selected['development'])-set(dev_ids))}
    variants=['baseline']+(['calibrated'] if calibrate else [])
    for partition in ('development','test'):
        if split!='all' and partition!=split:continue
        for variant in variants:
            if variant=='calibrated' and partition!='test':continue
            # Entirely unavailable backends are displayed as unavailable, not
            # allowed to erase the comparable set for the installed backends.
            active=[e for e in estimators if any((e,i) in predictions for i in selected[partition])]
            common=sorted(set(selected[partition]).intersection(*(set(i for e2,i in predictions if e2==e) for e in active))) if active else []
            summaries={};paired={}
            for estimator in estimators:
                threshold=report['calibration'].get(estimator,{}).get('selected_threshold') if variant=='calibrated' else None
                ids=common if estimator in active and (variant=='baseline' or threshold is not None) else []
                aligned=[];paired[estimator]={}
                for identifier in ids:
                    values,coverage=_aligned(tracks[identifier],predictions[estimator,identifier],threshold)
                    m=metrics(*values);aligned.append(values);paired[estimator][identifier]=m
                    report['per_track'].append({'track_id':identifier,'estimator':estimator,'split':partition,'variant':variant,
                                                'threshold':threshold,'uncovered_reference_frames':int((~coverage).sum()),**m})
                timing=[r['timing'] for r in report['predictions'] if r['status']=='ok' and r['estimator']==estimator and r['track_id'] in ids]
                summaries[estimator]={**aggregate(aligned),'status':'ok' if ids else 'unavailable',
                                      'requested_tracks':len(selected[partition]),'compared_track_ids':ids,
                                      'excluded_track_ids':sorted(set(selected[partition])-set(ids)),
                                      'total_processing_seconds':sum(t['total_processing_seconds'] for t in timing) if timing else None,
                                      'initialization_seconds':sum(t['initialization_seconds'] for t in timing) if timing else None,
                                      'peak_process_rss_mib':max(t['peak_process_rss_mib'] for t in timing) if timing else None,
                                      'mean_runtime_over_audio_duration':float(np.mean([t['runtime_over_audio_duration'] for t in timing])) if timing else None}
            report['comparisons'][f'{partition}/{variant}']={'estimators':summaries,'paired_rpa50':paired_intervals(paired,seed)}
    # Preserve individual measurements even if another backend's failure
    # excludes that track from the paired primary comparison.
    already={(r['estimator'],r['track_id'],r['split'],r['variant']) for r in report['per_track']}
    for row in report['per_track']:row['in_primary_comparison']=True
    for partition in ('development','test'):
        if split!='all' and partition!=split:continue
        for variant in variants:
            if variant=='calibrated' and partition!='test':continue
            for estimator in estimators:
                threshold=report['calibration'].get(estimator,{}).get('selected_threshold') if variant=='calibrated' else None
                if variant=='calibrated' and threshold is None:continue
                for identifier in selected[partition]:
                    if (estimator,identifier) not in predictions or (estimator,identifier,partition,variant) in already:continue
                    values,coverage=_aligned(tracks[identifier],predictions[estimator,identifier],threshold)
                    report['per_track'].append({'track_id':identifier,'estimator':estimator,'split':partition,'variant':variant,
                                                'threshold':threshold,'in_primary_comparison':False,
                                                'uncovered_reference_frames':int((~coverage).sum()),**metrics(*values)})
    report['elapsed_wall_seconds']=perf_counter()-started
    report['status']='partial' if any(r['status']!='ok' for r in report['predictions']) else 'complete'
    from .benchmark_reports import write_reports
    write_reports(report,output,tracks,predictions)
    return report

