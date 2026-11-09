# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""GTK transport presentation; cached media snapshots, no Gst queries on GTK."""
from pathlib import Path
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from queue import Queue,Empty
from time import monotonic
from gi.repository import Gtk,Gio,GLib
from .models import PlaybackConfig,Session,Source,State,Loop,Superseded
from .transport import Transport
from .render_coordinator import RenderCoordinator
from .timeline_view import TimelineView
from .waveform import overview
from ..synthesis.project import project_snapshot


class PlaybackWorkspace:
    def __init__(self,workspace,body):
        self.workspace=workspace;self.window=workspace.window;self.transport=None;self.coordinator=RenderCoordinator();self.callbacks=Queue();self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='vocalscope-waveform')
        self.config=PlaybackConfig();self.prepared=False;self.closed=False;self.updating=False;self.debounce=None;self.scrub=None;self.message='Load audio/project, then Play or load a piano render.';self.wave_generation=0;self.age_samples=[];self.last_preview_key=None;self.pending_seek_value=None
        self.expander=Gtk.Expander(label='Playback · vocal / piano comparison');box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5,margin_top=4);self.expander.set_child(box);body.append(self.expander)
        sources=Gtk.Box(spacing=5);self.vocal=Gtk.Entry(placeholder_text='Original vocal file',hexpand=True);self.piano=Gtk.Entry(placeholder_text='Existing piano WAV/FLAC (optional)',hexpand=True)
        sources.append(self.vocal);sources.append(self.piano)
        for label,name in [('Vocal…','vocal'),('Piano…','piano')]:
            button=Gtk.Button(label=label);button.connect('clicked',lambda _,n=name:self.choose(n));sources.append(button)
        box.append(sources)
        row=Gtk.Box(spacing=5);self.buttons={}
        for label,action in [('Load session','load'),('Play / Resume','play'),('Pause','pause'),('Stop','stop'),('Recover output','recover')]:
            button=Gtk.Button(label=label);button.connect('clicked',lambda _,a=action:self.command(a));row.append(button);self.buttons[action]=button
        self.mode=Gtk.DropDown.new_from_strings(['Vocal','Piano','Mix']);self.mode.connect('notify::selected',lambda *_:self.mix());row.append(self.mode);box.append(row)
        self.slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,1,.001);self.slider.set_draw_value(False);self.slider.connect('value-changed',self.seek_changed);box.append(self.slider)
        row=Gtk.Box(spacing=5);self.gains={}
        for name in ['vocal','piano']:
            row.append(Gtk.Label(label=name.title()+' gain'));control=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,1,.01);control.set_value(1.);control.set_size_request(100,-1);control.connect('value-changed',lambda *_:self.mix());row.append(control);self.gains[name]=control
        self.offset=Gtk.Entry(text='0',width_chars=6,tooltip_text='Piano alignment offset in seconds; zero by default. Reload session to apply.');row.append(Gtk.Label(label='Piano offset s'));row.append(self.offset);box.append(row)
        row=Gtk.Box(spacing=5);self.loop_start=Gtk.Entry(text='0',width_chars=6);self.loop_end=Gtk.Entry(text='1',width_chars=6);self.loop_enabled=Gtk.CheckButton(label='Loop');self.loop_enabled.connect('toggled',lambda *_:self.apply_loop())
        row.append(self.loop_enabled);row.append(self.loop_start);row.append(self.loop_end)
        for label,action in [('Apply loop',self.apply_loop),('Loop selected note',self.loop_selection)]:
            button=Gtk.Button(label=label);button.connect('clicked',lambda _,a=action:a());row.append(button)
        box.append(row)
        row=Gtk.Box(spacing=5);self.auto=Gtk.CheckButton(label='Audition edits automatically',active=True);row.append(self.auto)
        self.preview=Gtk.Button(label='Render/update piano');self.preview.connect('clicked',lambda *_:self.render_preview());row.append(self.preview)
        cancel=Gtk.Button(label='Cancel preview render');cancel.connect('clicked',lambda *_:self.coordinator.cancel());row.append(cancel);box.append(row)
        self.status=Gtk.Label(label=self.message,xalign=0,wrap=True,selectable=True);box.append(self.status)
        self.view=TimelineView(self.window);self.seek_handler=self.window.canvas.mpl_connect('button_press_event',self.canvas_seek)
        self.timer=GLib.timeout_add(33,self.poll)

    def watch(self,future,callback=None):
        def done(f):
            try:self.callbacks.put((callback,f.result(),None))
            except Exception as exc:self.callbacks.put((None,None,exc))
        future.add_done_callback(done)

    def audio_loaded(self,path):
        self.vocal.set_text(str(path));self.piano.set_text('');self.prepared=False;self.view.wave=None
        self.coordinator.cancel()
        if self.transport:self.watch(self.transport.stop())

    def project_changed(self,project,*,edit=False):
        if self.closed:return
        self.coordinator.revise(project_snapshot(project))
        if not edit:
            self.vocal.set_text(project.acoustic.metadata.path);self.piano.set_text('');self.prepared=False
            if self.transport:self.watch(self.transport.stop())
            self.message='Project loaded; Play original vocals or render/update piano.'
        elif self.auto.get_active() and self.prepared:
            if self.debounce:GLib.source_remove(self.debounce)
            self.debounce=GLib.timeout_add(150,self._auto_render)

    def _auto_render(self):
        self.debounce=None;self.render_preview();return GLib.SOURCE_REMOVE

    def make_session(self,piano_override=None,revision=0):
        vocal=self.vocal.get_text().strip();piano=piano_override or self.piano.get_text().strip()
        return Session(Source(vocal) if vocal else None,Source(piano,float(self.offset.get_text())) if piano else None,revision)

    def load(self,play=False,piano_override=None,revision=0,revision_accept=None):
        try:session=self.make_session(piano_override,revision)
        except (ValueError,TypeError) as exc:self.message=str(exc);return False
        if self.transport is None:self.transport=Transport(self.config)
        self.message='Loading shared playback pipeline…';self.wave_generation+=1;generation=self.wave_generation;self.view.duration=0;self.view.last_limits=None;self.view.wave=None
        def loaded(_):
            self.prepared=True;self.view.enabled=True;self.message='Playback ready.'
            duration=self.transport.snapshot().duration_seconds;self.slider.set_range(0,max(.001,duration));self.loop_end.set_text(f'{duration:.3f}')
            self.decorate()
            self.updating=True;self.mode.set_selected(['vocal','piano','mix'].index(self.transport.snapshot().mode));self.updating=False
            if play:self.watch(self.transport.play())
            wave_source=session.vocal or session.piano
            if wave_source:
                def work():
                    try:result=overview(wave_source.path);self.callbacks.put((lambda value:self.set_wave(value,generation,wave_source.offset_seconds),result,None))
                    except Exception as exc:self.callbacks.put((None,None,exc))
                self.pool.submit(work)
        future=self.transport.load(session,accept=revision_accept)
        self.watch(future,loaded)
        if revision_accept is not None:future.add_done_callback(lambda _:self.coordinator.unpin(revision))
        return True

    def set_wave(self,value,generation,offset=0.):
        if generation==self.wave_generation:self.view.wave=(value[0]+offset,value[1],value[2]);self.decorate()

    def decorate(self,*,full=False):
        if self.prepared and self.transport:self.view.decorate(self.transport.snapshot().duration_seconds,full=full)

    def command(self,action):
        if self.closed:return
        if action=='load':self.load();return
        if action=='play' and not self.prepared:self.load(play=True);return
        if not self.transport:self.message='Load a playback session first.';return
        self.watch(getattr(self.transport,action)())

    def mix(self):
        if self.transport and self.prepared and not self.updating:
            self.watch(self.transport.set_mix(['vocal','piano','mix'][self.mode.get_selected()],vocal_gain=self.gains['vocal'].get_value(),piano_gain=self.gains['piano'].get_value()))

    def seek_changed(self,*_):
        if self.updating or not self.prepared:return
        self.pending_seek_value=self.slider.get_value()
        if self.scrub:GLib.source_remove(self.scrub)
        self.scrub=GLib.timeout_add(80,self._seek_slider)

    def _seek_slider(self):
        self.scrub=None
        target=self.pending_seek_value if self.pending_seek_value is not None else self.slider.get_value();self.pending_seek_value=None
        if self.transport:self.watch(self.transport.seek(target))
        return GLib.SOURCE_REMOVE

    def canvas_seek(self,event):
        if not self.prepared or event.xdata is None or event.button!=1 or self.window.toolbar.mode:return
        axes=self.window.figure.axes
        if event.inaxes is (axes[2] if len(axes)>2 else None) or event.dblclick:
            self.updating=True;self.slider.set_value(event.xdata);self.updating=False;self._seek_slider()

    def apply_loop(self):
        if not self.transport:return
        try:loop=Loop(float(self.loop_start.get_text()),float(self.loop_end.get_text())) if self.loop_enabled.get_active() else None
        except ValueError as exc:self.message=str(exc);return
        self.watch(self.transport.set_loop(loop))

    def loop_selection(self):
        if not self.workspace.project or not self.workspace.selected:return
        note=self.workspace.project.get(self.workspace.selected);self.loop_start.set_text(str(note.start_seconds));self.loop_end.set_text(str(note.end_seconds));self.loop_enabled.set_active(True);self.apply_loop()

    def render_preview(self):
        project=self.workspace.project
        if project is None:self.message='Generate or load a transcription first.';return
        try:
            Source(project.acoustic.metadata.path,float(self.offset.get_text()))  # validate before starting a preview job
            status=self.coordinator.status()
            if status.current_revision==0:self.coordinator.revise(project_snapshot(project))
            settings=self.workspace.rendering.configuration();font=self.workspace.rendering.font_entry.get_text().strip() or None
            key=(font,settings)
            if self.last_preview_key is not None and key!=self.last_preview_key:self.coordinator.revise(project_snapshot(project))
            self.last_preview_key=key
            status=self.coordinator.status()
            if status.validated_revision==status.current_revision:
                self.coordinator.resume_current()
                audible=self.transport.snapshot().piano_revision if self.transport and self.prepared else 0
                if audible!=status.current_revision:self.ready({'revision':status.current_revision,'path':str(self.coordinator.files[status.current_revision]['path'])})
                else:self.message='Piano is already current; no rerender needed.'
                return
            self.coordinator.render_current(font,settings);self.message='Rendering current notes in the background; previous audio remains available.'
        except Exception as exc:self.message=f'Preview render failed: {exc}'

    def ready(self,event):
        revision=event['revision']
        token=self.coordinator.activation_token(revision)
        if token is None:return
        if not self.coordinator.pin(revision):return
        try:source=Source(event['path'],float(self.offset.get_text()))
        except (ValueError,TypeError) as exc:
            self.coordinator.unpin(revision);self.message=f'Preview activation failed: {exc}. Correct settings and retry Render/update piano.';return
        if self.transport is None or not self.prepared:
            # First render can prepare a piano-only session when original audio
            # is unavailable, without reading a source path merely for rendering.
            if self.vocal.get_text() and not Path(self.vocal.get_text()).is_file():self.vocal.set_text('')
            self.piano.set_text(event['path'])
            if not self.load(piano_override=event['path'],revision=revision,revision_accept=lambda:self.coordinator.commit(revision,token)):self.coordinator.unpin(revision)
            return
        start=monotonic()
        future=self.transport.replace_piano(source,revision,accept=lambda:self.coordinator.commit(revision,token))
        def done(f):
            try:
                value=f.result();self.callbacks.put((lambda _:self.replaced(revision,event['path'],start),value,None))
            except Exception as exc:self.callbacks.put((None,None,exc))
            finally:self.coordinator.unpin(revision)
        future.add_done_callback(done)

    def replaced(self,revision,path,start):
        self.piano.set_text(path);self.message=f'Piano revision {revision} active; controlled pause/replacement took {monotonic()-start:.3f} s.';self.decorate()

    def poll(self):
        if self.closed:return GLib.SOURCE_REMOVE
        for _ in range(30):
            try:callback,value,error=self.callbacks.get_nowait()
            except Empty:break
            if error:
                if not isinstance(error,Superseded):self.message=str(error)
            elif callback:callback(value)
        for _ in range(30):
            try:event=self.coordinator.events.get_nowait()
            except Empty:break
            if event['kind']=='ready':self.ready(event)
            elif event['kind']=='error':self.message=event['error']
        state=self.transport.snapshot() if self.transport else None;revision=self.coordinator.status()
        text=self.message
        if state:
            text=f'{state.state} · {state.position_seconds:.3f} / {state.duration_seconds:.3f} s · {state.sink} · '+text
            if state.position_valid:
                if self.scrub is None:
                    self.updating=True;self.slider.set_value(state.position_seconds);self.updating=False
                self.view.update(state);self.age_samples.append(self.view.last_age)
                if len(self.age_samples)>3000:del self.age_samples[:1000]
            if state.error:text+=' · '+state.error
            text+=f' · PCM peak {state.peak:.3f}'
            if state.peak>=1.:text+=' · Clipping risk: lower source gain'
        text+=f' · Project r{revision.current_revision}; render {revision.state}; validated r{revision.validated_revision}; audible r{state.piano_revision if state else 0}'
        if state and state.piano_revision!=revision.current_revision:text+=' (older/external piano)'
        self.status.set_text(text);return GLib.SOURCE_CONTINUE

    def choose(self,name):
        w=self.window
        if w.closed or w.dialog_cancellable is not None:return
        dialog=Gtk.FileDialog(title='Choose '+name+' audio',modal=True);w.dialog_cancellable=Gio.Cancellable()
        def selected(dialog,response):
            try:
                file=dialog.open_finish(response)
                if not w.closed:
                    path=file.get_path()
                    if path is None:raise ValueError('Choose local audio.')
                    getattr(self,name).set_text(path);self.prepared=False;self.message='New source selected; Load session to apply. Previous audio remains until then.'
            except GLib.Error as exc:
                if not w.closed and not w._dialog_cancelled(exc):self.message=exc.message
            except ValueError as exc:self.message=str(exc)
            finally:
                w.dialog_cancellable=None
                if w.closed:GLib.idle_add(w.close)
        dialog.open(w,w.dialog_cancellable,selected)

    def shutdown(self):
        if self.closed:return
        self.closed=True;GLib.source_remove(self.timer)
        self.window.canvas.mpl_disconnect(self.seek_handler);self.view.shutdown()
        for timer in (self.debounce,self.scrub):
            if timer:GLib.source_remove(timer)
        self.coordinator.cancel();future=self.transport.close() if self.transport else None
        def clean():
            if future:
                try:future.result(10)
                except Exception:pass
                if not self.transport.wait_closed(5) or self.transport.engine is not None:return  # retain leases if native teardown is unresolved
            self.coordinator.close();self.pool.shutdown(wait=True,cancel_futures=True)
        self.cleanup_thread=Thread(target=clean,name='vocalscope-playback-cleanup',daemon=False);self.cleanup_thread.start()
