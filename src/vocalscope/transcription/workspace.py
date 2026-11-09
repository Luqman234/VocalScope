# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""GTK note controls. Editing stays on main thread; DSP stays in owned process."""
from pathlib import Path
from io import BytesIO
from gi.repository import Gtk,Gio,GLib
from ..worker import transcribe_in_process
from ..export import result_document
from .models import TranscriptionResult
from .serialization import save_project,load_project,atomic_write
from .midi_export import midi_bytes
from .plotting import draw,NotePlot


class TranscriptionWorkspace:
    def __init__(self,window,body):
        self.window=window;self.project=None;self.saved_document=None;self.selected=None;self.updating=False
        row=Gtk.Box(spacing=6)
        self.generate=Gtk.Button(label='Generate notes',sensitive=False)
        self.generate.connect('clicked',lambda *_:self.generate_notes());row.append(self.generate)
        self.actions=[]
        for label,action in [('Load project…','load'),('Save project…','save'),('Export MIDI…','midi')]:
            b=Gtk.Button(label=label);b.connect('clicked',lambda _,a=action:self.choose(a));row.append(b);self.actions.append(b)
        body.append(row)
        self.editor=Gtk.Expander(label='Edit piano notes',sensitive=False)
        grid=Gtk.Grid(column_spacing=6,row_spacing=4);self.editor.set_child(grid);body.append(self.editor)
        self.selector=Gtk.DropDown.new_from_strings([]);self.selector.set_hexpand(True);self.selector.connect('notify::selected',self.select)
        grid.attach(self.selector,0,0,3,1)
        self.fields={}
        for i,(key,label) in enumerate([('midi_note','MIDI key'),('start_seconds','Start s'),('end_seconds','End s')]):
            entry=Gtk.Entry(width_chars=8);self.fields[key]=entry
            group=Gtk.Box(spacing=4);group.append(Gtk.Label(label=label));group.append(entry);grid.attach(group,i+3,0,1,1)
        for i,(label,command) in enumerate([('Apply','apply'),('Add','add'),('Delete','delete'),('Split midpoint','split'),('Merge next','merge'),('Undo','undo'),('Redo','redo')]):
            b=Gtk.Button(label=label);b.connect('clicked',lambda _,c=command:self.edit(c));grid.attach(b,i,1,1,1)
        self.click_handler=window.canvas.mpl_connect('button_press_event',self.click);self.note_plot=NotePlot(window.figure)
        self.refresh()
        from ..synthesis.workspace import RenderWorkspace
        self.rendering=RenderWorkspace(self,body)
        from ..playback.workspace import PlaybackWorkspace
        self.playback=PlaybackWorkspace(self,body)

    def dirty(self):
        from .serialization import document
        return self.project is not None and self.project.cursor>0 and document(self.project)!=self.saved_document

    def guard(self):
        if self.dirty():
            self.window.status.set_text('Save the edited project before replacing this transcription. Existing acoustic measurements remain available.');return False
        return True

    def refresh(self):
        w=self.window
        self.generate.set_sensitive(not w.busy and w.result is not None)
        self.editor.set_sensitive(not w.busy and self.project is not None)
        for i,b in enumerate(self.actions):b.set_sensitive(not w.busy and (i==0 or self.project is not None))
        if hasattr(self,"rendering"):self.rendering.refresh()

    def set_project(self,p,*,saved=False):
        from .serialization import document
        self.project=p;self.saved_document=document(p) if saved else None
        self.window.result=p.acoustic;self.window.source=Path(p.acoustic.metadata.path)
        self.window.file_label.set_text(f'{p.acoustic.metadata.filename} · {p.duration:.3f} s · saved acoustic analysis and editable notes')
        self.selected=p.notes[0].note_id if p.notes else None
        self.editor.set_expanded(True);self.update_notes()
        if hasattr(self,'playback'):self.playback.project_changed(p)
        self.window._set_busy(False,f'{len(p.notes)} editable notes · {p.acoustic.estimator_id} · {p.config.method}. MIDI uses discrete piano keys; acoustic pitch is preserved.')

    def update_notes(self):
        self.updating=True
        notes=self.project.notes if self.project else ()
        self.selector.set_model(Gtk.StringList.new([f'{i+1}: MIDI {n.midi_note} · {n.start_seconds:.3f}–{n.end_seconds:.3f} s' for i,n in enumerate(notes)]))
        index=next((i for i,n in enumerate(notes) if n.note_id==self.selected),0)
        self.selector.set_selected(index);self.updating=False;self.select(redraw=False);self.draw();self.refresh()

    def select(self,*_,redraw=True):
        if self.updating or self.project is None:return
        i=self.selector.get_selected()
        if i>=len(self.project.notes):self.selected=None;return
        n=self.project.notes[i];self.selected=n.note_id
        self.fields['midi_note'].set_text(str(n.midi_note));self.fields['start_seconds'].set_text(f'{n.start_seconds:.9f}');self.fields['end_seconds'].set_text(f'{n.end_seconds:.9f}')
        if redraw:self.draw()

    def draw(self):
        if self.project:
            dynamic=hasattr(self,'playback') and self.playback.prepared
            change=self.note_plot.update(self.project,selected=self.selected,dark=self.window.style_manager.get_dark(),dynamic=dynamic)
            if dynamic:self.playback.decorate(full=change['rebuilt'] or change['limits'])
            else:self.window.canvas.draw_idle()
            if change['rebuilt']:self.window.toolbar.update()

    def shutdown(self):
        self.window.canvas.mpl_disconnect(self.click_handler)
        self.playback.shutdown()

    def click(self,event):
        if self.window.busy or self.project is None or event.inaxes not in self.window.figure.axes:return
        if len(self.window.figure.axes)<2 or event.inaxes!=self.window.figure.axes[1]:return
        for i,n in enumerate(self.project.notes):
            if n.start_seconds<=event.xdata<=n.end_seconds and abs(n.midi_note-event.ydata)<.5:
                self.selector.set_selected(i);break

    def edit(self,command):
        if self.window.busy or self.project is None:return
        try:
            p=self.project
            if command in ('apply','add'):
                pitch=int(self.fields['midi_note'].get_text());start=float(self.fields['start_seconds'].get_text());end=float(self.fields['end_seconds'].get_text())
                if command=='add':self.selected=p.add(start,end,pitch)
                else:p.edit(self.selected,midi_note=pitch,start_seconds=start,end_seconds=end)
            elif command=='delete':p.delete(self.selected);self.selected=None
            elif command=='split':
                n=p.get(self.selected);p.split(self.selected,(n.start_seconds+n.end_seconds)/2)
            elif command=='merge':
                i=p.notes.index(p.get(self.selected))
                if i+1>=len(p.notes):raise ValueError('Select a note with a following adjacent note.')
                p.merge(self.selected,p.notes[i+1].note_id)
            elif command=='undo':p.undo()
            elif command=='redo':p.redo()
            if hasattr(self,'playback'):self.playback.project_changed(p,edit=True)
            self.update_notes();self.window.status.set_text(f'{command}: {len(p.notes)} notes. Save project to retain edits; MIDI export reflects current notes.')
        except (ValueError,TypeError) as exc:self.window.status.set_text(f'Edit rejected: {exc}')

    def generate_notes(self):
        w=self.window
        if w.busy or w.result is None or not self.guard():return
        result=w.result
        try:
            budget=w._read_memory_budget()
        except ValueError as exc:
            w.status.set_text(f'Invalid parameters: {exc}');return
        w._start_job(lambda:transcribe_in_process(result,w.cancelled,max_memory_mb=budget),self.set_project,'Generating notes in isolated process…')

    def save_to(self,path):
        from .serialization import document
        p=self.project
        if p is None:return
        snapshot=from_copy(p)
        def saved(_):
            self.saved_document=document(snapshot);self.window.status.set_text(f'Saved editable project: {path}')
        # Never silently replace a saved project: use a fresh name/version.
        self.window._start_job(lambda:save_project(snapshot,path),saved,'Saving editable project…')

    def load_from(self,path):
        if self.window.busy or not self.guard():return
        self.window._start_job(lambda:load_project(path),lambda p:self.set_project(p,saved=True),'Loading transcription project…')

    def midi_to(self,path):
        if self.project is None:return
        notes=self.project.notes;source=self.project.acoustic.metadata.path
        self.window._start_job(lambda:atomic_write(path,midi_bytes(notes),source=source),lambda _:self.window.status.set_text(f'Exported playable piano MIDI: {path}'),'Exporting MIDI…')

    def choose(self,action):
        w=self.window
        if w.busy or w.closed or w.dialog_cancellable is not None:return
        if action=='load' and not self.guard():return
        dialog=Gtk.FileDialog(title={'load':'Load editable transcription','save':'Save a new project version','midi':'Export piano MIDI'}[action],modal=True)
        if action!='load':dialog.set_initial_name('transcription.json' if action=='save' else 'melody.mid')
        w.dialog_cancellable=Gio.Cancellable()
        def done(dialog,response):
            try:
                file=dialog.open_finish(response) if action=='load' else dialog.save_finish(response)
                if w.closed:return
                path=file.get_path()
                if path is None:raise ValueError('Choose a local file.')
                {'load':self.load_from,'save':self.save_to,'midi':self.midi_to}[action](Path(path))
            except GLib.Error as exc:
                if not w.closed and not w._dialog_cancelled(exc):w.status.set_text(f'File chooser failed: {exc.message}')
            except ValueError as exc:w.status.set_text(str(exc))
            finally:
                w.dialog_cancellable=None
                if w.closed:GLib.idle_add(w.close)
        if action=='load':dialog.open(w,w.dialog_cancellable,done)
        else:dialog.save(w,w.dialog_cancellable,done)


def from_copy(project):
    from .serialization import document,from_document
    return from_document(document(project))
