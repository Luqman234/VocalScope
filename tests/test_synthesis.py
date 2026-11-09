# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Independent note truth, real PCM tests, and pure mathematical scheduling."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import json,sys,subprocess,hashlib
import numpy as np
import pytest
import soundfile as sf
from vocalscope.transcription.models import NoteEvent
from vocalscope.synthesis.models import RenderConfig,SynthesisError,RenderCancelled
from vocalscope.synthesis.scheduler import schedule_notes
from vocalscope.synthesis.renderer import render_notes
from vocalscope.synthesis.export import export_audio,publish_render


def note(key=69,start=0.,end=.5,identity='a',velocity=80):
    return NoteEvent(identity,start,end,key,float(key),0.,velocity)


@pytest.mark.parametrize('rate',[44100,48000])
def test_scheduler_half_sample_error_and_order(rate):
    notes=[note(start=0,end=.1234567,identity='a'),note(start=.1234567,end=.900001,identity='b')]
    plan=schedule_notes(notes,RenderConfig(sample_rate=rate))
    assert plan.max_rounding_error_seconds<=.5/rate+1e-15
    at=[e.kind for e in plan.events if e.sample_index==round(.1234567*rate)]
    assert at==['note_off','note_on']
    assert plan.events[0].sample_index==0 and plan.events[-1].kind=='note_off'


def test_overlapping_same_pitch_allocates_channels():
    plan=schedule_notes([note(end=1,identity='a'),note(start=.5,end=1.5,identity='b')],RenderConfig())
    ons=[e for e in plan.events if e.kind=='note_on'];assert ons[0].channel!=ons[1].channel
    assert [e.channel for e in plan.events if e.kind=='note_off']==[e.channel for e in ons]
    with pytest.raises(SynthesisError,match='15 overlapping'):schedule_notes([note(identity=str(i)) for i in range(16)],RenderConfig())


def test_scheduler_short_notes_and_limits():
    config=RenderConfig(sample_rate=48000)
    plan=schedule_notes([note(start=.001,end=.001+1/48000)],config)
    assert plan.events[1].sample_index-plan.events[0].sample_index==1
    with pytest.raises(ValueError,match='zero samples'):schedule_notes([note(end=1e-8)],config)
    with pytest.raises(ValueError,match='Duplicate'):schedule_notes([note(),note()],config)
    with pytest.raises(SynthesisError,match='duration'):schedule_notes([note(end=4000)],config)
    with pytest.raises(ValueError):schedule_notes([note()],config,duration_seconds=.2)


@pytest.mark.parametrize('kwargs',[{'sample_rate':0},{'gain':float('nan')},{'gain':-1},{'tail_seconds':-1},{'polyphony':0},{'preset':128},{'bank':-1},{'normalize_peak':1},{'chunk_frames':1},{'interpolation':9}])
def test_config_validation(kwargs):
    with pytest.raises(ValueError):RenderConfig(**kwargs)


def test_soundfont_validation_and_search_order(tmp_path,monkeypatch):
    import struct
    from vocalscope.synthesis import soundfont as fonts
    good=tmp_path/'test.sf2';good.write_bytes(b'RIFF'+struct.pack('<I',4)+b'sfbk')
    assert fonts.validate_soundfont(good)['size_bytes']==12  # structural validation only
    settings=tmp_path/'settings.json';settings.write_text(json.dumps({'soundfont_path':str(good)}))
    monkeypatch.setattr(fonts,'SYSTEM_FONTS',())
    assert fonts.resolve_soundfont(settings_file=settings)==good
    assert fonts.resolve_soundfont(good,settings_file=tmp_path/'bad.json')==good
    with pytest.raises(SynthesisError):fonts.resolve_soundfont(tmp_path/'missing.sf2',settings_file=settings)
    settings.write_text('{broken')
    with pytest.raises(SynthesisError,match='settings'):fonts.resolve_soundfont(settings_file=settings)
    with pytest.raises(SynthesisError,match='required'):fonts.resolve_soundfont(settings_file=tmp_path/'absent')
    good.write_bytes(b'not a font')
    with pytest.raises(SynthesisError):fonts.validate_soundfont(good)


def test_publish_rollback_and_protection(tmp_path,monkeypatch):
    from vocalscope.synthesis import export as exports
    work=tmp_path/'work';work.mkdir();out=tmp_path/'out'
    wav=work/'piano.wav';wav.write_bytes(b'new');manifest=work/'render.json';manifest.write_text('{}')
    staged={'wav':str(wav),'json':str(manifest)};original=exports.os.link
    def fail(source,target):
        if str(target).endswith('render.json'):raise PermissionError('simulated permission failure')
        return original(source,target)
    monkeypatch.setattr(exports.os,'link',fail)
    with pytest.raises(PermissionError):publish_render(staged,out)
    assert not list(out.iterdir())
    with pytest.raises(SynthesisError,match='input'):publish_render(staged,out,protected_paths=[out/'piano.wav'])


def test_optional_dependency_absence_is_actionable():
    code='''import builtins
real=builtins.__import__
def blocked(name,*args,**kwargs):
 if name=="fluidsynth":raise ImportError("simulated missing optional binding")
 return real(name,*args,**kwargs)
builtins.__import__=blocked
from vocalscope.synthesis.fluidsynth_backend import native_api
from vocalscope.synthesis.models import SynthesisError
try:native_api()
except SynthesisError as e:
 assert "optional synthesis" in str(e);assert "fluidsynth" in str(e)
else:raise AssertionError("missing backend silently replaced")
assert "gi" not in __import__('sys').modules
'''
    assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0


def measured_pitch(audio,sample_rate):
    # Measurement, not reference truth: expected frequencies below are fixed
    # musical notes independent of both this estimator and rendered output.
    import librosa
    y=audio.mean(axis=1).astype(float)
    values=librosa.yin(y,fmin=100,fmax=1000,sr=sample_rate,frame_length=2048,hop_length=256)
    return float(np.median(values[2:-2]))


@pytest.mark.synthesis
@pytest.mark.parametrize('rate',[44100,48000])
def test_real_a4_stereo_pitch_tail_and_determinism(soundfont_path,rate):
    config=RenderConfig(sample_rate=rate)
    audio,report=render_notes([note(start=.2,end=.8)],soundfont_path,config)
    assert audio.shape==(round(2.3*rate),2) and np.isfinite(audio).all()
    assert np.max(abs(audio[:round(.2*rate)]))<1e-10
    assert np.max(abs(audio[round(.8*rate):round(1.1*rate)]))>1e-5
    cents=1200*np.log2(measured_pitch(audio[round(.3*rate):round(.65*rate)],rate)/440)
    assert abs(cents)<35
    repeated,_=render_notes([note(start=.2,end=.8)],soundfont_path,config)
    np.testing.assert_array_equal(audio,repeated)
    assert report['scheduler']['unreleased_midi_notes']==0 and report['backend']['audio_driver'] is None


@pytest.mark.synthesis
def test_repeated_a4_and_melody(soundfont_path):
    rate=48000;config=RenderConfig(sample_rate=rate)
    notes=[note(start=s,end=s+.25,identity=str(i)) for i,s in enumerate([.1,.6,1.1])]
    audio,r=render_notes(notes,soundfont_path,config)
    assert len([e for e in r['scheduler']['events'] if e['kind']=='note_on'])==3
    for n in notes:
        before=audio[max(0,round((n.start_seconds-.04)*rate)):round(n.start_seconds*rate)]
        after=audio[round((n.start_seconds+.01)*rate):round((n.start_seconds+.09)*rate)]
        assert np.sqrt(np.mean(after**2))>2*max(1e-9,np.sqrt(np.mean(before**2)))
    notes=[note(key=k,start=i*.5,end=i*.5+.35,identity=str(i)) for i,k in enumerate([60,62,64,67])]
    audio,r=render_notes(notes,soundfont_path,config)
    for n in notes:
        frequency=measured_pitch(audio[round((n.start_seconds+.08)*rate):round((n.end_seconds-.03)*rate)],rate)
        assert abs(1200*np.log2(frequency/(440*2**((n.midi_note-69)/12))))<40
    assert [e['midi_note'] for e in r['scheduler']['events'] if e['kind']=='note_on']==[60,62,64,67]


@pytest.mark.synthesis
def test_real_empty_overlap_short_and_missing_preset(soundfont_path):
    audio,report=render_notes([],soundfont_path)
    assert audio.shape==(66150,2) and np.count_nonzero(audio)==0
    audio,_=render_notes([],soundfont_path,RenderConfig(tail_seconds=0));assert audio.shape==(1,2)
    notes=[note(end=.5,identity='a'),note(start=.1,end=.7,identity='b'),note(72,.1,.7,'c')]
    audio,r=render_notes(notes,soundfont_path);assert r['diagnostics']['peak_absolute']>0 and r['scheduler']['unreleased_midi_notes']==0
    render_notes([note(end=1/48000)],soundfont_path,RenderConfig(sample_rate=48000))
    with pytest.raises(SynthesisError,match='does not exist'):render_notes([note()],soundfont_path,RenderConfig(bank=16383,preset=127))
    with pytest.raises(SynthesisError,match='buffer budget'):render_notes([note(end=20)],soundfont_path,RenderConfig(max_buffer_mb=.01))


@pytest.mark.synthesis
def test_real_wav_flac_roundtrip_and_normalization(soundfont_path,tmp_path):
    config=RenderConfig(sample_rate=48000,normalize_peak=True)
    result=export_audio([note()],soundfont_path,tmp_path,config)
    wav,wr=sf.read(result['paths']['wav'],dtype='float32',always_2d=True);flac,fr=sf.read(result['paths']['flac'],dtype='float32',always_2d=True)
    assert wr==fr==48000 and wav.shape==flac.shape==(96000,2)
    assert abs(np.max(abs(wav))-.98)<1e-6
    assert np.max(abs(wav-flac))<=2**-23+1e-8
    assert sf.info(result['paths']['wav']).subtype=='FLOAT' and sf.info(result['paths']['flac']).subtype=='PCM_24'
    assert json.load(open(result['paths']['json']))['status']=='complete'
    with pytest.raises(FileExistsError):export_audio([note()],soundfont_path,tmp_path,config)
    assert not list(tmp_path.glob('.vocalscope-render-*'))


@pytest.mark.synthesis
def test_real_cancellation_cleanup_and_native_failure(soundfont_path,tmp_path,monkeypatch):
    from vocalscope.synthesis.fluidsynth_backend import FluidSynthBackend
    original=FluidSynthBackend.samples;closed=[];close=FluidSynthBackend.close;event=Event()
    def cancel_after_block(self,count):
        audio=original(self,count);event.set();return audio
    def record_close(self):closed.append(True);return close(self)
    monkeypatch.setattr(FluidSynthBackend,'samples',cancel_after_block);monkeypatch.setattr(FluidSynthBackend,'close',record_close)
    with pytest.raises(RenderCancelled):export_audio([note(end=60)],soundfont_path,tmp_path,cancelled=event)
    assert closed and not list(tmp_path.iterdir())
    monkeypatch.setattr(FluidSynthBackend,'samples',lambda self,count:np.full((count,2),np.nan,dtype='float32'))
    with pytest.raises(SynthesisError,match='Invalid stereo'):export_audio([note()],soundfont_path,tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.synthesis
def test_clipping_is_reported_not_hidden(soundfont_path,tmp_path):
    notes=[note(k,0,1,str(k),127) for k in range(48,84)]
    result=export_audio(notes,soundfont_path,tmp_path/'float',RenderConfig(gain=10),formats=('wav',))
    assert result['report']['diagnostics']['clipping_risk'] and sf.read(result['paths']['wav'])[0].max()>1
    with pytest.raises(SynthesisError,match='would clip'):export_audio(notes,soundfont_path,tmp_path/'integer',RenderConfig(gain=10))
    assert not list((tmp_path/'integer').iterdir())


@pytest.mark.synthesis
def test_real_project_cli_headless_and_source_preservation(soundfont_path,tmp_path):
    project=Path('results/stage3-human-pyin/vocadito_1.notes.json')
    if not project.exists():pytest.skip('Local Stage 3 genuine project unavailable')
    before=hashlib.sha256(project.read_bytes()).hexdigest()
    env=__import__('os').environ.copy()
    for key in ['DISPLAY','WAYLAND_DISPLAY','PULSE_SERVER','PIPEWIRE_REMOTE']:env.pop(key,None)
    code='from vocalscope.cli import main;import sys;rc=main(sys.argv[1:]);assert "gi" not in sys.modules and "torch" not in sys.modules;raise SystemExit(rc)'
    p=subprocess.run([sys.executable,'-c',code,'render-piano',str(project),'--soundfont',str(soundfont_path),'--sample-rate','48000','--output',str(tmp_path)],capture_output=True,text=True,env=env,timeout=60)
    assert p.returncode==0,p.stderr
    assert hashlib.sha256(project.read_bytes()).hexdigest()==before
    report=json.loads((tmp_path/'render.json').read_text());assert len(report['rendered_notes'])==65
    assert report['provenance']['project_sha256']==before
    assert sf.info(tmp_path/'piano.wav').channels==2


@pytest.mark.synthesis
def test_current_edited_project_needs_no_source_audio(soundfont_path,tmp_path,analyzed_case):
    from vocalscope.audio import load_audio
    from vocalscope.transcription.pipeline import transcribe_analysis
    from vocalscope.transcription.serialization import save_project
    from vocalscope.synthesis.project import read_project_snapshot
    from vocalscope.synthesis.process import render_snapshot_in_process
    _,a=analyzed_case('sine_A4');p=transcribe_analysis(load_audio(a.metadata.path),a)
    identity=p.notes[0].note_id;p.edit(identity,midi_note=70,start_seconds=.01,end_seconds=.6)
    right=p.split(identity,.3);p.merge(identity,right);p.add(.8,1.2,72)
    deleted=p.add(1.3,1.5,60);p.delete(deleted);p.undo();p.redo()
    path=tmp_path/'edited.json';save_project(p,path)
    doc=json.loads(path.read_text());doc['acoustic']['source']['path']='/no/such/original-audio.wav';path.write_text(json.dumps(doc,allow_nan=False))
    original=path.read_bytes();snapshot=read_project_snapshot(path)
    result=render_snapshot_in_process(snapshot,soundfont_path,tmp_path/'piano')
    assert [n['midi_note'] for n in result['report']['rendered_notes']]==[70,72]
    assert result['report']['rendered_notes'][0]['edited'] is True
    assert path.read_bytes()==original and result['report']['provenance']['edit_cursor']==p.cursor


@pytest.mark.synthesis
def test_process_cancel_and_native_invalid_font_cleanup(soundfont_path,tmp_path):
    from vocalscope.synthesis.process import render_snapshot_in_process,inspect_in_process
    event=Event();event.set();snapshot={'notes':[__import__('dataclasses').asdict(note(end=60))],'duration_seconds':60.,'provenance':{}}
    with pytest.raises(Exception,match='cancelled'):render_snapshot_in_process(snapshot,soundfont_path,tmp_path/'cancelled',cancelled=event)
    assert not list((tmp_path/'cancelled').iterdir())
    # Structurally valid RIFF but invalid native SoundFont: fail without a
    # Python traceback or any claimed completed render.
    bad=tmp_path/'bad.sf2';bad.write_bytes(b'RIFF\x04\x00\x00\x00sfbk')
    with pytest.raises(Exception,match='failed'):inspect_in_process(bad)


@pytest.mark.synthesis
def test_quiet_velocity_and_optional_effects(soundfont_path,tmp_path):
    quiet=note(velocity=1)
    result=export_audio([quiet],soundfont_path,tmp_path/'quiet',RenderConfig(reverb=True,chorus=True))
    assert 0<result['report']['diagnostics']['peak_absolute']<1e-3
    assert result['report']['backend']['settings']['synth.reverb.active']==1
    assert result['report']['backend']['settings']['synth.chorus.active']==1
    assert sf.read(result['paths']['flac'])[0].any()
    dry,_=render_notes([note()],soundfont_path,RenderConfig(tail_seconds=.1))
    wet,report=render_notes([note()],soundfont_path,RenderConfig(tail_seconds=.1,reverb=True,chorus=True))
    assert not np.array_equal(dry,wet) and report['configuration']['tail_seconds']==.1
