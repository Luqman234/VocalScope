# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Actual GTK/Wayland rendering, current-edit preservation, cancellation/recovery."""
import json,time,os
from pathlib import Path
import pytest
import soundfile as sf

pytestmark=[pytest.mark.gui,pytest.mark.synthesis,pytest.mark.filterwarnings('ignore:.*is deprecated.*:DeprecationWarning:matplotlib.backends'),pytest.mark.filterwarnings('ignore:.*deprecated.*:DeprecationWarning:gi')]


def test_native_offline_piano_render(soundfont_path,tmp_path,analyzed_case,record_testsuite_property):
    gi=pytest.importorskip('gi');gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
    from gi.repository import Gtk,Gdk,GLib
    Gtk.init()
    if Gdk.Display.get_default() is None:pytest.skip('No accessible native display')
    from vocalscope.gui import VocalScopeApplication
    from vocalscope.audio import load_audio
    from vocalscope.transcription.pipeline import transcribe_analysis
    from vocalscope.transcription.serialization import document
    _,a=analyzed_case('sine_A4');project=transcribe_analysis(load_audio(a.metadata.path),a)
    project.edit(project.notes[0].note_id,midi_note=70);before=document(project)
    app=VocalScopeApplication();app.set_application_id('io.github.vocalscope.SynthesisTest');app.register(None);app.activate();w=app.get_active_window()
    beats=[];timer=GLib.timeout_add(20,lambda:beats.append(time.monotonic()) or GLib.SOURCE_CONTINUE)
    def until(predicate,timeout=60):
        deadline=time.monotonic()+timeout;context=GLib.MainContext.default()
        while not predicate() and time.monotonic()<deadline:
            while context.pending():context.iteration(False)
            time.sleep(.005)
        assert predicate(),w.status.get_text()
    try:
        until(lambda:w.get_mapped());record_testsuite_property('synthesis_display',Gdk.Display.get_default().__gtype__.name)
        w.transcription.set_project(project);r=w.transcription.rendering;r.expander.set_expanded(True);r.font_entry.set_text(str(soundfont_path))
        r.verify.emit('clicked');assert w.busy;until(lambda:not w.busy)
        assert 'Piano 1' in r.instrument.get_text()
        r.rate.set_selected(1);heartbeats=len(beats)
        assert r.render_to(tmp_path/'audio');assert w.busy and not w.transcription.editor.get_sensitive()
        assert not r.render_to(tmp_path/'concurrent')
        until(lambda:not w.busy);assert len(beats)>heartbeats+2
        result=json.loads((tmp_path/'audio/render.json').read_text())
        assert result['rendered_notes'][0]['midi_note']==70 and result['rendered_notes'][0]['edited'] is True
        assert sf.info(tmp_path/'audio/piano.wav').samplerate==48000 and sf.info(tmp_path/'audio/piano.flac').channels==2
        assert document(project)==before
        r.render_to(tmp_path/'audio');until(lambda:not w.busy);assert 'Failed' in w.status.get_text()
        r.font_entry.set_text(str(tmp_path/'invalid.sf2'));r.inspect();until(lambda:not w.busy);assert 'Failed' in w.status.get_text()
        r.font_entry.set_text(str(soundfont_path));r.choose_font();assert w.dialog_cancellable
        GLib.timeout_add(400,lambda:w.dialog_cancellable.cancel() if w.dialog_cancellable else None)
        until(lambda:w.dialog_cancellable is None)
        assert r.render_to(tmp_path/'cancelled');r.cancel.emit('clicked');until(lambda:not w.busy)
        assert 'cancelled' in w.status.get_text().lower() and not list((tmp_path/'cancelled').iterdir())
        assert r.render_to(tmp_path/'cancelled');until(lambda:not w.busy);assert (tmp_path/'cancelled/render.json').exists()
        r.wav.set_active(False);r.flac.set_active(False);assert not r.render_to(tmp_path/'none')
        assert 'Select WAV' in w.status.get_text();r.wav.set_active(True)
        r.render_to(tmp_path/'wav-only');until(lambda:not w.busy);assert (tmp_path/'wav-only/piano.wav').exists() and not (tmp_path/'wav-only/piano.flac').exists()
        if os.geteuid()!=0:
            locked=tmp_path/'locked';locked.mkdir();locked.chmod(0o500)
            try:r.render_to(locked);until(lambda:not w.busy);assert 'Failed' in w.status.get_text()
            finally:locked.chmod(0o700)
        record_testsuite_property('native_render_edit_cancel_recovery','passed');record_testsuite_property('synthesis_heartbeats',str(len(beats)-heartbeats))
        r.render_to(tmp_path/'close');assert w.busy;w.close();until(lambda:not w.get_mapped());assert w.closed
        record_testsuite_property('close_during_piano_render','passed')
    finally:
        GLib.source_remove(timer);w.close();app.quit()
