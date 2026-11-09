# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import json,os,subprocess,sys
from pathlib import Path
import pytest
from vocalscope.playback.models import *
from vocalscope.playback.timeline import active_note_ids


def test_headless_cli_uses_no_gtk_synth_or_torch(impulse_files,tmp_path):
    output=tmp_path/'diagnostic.json'
    script='''import sys
from vocalscope.cli import main
code=main(sys.argv[1:])
assert not any(n.startswith(('gi.repository.Gtk','torch','fluidsynth')) for n in sys.modules)
raise SystemExit(code)
'''
    env=dict(os.environ);env.pop('DISPLAY',None);env.pop('WAYLAND_DISPLAY',None)
    args=['playback-test','--vocal',str(impulse_files[0]),'--piano',str(impulse_files[1]),'--sink','appsink','--seconds','.2','--output',str(output)]
    run=subprocess.run([sys.executable,'-c',script,*args],env=env,text=True,capture_output=True,timeout=15)
    assert run.returncode==0,run.stderr
    result=json.loads(output.read_text());assert result['status']=='complete' and abs(result['paused_drift_seconds'])<.002
    bad=subprocess.run([sys.executable,'-m','vocalscope','playback-test','--vocal',str(tmp_path/'missing.wav'),'--output',str(output)],env=env,text=True,capture_output=True,timeout=8)
    assert bad.returncode!=0 and json.loads(output.read_text())==result
    from vocalscope.playback.diagnostics import run_playback_test
    before=impulse_files[1].read_bytes()
    with pytest.raises(ValueError,match='either audio source'):run_playback_test(impulse_files[0],impulse_files[1],impulse_files[1])
    assert impulse_files[1].read_bytes()==before


def test_contract_validation_and_overlapping_highlights():
    for kwargs in [{'fade_seconds':0.},{'sample_rate':44100},{'master_gain':float('nan')},{'capture_seconds':121},{'sink':'unknown'}]:
        with pytest.raises(ValueError):PlaybackConfig(**kwargs)
    with pytest.raises(ValueError):Session()
    with pytest.raises(ValueError):Session(vocal=Source('a'),piano_revision=-1)
    with pytest.raises(ValueError):Source('a',float('inf'))
    with pytest.raises(ValueError):Loop(.2,.21).validate(1.)
    from types import SimpleNamespace
    notes=[SimpleNamespace(note_id='a',start_seconds=.1,end_seconds=.5),SimpleNamespace(note_id='b',start_seconds=.2,end_seconds=.6)]
    assert active_note_ids(notes,.2)==('a','b') and active_note_ids(notes,.5)==('b',) and active_note_ids(notes,.6)==()
