# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Real mapped Wayland note editing, project persistence, failure and recovery."""
import time
from pathlib import Path
import pytest

pytestmark=[pytest.mark.gui,pytest.mark.filterwarnings('ignore:.*is deprecated.*:DeprecationWarning:matplotlib.backends'),pytest.mark.filterwarnings('ignore:.*deprecated.*:DeprecationWarning:gi')]


def test_native_transcription_editor(tmp_path,analyzed_case,record_testsuite_property):
    gi=pytest.importorskip('gi');gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
    from gi.repository import Gtk,Gdk,GLib
    Gtk.init()
    if Gdk.Display.get_default() is None:pytest.skip('No accessible native display')
    from vocalscope.gui import VocalScopeApplication
    from vocalscope.transcription.serialization import load_project
    import pretty_midi
    app=VocalScopeApplication();app.set_application_id('io.github.vocalscope.TranscriptionTest');app.register(None);app.activate();w=app.get_active_window()
    record_testsuite_property('transcription_display',Gdk.Display.get_default().__gtype__.name)
    beats=[];timer=GLib.timeout_add(20,lambda:beats.append(time.monotonic()) or GLib.SOURCE_CONTINUE)
    def until(predicate,timeout=60):
        deadline=time.monotonic()+timeout;context=GLib.MainContext.default()
        while not predicate() and time.monotonic()<deadline:
            while context.pending():context.iteration(False)
            time.sleep(.005)
        assert predicate(),w.status.get_text()
    try:
        until(lambda:w.get_mapped());_,a=analyzed_case('sine_A4')
        w.load_path(Path(a.metadata.path));until(lambda:not w.busy)
        w.analyze_button.emit('clicked');until(lambda:not w.busy);assert w.result is not None
        ws=w.transcription;before=len(beats);ws.generate.emit('clicked');assert w.busy
        assert not w._start_job(lambda:None,lambda _:None,'reject')
        until(lambda:not w.busy);assert len(beats)>before+2
        assert ws.project and len(ws.project.notes)==1 and len(w.figure.axes)==2
        acoustic=ws.project.acoustic.midi_pitch.copy();id=ws.selected
        ws.fields['midi_note'].set_text('70');ws.edit('apply');assert ws.project.get(id).midi_note==70
        ws.edit('split');assert len(ws.project.notes)==2
        ws.edit('merge');assert len(ws.project.notes)==1
        ws.edit('undo');assert len(ws.project.notes)==2
        ws.edit('redo');assert len(ws.project.notes)==1
        ws.fields['start_seconds'].set_text('-1');ws.edit('apply');assert 'rejected' in w.status.get_text()
        ws.select();ws.generate_notes();assert not w.busy and ws.project.get(id).midi_note==70
        saved=tmp_path/'edited.json';ws.save_to(saved);until(lambda:not w.busy);assert saved.exists()
        assert load_project(saved).notes==ws.project.notes
        ws.load_from(saved);until(lambda:not w.busy);assert ws.project.get(id).midi_note==70
        ws.midi_to(tmp_path/'melody.mid');until(lambda:not w.busy)
        assert pretty_midi.PrettyMIDI(str(tmp_path/'melody.mid')).instruments[0].notes[0].pitch==70
        ws.midi_to(tmp_path/'melody.mid');until(lambda:not w.busy);assert 'Failed' in w.status.get_text()
        ws.edit('delete');assert not ws.project.notes
        ws.fields['start_seconds'].set_text('.2');ws.fields['end_seconds'].set_text('.4');ws.fields['midi_note'].set_text('60');ws.edit('add');assert len(ws.project.notes)==1
        ws.edit('undo');ws.edit('undo');assert ws.project.notes[0].note_id==id
        import numpy as np
        np.testing.assert_array_equal(acoustic,ws.project.acoustic.midi_pitch)
        ws.save_to(tmp_path/'version2.json');until(lambda:not w.busy)
        ws.choose('load');assert w.dialog_cancellable
        GLib.timeout_add(400,lambda:w.dialog_cancellable.cancel() if w.dialog_cancellable else None)
        until(lambda:w.dialog_cancellable is None)
        ws.generate_notes();until(lambda:not w.busy);assert ws.project.notes[0].midi_note==69
        record_testsuite_property('note_edit_save_load_midi','passed')
        record_testsuite_property('transcription_heartbeat',str(len(beats)-before))
        ws.generate_notes();assert w.busy;w.close();until(lambda:not w.get_mapped());assert w.closed
        record_testsuite_property('close_during_transcription','passed')
    finally:
        GLib.source_remove(timer);w.close();app.quit()
