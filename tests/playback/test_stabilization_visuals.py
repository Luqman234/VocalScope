# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
import soundfile as sf
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from vocalscope.ui_metrics import LoopMetrics


def test_latency_deadlines_execution_gaps_and_phase_accounting():
    now=[0];m=LoopMetrics(interval=.01,clock=lambda:now[0]);m.begin()
    now[0]=12_000_000;m.tick(lambda:now.__setitem__(0,15_000_000))
    m.phase='blocked';now[0]=315_000_000;m.tick()
    d=m.report()
    assert d['samples'][0]['scheduled_ns']==10_000_000
    assert d['samples'][0]['delay_seconds']==.002 and d['samples'][0]['execution_seconds']==.003
    assert d['phases']['blocked']['delay']['max_ms']==290
    assert d['all']['gaps_above_ms']['250']==1 and d['dropped_samples']==0
    assert set(d['phases'])=={'startup','blocked'}
    with pytest.raises(ValueError):LoopMetrics(interval=0)


def test_waveform_cache_is_bounded_immutable_and_invalidated(tmp_path):
    from vocalscope.playback.waveform import overview,_overview
    _overview.cache_clear();path=tmp_path/'wave.wav';sf.write(path,np.zeros(480),48000)
    first=overview(path);second=overview(path);assert first is second and _overview.cache_info().hits==1
    assert not first[0].flags.writeable
    sf.write(path,np.ones(960)*.1,48000);third=overview(path);assert third is not first and max(third[2])>0
    for i in range(8):
        p=tmp_path/f'{i}.wav';sf.write(p,np.zeros(10),48000);overview(p)
    assert _overview.cache_info().currsize==4


def test_note_artist_and_static_layer_reuse(analyzed_case):
    from vocalscope.audio import load_audio
    from vocalscope.transcription.pipeline import transcribe_analysis
    from vocalscope.transcription.plotting import NotePlot
    from vocalscope.playback.timeline_view import TimelineView
    from vocalscope.playback.models import Snapshot,State
    _,a=analyzed_case('sine_A4');p=transcribe_analysis(load_audio(a.metadata.path),a);note=p.notes[0]
    p.notes=tuple(replace(note,note_id=str(i),start_seconds=i/40,end_seconds=(i+1)/40,midi_note=69,midi_pitch=69.,cents_deviation=0.) for i in range(65))
    fig=Figure(figsize=(8,5));canvas=FigureCanvasAgg(fig);plot=NotePlot(fig);plot.update(p)
    ws=SimpleNamespace(project=p,selected='1');w=SimpleNamespace(figure=fig,canvas=canvas,transcription=ws,closed=False)
    view=TimelineView(w);view.enabled=True;view.decorate(p.duration);canvas.draw();axes=tuple(fig.axes);patch=plot.patches['1']
    captures=view.counters['background_captures'];bakes=view.counters['note_bakes']
    for i in range(100):view.update(Snapshot(state=State.PLAYING,position_seconds=i*.01,position_valid=True))
    assert view.counters['dynamic_artists']<=500 and view.counters['background_captures']==captures
    assert view.counters['note_bakes']==bakes and len(view.overlays)<=2
    edited=replace(p.notes[1],midi_note=70,cents_deviation=-100.);p.notes=(p.notes[0],edited,*p.notes[2:])
    change=plot.update(p,selected='1',dynamic=True);view.decorate(p.duration,full=change['limits'])
    assert plot.rebuilds==1 and plot.patches['1'] is patch and tuple(fig.axes)==axes
    assert patch.get_y()==69.65 and view.counters['note_bakes']==bakes+1
    snapshot=Snapshot(position_seconds=.3,position_valid=True)
    view.update(snapshot);blits=view.counters['blits'];view.update(snapshot)
    assert view.counters['blits']==blits and view.counters['skipped_updates']>0
    view.shutdown();view.shutdown()
