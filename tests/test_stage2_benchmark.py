# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Small artificial fixtures exercise orchestration, never advertised as Vocadito results."""

import csv
from dataclasses import replace
import hashlib
import json
import numpy as np
import soundfile as sf
import pytest

from vocalscope import benchmark
from vocalscope.backends import EstimatorOutput
from vocalscope.datasets import VocalTrack,digest
from vocalscope.evaluation import fixed_split
from vocalscope.prediction_cache import PredictionCache


@pytest.fixture
def fixture_dataset(tmp_path,monkeypatch):
    tracks={}
    for identifier in ('1','2','3','4'):
        audio=tmp_path/f'{identifier}.wav';sf.write(audio,np.zeros(2205),22050)
        annotation=tmp_path/f'{identifier}.csv';annotation.write_text('0,440\n.01,0\n.02,0\n.03,0\n')
        tracks[identifier]=VocalTrack(identifier,audio,annotation,np.array([0.,.01,.02,.03]),np.array([440.,0,0,0]),.1,digest(audio),digest(annotation),'fixture')
    class FixtureDataset:
        track_ids=list(tracks)
        def __init__(self,path):pass
        def load_track(self,identifier):return tracks[identifier]
        def identity(self):return {'dataset':'artificial-unit-fixture','version':'fixture','source':'unit-test-only','license':'synthetic-fixture','attribution':'Artificial fixture, not real-vocal evidence','track_count':4}
    monkeypatch.setattr(benchmark,'Vocadito',FixtureDataset)
    return tracks


def fake_worker(*,fail_track=None):
    def run(jobs,config,settings,cache_dir,output_dir,resume):
        cache=PredictionCache(cache_dir);rows=[]
        for job in jobs:
            identifier=job['track_id'];estimator=settings.estimator_id
            if estimator=='yin' and identifier==fail_track:
                rows.append({'track_id':identifier,'estimator':estimator,'status':'failed','error':'Deliberate fixture failure'})
                continue
            key=hashlib.sha256((estimator+identifier).encode()).hexdigest()
            prediction=EstimatorOutput(estimator,'fixture',np.array([0.,.01,.02,.03]),np.full(4,440.),np.array([True,True,False,False]),np.array([.9,.8,.4,.3]),'normalized_autocorrelation',22050,0,.1)
            timing={'total_processing_seconds':.1,'initialization_seconds':0,'inference_seconds':.1,'peak_process_rss_mib':64,'runtime_over_audio_duration':1}
            cache.save(key,prediction,timing)
            rows.append({'track_id':identifier,'estimator':estimator,'status':'ok','cache_key':key,'cached':False,'timing':timing})
        return rows
    return run


def test_benchmark_failure_reporting_and_serialization(tmp_path,monkeypatch,fixture_dataset):
    failed=fixed_split(list(fixture_dataset))['test'][0]
    monkeypatch.setattr(benchmark,'_run_backend',fake_worker(fail_track=failed))
    output=tmp_path/'report'
    report=benchmark.run_benchmark(tmp_path,output,['pyin','yin'],split='all')
    assert report['status']=='partial'
    summary=report['comparisons']['test/baseline']['estimators']
    assert summary['pyin']['tracks']==summary['yin']['tracks']==1
    assert failed in summary['pyin']['excluded_track_ids']
    assert any(row['track_id']==failed and not row['in_primary_comparison'] for row in report['per_track'])
    with (output/'per-track.csv').open() as stream:rows=list(csv.DictReader(stream))
    assert any(r['status']=='failed' and r['track_id']==failed for r in rows)
    json.loads((output/'results.json').read_text(),parse_constant=lambda x:pytest.fail(x))
    for name in ('aggregate.csv','REPORT.md','accuracy-comparison.png','runtime-comparison.png','voicing-errors.png'):
        assert (output/name).is_file()


def test_threshold_selection_never_receives_heldout_labels(tmp_path,monkeypatch,fixture_dataset):
    split=fixed_split(list(fixture_dataset))
    dev_references={id(fixture_dataset[i].reference_f0) for i in split['development']}
    test_references={id(fixture_dataset[i].reference_f0) for i in split['test']}
    called=[];real_select=benchmark.select_threshold
    def spy(values,confidence_type):
        identities={id(row[0]) for row in values}
        assert identities<=dev_references and not identities&test_references
        called.append(identities)
        return real_select(values,confidence_type)
    monkeypatch.setattr(benchmark,'_run_backend',fake_worker())
    monkeypatch.setattr(benchmark,'select_threshold',spy)
    report=benchmark.run_benchmark(tmp_path,tmp_path/'calibration',['yin'],split='test',calibrate=True)
    assert len(called)==1
    calibration=report['calibration']['yin']
    assert calibration['development_track_ids']==split['development']
    assert calibration['test_track_ids_used_for_selection']==[]
    assert calibration['selected_threshold']==.9
    assert report['dataset']['split_counts']=={'train':0,'development':2,'test':2}

