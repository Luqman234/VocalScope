# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import json,os,subprocess,time
from dataclasses import asdict
import pytest
from vocalscope.playback.transport import Transport
from vocalscope.playback.models import *

pytestmark=pytest.mark.audio_output


def test_actual_pipewire_stream_and_cleanup(impulse_files,record_testsuite_property):
    t=Transport(PlaybackConfig(sink='pipewiresink',master_gain=.03))
    client_ids=[];node_serials=[]
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]))).result(12);t.set_mix('mix').result(4);t.play().result(5);time.sleep(.2)
        dump=json.loads(subprocess.check_output(['pw-dump'],text=True))
        clients=[o for o in dump if str(o.get('info',{}).get('props',{}).get('application.process.id'))==str(os.getpid())]
        client_ids=[o['id'] for o in clients]
        nodes=[o for o in dump if o['type'].endswith(':Node') and o.get('info',{}).get('props',{}).get('client.id') in client_ids]
        assert nodes and any(o['info']['state']=='running' for o in nodes),nodes
        node_serials=[o['info']['props']['object.serial'] for o in nodes]
        assert t.snapshot().position_seconds>.1 and t.snapshot().state==State.PLAYING
        diag=t.diagnostics().result(3);assert 'pipewire' in diag['clock'].lower()
        record_testsuite_property('real_pipewire_clock',diag['clock']);record_testsuite_property('real_pipewire_running_node_ids',str([n['id'] for n in nodes]))
        t.pause().result(4);t.seek(.5).result(5);t.set_mix('piano').result(4);t.play().result(3);time.sleep(.1)
        for mode in ['vocal','mix','piano','mix']:t.set_mix(mode).result(3)
        t.set_loop(Loop(.6,.9)).result(5)
        deadline=time.monotonic()+3
        while t.snapshot().loop_count<3 and time.monotonic()<deadline:time.sleep(.01)
        assert t.snapshot().loop_count>=3
        t.set_loop(None).result(4);t.pause().result(3)
        t.replace_piano(Source(impulse_files[1]),1).result(8);t.play().result(3);time.sleep(.1)
    finally:t.close().result(5);assert t.wait_closed()
    time.sleep(.1);after=json.loads(subprocess.check_output(['pw-dump'],text=True))
    # Numeric PipeWire IDs are immediately reusable by pw-dump itself. Compare
    # persistent object serials to verify that our actual audio nodes are gone.
    assert not any(o.get('info',{}).get('props',{}).get('object.serial') in node_serials for o in after)
    record_testsuite_property('pipewire_stream_cleanup','passed')


def test_native_pipewire_early_stop_and_close(impulse_files,tmp_path):
    for action in ['stop','close']:
        t=Transport(PlaybackConfig(sink='pipewiresink',master_gain=.03))
        load=t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1])))
        try:
            if action=='stop':t.stop().result(8);assert t.snapshot().state==State.STOPPED
        finally:t.close().result(8);assert t.wait_closed()
    import numpy as np,soundfile as sf
    invalid=tmp_path/'nonfinite.wav';sf.write(invalid,np.full(48000,np.nan),48000,subtype='FLOAT')
    t=Transport(PlaybackConfig(sink='pipewiresink',master_gain=.03))
    try:
        with pytest.raises(PlaybackError,match='non-finite'):t.load(Session(vocal=Source(invalid))).result(5)
        assert t.snapshot().state==State.ERROR
        dc=tmp_path/'constant.wav';sf.write(dc,np.full((24000,2),.1,dtype='float32'),48000,subtype='FLOAT')
        t.load(Session(vocal=Source(dc))).result(8)
        # Inspect the actual final PCM preroll before playing: a native-only
        # bootstrap must not leave the first audible buffer silently muted.
        assert .00299<t.snapshot().peak<.00301
    finally:t.close().result(5);assert t.wait_closed()
