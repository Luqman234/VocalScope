# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import gc,time,weakref
import numpy as np
import pytest
from vocalscope.playback.models import *
from vocalscope.playback.transport import Transport


def test_repeated_sessions_release_pipeline_wrappers_and_fds(impulse_files):
    import psutil
    process=psutil.Process();references=[];fds=[]
    for _ in range(15):
        t=Transport(PlaybackConfig(sink='fakesink'));t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]))).result(6)
        references.append(weakref.ref(t.engine.pipeline));t.play().result(3);t.pause().result(3);t.close().result(5);assert t.wait_closed();del t
        gc.collect();fds.append(process.num_fds())
    assert not any(r() is not None for r in references)
    assert max(fds[3:])-min(fds[3:])<=2,fds
    assert fds[-1]<=fds[3]+1,fds


def test_small_loop_exact_content_and_rapid_switches(impulse_files):
    t=Transport(PlaybackConfig(sink='appsink'))
    try:
        t.load(Session(vocal=Source(impulse_files[0]),piano=Source(impulse_files[1]))).result(6);t.set_mix('mix').result(3);t.set_loop(Loop(.2,.25)).result(4);t.play().result(3)
        deadline=time.monotonic()+4
        while t.snapshot().loop_count<12 and time.monotonic()<deadline:time.sleep(.01)
        assert t.snapshot().loop_count>=12;t.pause().result(3)
        sizes=[];size=0;previous=-1
        for pts,data in t.capture().result(3):
            if pts<previous:sizes.append(size);size=0
            previous=pts;size+=len(data)
        assert len(sizes)>=10 and all(n==2400 for n in sizes),sizes
        t.set_loop(None).result(4);t.play().result(3);generation=t.snapshot().generation
        for i in range(100):t.set_mix(['vocal','piano','mix'][i%3]).result(3)
        assert t.snapshot().generation==generation
    finally:t.close().result(5);assert t.wait_closed()


@pytest.mark.gui
@pytest.mark.synthesis
def test_native_cached_edit_reload_and_repeated_window_cleanup(soundfont_path,gst_available,analyzed_case,record_testsuite_property):
    import gi
    gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
    from gi.repository import Gtk,Gdk,GLib
    Gtk.init()
    if Gdk.Display.get_default() is None:pytest.skip('Native display required')
    from vocalscope.gui import VocalScopeApplication
    from vocalscope.audio import load_audio
    from vocalscope.transcription.pipeline import transcribe_analysis
    _,a=analyzed_case('sine_A4');app=VocalScopeApplication();app.set_application_id('io.github.vocalscope.StabilizationLifecycle');app.register(None)
    def until(predicate,timeout=12):
        deadline=time.monotonic()+timeout;context=GLib.MainContext.default()
        while not predicate() and time.monotonic()<deadline:
            while context.pending():context.iteration(False)
            time.sleep(.003)
        assert predicate()
    roots=[];source_ids=[]
    try:
        for i in range(4):
            app.activate();w=app.get_active_window();until(lambda:w.get_mapped());ws=w.transcription
            ws.set_project(transcribe_analysis(load_audio(a.metadata.path),a));p=ws.playback;p.config=PlaybackConfig(sink='fakesink');p.auto.set_active(False)
            p.command('play');until(lambda:p.prepared and p.view.drawn_position>.05);axes=tuple(w.figure.axes);builds=p.view.counters['full_layouts'];old_patch=ws.note_plot.patches[ws.selected]
            frames=w.canvas.presented_frames;until(lambda:w.canvas.presented_frames>=frames+3)
            for key in [69,70,69,70,69]:ws.fields['midi_note'].set_text(str(key));ws.edit('apply')
            assert tuple(w.figure.axes)==axes and p.view.counters['full_layouts']==builds
            assert ws.note_plot.patches[ws.selected] is old_patch
            p.command('load');until(lambda:p.prepared and not p.transport.snapshot().seeking);p.command('play');until(lambda:p.transport.snapshot().position_seconds>.15)
            until(lambda:abs(p.view.drawn_position-p.transport.snapshot().position_seconds)<.06)
            assert p.view.lines and all(line.axes is not None for line in p.view.lines)
            timer=p.timer;root=p.coordinator.root;roots.append(root);source_ids.append(timer)
            w.close();until(lambda:not w.get_mapped() and not p.cleanup_thread.is_alive())
            assert GLib.MainContext.default().find_source_by_id(timer) is None and p.transport.wait_closed()
            assert not root.exists();del p,ws,w;gc.collect()
        record_testsuite_property('repeated_native_windows','4');record_testsuite_property('incremental_note_artist_reuse','passed');record_testsuite_property('glib_timer_cleanup','passed')
        record_testsuite_property('native_gtk_paint_callbacks','advanced during queried-time cursor updates')
    finally:
        for w in app.get_windows():w.close()
        app.quit()
