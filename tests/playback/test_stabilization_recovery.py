# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import json,os,socket,subprocess,time
from pathlib import Path
import pytest
from vocalscope.playback.models import *
from vocalscope.playback.transport import Transport


def wait(predicate,timeout=6):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:time.sleep(.005)
    assert predicate()


def test_pause_and_stop_intent_during_error_prevent_unwanted_resume(impulse_files):
    Loop(.2,.25).validate(1.)  # exact 50ms, despite binary subtraction rounding
    from vocalscope.playback.gst import bindings
    from gi.repository import GLib
    Gst,*_=bindings();t=Transport(PlaybackConfig(sink='fakesink'))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]))).result(5);t.set_mix('piano').result(3);t.play().result(3);time.sleep(.05)
        def error():
            p=t.engine.pipeline;e=GLib.Error.new_literal(Gst.ResourceError.quark(),'controlled sink fault',int(Gst.ResourceError.FAILED));p.post_message(Gst.Message.new_error(p,e,'test fault'));wait(lambda:t.snapshot().state==State.ERROR)
        error();t.pause().result(3);position=t.snapshot().position_seconds;t.recover().result(5)
        wait(lambda:t.snapshot().state==State.PAUSED);assert abs(t.snapshot().position_seconds-position)<.02 and t.snapshot().mode=='piano'
        t.play().result(3);error();t.stop().result(3);t.recover().result(5)
        wait(lambda:t.snapshot().state==State.STOPPED);assert t.snapshot().position_seconds<.002
    finally:t.close().result(5);assert t.wait_closed()


def test_close_acknowledgement_is_idempotent(impulse_files):
    t=Transport(PlaybackConfig(sink='fakesink'));t.load(Session(vocal=Source(impulse_files[0]))).result(5)
    first=t.close();assert t.close() is first;first.result(5);assert t.wait_closed() and t.engine is None
    t=Transport(PlaybackConfig(sink='fakesink'));t.load(Session(vocal=Source(impulse_files[0]))).result(5)
    recovery=t.recover();closed=t.close();closed.result(5)
    assert t.wait_closed() and recovery.done() and t.engine is None


@pytest.mark.audio_output
def test_private_pipewire_connection_disconnect_and_actual_recovery(impulse_files,monkeypatch,record_testsuite_property):
    """Only our client's socket is interrupted. No device/service is modified."""
    from vocalscope.playback.engine import Engine
    original=Engine.element;connections=[]
    def element(self,factory,name):
        e=original(self,factory,name)
        if factory=='pipewiresink':
            sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.connect(str(Path(os.environ['XDG_RUNTIME_DIR'])/'pipewire-0'))
            # Installed plugin duplicates the provided fd with F_DUPFD_CLOEXEC;
            # the Python socket remains ours and can safely disconnect only it.
            e.set_property('fd',sock.fileno());connections.append(sock)
        return e
    monkeypatch.setattr(Engine,'element',element)
    t=Transport(PlaybackConfig(sink='pipewiresink',master_gain=.03,operation_timeout=5))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]))).result(9);t.set_mix('mix').result(4);t.play().result(3);time.sleep(.15)
        generation=t.snapshot().generation;position=t.snapshot().position_seconds
        begin=time.monotonic();connections[-1].shutdown(socket.SHUT_RDWR)
        wait(lambda:t.snapshot().state==State.ERROR,8);detection=time.monotonic()-begin
        assert t.engine is None and t.snapshot().position_seconds>=position-.03
        begin=time.monotonic();t.recover().result(9);wait(lambda:t.snapshot().state==State.PLAYING)
        recovery=time.monotonic()-begin;assert t.snapshot().generation>generation and t.snapshot().mode=='mix'
        before=t.snapshot().position_seconds;time.sleep(.15);assert t.snapshot().position_seconds>before+.05
        dump=json.loads(subprocess.check_output(['pw-dump'],text=True));clients=[o['id'] for o in dump if str(o.get('info',{}).get('props',{}).get('application.process.id'))==str(os.getpid())]
        nodes=[o for o in dump if o['type'].endswith(':Node') and o.get('info',{}).get('props',{}).get('client.id') in clients]
        assert sum(o['info']['state']=='running' for o in nodes)==1
        record_testsuite_property('private_pipewire_disconnect_detection_seconds',str(detection));record_testsuite_property('private_pipewire_actual_recovery_seconds',str(recovery));record_testsuite_property('private_connection_recovery','actual running native stream and advancing media time')
        pending=t.recover();t.close().result(8);assert t.wait_closed() and pending.done() and t.engine is None
        record_testsuite_property('native_close_during_recovery','passed')
    finally:
        t.close().result(8);assert t.wait_closed()
        for s in connections:s.close()


@pytest.mark.audio_output
def test_unavailable_private_pulse_endpoint_then_real_recovery(impulse_files,monkeypatch,record_testsuite_property):
    from vocalscope.playback.engine import Engine
    original=Engine.element;fault=[True]
    def element(self,factory,name):
        e=original(self,factory,name)
        if factory=='pulsesink' and fault[0]:e.set_property('server',f'unix:/tmp/vocalscope-absent-{os.getpid()}')
        return e
    monkeypatch.setattr(Engine,'element',element);t=Transport(PlaybackConfig(sink='pulsesink',master_gain=.03,operation_timeout=3))
    try:
        begin=time.monotonic()
        with pytest.raises(PlaybackError):t.load(Session(vocal=Source(impulse_files[0]))).result(6)
        assert t.snapshot().state==State.ERROR and t.engine is None;elapsed=time.monotonic()-begin
        fault[0]=False;t.recover().result(7);t.play().result(4);before=t.snapshot().position_seconds;time.sleep(.15)
        assert t.snapshot().position_seconds>before+.05
        record_testsuite_property('absent_endpoint_detection_seconds',str(elapsed));record_testsuite_property('pulse_endpoint_recovery','actual playback with advancing media position')
    finally:t.close().result(6);assert t.wait_closed()
