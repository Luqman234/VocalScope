# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import time
from pathlib import Path
import pytest

pytestmark=[pytest.mark.gui,pytest.mark.synthesis,pytest.mark.filterwarnings('ignore:.*is deprecated.*:DeprecationWarning:matplotlib.backends'),pytest.mark.filterwarnings('ignore:.*deprecated.*:DeprecationWarning:gi')]


@pytest.mark.parametrize('playback_sink',['fakesink',pytest.param('pipewiresink',marks=pytest.mark.audio_output)])
def test_native_playback_and_edit_audition(soundfont_path,analyzed_case,tmp_path,gst_available,record_testsuite_property,playback_sink):
    import gi
    gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
    from gi.repository import Gtk,Gdk,GLib
    Gtk.init()
    if Gdk.Display.get_default() is None:pytest.skip('No accessible native display')
    from vocalscope.gui import VocalScopeApplication
    from vocalscope.playback.models import PlaybackConfig,State
    from vocalscope.audio import load_audio
    from vocalscope.transcription.pipeline import transcribe_analysis
    from vocalscope.transcription.serialization import document
    _,a=analyzed_case('sine_A4');project=transcribe_analysis(load_audio(a.metadata.path),a)
    original_pitch=a.midi_pitch.copy();app=VocalScopeApplication();app.set_application_id('io.github.vocalscope.PlaybackTest.'+playback_sink);app.register(None);app.activate();w=app.get_active_window()
    ticks=[];timer=GLib.timeout_add(20,lambda:ticks.append(time.monotonic()) or GLib.SOURCE_CONTINUE)
    def until(predicate,timeout=15):
        end=time.monotonic()+timeout;context=GLib.MainContext.default()
        while not predicate() and time.monotonic()<end:
            while context.pending():context.iteration(False)
            time.sleep(.005)
        assert predicate(),w.transcription.playback.status.get_text()
    try:
        until(lambda:w.get_mapped());ws=w.transcription;p=ws.playback;p.config=PlaybackConfig(sink=playback_sink,master_gain=.03 if playback_sink=='pipewiresink' else .8);p.expander.set_expanded(True)
        p.vocal.set_text(a.metadata.path);p.command('play');until(lambda:p.transport and p.transport.snapshot().state==State.PLAYING and len(w.figure.axes)==3)
        p.command('stop');until(lambda:p.transport.snapshot().state==State.STOPPED);ws.set_project(project)
        ws.rendering.font_entry.set_text(str(soundfont_path));before=len(ticks)
        p.command('play');until(lambda:p.transport and p.transport.snapshot().state==State.PLAYING)
        until(lambda:p.view.drawn_position>.1 and len(w.figure.axes)==3)
        assert len(ticks)>before+2
        p.command('pause');until(lambda:p.transport.snapshot().state==State.PAUSED)
        paused=p.transport.snapshot().position_seconds;time.sleep(.05);assert abs(p.transport.snapshot().position_seconds-paused)<.002
        p.slider.set_value(.7);until(lambda:abs(p.transport.snapshot().position_seconds-.7)<.03)
        selected=ws.selected;until(lambda:selected in p.view.active_ids);assert ws.selected==selected
        p.offset.set_text('nan');p.render_preview();assert 'Preview render failed' in p.message and not p.coordinator.status().in_progress;p.offset.set_text('0')
        p.render_preview();until(lambda:p.coordinator.status().active_revision==p.coordinator.status().current_revision and p.coordinator.status().active_revision>0)
        for mode in [1,2,0]:
            p.mode.set_selected(mode);until(lambda:p.transport.snapshot().mode==['vocal','piano','mix'][mode])
        p.command('play');until(lambda:p.transport.snapshot().state==State.PLAYING)
        revision=p.coordinator.status().current_revision;ws.fields['midi_note'].set_text('71');ws.edit('apply')
        assert p.coordinator.status().current_revision>revision
        until(lambda:p.coordinator.status().active_revision==p.coordinator.status().current_revision)
        assert project.get(selected).midi_note==71 and p.transport.snapshot().piano_revision==p.coordinator.status().current_revision
        active_before=p.coordinator.status().active_revision;p.auto.set_active(False)
        ws.fields['midi_note'].set_text('72');ws.edit('apply');p.render_preview()
        assert p.coordinator.status().in_progress
        p.preview.get_next_sibling().emit('clicked')  # actual Cancel preview control
        until(lambda:not p.coordinator.status().in_progress)
        assert p.coordinator.status().active_revision==active_before
        p.render_preview();until(lambda:p.coordinator.status().active_revision==p.coordinator.status().current_revision)
        record_testsuite_property('preview_cancel_retry','passed')
        p.command('pause');until(lambda:p.transport.snapshot().state==State.PAUSED)
        p.loop_start.set_text('.2');p.loop_end.set_text('.5');p.loop_enabled.set_active(True)
        until(lambda:p.transport.snapshot().loop is not None and not p.transport.snapshot().seeking)
        p.command('play');until(lambda:p.transport.snapshot().loop_count>=2)
        p.loop_enabled.set_active(False);until(lambda:p.transport.snapshot().loop is None)
        p.command('stop');until(lambda:p.transport.snapshot().state==State.STOPPED)
        assert p.transport.snapshot().position_seconds<.002
        import numpy as np
        np.testing.assert_array_equal(original_pitch,project.acoustic.midi_pitch)
        record_testsuite_property('playback_display',Gdk.Display.get_default().__gtype__.name);record_testsuite_property('playhead_highlight_edit_audition','passed');record_testsuite_property('playback_heartbeat_count',str(len(ticks)-before))
        record_testsuite_property('playback_gui_sink',playback_sink)
        if p.age_samples:record_testsuite_property('playhead_snapshot_age_max_ms',str(max(p.age_samples)*1000))
        if p.age_samples:record_testsuite_property('playhead_snapshot_age_p95_ms',str(np.percentile(p.age_samples,95)*1000))
        if len(ticks)>1:
            record_testsuite_property('gtk_heartbeat_gap_p95_ms',str(np.percentile(np.diff(ticks),95)*1000));record_testsuite_property('gtk_heartbeat_gap_max_ms',str(max(np.diff(ticks))*1000))
        root=p.coordinator.root;p.command('play');ws.fields['midi_note'].set_text('73');ws.edit('apply');p.render_preview()
        assert p.coordinator.status().in_progress
        w.close();until(lambda:not w.get_mapped());p.cleanup_thread.join(10)
        assert not p.cleanup_thread.is_alive() and not root.exists() and p.transport.wait_closed()
        record_testsuite_property('playback_shutdown_cleanup','passed')
    finally:
        GLib.source_remove(timer);w.close();app.quit()
