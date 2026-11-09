# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from dataclasses import replace
from pathlib import Path
from time import monotonic,sleep
import numpy as np
import pytest
import soundfile as sf
from vocalscope.playback.models import *
from vocalscope.playback.transport import Transport
from vocalscope.playback.timeline import active_note_ids

# Prespecified software tolerances: two canonical samples PCM alignment,
# 20 ms query/seek tolerance, 2 ms paused drift; no physical output claim.
ALIGNMENT_SAMPLES=2


def wait(predicate,timeout=5):
    end=monotonic()+timeout
    while not predicate() and monotonic()<end:sleep(.005)
    assert predicate()


def peaks(rows,channel):
    out=[];previous_pts=-1;reset=True
    for pts,block in rows:
        if pts<previous_pts:reset=True
        previous_pts=pts
        indices=np.flatnonzero(abs(block[:,channel])>.005)
        for i in indices:
            timestamp=pts/1e9+int(i)/48000;amplitude=float(abs(block[i,channel]))
            if not reset and out and 0<=timestamp-out[-1][0]<.005:
                if amplitude>out[-1][1]:out[-1]=(timestamp,amplitude)
            else:out.append((timestamp,amplitude));reset=False
    return [t for t,_ in out]


def test_real_states_pause_stop_and_rapid_commands(impulse_files):
    t=Transport(PlaybackConfig(sink='appsink'))
    try:
        t.load(Session(vocal=Source(impulse_files[0]))).result(8);assert t.snapshot().state==State.READY
        t.play().result(3);sleep(.1);t.pause().result(3);first=t.snapshot().position_seconds;sleep(.1)
        assert abs(t.snapshot().position_seconds-first)<.002
        for _ in range(5):t.play().result(3);t.pause().result(3)
        t.seek(1.2).result(4);assert abs(t.snapshot().position_seconds-1.2)<.02
        seeks=[t.seek(.5+i*.02) for i in range(20)];stop=t.stop();stop.result(5)
        assert t.snapshot().state==State.STOPPED and abs(t.snapshot().position_seconds)<.002
        sleep(.05);assert abs(t.snapshot().position_seconds)<.002
    finally:t.close().result(3);assert t.wait_closed()


@pytest.mark.parametrize('offset,start',[(0.,0.),(0.,.6),(.2,0.),(.2,.6),(-.1,0.),(-.1,.6)])
def test_real_pcm_alignment_after_seek_and_offsets(impulse_files,offset,start):
    t=Transport(PlaybackConfig(sink='appsink',sink_sync=False))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1],offset))).result(8)
        t.set_mix('mix').result(3)
        if start:t.seek(start).result(5)
        t.capture(True).result(2);t.play().result(3);wait(lambda:t.snapshot().state==State.PAUSED)
        rows=t.capture().result(2);v=peaks(rows,0);p=peaks(rows,1)
        expected=[x for x in [.25,.75,1.25,2.25] if x>=start]
        expected_p=[x+offset for x in [.25,.75,1.25,2.25] if x+offset>=start]
        assert len(v)==len(expected) and len(p)==len(expected_p),(v,p)
        np.testing.assert_allclose(v,expected,atol=ALIGNMENT_SAMPLES/48000,rtol=0)
        np.testing.assert_allclose(p,expected_p,atol=ALIGNMENT_SAMPLES/48000,rtol=0)
    finally:t.close().result(3);assert t.wait_closed()


def test_shorter_source_ends_and_seek_after_eos(impulse_files,tmp_path):
    short=tmp_path/'short.wav';sf.write(short,np.zeros((24000,2)),48000)
    t=Transport(PlaybackConfig(sink='appsink',sink_sync=False))
    try:
        t.load(Session(vocal=Source(short),piano=Source(impulse_files[1]))).result(5)
        assert t.snapshot().duration_seconds==3
        t.seek(1.1).result(5);t.set_mix('piano').result(2);t.play().result(3);wait(lambda:t.snapshot().position_seconds>=2.99)
        t.pause().result(2);t.seek(.2).result(4);assert abs(t.snapshot().position_seconds-.2)<.02
        t.play().result(3)
    finally:t.close().result(3);t.wait_closed()


def test_loop_pcm_and_media_position(impulse_files):
    t=Transport(PlaybackConfig(sink='appsink'))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]))).result(5);t.set_mix('mix').result(2)
        t.set_loop(Loop(.6,.9)).result(4);t.play().result(3)
        wait(lambda:t.snapshot().loop_count>=3,3)
        assert .6<=t.snapshot().position_seconds<=.91
        rows=t.capture().result(2);v=peaks(rows,0);p=peaks(rows,1)
        assert len(v)>=3 and len(p)>=3
        assert max(abs(a-b) for a,b in zip(v,p))<=ALIGNMENT_SAMPLES/48000
        t.pause().result(2);t.seek(.7).result(4);t.play().result(3);t.stop().result(4)
        assert t.snapshot().state==State.STOPPED and t.snapshot().position_seconds<.002
        with pytest.raises(ValueError):t.set_loop(Loop(.9,.5)).result(3)
        t.set_loop(None).result(4)
    finally:t.close().result(3);t.wait_closed()


def test_mixer_does_not_restart_and_replacement_preserves_position(impulse_files):
    t=Transport(PlaybackConfig(sink='appsink'))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1],0.),piano_revision=1)).result(5)
        t.play().result(2)
        generation=t.snapshot().generation
        for mode in ['piano','mix','vocal','mix']:
            before=t.snapshot().position_seconds;t.set_mix(mode).result(2);assert t.snapshot().position_seconds>=before-.002
        assert t.snapshot().generation==generation
        t.pause().result(2);t.seek(.8).result(4);t.replace_piano(Source(impulse_files[1]),2).result(5)
        assert abs(t.snapshot().position_seconds-.8)<.02 and t.snapshot().piano_revision==2 and t.snapshot().state==State.PAUSED
        with pytest.raises(Superseded):t.replace_piano(Source(impulse_files[1]),1).result(3)
        t.play().result(2);before=t.snapshot().position_seconds;t.replace_piano(Source(impulse_files[1]),3).result(5);wait(lambda:t.snapshot().state==State.PLAYING)
        assert abs(t.snapshot().position_seconds-before)<.1
    finally:t.close().result(3);t.wait_closed()


def test_errors_recover_and_source_missing(impulse_files,tmp_path):
    t=Transport(PlaybackConfig(sink='fakesink'))
    try:
        with pytest.raises(PlaybackError):t.load(Session(vocal=Source(tmp_path/'missing.wav'))).result(5)
        assert t.snapshot().state==State.ERROR
        t.load(Session(vocal=Source(impulse_files[0]))).result(5);t.play().result(2)
        t.recover().result(5);wait(lambda:t.snapshot().state==State.PLAYING)
        bad=tmp_path/'bad.wav';bad.write_text('invalid media')
        with pytest.raises(PlaybackError):t.replace_piano(Source(bad),2).result(5)
        assert t.snapshot().state==State.PLAYING
    finally:t.close().result(3);assert t.wait_closed()


def test_actual_bus_error_and_clock_loss_recovery(impulse_files):
    from vocalscope.playback.gst import bindings
    from gi.repository import GLib
    Gst,*_=bindings();t=Transport(PlaybackConfig(sink='fakesink'))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]))).result(5);t.set_mix('piano').result(4);t.play().result(2)
        pipeline=t.engine.pipeline
        pipeline.post_message(Gst.Message.new_clock_lost(pipeline,pipeline.get_clock()));sleep(.05)
        assert t.snapshot().state==State.PLAYING
        error=GLib.Error.new_literal(Gst.ResourceError.quark(),'simulated output disconnection',int(Gst.ResourceError.FAILED))
        pipeline.post_message(Gst.Message.new_error(pipeline,error,'controlled integration-test bus fault'))
        wait(lambda:t.snapshot().state==State.ERROR);assert t.engine is None
        t.recover().result(6);wait(lambda:t.snapshot().state==State.PLAYING)
        assert t.snapshot().mode=='piano'
    finally:t.close().result(4);assert t.wait_closed()


def test_close_during_load_and_initial_obsolete_revision(impulse_files):
    t=Transport(PlaybackConfig(sink='fakesink'))
    f=t.load(Session(vocal=Source(impulse_files[0])));closed=t.close();closed.result(5);assert t.wait_closed()
    t=Transport(PlaybackConfig(sink='fakesink'))
    try:
        with pytest.raises(Superseded):t.load(Session(piano=Source(impulse_files[1]),piano_revision=2),accept=lambda:False).result(6)
        assert t.snapshot().state==State.EMPTY and t.engine is None
    finally:t.close().result(4);t.wait_closed()


def test_missing_gstreamer_shutdown_is_safe(tmp_path):
    import subprocess,sys
    script='''import builtins
real=builtins.__import__
def block(name,*a,**k):
 if name=="gi":raise ImportError("test unavailable optional GI")
 return real(name,*a,**k)
builtins.__import__=block
from vocalscope.playback.transport import Transport
from vocalscope.playback.models import Session,Source,PlaybackConfig,PlaybackError
t=Transport(PlaybackConfig(sink="fakesink"))
try:t.load(Session(vocal=Source("missing.wav"))).result(3)
except PlaybackError as e:assert "GStreamer playback unavailable" in str(e)
else:raise AssertionError("missing optional backend was substituted")
t.close().result(3)
assert t.wait_closed()
'''
    p=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=10);assert p.returncode==0,p.stderr


def test_nonfinite_pcm_is_rejected_before_output(tmp_path,gst_available):
    path=tmp_path/'invalid-float.wav';sf.write(path,np.full((48000,2),np.nan,dtype='float32'),48000,subtype='FLOAT')
    t=Transport(PlaybackConfig(sink='fakesink',operation_timeout=2))
    try:
        with pytest.raises(PlaybackError,match='non-finite'):t.load(Session(vocal=Source(path))).result(5)
        assert t.snapshot().state==State.ERROR
    finally:t.close().result(4);t.wait_closed()
