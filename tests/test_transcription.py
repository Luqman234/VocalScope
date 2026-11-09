# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Independent segmentation fixtures plus real CPU audio-to-MIDI integration."""
from dataclasses import replace,asdict
import json
import numpy as np
import pytest
import soundfile as sf
from vocalscope.models import AnalysisConfig,AudioMetadata,AudioData,AnalysisResult
from vocalscope.notes import midi_to_hz,note_measurements
from vocalscope.transcription.models import NoteEvent,TranscriptionConfig,TranscriptionResult,Boundary
from vocalscope.transcription.onsets import AcousticFeatures,extract_features
from vocalscope.transcription.pipeline import transcribe_analysis,transcribe_file
from vocalscope.transcription.serialization import document,from_document,export_bundle,load_project
from vocalscope.transcription.midi_export import midi_bytes
from vocalscope.transcription.pitch_center import pitch_center
from vocalscope.transcription.dataset import grouped_split,grouped_folds,load_note_csv,NoteReference
from vocalscope.transcription.evaluation import evaluate,prf


def fixture(midi,onsets=(),flatness=0.,hop=.01):
    m=np.asarray(midi,dtype=float);duration=len(m)*hop;t=np.arange(len(m))*hop
    meta=AudioMetadata('fixture.wav','fixture.wav',22050,1,round(duration*22050),duration,'WAV','FLOAT','mono',.5,.3,0.,())
    config=AnalysisConfig();v=np.isfinite(m);f=midi_to_hz(m);names,cents=note_measurements(m)
    result=AnalysisResult(meta,config,round(duration*22050),t,f,v,v.astype(float),m,names,cents,0.,{})
    audio=AudioData(np.zeros(round(duration*22050)),22050,meta)
    features=AcousticFeatures(t,np.zeros(len(m)),np.ones(len(m)),np.full(len(m),flatness),tuple(Boundary(x,'test_articulation',1.,'articulation') for x in onsets),{}, {})
    return audio,result,features


def run(midi,*,onsets=(),flatness=0.,method='combined',**kwargs):
    audio,result,features=fixture(midi,onsets,flatness)
    p=transcribe_analysis(audio,result,TranscriptionConfig(method=method,**kwargs),features=features,source_sha256='a'*64)
    return p


@pytest.mark.parametrize('case', ['sustain','vibrato3','vibrato5','short_gap','glissando'])
def test_no_note_spam(case):
    t=np.arange(200)*.01;m=np.full(200,69.)
    if case.startswith('vibrato'):m+=.4*np.sin(2*np.pi*int(case[-1])*t)
    if case=='short_gap':m[80:84]=np.nan
    if case=='glissando':m+=3*t/2
    p=run(m);assert len(p.notes)==1
    if case=='glissando':assert 'wide_pitch_gesture' in p.notes[0].flags
    if case=='short_gap':assert p.notes[0].pitch_coverage<1 and np.isnan(p.acoustic.midi_pitch[82])


@pytest.mark.parametrize('sequence',[[69,71,72],[72,71,69]])
def test_legato_melody(sequence):
    p=run(np.repeat(sequence,50));assert [n.midi_note for n in p.notes]==sequence
    assert max(abs(n.start_seconds-i*.5) for i,n in enumerate(p.notes))<.04


def test_repeated_same_note_and_ablation():
    m=np.full(180,69.)
    assert len(run(m,onsets=(.6,1.2)).notes)==3
    assert len(run(m,onsets=(.6,1.2),method='pitch-only').notes)==1


@pytest.mark.parametrize('flatness,m',[ (0.,np.full(200,np.nan)),(.9,np.full(200,69.))])
def test_silence_and_noise_rejection(flatness,m):assert not run(m,flatness=flatness).notes


def test_staccato_and_long_rest():
    m=np.full(100,np.nan);m[10:19]=69;m[40:49]=71
    p=run(m);assert [n.midi_note for n in p.notes]==[69,71]
    assert p.notes[0].end_seconds<p.notes[1].start_seconds


def test_naive_vibrato_baseline():
    m=69+.6*np.sin(2*np.pi*5*np.arange(200)*.01)
    assert len(run(m,method='naive').notes)>10
    assert len(run(m).notes)==1


def test_robust_pitch_center():
    center,key,cents,_=pitch_center([68.9,69.1,69.,69.,80.,np.nan])
    assert key==69 and center==69 and cents==0


@pytest.mark.parametrize('changes',[{'start_seconds':-1},{'end_seconds':0},{'midi_note':128},{'velocity':0},{'midi_pitch':float('nan')},{'source_start_frame':3}])
def test_note_validation(changes):
    n=NoteEvent('id',0,1,69,69.,0)
    with pytest.raises(ValueError):replace(n,**changes)


def test_edit_journal_and_reopening(tmp_path):
    p=run(np.full(200,69.));original=p.generated_notes;acoustic=p.acoustic.midi_pitch.copy();id=p.notes[0].note_id
    p.edit(id,midi_note=70,start_seconds=.02)
    right=p.split(id,1.)
    p.edit(right,midi_note=70);p.merge(id,right)
    p.delete(id);new=p.add(.1,.5,60);p.undo();p.redo();assert p.notes[0].note_id==new
    q=from_document(json.loads(json.dumps(document(p),allow_nan=False)))
    assert q.notes==p.notes and q.generated_notes==original
    q.undo();q.redo();assert q.notes==p.notes
    np.testing.assert_array_equal(acoustic,p.acoustic.midi_pitch)
    with pytest.raises(ValueError):p.add(.2,.4,60)
    bad=document(p);bad['cursor']=99
    with pytest.raises(ValueError):from_document(bad)
    bad=document(p);bad['notes'][0]['midi_note']=10
    with pytest.raises(ValueError):from_document(bad)


def test_midi_and_export_roundtrip(tmp_path):
    import pretty_midi,io,csv
    p=run(np.repeat([69,71,72],50));paths=export_bundle(p,tmp_path)
    assert load_project(paths['json']).notes==p.notes
    midi=pretty_midi.PrettyMIDI(io.BytesIO(paths['mid'].read_bytes()))
    assert midi.instruments[0].program==0
    for expected,actual in zip(p.notes,midi.instruments[0].notes,strict=True):
        assert expected.midi_note==actual.pitch and expected.velocity==actual.velocity
        assert abs(expected.start_seconds-actual.start)<.000027
        assert abs(expected.end_seconds-actual.end)<.000027
    rows=list(csv.DictReader(paths['csv'].open()));assert len(rows)==len(p.notes)
    assert float(rows[0]['midi_pitch'])==p.notes[0].midi_pitch
    assert paths['png'].stat().st_size>1000
    with pytest.raises(FileExistsError):export_bundle(p,tmp_path)
    empty=pretty_midi.PrettyMIDI(io.BytesIO(midi_bytes([])));assert not empty.instruments


def test_singer_grouping_no_leakage():
    metadata={str(i):{'singer_id':f'S{i//2}'} for i in range(20)}
    s=grouped_split(metadata);assert not set(s['development_singers'])&set(s['test_singers'])
    assert sorted(s['development']+s['test'],key=int)==list(metadata)
    assert grouped_folds(metadata)==grouped_folds(metadata)
    metadata['0']['singer_id']=''
    with pytest.raises(ValueError):grouped_split(metadata)


def test_annotation_semantics_and_both_paths(tmp_path):
    p=tmp_path/'notes.csv';p.write_text('.1,440,.5\n.8,493.883301,.2\n')
    intervals,frequencies=load_note_csv(p,duration=1.)
    np.testing.assert_allclose(intervals,[[.1,.6],[.8,1.]])
    notes=[NoteEvent('1',.1,.6,69,69.,0),NoteEvent('2',.8,1.,71,71.,0)]
    for annotator in ('A1','A2'):
        r=NoteReference('1',annotator,intervals,frequencies,'hash')
        scores=evaluate(r,notes);assert scores['offset']['f1']==1.
        assert evaluate(r,[])['onset']['precision'] is None
    assert prf(0,0,0)['f1'] is None
    p.write_text('.1,440,-1\n')
    with pytest.raises(Exception):load_note_csv(p)


def test_onset_time_alignment(tmp_path):
    from vocalscope.audio import load_audio
    sr=22050;t=np.arange(sr*2)/sr;y=.3*np.sin(2*np.pi*440*t)
    y[:round(.5*sr)]=0;y[round(1.*sr):round(1.2*sr)]=0
    path=tmp_path/'onsets.wav';sf.write(path,y,sr,subtype='FLOAT')
    f=extract_features(load_audio(path))
    assert min(abs(b.time_seconds-.5) for b in f.candidates)<.05
    assert min(abs(b.time_seconds-1.2) for b in f.candidates)<.05


@pytest.mark.scientific
def test_real_audio_to_notes_and_midi(tmp_path):
    sr=22050;t=np.arange(sr*2)/sr
    # Integrated phase, deterministic harmonic-rich melody.
    freq=np.where(t<1,440.,493.883301)
    phase=2*np.pi*np.cumsum(freq)/sr;y=.3*np.sin(phase)+.1*np.sin(2*phase)
    path=tmp_path/'melody.wav';sf.write(path,y,sr,subtype='FLOAT')
    p=transcribe_file(path);assert [n.midi_note for n in p.notes]==[69,71]
    export_bundle(p,tmp_path/'output')


def test_onset_threshold_is_consistent_with_feature_reuse(tmp_path):
    from vocalscope.audio import load_audio
    sr=22050;t=np.arange(sr*2)/sr;y=.3*np.sin(2*np.pi*440*t)*(np.sin(3*np.pi*t)>0)
    path=tmp_path/'repeat.wav';sf.write(path,y,sr,subtype='FLOAT');audio=load_audio(path)
    all_features=extract_features(audio,.35);strict=extract_features(audio,.6)
    assert strict.candidates==tuple(b for b in all_features.candidates if b.strength>=.6)
