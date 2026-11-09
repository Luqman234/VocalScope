# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Minimal GTK offline render panel. No synthesis bindings load on GTK's thread."""
from pathlib import Path
from threading import Event
from gi.repository import Gtk,Gio,GLib
from .models import RenderConfig
from .project import project_snapshot
from .process import inspect_in_process,render_snapshot_in_process


class CombinedCancellation:
    def __init__(self,*events):self.events=events
    def is_set(self):return any(e.is_set() for e in self.events)


class RenderWorkspace:
    def __init__(self,workspace,body):
        self.workspace=workspace;self.window=workspace.window;self.cancelled=Event();self.running=False
        self.expander=Gtk.Expander(label='Offline piano rendering · WAV / FLAC')
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5,margin_top=4,margin_bottom=4);self.expander.set_child(box);body.append(self.expander)
        fontrow=Gtk.Box(spacing=6);self.font_entry=Gtk.Entry(placeholder_text='SoundFont path (.sf2 or .sf3); blank uses application/system settings',hexpand=True)
        fontrow.append(self.font_entry);self.choose=Gtk.Button(label='SoundFont…');self.choose.connect('clicked',lambda *_:self.choose_font());fontrow.append(self.choose)
        self.verify=Gtk.Button(label='Verify preset');self.verify.connect('clicked',lambda *_:self.inspect());fontrow.append(self.verify);box.append(fontrow)
        self.instrument=Gtk.Label(label='Select a SoundFont, then verify its bank/preset. Synthesis is optional.',xalign=0,wrap=True,selectable=True);box.append(self.instrument)
        grid=Gtk.Grid(column_spacing=8,row_spacing=4);box.append(grid);self.entries={}
        for i,(key,label,default) in enumerate([('bank','Bank','0'),('preset','Preset','0'),('gain','Gain','0.2'),('tail_seconds','Tail s','1.5')]):
            group=Gtk.Box(spacing=3);group.append(Gtk.Label(label=label));entry=Gtk.Entry(text=default,width_chars=5);group.append(entry);self.entries[key]=entry;grid.attach(group,i,0,1,1)
        self.rate=Gtk.DropDown.new_from_strings(['44100 Hz','48000 Hz']);grid.attach(self.rate,4,0,1,1)
        self.reverb=Gtk.CheckButton(label='Reverb');self.chorus=Gtk.CheckButton(label='Chorus');self.normalize=Gtk.CheckButton(label='Normalize peak (0.98)')
        for i,c in enumerate([self.reverb,self.chorus,self.normalize]):grid.attach(c,i,1,1,1)
        self.wav=Gtk.CheckButton(label='WAV float32',active=True);self.flac=Gtk.CheckButton(label='FLAC PCM24',active=True);grid.attach(self.wav,3,1,1,1);grid.attach(self.flac,4,1,1,1)
        row=Gtk.Box(spacing=6);self.render=Gtk.Button(label='Render current notes…');self.render.connect('clicked',lambda *_:self.choose_output());row.append(self.render)
        self.cancel=Gtk.Button(label='Cancel render',sensitive=False);self.cancel.connect('clicked',lambda *_:self.cancel_render());row.append(self.cancel);box.append(row)
        self.font_entry.connect('changed',self.unverified)
        self.entries['bank'].connect('changed',self.unverified);self.entries['preset'].connect('changed',self.unverified)
        self.controls=(self.font_entry,self.choose,self.verify,grid,self.render)
        self.refresh()

    def unverified(self,*_):
        self.instrument.set_text('Preset unverified for current SoundFont/bank/preset. Verify or render to inspect the actual instrument.')

    def refresh(self):
        busy=self.window.busy
        for c in self.controls:c.set_sensitive(not busy)
        self.render.set_sensitive(not busy and self.workspace.project is not None)
        self.cancel.set_sensitive(busy and self.running)

    def configuration(self):
        return RenderConfig(sample_rate=[44100,48000][self.rate.get_selected()],bank=int(self.entries['bank'].get_text()),preset=int(self.entries['preset'].get_text()),
            gain=float(self.entries['gain'].get_text()),tail_seconds=float(self.entries['tail_seconds'].get_text()),reverb=self.reverb.get_active(),chorus=self.chorus.get_active(),normalize_peak=self.normalize.get_active())

    def inspect(self):
        if self.window.busy or self.window.closed:return
        try:config=self.configuration()
        except ValueError as exc:self.window.status.set_text(f'Invalid render settings: {exc}');return
        path=self.font_entry.get_text().strip() or None
        def complete(response):self.instrument.set_text(self.description(response['soundfont']))
        self.window._start_job(lambda:inspect_in_process(path,config,self.window.cancelled),complete,'Loading and verifying SoundFont in isolated process…')

    @staticmethod
    def description(info):return f"{info['preset_name']} · bank {info['bank']}, preset {info['preset']} · {Path(info['path']).name} · SHA256 {info['sha256'][:12]}…"

    def render_to(self,directory):
        w=self.window
        if w.busy or w.closed or self.workspace.project is None:return False
        try:
            config=self.configuration();formats=tuple(k for k,c in [('wav',self.wav),('flac',self.flac)] if c.get_active())
            if not formats:raise ValueError('Select WAV and/or FLAC.')
            snapshot=project_snapshot(self.workspace.project)
        except ValueError as exc:w.status.set_text(f'Invalid render settings: {exc}');return False
        font=self.font_entry.get_text().strip() or None;self.cancelled=Event();self.running=True
        cancellation=CombinedCancellation(self.cancelled,w.cancelled)
        def work():
            try:return render_snapshot_in_process(snapshot,font,directory,config,formats=formats,cancelled=cancellation)
            finally:self.running=False  # plain state only; widgets update via deliver/refresh
        def completed(result):
            self.instrument.set_text(self.description(result['report']['soundfont']))
            warning=' '.join(result['report']['warnings'])
            w.status.set_text(f"Rendered {len(snapshot['notes'])} current notes to {directory}. {warning}")
        accepted=w._start_job(work,completed,'Rendering current edited notes to piano audio…')
        if not accepted:self.running=False
        return accepted

    def cancel_render(self):
        if self.running:self.cancelled.set();self.window.status.set_text('Cancelling render and removing temporary output…')

    def choose_font(self):
        w=self.window
        if w.busy or w.closed or w.dialog_cancellable is not None:return
        dialog=Gtk.FileDialog(title='Select a licensed piano SoundFont',modal=True)
        filters=Gio.ListStore.new(Gtk.FileFilter);f=Gtk.FileFilter(name='SoundFonts (SF2 / SF3)')
        for pattern in ('*.sf2','*.sf3','*.SF2','*.SF3'):f.add_pattern(pattern)
        filters.append(f);dialog.set_filters(filters);w.dialog_cancellable=Gio.Cancellable()
        def done(dialog,response):
            selected=None
            try:
                selected=dialog.open_finish(response)
                if w.closed:return
                if selected.get_path() is None:raise ValueError('Choose a local SoundFont file.')
                self.font_entry.set_text(selected.get_path())
            except GLib.Error as exc:
                if not w.closed and not w._dialog_cancelled(exc):w.status.set_text(f'SoundFont chooser failed: {exc.message}')
            except ValueError as exc:w.status.set_text(str(exc))
            finally:
                w.dialog_cancellable=None
                if w.closed:GLib.idle_add(w.close)
                elif selected is not None:GLib.idle_add(self.inspect)
        dialog.open(w,w.dialog_cancellable,done)

    def choose_output(self):
        w=self.window
        if w.busy or w.closed or self.workspace.project is None or w.dialog_cancellable is not None:return
        dialog=Gtk.FileDialog(title='Piano audio export folder (existing files protected)',modal=True);w.dialog_cancellable=Gio.Cancellable()
        def done(dialog,response):
            try:
                chosen=dialog.select_folder_finish(response)
                if w.closed:return
                path=chosen.get_path()
                if path is None:raise ValueError('Choose a local output folder.')
                self.render_to(Path(path))
            except GLib.Error as exc:
                if not w.closed and not w._dialog_cancelled(exc):w.status.set_text(f'Export chooser failed: {exc.message}')
            except ValueError as exc:w.status.set_text(str(exc))
            finally:
                w.dialog_cancellable=None
                if w.closed:GLib.idle_add(w.close)
        dialog.select_folder(w,w.dialog_cancellable,done)
