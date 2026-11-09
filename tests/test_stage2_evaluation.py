# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

from vocalscope.backends import EstimatorConfig, EstimatorOutput
from vocalscope.datasets import Vocadito, digest, load_reference
from vocalscope.errors import VocalScopeError
from vocalscope.evaluation import align_frames, metrics, aggregate, fixed_split, select_threshold
from vocalscope.models import AnalysisConfig
from vocalscope.prediction_cache import prediction_key, PredictionCache
from vocalscope.benchmark import paired_intervals


def test_alignment_no_interpolation_no_extrapolation():
    times=np.array([0,.25,.5,.75])
    pitches=np.array([220,np.nan,440,880]);voiced=np.array([True,False,True,True])
    ref=np.array([-.1,0,.125,.25,.375,.5,.875])
    aligned,v,covered=align_frames(times,pitches,voiced,ref,1)
    np.testing.assert_array_equal(aligned,[0,220,220,0,0,440,0])
    assert not covered[0] and not covered[-1]
    assert not v[3] and not v[4]


def test_known_metric_denominators_and_octaves():
    m=metrics(np.array([440,440,0,440]),np.array([440,880,440,0]),np.array([True,True,True,False]))
    assert m['raw_pitch_accuracy_50c']==pytest.approx(1/3)
    assert m['raw_chroma_accuracy']==pytest.approx(2/3)
    assert m['voicing_recall']==pytest.approx(2/3)
    assert m['voicing_false_alarm_rate']==1
    assert m['voicing_precision']==pytest.approx(2/3)
    assert m['voicing_f1']==pytest.approx(2/3)
    assert m['overall_accuracy']==.25
    assert m['median_absolute_error_cents']==pytest.approx(600)
    assert m['mean_absolute_error_cents']==pytest.approx(600)
    assert m['p90_absolute_error_cents']==pytest.approx(1080)
    assert m['p95_absolute_error_cents']==pytest.approx(1140)
    assert m['octave_error_rate']==.5


def test_zero_denominators_are_undefined_and_macro_differs_from_pooling():
    m=metrics(np.zeros(2),np.zeros(2),np.zeros(2,dtype=bool))
    for name in ('raw_pitch_accuracy_50c','raw_chroma_accuracy','voicing_recall','voicing_precision','voicing_f1','median_absolute_error_cents'):
        assert m[name] is None
    assert m['overall_accuracy']==1
    a=(np.full(10,440),np.full(10,440),np.ones(10,dtype=bool))
    b=(np.array([440]),np.array([880]),np.ones(1,dtype=bool))
    result=aggregate([a,b])
    assert result['frame_weighted']['raw_pitch_accuracy_50c']==pytest.approx(10/11)
    assert result['track_macro']['raw_pitch_accuracy_50c']==.5


def test_reference_loading_and_missing_dataset(tmp_path):
    path=tmp_path/'f0.csv';path.write_text('0,0\n0.01,220\n0.02,440\n')
    t,f=load_reference(path)
    np.testing.assert_array_equal(f,[0,220,440]);assert not t.flags.writeable
    with pytest.raises(VocalScopeError,match='not found'):
        Vocadito(tmp_path)
    for text in ('0,220\n0,440','0,-1\n.1,440','0,nan\n.1,220'):
        path.write_text(text)
        with pytest.raises(VocalScopeError):load_reference(path)


def test_track_integrity_and_alignment_on_small_fixture(tmp_path):
    audio=tmp_path/'tone.wav';sf.write(audio,np.zeros(8000),8000)
    annotation=tmp_path/'f0.csv';annotation.write_text('0,0\n.5,220\n.9,0\n')
    dataset=object.__new__(Vocadito);dataset.root=tmp_path;dataset.metadata={}
    dataset.index={'tracks':{'fixture':{'audio':['tone.wav',digest(audio,'md5')],'f0':['f0.csv',digest(annotation,'md5')]}}}
    track=dataset.load_track('fixture')
    assert track.duration_seconds==1 and track.track_id=='fixture'
    annotation.write_text('0,0\n.5,330\n')
    with pytest.raises(VocalScopeError,match='damaged'):
        dataset.load_track('fixture')
    audio.unlink()
    with pytest.raises(VocalScopeError,match='missing'):
        dataset.load_track('fixture')


def test_splits_are_deterministic_disjoint_and_crossvalidation_complete():
    ids=[str(i) for i in range(40)]
    split=fixed_split(ids)
    assert split==fixed_split(list(reversed(ids)))
    assert len(split['development'])==len(split['test'])==20
    assert not set(split['development'])&set(split['test'])
    folds=[fixed_split(ids,folds=5,fold=i) for i in range(5)]
    assert sorted(x for f in folds for x in f['test'])==sorted(ids)
    for f in folds:assert not set(f['development'])&set(f['test'])


def test_development_threshold_selection_and_precision_recall():
    dev=[(np.array([440,440,0,0]),np.array([440,440,440,440]),np.array([.9,.8,.4,.3]))]
    chosen=select_threshold(dev,'crepe_periodicity')
    assert chosen['selected_threshold']==.5
    assert len(chosen['development_precision_recall'])==6


def test_prediction_cache_round_trip_and_invalidation(tmp_path):
    config=AnalysisConfig();settings=EstimatorConfig(estimator_id='yin')
    key=prediction_key('a'*64,config,settings)
    assert key!=prediction_key('b'*64,config,settings)
    assert key!=prediction_key('a'*64,replace(config,hop_length=256),settings)
    assert key!=prediction_key('a'*64,config,replace(settings,yin_voicing_threshold=.7))
    cache=PredictionCache(tmp_path)
    output=EstimatorOutput('yin','test',np.array([0.,.1]),np.array([440.,440.]),np.array([True,False]),np.array([.9,.1]),'normalized_autocorrelation',22050,0,.1)
    cache.save(key,output,{'inference_seconds':.1})
    restored,timing=cache.load(key)
    np.testing.assert_array_equal(restored.voiced,output.voiced)
    assert timing['inference_seconds']==.1
    cache.path(key).write_bytes(b'corrupt')
    assert cache.load(key) is None


def test_bootstrap_resamples_tracks_deterministically():
    data={'a':{'1':{'raw_pitch_accuracy_50c':.5},'2':{'raw_pitch_accuracy_50c':.7}},
          'b':{'1':{'raw_pitch_accuracy_50c':.7},'2':{'raw_pitch_accuracy_50c':.5}}}
    first=paired_intervals(data,20261109)
    assert first==paired_intervals(data,20261109)
    assert first[0]['tracks']==2
    assert first[0]['mean_difference']==pytest.approx(0)


def test_dataset_download_resumes_and_checks_archive_paths(tmp_path,monkeypatch):
    import io,hashlib,zipfile
    from vocalscope import datasets
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('Audio/fixture.txt','synthetic fixture')
    payload=buffer.getvalue();requests=[]
    class Response(io.BytesIO):
        def __init__(self,data,status,headers):super().__init__(data);self.status=status;self.headers=headers
    def opened(request,timeout):
        offset=request.get_header('Range');requests.append(offset)
        if offset:
            start=int(offset.removeprefix('bytes=').removesuffix('-'))
            return Response(payload[start:],206,{'Content-Range':f'bytes {start}-{len(payload)-1}/{len(payload)}'})
        return Response(payload[:len(payload)//2],200,{})
    monkeypatch.setattr(datasets,'ARCHIVE_MD5',hashlib.md5(payload).hexdigest())
    monkeypatch.setattr(datasets.urllib.request,'urlopen',opened)
    datasets.download_vocadito(tmp_path/'safe')
    assert len(requests)==2 and requests[1].startswith('bytes=')
    assert (tmp_path/'safe/Audio/fixture.txt').read_text()=='synthetic fixture'
    malicious=io.BytesIO()
    with zipfile.ZipFile(malicious,'w') as z:z.writestr('../outside.txt','bad')
    bad=tmp_path/'bad';bad.mkdir();(bad/'vocadito.zip').write_bytes(malicious.getvalue())
    monkeypatch.setattr(datasets,'ARCHIVE_MD5',hashlib.md5(malicious.getvalue()).hexdigest())
    with pytest.raises(VocalScopeError,match='Unsafe'):
        datasets.download_vocadito(bad)
    assert not (tmp_path/'outside.txt').exists()

