# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
import soundfile as sf

from vocalscope.backends import EstimatorConfig, PitchEstimator, availability, get_estimator
from vocalscope.errors import VocalScopeError
from vocalscope.export import result_document, result_from_document, FIELDS
from vocalscope.models import AnalysisConfig, AudioData, AudioMetadata
from vocalscope.pitch import analyze_audio, analyze_file
from vocalscope.validation import make_case


def audio_case(name='sine_A4',duration=2):
    case=make_case(name,duration=duration)
    meta=AudioMetadata('synthetic',name,case.sample_rate,1,len(case.samples),len(case.samples)/case.sample_rate,'SYNTHETIC','FLOAT','none',0.6,0.1,0)
    return AudioData(case.samples,case.sample_rate,meta)


@pytest.mark.parametrize('name',['sine_A4','silence_gap','vibrato_5hz'])
def test_pyin_stage1_golden_consistency(name):
    reference=json.loads((Path(__file__).parent/'fixtures/stage1-pyin.json').read_text())[name]
    result=analyze_audio(audio_case(name,3 if name=='silence_gap' else 2))
    np.testing.assert_allclose(result.f0_hz,np.asarray(reference['f0'],dtype=float),rtol=1e-10,equal_nan=True)
    np.testing.assert_array_equal(result.voiced,reference['voiced'])
    np.testing.assert_allclose(result.voiced_probability,reference['probability'],rtol=1e-10,atol=1e-12)
    np.testing.assert_allclose(result.time_seconds,reference['times'],atol=1e-12)


@pytest.mark.parametrize('identifier',['pyin','yin'])
def test_backend_interface(identifier):
    estimator=get_estimator(identifier)
    assert isinstance(estimator,PitchEstimator)
    output=estimator.analyze(audio_case(),AnalysisConfig(),EstimatorConfig(estimator_id=identifier))
    assert output.estimator_id==identifier
    assert output.sample_rate==22050
    assert len(output.times)==len(output.candidates)==len(output.score)==len(output.voiced)
    assert output.inference_seconds>0


@pytest.mark.parametrize('name',['sine_A4','silence','noise_only','soft_A4'])
def test_yin_explicit_voicing(name):
    result=analyze_audio(audio_case(name),settings=EstimatorConfig(estimator_id='yin'))
    assert np.all(np.isnan(result.voiced_probability))
    assert result.confidence_type=='normalized_autocorrelation'
    assert np.all(np.isnan(result.f0_hz[~result.voiced]))
    interior=(result.time_seconds>.25)&(result.time_seconds<1.75)
    if name in ('sine_A4','soft_A4'):
        assert result.voiced[interior].mean()>.95
        assert np.median(np.abs(1200*np.log2(result.f0_hz[interior]/440)))<15
    else:
        assert not result.voiced[interior].any()


def test_legacy_schema_read_and_new_score_semantics():
    result=analyze_audio(audio_case())
    document=result_document(result)
    document['schema_version']='1.0.0';document.pop('estimator')
    for row in document['frames']:
        for name in ('estimator_id','confidence_type','confidence_value'):row.pop(name)
    restored=result_from_document(document)
    np.testing.assert_array_equal(restored.f0_hz,result.f0_hz)
    assert restored.estimator_id=='pyin'
    assert FIELDS[:7]==('time_seconds','f0_hz','voiced','voiced_probability','midi_pitch','nearest_note','cents_deviation')
    yin=analyze_audio(audio_case(),settings=EstimatorConfig(estimator_id='yin'))
    assert all(row['voiced_probability'] is None for row in result_document(yin)['frames'])
    with pytest.raises(ValueError,match='not probabilities'):
        replace(yin,voiced_probability=np.ones_like(yin.confidence))


def test_optional_availability_does_not_import_torch():
    code="from vocalscope.backends import availability,get_estimator; import sys; print(availability()); get_estimator('pyin'); get_estimator('yin'); assert 'torch' not in sys.modules"
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_missing_neural_backend_reports_failure(monkeypatch):
    monkeypatch.setattr('vocalscope.backends.availability',lambda:{'crepe':'missing optional torchcrepe'})
    with pytest.raises(VocalScopeError,match='optional'):
        get_estimator('crepe')


def test_cli_selects_yin_and_keeps_headless(tmp_path):
    audio=audio_case(duration=1);path=tmp_path/'voice.wav'
    sf.write(path,audio.samples,audio.sample_rate,subtype='FLOAT')
    code="from vocalscope.cli import main; import sys; rc=main(sys.argv[1:]); assert 'torch' not in sys.modules; assert 'gi' not in sys.modules; raise SystemExit(rc)"
    p=subprocess.run([sys.executable,'-c',code,'analyze',str(path),'--estimator','yin','--output',str(tmp_path/'out'),'--formats','json'],capture_output=True,text=True,timeout=60)
    assert p.returncode==0,p.stderr
    document=json.loads((tmp_path/'out/voice.json').read_text())
    assert document['estimator']['id']=='yin'
    assert document['analysis']['algorithm']=='librosa.yin'


@pytest.mark.neural
@pytest.mark.parametrize('model',['tiny','full'])
def test_crepe_cpu_smoke_and_determinism(model):
    if availability()['crepe']:pytest.skip(availability()['crepe'])
    cfg=EstimatorConfig(estimator_id='crepe',crepe_model=model,crepe_batch_size=32)
    first=analyze_audio(audio_case(duration=1),settings=cfg)
    second=analyze_audio(audio_case(duration=1),settings=cfg)
    assert first.backend_metadata['inference_device']=='cpu'
    assert first.confidence_type=='crepe_periodicity'
    assert len(first.time_seconds)==101
    assert np.all(np.isnan(first.voiced_probability))
    np.testing.assert_allclose(first.f0_hz,second.f0_hz,atol=1e-5,equal_nan=True)
    np.testing.assert_allclose(first.confidence,second.confidence,atol=1e-6)
    assert np.median(np.abs(1200*np.log2(first.f0_hz[first.voiced]/440)))<50


@pytest.mark.neural
def test_crepe_silence_and_batch_independence():
    if availability()['crepe']:pytest.skip(availability()['crepe'])
    cfg=EstimatorConfig(estimator_id='crepe',crepe_model='tiny',crepe_batch_size=16)
    silent=analyze_audio(audio_case('silence',duration=1),settings=cfg)
    assert not silent.voiced.any()
    first=analyze_audio(audio_case(duration=1),settings=cfg)
    second=analyze_audio(audio_case(duration=1),settings=replace(cfg,crepe_batch_size=128))
    np.testing.assert_allclose(first.f0_hz,second.f0_hz,atol=1e-4,equal_nan=True)


@pytest.mark.neural
def test_crepe_failed_initialization_cannot_reuse_random_weights(monkeypatch):
    if availability()['crepe']:pytest.skip(availability()['crepe'])
    import torch,torchcrepe
    original=torchcrepe.load.model
    for attribute in ('model','capacity'):
        monkeypatch.delattr(torchcrepe.infer,attribute,raising=False)
    def fail(device,capacity):
        torchcrepe.infer.capacity=capacity
        torchcrepe.infer.model=torch.nn.Identity()
        raise OSError('Injected checkpoint failure')
    monkeypatch.setattr(torchcrepe.load,'model',fail)
    config=EstimatorConfig(estimator_id='crepe',crepe_model='tiny')
    with pytest.raises(VocalScopeError,match='checkpoint failure'):
        analyze_audio(audio_case(duration=1),settings=config)
    assert not hasattr(torchcrepe.infer,'model')
    monkeypatch.setattr(torchcrepe.load,'model',original)
    recovered=analyze_audio(audio_case(duration=1),settings=config)
    assert not recovered.backend_metadata['weights_reused']
    assert recovered.voiced.mean()>.9

