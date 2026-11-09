# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from dataclasses import replace
import json,subprocess,sys
from pathlib import Path
from threading import Event
import pytest
from vocalscope.worker import transcribe_in_process
from vocalscope.transcription.models import TranscriptionConfig
from vocalscope.transcription.serialization import load_project


def test_transcription_cli_headless(tmp_path,analyzed_case):
    _,result=analyzed_case('sine_A4')
    code='from vocalscope.cli import main; import sys; rc=main(sys.argv[1:]); assert "gi" not in sys.modules; assert "torch" not in sys.modules; raise SystemExit(rc)'
    process=subprocess.run([sys.executable,'-c',code,'transcribe',result.metadata.path,'--output',str(tmp_path),'--estimator','yin'],capture_output=True,text=True,timeout=60)
    assert process.returncode==0,process.stderr
    project=load_project(next(tmp_path.glob('*.json')))
    assert project.acoustic.estimator_id=='yin' and len(project.notes)==1
    assert next(tmp_path.glob('*.mid')).read_bytes().startswith(b'MThd')
    bad=subprocess.run([sys.executable,'-m','vocalscope','transcribe',str(tmp_path/'missing.wav')],capture_output=True,text=True)
    assert bad.returncode!=0 and 'Traceback' not in bad.stderr


def test_transcription_worker_and_cancellation(analyzed_case):
    _,a=analyzed_case('sine_A4');p=transcribe_in_process(a)
    assert len(p.notes)==1 and p.notes[0].midi_note==69
    cancelled=Event();cancelled.set()
    with pytest.raises(Exception,match='cancelled'):transcribe_in_process(a,cancelled)
    bad=replace(a,backend_metadata={'source_sha256':'0'*64})
    with pytest.raises(Exception,match='changed'):transcribe_in_process(bad)


def test_development_selection_never_receives_test_ids():
    from vocalscope.transcription.benchmark import choose_configuration
    seen=[]
    def score(track,c):
        seen.append(track);assert track in ['1','2'];return .4+c.onset_threshold/10
    chosen,trials=choose_configuration(['1','2'],score)
    assert chosen.onset_threshold==.6 and len(trials)==4
    assert set(seen)=={'1','2'}


def test_invalid_project_and_source_protection(tmp_path,analyzed_case):
    from vocalscope.transcription.serialization import load_project,atomic_write
    p=tmp_path/'damaged.json';p.write_text('{"schema_version":"1.0.0","kind":"vocalscope.transcription"}')
    with pytest.raises(ValueError,match='Damaged'):load_project(p)
    p.write_text('{"value":NaN}')
    with pytest.raises(ValueError,match='Nonfinite'):load_project(p)
    with pytest.raises(ValueError,match='source'):atomic_write(p,b'bad',overwrite=True,source=p)


def test_reopened_project_rejects_changed_source(tmp_path,analyzed_case):
    import soundfile as sf
    import numpy as np
    from vocalscope.transcription.pipeline import transcribe_file
    from vocalscope.transcription.serialization import document,from_document
    _,a=analyzed_case('sine_A4');path=tmp_path/'source.wav';path.write_bytes(Path(a.metadata.path).read_bytes())
    p=transcribe_file(path);q=from_document(document(p))
    assert q.acoustic.backend_metadata['source_sha256']==q.source_sha256
    sf.write(path,np.zeros(q.acoustic.analysis_samples),q.acoustic.config.sample_rate,subtype='FLOAT')
    with pytest.raises(Exception,match='changed'):transcribe_in_process(q.acoustic)
