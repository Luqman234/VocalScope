# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from pathlib import Path
from threading import Event
from time import monotonic,sleep
import numpy as np
import pytest
import soundfile as sf
from vocalscope.playback.render_coordinator import RenderCoordinator
from vocalscope.playback.models import *
from vocalscope.playback.transport import Transport
from vocalscope.synthesis.project import project_snapshot
from vocalscope.synthesis.process import render_snapshot_in_process
from vocalscope.synthesis.models import RenderConfig
from vocalscope.audio import load_audio
from vocalscope.transcription.pipeline import transcribe_analysis


def until(predicate,timeout=10):
    deadline=monotonic()+timeout
    while not predicate() and monotonic()<deadline:sleep(.01)
    assert predicate()


@pytest.mark.synthesis
def test_real_edit_render_replace_and_file_lifetime(soundfont_path,analyzed_case,gst_available):
    _,a=analyzed_case('sine_A4');p=transcribe_analysis(load_audio(a.metadata.path),a);c=RenderCoordinator();t=Transport(PlaybackConfig(sink='fakesink'))
    try:
        first=c.request(project_snapshot(p),soundfont_path);until(lambda:c.status().validated_revision==first)
        path1=c.files[first]['path'];assert c.pin(first)
        t.load(Session(piano=Source(path1),piano_revision=first),accept=lambda:c.commit(first)).result(6);c.unpin(first)
        t.seek(.6).result(4);p.edit(p.notes[0].note_id,midi_note=71)
        second=c.request(project_snapshot(p),soundfont_path);until(lambda:c.status().validated_revision==second)
        assert path1.exists() and c.status().active_revision==first
        assert c.pin(second);path2=c.files[second]['path'];t.replace_piano(Source(path2),second,accept=lambda:c.commit(second)).result(5);c.unpin(second)
        assert t.snapshot().piano_revision==second and abs(t.snapshot().position_seconds-.6)<.02
        assert path2.exists() and not path1.exists()
        y,sr=sf.read(path2,always_2d=True)
        import librosa
        pitch=librosa.yin(y[int(.2*sr):int(.6*sr)].mean(axis=1),fmin=100,fmax=1000,sr=sr)
        assert abs(1200*np.log2(np.median(pitch)/(440*2**(2/12))))<35
    finally:t.close().result(4);t.wait_closed();c.close();assert not c.root.exists()


@pytest.mark.synthesis
def test_old_real_render_completes_after_new_and_is_discarded(soundfont_path,analyzed_case,gst_available):
    _,a=analyzed_case('sine_A4');p=transcribe_analysis(load_audio(a.metadata.path),a);old_ready=Event();release_old=Event()
    def runner(snapshot,font,directory,config,**kwargs):
        result=render_snapshot_in_process(snapshot,font,directory,config,formats=('wav',))
        if snapshot['notes'][0]['midi_note']==69:old_ready.set();assert release_old.wait(8)
        return result
    c=RenderCoordinator(runner)
    try:
        first=c.request(project_snapshot(p),soundfont_path);assert old_ready.wait(8)
        p.edit(p.notes[0].note_id,midi_note=72);second=c.request(project_snapshot(p),soundfont_path)
        until(lambda:c.status().validated_revision==second);release_old.set();until(lambda:not c.status().in_progress)
        assert c.status().validated_revision==second and first not in c.files and second in c.files
        assert not c.commit(first) and c.commit(second)
    finally:release_old.set();c.close()


def test_replacement_rejects_stale_activation_and_restores_session(impulse_files):
    t=Transport(PlaybackConfig(sink='fakesink'))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]),piano_revision=3)).result(5)
        t.seek(.7).result(4)
        with pytest.raises(Superseded):t.replace_piano(Source(impulse_files[1]),4,accept=lambda:False).result(8)
        assert t.snapshot().piano_revision==3 and abs(t.snapshot().position_seconds-.7)<.02
        with pytest.raises(ValueError):t.replace_piano(Source(impulse_files[1]),-1).result(3)
    finally:t.close().result(3);t.wait_closed()


@pytest.mark.synthesis
def test_failed_and_cancelled_preview_keeps_last_real_audio(soundfont_path,analyzed_case):
    _,a=analyzed_case('sine_A4');p=transcribe_analysis(load_audio(a.metadata.path),a)
    completed=Event();release=Event();calls=[]
    def runner(snapshot,font,directory,config,**kwargs):
        calls.append(len(calls)+1)
        if len(calls)==2:raise RuntimeError('controlled render worker failure')
        result=render_snapshot_in_process(snapshot,font,directory,config,formats=('wav',))
        if len(calls)==3:completed.set();assert release.wait(8)
        return result
    c=RenderCoordinator(runner)
    try:
        first=c.request(project_snapshot(p),soundfont_path);until(lambda:c.status().validated_revision==first);assert c.commit(first);original=c.files[first]['path'];identity=original.read_bytes()
        p.edit(p.notes[0].note_id,midi_note=71);second=c.request(project_snapshot(p),soundfont_path)
        until(lambda:c.status().state=='ERROR');assert 'controlled render worker failure' in c.status().error
        assert c.status().active_revision==first and original.read_bytes()==identity
        c.render_current(soundfont_path);assert completed.wait(8);c.cancel();release.set();until(lambda:not c.status().in_progress)
        assert c.status().validated_revision==first and original.read_bytes()==identity and not c.commit(second)
        c.render_current(soundfont_path);until(lambda:c.status().validated_revision==second);assert c.commit(second)
    finally:release.set();c.close()


@pytest.mark.synthesis
def test_cancelled_activation_token_cannot_commit_after_retry(soundfont_path,analyzed_case,gst_available):
    _,a=analyzed_case('sine_A4');p=transcribe_analysis(load_audio(a.metadata.path),a);c=RenderCoordinator();t=Transport(PlaybackConfig(sink='fakesink'))
    try:
        first=c.request(project_snapshot(p),soundfont_path);until(lambda:c.status().validated_revision==first)
        assert c.pin(first);token=c.activation_token(first)
        t.load(Session(piano=Source(c.files[first]['path']),piano_revision=first),accept=lambda:c.commit(first,token)).result(7);c.unpin(first);t.seek(.5).result(3)
        p.edit(p.notes[0].note_id,midi_note=72);second=c.request(project_snapshot(p),soundfont_path);until(lambda:c.status().validated_revision==second)
        token=c.activation_token(second);assert c.pin(second)
        def cancel_during_activation():
            c.cancel();c.resume_current()
            return c.commit(second,token)
        with pytest.raises(Superseded):t.replace_piano(Source(c.files[second]['path']),second,accept=cancel_during_activation).result(8)
        c.unpin(second)
        assert t.snapshot().piano_revision==first and abs(t.snapshot().position_seconds-.5)<.02 and c.status().active_revision==first
        assert c.pin(second);fresh=c.activation_token(second);t.replace_piano(Source(c.files[second]['path']),second,accept=lambda:c.commit(second,fresh)).result(6);c.unpin(second)
        assert t.snapshot().piano_revision==second and not c.pins
    finally:t.close().result(5);t.wait_closed();c.close()


@pytest.mark.synthesis
def test_immediate_render_retry_waits_for_cancelled_worker(soundfont_path,analyzed_case):
    _,a=analyzed_case('sine_A4');p=transcribe_analysis(load_audio(a.metadata.path),a);started=Event();release=Event();calls=[]
    def runner(snapshot,font,directory,config,**kwargs):
        calls.append(1)
        if len(calls)==1:started.set();assert release.wait(8)
        return render_snapshot_in_process(snapshot,font,directory,config,**kwargs)
    c=RenderCoordinator(runner)
    try:
        revision=c.request(project_snapshot(p),soundfont_path);assert started.wait(5)
        c.cancel();c.render_current(soundfont_path);release.set()
        until(lambda:c.status().validated_revision==revision)
        assert len(calls)==2 and c.status().discarded_revisions==1 and c.commit(revision,c.activation_token(revision))
    finally:release.set();c.close()
